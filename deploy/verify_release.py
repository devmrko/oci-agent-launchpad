"""Validate a trusted build result before producing immutable deployment inputs."""

import argparse
import email.parser
import hashlib
import io
import json
import re
import stat
import zipfile
from pathlib import Path


def canonical(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def digest(value):
    if not isinstance(value, str) or not re.fullmatch('[a-f0-9]{64}', value):
        raise ValueError('Invalid SHA-256')
    return value


def validate_result(directory):
    metadata_path = directory / 'release.json'
    bundle = directory / 'release.zip'
    if metadata_path.is_symlink() or bundle.is_symlink():
        raise ValueError('Release files must not be symlinks')
    if metadata_path.stat().st_size > 128 * 1024 or bundle.stat().st_size > 1024**3:
        raise ValueError('Release too large')
    metadata = json.loads(metadata_path.read_text())
    if metadata.get('schema_version') != 1:
        raise ValueError('Unsupported release schema')
    for key in ['foundation_commit', 'launchpad_commit']:
        if not re.fullmatch('[a-f0-9]{40}', metadata.get(key, '')):
            raise ValueError('Invalid source commit')
    for key in ['source_sha256', 'manifest_sha256', 'bundle_sha256']:
        digest(metadata.get(key))
    build_id = metadata.get('build_id')
    if not isinstance(build_id, str) or not 1 <= len(build_id) <= 2048 or any(ord(c) < 32 for c in build_id):
        raise ValueError('Invalid build ID')
    if metadata.get('target') != {'os': 'linux', 'architecture': 'x86_64', 'python': '3.12'}:
        raise ValueError('Unsupported release target')
    if metadata.get('verification') != {'dependency_check': 'passed', 'imports': 'passed', 'example_tests': 'passed'}:
        raise ValueError('Build verification has not passed')
    expected = {'launchpad-service-desk': metadata.get('app_version'),
                'devmrko-python-foundation': metadata.get('foundation_version')}
    for version in expected.values():
        if not isinstance(version, str) or not re.fullmatch('[A-Za-z0-9_.+-]+', version):
            raise ValueError('Invalid package version')
    with bundle.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != metadata['bundle_sha256']:
            raise ValueError('Bundle checksum mismatch')
    with zipfile.ZipFile(bundle) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if len(names) != len(set(names)) or not 3 <= len(names) <= 301:
            raise ValueError('Duplicate or invalid archive entries')
        if sum(e.file_size for e in entries) > 1024**3 or any(
            e.file_size > 200 * 1024**2 or e.is_dir() or stat.S_ISLNK(e.external_attr >> 16)
            for e in entries
        ):
            raise ValueError('Unsafe archive entry or size')
        if archive.getinfo('manifest.json').file_size > 128 * 1024:
            raise ValueError('Manifest too large')
        raw = archive.read('manifest.json')
        if hashlib.sha256(raw).hexdigest() != metadata['manifest_sha256']:
            raise ValueError('Manifest checksum mismatch')
        files = json.loads(raw).get('files')
        if not isinstance(files, dict) or set(names) != set(files) | {'manifest.json'} or 'requirements.txt' not in files:
            raise ValueError('Archive does not match manifest')
        if metadata.get('files') != len(files):
            raise ValueError('Manifest file count mismatch')
        found = {}
        for name, sha in files.items():
            if name != 'requirements.txt' and not re.fullmatch(r'[A-Za-z0-9_.+-]+\.whl', name):
                raise ValueError('Unsafe package name')
            content = archive.read(name)
            if hashlib.sha256(content).hexdigest() != digest(sha):
                raise ValueError('Package checksum mismatch')
            if name.endswith('.whl') and any(name.startswith(p.replace('-', '_') + '-') for p in expected):
                with zipfile.ZipFile(io.BytesIO(content)) as wheel:
                    info = [i for i in wheel.infolist() if i.filename.endswith('.dist-info/METADATA')]
                    if len(info) != 1 or info[0].file_size > 256 * 1024:
                        raise ValueError('Invalid wheel metadata')
                    headers = email.parser.BytesParser().parsebytes(wheel.read(info[0]))
                    package = canonical(headers.get('Name', ''))
                    if package not in expected or package in found or headers.get('Version') != expected[package]:
                        raise ValueError('Wheel version mismatch')
                    found[package] = headers['Version']
        pins = {}
        for line in archive.read('requirements.txt').decode().splitlines():
            if not re.fullmatch('[A-Za-z0-9_.-]+==[A-Za-z0-9_.+!-]+', line):
                raise ValueError('Requirements must be exact pins')
            name, version = line.split('==')
            name = canonical(name)
            if name in pins:
                raise ValueError('Duplicate requirement')
            pins[name] = version
        if found != expected or any(pins.get(k) != v for k, v in expected.items()):
            raise ValueError('Required app/Foundation package mismatch')
    return metadata


def deployment_inputs(directory, base, alias=None):
    metadata = validate_result(directory)
    alias = alias or 'memory-' + metadata['app_version'] + '-' + metadata['bundle_sha256'][:12]
    if not re.fullmatch('[A-Za-z0-9_-][A-Za-z0-9_.-]*', alias):
        raise ValueError('Invalid release alias')
    return {**base, 'bundle_path': str((directory / 'release.zip').resolve()),
            'release_metadata_path': str((directory / 'release.json').resolve()),
            'bundle_sha256': metadata['bundle_sha256'], 'manifest_sha256': metadata['manifest_sha256'],
            'app_version': metadata['app_version'], 'release_alias': alias}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result', type=Path, required=True)
    parser.add_argument('--base-vars', type=Path)
    parser.add_argument('--alias')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.output:
        if args.base_vars is None:
            parser.error('--base-vars is required for Terraform output')
        value = deployment_inputs(args.result, json.loads(args.base_vars.read_text()), args.alias)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x') as stream:
            json.dump(value, stream, indent=2)
        print('Verified deployment inputs written: ' + str(args.output))
    else:
        print(json.dumps(validate_result(args.result), indent=2))


if __name__ == '__main__':
    main()
