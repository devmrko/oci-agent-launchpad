"""Register this demo VM as a dedicated OCI DevOps environment."""

import json
import uuid
from pathlib import Path

import oci
from oci.devops import models as m

folder = Path(".run/oci-launchpad")
spec = json.loads((folder / "config.json").read_text())
state_path = folder / "state.json"
state = json.loads(state_path.read_text())
cfg = oci.config.from_file()
cfg["region"] = spec["region"]
ons = oci.ons.NotificationControlPlaneClient(cfg)
devops = oci.devops.DevopsClient(cfg)
name = spec["name"]
comp = spec["compartment_id"]


def save(key, value):
    state[key] = value
    state_path.write_text(json.dumps(state, indent=2))
    print(key + ": recorded", flush=True)
    return value


def token(kind):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, comp + name + kind))


if "topic" not in state:
    topics = oci.pagination.list_call_get_all_results(
        ons.list_topics, compartment_id=comp
    ).data
    found = [t for t in topics if t.name == name]
    save(
        "topic",
        found[0].topic_id
        if found
        else ons.create_topic(
            oci.ons.models.CreateTopicDetails(
                compartment_id=comp,
                name=name,
                description="Launchpad demo DevOps topic; no subscriptions",
            ),
            opc_retry_token=token("topic"),
        ).data.topic_id,
    )
if "project" not in state:
    projects = oci.pagination.list_call_get_all_results(
        devops.list_projects, compartment_id=comp
    ).data
    found = [x for x in projects if x.name == name]
    save(
        "project",
        found[0].id
        if found
        else devops.create_project(
            m.CreateProjectDetails(
                compartment_id=comp,
                name=name,
                description="Synthetic service desk example",
                notification_config=m.NotificationConfig(topic_id=state["topic"]),
            ),
            opc_retry_token=token("project"),
        ).data.id,
    )
if "environment" not in state:
    environments = oci.pagination.list_call_get_all_results(
        devops.list_deploy_environments, project_id=state["project"]
    ).data
    found = [x for x in environments if x.display_name == name]
    save(
        "environment",
        found[0].id
        if found
        else devops.create_deploy_environment(
            m.CreateComputeInstanceGroupDeployEnvironmentDetails(
                project_id=state["project"],
                display_name=name,
                description="Oracle Linux demo VM; direct SSH app deployment validated separately",
                compute_instance_group_selectors=m.ComputeInstanceGroupSelectorCollection(
                    items=[
                        m.ComputeInstanceGroupByIdsSelector(
                            compute_instance_ids=[state["vm-ol9"]]
                        )
                    ]
                ),
            ),
            opc_retry_token=token("environment"),
        ).data.id,
    )
print(devops.get_deploy_environment(state["environment"]).data.lifecycle_state)
