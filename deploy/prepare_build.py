"""Prepare a dedicated OCI build pipeline for an existing pinned-source repository."""

import argparse
import json
from pathlib import Path

import oci


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    settings = json.loads(a.config.read_text())
    cfg = oci.config.from_file(profile_name=settings.get('profile', 'DEFAULT'))
    cfg['region'] = settings['region']
    c = oci.devops.DevopsClient(cfg)
    m = oci.devops.models
    project = c.get_project(settings['project_id']).data
    if project.compartment_id != settings['compartment_id']:
        raise ValueError('Project compartment mismatch')
    repo = c.get_repository(settings['repository_id']).data
    if repo.project_id != project.id:
        raise ValueError('Source repository project mismatch')
    pipelines = oci.pagination.list_call_get_all_results(c.list_build_pipelines, project_id=project.id).data
    pipeline = next((item for item in pipelines if item.display_name == settings['name']), None)
    if pipeline is None:
        pipeline = c.create_build_pipeline(m.CreateBuildPipelineDetails(
            project_id=project.id, display_name=settings['name'],
            description='Build pinned source snapshots independently of Companion')).data
    stages = oci.pagination.list_call_get_all_results(c.list_build_pipeline_stages, build_pipeline_id=pipeline.id).data
    if not stages:
        stage = c.create_build_pipeline_stage(m.CreateBuildStageDetails(
            display_name='build-and-test', build_pipeline_id=pipeline.id, build_pipeline_stage_type='BUILD',
            build_pipeline_stage_predecessor_collection=m.BuildPipelineStagePredecessorCollection(
                items=[m.BuildPipelineStagePredecessor(id=pipeline.id)]),
            image='OL8_X86_64_STANDARD_10', build_spec_file='build_spec.yml',
            stage_execution_timeout_in_seconds=3600, primary_build_source='source',
            build_source_collection=m.BuildSourceCollection(items=[m.DevopsCodeRepositoryBuildSource(
                name='source', repository_id=repo.id, repository_url=repo.http_url,
                branch=settings.get('branch', 'main'))]))).data
    elif len(stages) == 1 and stages[0].build_pipeline_stage_type == 'BUILD':
        stage = stages[0]
        # Never silently adopt a different build contract merely because names match.
        if stage.build_spec_file != 'build_spec.yml' or stage.build_source_collection.items[0].repository_id != repo.id:
            raise ValueError('Existing pipeline has a different source or specification')
    else:
        raise ValueError('Existing pipeline layout requires explicit reconciliation')
    i = oci.identity.IdentityClient({**cfg, 'region': settings['home_region']})
    comp = project.compartment_id
    statement = (f"Allow any-user to read devops-repositories in compartment id {comp} "
                 f"where ALL {{request.principal.type = 'devopsbuildpipeline', request.principal.id = '{pipeline.id}'}}")
    policies = oci.pagination.list_call_get_all_results(i.list_policies, comp).data
    policy = next((item for item in policies if item.name == settings['name'] + '-read'), None)
    if policy is None:
        policy = i.create_policy(oci.identity.models.CreatePolicyDetails(
            compartment_id=comp, name=settings['name'] + '-read',
            description='Source read access for this build pipeline only', statements=[statement])).data
    elif policy.statements != [statement]:
        raise ValueError('Existing policy differs; refusing automatic changes')
    result = {'pipeline_id': pipeline.id, 'stage_id': stage.id, 'repository_id': repo.id, 'policy_id': policy.id}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
