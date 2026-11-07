"""Plan or provision a verified release pipeline and bind its shared IAM policy."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from prepare_release import read_object, settings
from verify_release import validate_result, deployment_inputs
from prepare_pipeline_iam import prepare, check_plan, read, identity

ADDRESSES = {
    'oci_devops_deploy_environment.target', 'oci_artifacts_repository.releases',
    'oci_generic_artifacts_content_artifact_by_path.bundle', 'oci_devops_deploy_pipeline.release',
    'oci_devops_deploy_artifact.bundle', 'oci_devops_deploy_artifact.spec',
    'oci_devops_deploy_stage.release', 'oci_generic_artifacts_content_artifact_by_path.metadata[0]',
}


def prepared_inputs(directory, expected):
    receipt, actual = read_object(directory / 'preparation.json')
    if actual != expected or receipt.get('status') != 'READY' or receipt.get('schema_version') != 1:
        raise ValueError('Preparation receipt mismatch or not READY')
    config, config_hash = read_object(directory / 'deployment.json')
    variables, vars_hash = read_object(directory / 'release.tfvars.json')
    if receipt['files'] != {'deployment.json': config_hash, 'release.tfvars.json': vars_hash}:
        raise ValueError('Prepared files changed')
    settings(variables, config)
    if variables.get('create_deployment_policy') is not False:
        raise ValueError('Shared policy mode requires create_deployment_policy=false')
    metadata = validate_result(directory / 'result')
    if variables != deployment_inputs(directory / 'result', variables, receipt['release_alias']):
        raise ValueError('Package inputs differ from verified result')
    for key in ('build_id', 'launchpad_commit', 'foundation_commit', 'bundle_sha256', 'manifest_sha256'):
        if receipt[key] != metadata[key]:
            raise ValueError('Package provenance mismatch')
    if receipt['target'] != {k: variables[k] for k in ('region', 'compartment_id', 'project_id', 'instance_id')}:
        raise ValueError('Prepared target mismatch')
    return receipt, variables


def release_plan(plan, reused):
    if plan.get('errored') or plan.get('deferred_changes'):
        raise ValueError('Incomplete release plan')
    if any(c['status'] not in ('pass', 'unknown') for c in plan.get('checks', [])):
        raise ValueError('Release condition failed')
    if any(r['change']['actions'] != ['no-op'] for r in plan.get('resource_drift', [])):
        raise ValueError('Release drift needs separate review')
    managed = [r for r in plan.get('resource_changes', []) if r.get('mode') == 'managed']
    if {r['address'] for r in managed} != ADDRESSES or len(managed) != len(ADDRESSES):
        raise ValueError('Unexpected release resource set')
    actions = [r['change']['actions'] for r in managed]
    if any(a not in (['create'], ['no-op']) for a in actions):
        raise ValueError('Release modification, deletion or replacement forbidden')
    if reused and any(a == ['create'] for a in actions):
        raise ValueError('Reused alias cannot create duplicate infrastructure')


class Terraform:
    def __init__(self, executable, module, workspace, output):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,89}', workspace):
            raise ValueError('Invalid workspace name')
        self.command = [str(executable.resolve()), '-chdir=' + str(module.resolve())]
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(('TF_CLI_ARGS', 'TF_VAR_'))}
        self.env.update(TF_WORKSPACE=workspace, TF_INPUT='0', TF_IN_AUTOMATION='1')
        self.output = output

    def call(self, *args):
        result = subprocess.run([*self.command, *args], env=self.env, capture_output=True)
        # Terraform diagnostics stay in the private run directory, never dump credentials to stdout.
        with (self.output / 'terraform.log').open('ab') as stream:
            stream.write(('workspace=' + self.env['TF_WORKSPACE'] + ' command=' + args[0] + '\n').encode())
            stream.write((b'JSON result captured privately\n' if args[:2] == ('show', '-json') else result.stdout) + result.stderr)
        if result.returncode:
            raise RuntimeError('Terraform failed; inspect private terraform.log')
        return result.stdout

    def plan(self, variables, name):
        saved = self.output / (name + '.tfplan')
        self.call('plan', '-input=false', '-no-color', '-lock-timeout=30s',
                  '-var-file=' + str(variables.resolve()), '-out=' + str(saved.resolve()))
        raw = self.call('show', '-json', str(saved.resolve()))
        (self.output / (name + '.plan.json')).write_bytes(raw)
        return json.loads(raw), saved

    def state(self):
        return json.loads(self.call('show', '-json'))

    def apply(self, saved):
        self.call('apply', '-input=false', '-no-color', '-lock-timeout=30s', str(saved.resolve()))


def run(args, factory=Terraform):
    receipt, variables = prepared_inputs(args.prepared, args.receipt_sha256)
    if args.release_workspace == args.owner_workspace:
        raise ValueError('Release and policy owner workspaces must differ')
    owner_vars = read(args.owner_vars)
    if tuple(owner_vars[k] for k in ('project_id', 'compartment_id', 'instance_id', 'region', 'home_region')) != tuple(
            variables[k] for k in ('project_id', 'compartment_id', 'instance_id', 'region', 'home_region')):
        raise ValueError('Policy owner target mismatch')
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    release = factory(args.terraform, args.module, args.release_workspace, args.output)
    owner = factory(args.terraform, args.module, args.owner_workspace, args.output)
    progress = {'stage': 'STARTED', 'release_workspace': args.release_workspace,
                'owner_workspace': args.owner_workspace, 'execute': args.execute}
    def mark(stage):
        progress['stage'] = stage
        temporary = args.output / 'progress.tmp'
        temporary.write_text(json.dumps(progress, indent=2) + '\n')
        temporary.replace(args.output / 'progress.json')
    try:
        mark('VALIDATING_OWNER')
        _, target = identity(owner.state())
        if target != tuple(variables[k] for k in ('project_id', 'compartment_id', 'instance_id')):
            raise ValueError('Policy owner state target mismatch')
        if not args.iam_only:
            mark('PLANNING_RELEASE')
            plan, saved = release.plan(args.prepared / 'release.tfvars.json', 'release')
            release_plan(plan, receipt['existing_alias_reused'])
            mark('RELEASE_PLAN_VERIFIED')
            if not args.execute:
                return progress
            # Recheck mutable local package inputs immediately before applying the saved plan.
            prepared_inputs(args.prepared, args.receipt_sha256)
            mark('APPLYING_RELEASE')
            release.apply(saved)
            mark('RELEASE_APPLIED')
        mark('PLANNING_IAM')
        release_state = release.state()
        _, target = identity(release_state)
        if target != tuple(variables[k] for k in ('project_id', 'compartment_id', 'instance_id')):
            raise ValueError('Release state target mismatch')
        boot = release_state['values']['outputs']['bootstrap_release']['value']
        if boot != {'directory': receipt['release_alias'], 'version': variables['app_version'],
                    'manifest_sha256': variables['manifest_sha256']}:
            raise ValueError('Release state package mismatch')
        binding_dir = args.output / 'iam'
        prepare(owner_vars, owner.state(), release_state, binding_dir)
        plan, saved = owner.plan(binding_dir / 'owner.tfvars.json', 'iam')
        check_plan(plan, read(binding_dir / 'binding.json'))
        mark('IAM_PLAN_VERIFIED')
        if args.execute:
            mark('APPLYING_IAM')
            owner.apply(saved)
            mark('INFRASTRUCTURE_APPLIED')
        return progress
    except Exception:
        progress['failed_stage'] = progress['stage']
        mark('FAILED')
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('prepared', 'owner-vars', 'output', 'terraform', 'module'):
        parser.add_argument('--' + flag, type=Path, required=True)
    for flag in ('receipt-sha256', 'release-workspace', 'owner-workspace'):
        parser.add_argument('--' + flag, required=True)
    parser.add_argument('--execute', action='store_true', help='Apply verified release and IAM plans')
    parser.add_argument('--iam-only', action='store_true', help='Resume IAM for an already-created release')
    print(json.dumps(run(parser.parse_args())))


if __name__ == '__main__':
    main()
