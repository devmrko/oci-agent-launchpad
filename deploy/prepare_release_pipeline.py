"""Register an immutable release activation pipeline (does not start deployment)."""

import argparse
import base64
import json
import uuid
from pathlib import Path

import oci
from activate_release import validate
from oci.devops import models as m


def deployment_spec(alias):
    # validate() is always called before generating this command.
    return (
        "version: 1.0\ncomponent: deployment\ntimeoutInSeconds: 300\nsteps:\n"
        "  - stepType: Command\n    name: Activate and verify release\n"
        "    timeoutInSeconds: 240\n    command: |\n"
        "      set -eu\n      sudo -n /usr/local/sbin/launchpad-activate "
        + alias
        + "\n"
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--profile", default="DEFAULT")
    p.add_argument("--region", required=True)
    p.add_argument("--project-id", required=True)
    p.add_argument("--environment-id", required=True)
    p.add_argument("--release-config", required=True)
    p.add_argument("--release", required=True)
    p.add_argument("--state", required=True)
    a = p.parse_args()
    validate(json.loads(Path(a.release_config).read_text()), a.release)
    cfg = oci.config.from_file(profile_name=a.profile)
    cfg["region"] = a.region
    client = oci.devops.DevopsClient(cfg)
    project = client.get_project(a.project_id).data
    environment = client.get_deploy_environment(a.environment_id).data
    if (
        environment.project_id != project.id
        or environment.compartment_id != project.compartment_id
    ):
        raise ValueError(
            "Environment must belong to the selected project and compartment"
        )
    if environment.deploy_environment_type != "COMPUTE_INSTANCE_GROUP":
        raise ValueError("An instance-group environment is required")
    path = Path(a.state)
    identity = {
        "project": a.project_id,
        "environment": a.environment_id,
        "region": a.region,
        "release": a.release,
    }
    state = json.loads(path.read_text()) if path.exists() else {"binding": identity}
    if state["binding"] != identity:
        raise ValueError("Existing state belongs to a different target")

    def save(key, value):
        state[key] = value
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2))
        path.chmod(0o600)
        return value

    def token(kind):
        return str(
            uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(identity, sort_keys=True) + kind)
        )

    if "pipeline" not in state:
        save(
            "pipeline",
            client.create_deploy_pipeline(
                m.CreateDeployPipelineDetails(
                    project_id=project.id,
                    display_name="launchpad-" + a.release,
                    description="Activate preinstalled release; health failure restores previous version",
                ),
                opc_retry_token=token("pipeline"),
            ).data.id,
        )
    if "artifact" not in state:
        save(
            "artifact",
            client.create_deploy_artifact(
                m.CreateDeployArtifactDetails(
                    project_id=project.id,
                    display_name="activate-" + a.release,
                    deploy_artifact_type="DEPLOYMENT_SPEC",
                    argument_substitution_mode="NONE",
                    deploy_artifact_source=m.InlineDeployArtifactSource(
                        base64_encoded_content=base64.b64encode(
                            deployment_spec(a.release).encode()
                        ).decode()
                    ),
                ),
                opc_retry_token=token("artifact"),
            ).data.id,
        )
    if "stage" not in state:
        save(
            "stage",
            client.create_deploy_stage(
                m.CreateComputeInstanceGroupDeployStageDetails(
                    display_name="Activate " + a.release,
                    deploy_pipeline_id=state["pipeline"],
                    deploy_stage_predecessor_collection=m.DeployStagePredecessorCollection(
                        items=[m.DeployStagePredecessor(id=state["pipeline"])]
                    ),
                    compute_instance_group_deploy_environment_id=environment.id,
                    deployment_spec_deploy_artifact_id=state["artifact"],
                    deploy_artifact_ids=[],
                    rollout_policy=m.ComputeInstanceGroupLinearRolloutPolicyByCount(
                        batch_count=1, batch_delay_in_seconds=1
                    ),
                ),
                opc_retry_token=token("stage"),
            ).data.id,
        )
    print(
        json.dumps(
            {"pipeline": state["pipeline"], "stage": state["stage"], "started": False}
        )
    )


if __name__ == "__main__":
    main()
