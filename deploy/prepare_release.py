"""Prepare verified, consistent Terraform and VM release inputs without cloud mutations."""
import argparse
import copy
import hashlib
import json
import re
import shutil
from pathlib import Path

from activate_release import validate
from verify_release import deployment_inputs, validate_result

BASE_KEYS = {'region', 'home_region', 'compartment_id', 'project_id', 'instance_id',
             'profile', 'name', 'staging_root', 'create_deployment_policy', 'additional_pipeline_ids',
             'bundle_path', 'bundle_sha256', 'manifest_sha256', 'release_alias', 'app_version', 'release_metadata_path',
             'post_deploy_check_command', 'post_deploy_check_timeout_seconds'}
CONFIG_KEYS = {'service', 'release_root', 'port', 'health_timeout_seconds', 'staging_root', 'releases'}


def read_object(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 128 * 1024:
        raise ValueError('Expected a small regular JSON file')
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError('Expected a JSON object')
    return value, hashlib.sha256(raw).hexdigest()


def settings(base, config):
    if base.keys() - BASE_KEYS or config.keys() - CONFIG_KEYS:
        raise ValueError('Unknown configuration keys; do not supply secrets')
    for key in ('region', 'home_region'):
        if not isinstance(base.get(key), str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)+', base[key]):
            raise ValueError('Invalid region')
    for key, kind in [('compartment_id', 'compartment'), ('project_id', 'devopsproject'), ('instance_id', 'instance')]:
        if not isinstance(base.get(key), str) or not re.fullmatch(r'ocid1\.' + kind + r'\.[A-Za-z0-9._-]+', base[key]):
            raise ValueError('Invalid target identifier: ' + key)
    for key in ('name', 'profile'):
        if key in base and (not isinstance(base[key], str) or not re.fullmatch(r'[A-Za-z0-9_-]+', base[key])):
            raise ValueError('Invalid ' + key)
    if 'create_deployment_policy' in base and type(base['create_deployment_policy']) is not bool:
        raise ValueError('Invalid policy mode')
    # A new release must not silently become an owner of old release policies.
    if base.get('additional_pipeline_ids'):
        raise ValueError('Use a release target input, not a shared policy owner input')
    command = base.get('post_deploy_check_command')
    if command is not None and (not isinstance(command, str) or not re.fullmatch(r'/usr/local/sbin/[A-Za-z0-9_-]+', command)):
        raise ValueError('Invalid post-deployment verifier path')
    timeout = base.get('post_deploy_check_timeout_seconds', 300)
    if type(timeout) is not int or not 30 <= timeout <= 600:
        raise ValueError('Invalid post-deployment verifier timeout')
    staging = config.get('staging_root')
    if not isinstance(staging, str) or not re.fullmatch(r'/[A-Za-z0-9_/-]+', staging) or '..' in Path(staging).parts:
        raise ValueError('Invalid staging root')
    if base.get('staging_root', '/var/ocarun_staging/launchpad') != staging:
        raise ValueError('Terraform and VM staging roots differ')
    releases = config.get('releases')
    if not isinstance(releases, dict) or not releases or len(releases) > 100:
        raise ValueError('Expected existing release configuration')
    directories = []
    for alias, release in releases.items():
        if not isinstance(release, dict) or release.keys() - {'directory', 'version', 'manifest_sha256'}:
            raise ValueError('Unknown release fields')
        validate(config, alias)
        if 'manifest_sha256' in release and not re.fullmatch(r'[a-f0-9]{64}', release['manifest_sha256']):
            raise ValueError('Invalid existing manifest')
        directories.append(release['directory'])
    if len(set(directories)) != len(directories):
        raise ValueError('Existing releases share a directory')


def prepare(result, base_path, config_path, output, expected_build, expected_app, expected_foundation, alias=None):
    if output.exists() or output.is_symlink():
        raise ValueError('Output already exists')
    base, base_hash = read_object(base_path)
    config, config_hash = read_object(config_path)
    settings(base, config)
    metadata = validate_result(result)
    for key, expected in [('build_id', expected_build), ('launchpad_commit', expected_app), ('foundation_commit', expected_foundation)]:
        if metadata[key] != expected:
            raise ValueError('Build provenance mismatch: ' + key)
    inputs = deployment_inputs(result, base, alias)
    alias = inputs['release_alias']
    entry = {'directory': alias, 'version': metadata['app_version'], 'manifest_sha256': metadata['manifest_sha256']}
    merged = copy.deepcopy(config)
    previous = merged['releases'].get(alias)
    if previous is not None and previous != entry:
        raise ValueError('Existing release alias has different contents')
    if any(k != alias and v['directory'] == alias for k, v in merged['releases'].items()):
        raise ValueError('Release directory belongs to another alias')
    merged['releases'][alias] = entry
    validate(merged, alias)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(mode=0o700)  # Exclusive; partial failures are never marked READY.
    packaged = output / 'result'
    packaged.mkdir(mode=0o700)
    for filename in ('release.json', 'release.zip'):
        shutil.copyfile(result / filename, packaged / filename)
    copied = validate_result(packaged)
    if copied != metadata:
        raise ValueError('Source changed while preparing release')
    inputs['bundle_path'] = str((packaged / 'release.zip').resolve())
    inputs['release_metadata_path'] = str((packaged / 'release.json').resolve())
    inputs['staging_root'] = merged['staging_root']
    def write(name, value):
        with (output / name).open('x') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
    write('release.tfvars.json', inputs)
    write('deployment.json', merged)
    receipt = {'schema_version': 1, 'status': 'READY', 'release_alias': alias,
               'build_id': metadata['build_id'], 'launchpad_commit': metadata['launchpad_commit'],
               'foundation_commit': metadata['foundation_commit'], 'bundle_sha256': metadata['bundle_sha256'],
               'manifest_sha256': metadata['manifest_sha256'], 'base_vars_sha256': base_hash,
               'previous_vm_config_sha256': config_hash, 'existing_alias_reused': previous is not None,
               'target': {k: base[k] for k in ('region', 'compartment_id', 'project_id', 'instance_id')},
               'files': {name: hashlib.sha256((output / name).read_bytes()).hexdigest()
                         for name in ('release.tfvars.json', 'deployment.json')},
               'pending': ['register-vm-manifest', 'terraform-plan-apply', 'pipeline-iam', 'deployment-and-health']}
    # Last file: consumers must require this marker and verify files again before use.
    write('preparation.json', receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('result', 'base-vars', 'deployment-config', 'output'):
        parser.add_argument('--' + flag, type=Path, required=True)
    for flag in ('expected-build-id', 'expected-launchpad-commit', 'expected-foundation-commit'):
        parser.add_argument('--' + flag, required=True)
    parser.add_argument('--alias')
    args = parser.parse_args()
    receipt = prepare(args.result, args.base_vars, args.deployment_config, args.output,
                      args.expected_build_id, args.expected_launchpad_commit, args.expected_foundation_commit, args.alias)
    print(json.dumps({'status': receipt['status'], 'release_alias': receipt['release_alias'],
                      'output': str(args.output), 'cloud_modified': False, 'vm_modified': False}))


if __name__ == '__main__':
    main()
