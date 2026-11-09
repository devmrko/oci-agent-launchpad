"""Prepare additive IAM inputs from matching release states and verify a saved plan."""
import argparse
import copy
import json
from pathlib import Path
import re

PIPELINE = 'oci_devops_deploy_pipeline.release'
POLICY = 'oci_identity_policy.release[0]'
PERMISSIONS = ('read devops-family', 'read instance-family', 'use instance-agent-command-family',
               'use ons-topics', 'read generic-artifacts', 'read artifact-repositories')


def read(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('Expected a regular JSON input under 16 MiB')
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError('Expected a JSON object')
    return value


def resources(state):
    if state.get('format_version') != '1.0':
        raise ValueError('Unsupported Terraform JSON state format')
    root = state['values']['root_module']
    if root.get('child_modules'):
        raise ValueError('Expected the standalone release module')
    for check in state.get('checks', []):
        if check['status'] != 'pass':
            raise ValueError('Terraform checks have not passed')
    return {r['address']: r['values'] for r in root['resources']}


def identity(state):
    items = resources(state)
    pipeline = items[PIPELINE]
    identifier = pipeline['id']
    if not re.fullmatch(r'ocid1\.devopsdeploypipeline\.[A-Za-z0-9._-]+', identifier):
        raise ValueError('Invalid pipeline OCID')
    project = items['data.oci_devops_project.target']
    vm = items['data.oci_core_instance.target']
    environment = items['oci_devops_deploy_environment.target']
    if pipeline['project_id'] != project['id'] or project['compartment_id'] != vm['compartment_id']:
        raise ValueError('Project/VM mismatch')
    selectors = environment['compute_instance_group_selectors']
    if (environment['project_id'] != project['id'] or len(selectors) != 1
            or len(selectors[0]['items']) != 1):
        raise ValueError('Unexpected deployment environment')
    selector = selectors[0]['items'][0]
    if selector['selector_type'] != 'INSTANCE_IDS' or selector['compute_instance_ids'] != [vm['id']]:
        raise ValueError('Environment must select exactly the target VM')
    if state['values']['outputs']['pipeline_id']['value'] != identifier:
        raise ValueError('Pipeline output mismatch')
    return identifier, (project['id'], vm['compartment_id'], vm['id'])


def legacy_statements(pipelines, compartment, instance):
    return [f"Allow any-user to {permission} in compartment id {compartment} where request.principal.id = '{pipeline}'"
            for pipeline in pipelines for permission in PERMISSIONS] + [
        f"Allow any-user to {permission} in compartment id {compartment} where request.principal.id = '{instance}'"
        for permission in ('use instance-agent-command-execution-family', 'read generic-artifacts')]


def statements(pipelines, compartment, instance):
    result = []
    for permission in (*PERMISSIONS, 'use instance-agent-command-execution-family'):
        principals = ([instance] if permission == 'use instance-agent-command-execution-family' else
                      list(dict.fromkeys([*pipelines, *([instance] if permission == 'read generic-artifacts' else [])])))
        conditions = [f"request.principal.id = '{principal}'" for principal in principals]
        condition = conditions[0] if len(conditions) == 1 else 'any {' + ', '.join(conditions) + '}'
        result.append(f"Allow any-user to {permission} in compartment id {compartment} where {condition}")
    return result


def prepare(owner_vars, owner_state, release_state, output):
    if output.exists() or output.is_symlink():
        raise ValueError('Output already exists')
    owner, target = identity(owner_state)
    pipeline, release_target = identity(release_state)
    if target != release_target:
        raise ValueError('Policy owner and release must have the same project, compartment and VM')
    if tuple(owner_vars[k] for k in ('project_id', 'compartment_id', 'instance_id')) != target:
        raise ValueError('Owner input target mismatch')
    if owner_vars.get('create_deployment_policy', True) is not True:
        raise ValueError('Input does not own a policy')
    if any(k.startswith('oci_identity_policy.') for k in resources(release_state)):
        raise ValueError('Release already owns a policy; use the shared-policy path')
    policy = resources(owner_state)[POLICY]
    previous = owner_vars.get('additional_pipeline_ids', [])
    if (not isinstance(previous, list) or len(set(previous)) != len(previous) or owner in previous
            or any(not isinstance(v, str) or not re.fullmatch(r'ocid1\.devopsdeploypipeline\.[A-Za-z0-9._-]+', v) for v in previous)):
        raise ValueError('Invalid existing pipeline list')
    expected = statements([owner, *previous], target[1], target[2])
    legacy = legacy_statements([owner, *previous], target[1], target[2])
    if policy['compartment_id'] != target[1] or sorted(policy['statements']) not in (sorted(expected), sorted(legacy)):
        raise ValueError('Owner inputs do not match existing policy; refresh inputs/state')
    inputs = copy.deepcopy(owner_vars)
    additions = list(previous)
    if pipeline != owner and pipeline not in additions:
        additions.append(pipeline)
    inputs['additional_pipeline_ids'] = additions
    after = copy.deepcopy(policy)
    after['statements'] = statements([owner, *additions], target[1], target[2])
    output.mkdir(mode=0o700, parents=True)
    for name, value in [('owner.tfvars.json', inputs), ('binding.json', {
        'schema_version': 1, 'pipeline_id': pipeline, 'policy_address': POLICY,
        'before': policy, 'after': after, 'already_bound': additions == previous})]:
        with (output / name).open('x') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
    return {'status': 'PREPARED', 'already_bound': additions == previous, 'cloud_modified': False}


def normalized(value):
    value = copy.deepcopy(value)
    # OCI provider exposes deprecated, computed-only concurrency metadata.
    for key in ('ETag', 'lastUpdateETag'):
        value.pop(key, None)
    value['statements'] = sorted(value['statements'])
    return value


def unknown(value):
    if isinstance(value, dict):
        return any(unknown(v) for v in value.values())
    if isinstance(value, list):
        return any(unknown(v) for v in value)
    return value is True


def check_plan(plan, binding):
    if binding.get('schema_version') != 1 or binding.get('policy_address') != POLICY:
        raise ValueError('Unsupported binding')
    if plan.get('errored') or plan.get('deferred_changes'):
        raise ValueError('Incomplete Terraform plan')
    for check in plan.get('checks', []):
        if check['status'] != 'pass':
            raise ValueError('Terraform checks have not passed')
    for resource in plan.get('resource_drift', []):
        change = resource['change']
        if change['actions'] == ['no-op']:
            continue
        if (resource.get('address') != POLICY or change['actions'] != ['update']
                or normalized(change['before']) != normalized(change['after'])):
            raise ValueError('Refresh drift requires separate review')
    found = False
    for resource in plan.get('resource_changes', []):
        if resource.get('mode') != 'managed':
            continue
        change = resource['change']
        if resource['address'] != POLICY:
            if change['actions'] != ['no-op']:
                raise ValueError('Unexpected non-policy resource change')
            continue
        found = True
        if change['actions'] not in (['no-op'], ['update']) or unknown({k: v for k, v in change.get('after_unknown', {}).items() if k not in ('ETag', 'lastUpdateETag')}):
            raise ValueError('Policy replacement or unknown value forbidden')
        if normalized(change['before']) != normalized(binding['before']) or normalized(change['after']) != normalized(binding['after']):
            raise ValueError('Policy differs from reviewed additive binding')
    if not found:
        raise ValueError('Expected policy missing from plan')
    return {'status': 'PLAN_VERIFIED', 'pipeline_id': binding['pipeline_id'], 'cloud_modified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('prepare')
    for flag in ('owner-vars', 'owner-state', 'release-state', 'output'):
        p.add_argument('--' + flag, type=Path, required=True)
    p = commands.add_parser('check-plan')
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--binding', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare(read(args.owner_vars), read(args.owner_state), read(args.release_state), args.output)
    else:
        result = check_plan(read(args.plan), read(args.binding))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
