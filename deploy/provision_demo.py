"""Provision an isolated demo VM. Requires OCI Python SDK and an existing API profile.
State contains OCIDs, not credentials. Never pass private keys in config.
"""

import argparse
import base64
import json
import uuid
from pathlib import Path

import oci
from oci.core import models as m

p = argparse.ArgumentParser()
p.add_argument("--config", required=True)
p.add_argument("--state", required=True)
a = p.parse_args()
spec = json.loads(Path(a.config).read_text())
state_path = Path(a.state)
state = json.loads(state_path.read_text()) if state_path.exists() else {}
config = oci.config.from_file(profile_name=spec.get("profile", "DEFAULT"))
config["region"] = spec["region"]
network = oci.core.VirtualNetworkClient(config)
compute = oci.core.ComputeClient(config)
compartment = spec["compartment_id"]
name = spec["name"]
tags = {"project": "oci-agent-launchpad", "purpose": "synthetic-demo"}


def save(key, value):
    state[key] = value
    state_path.write_text(json.dumps(state, indent=2))
    print(key + ": recorded", flush=True)
    return value


def create(key, listing, request):
    if key in state:
        return state[key]
    matches = [
        x
        for x in listing()
        if x.display_name == name + "-" + key
        and x.lifecycle_state not in ("TERMINATED", "TERMINATING")
    ]
    if len(matches) > 1:
        raise RuntimeError("Ambiguous existing resource: " + key)
    if matches:
        return save(key, matches[0].id)
    token = str(uuid.uuid5(uuid.NAMESPACE_URL, compartment + name + key))
    return save(key, request(token).data.id)


def all_items(method, **kwargs):
    return oci.pagination.list_call_get_all_results(method, **kwargs).data


vcn = create(
    "vcn",
    lambda: all_items(network.list_vcns, compartment_id=compartment),
    lambda token: network.create_vcn(
        m.CreateVcnDetails(
            compartment_id=compartment,
            display_name=name + "-vcn",
            cidr_blocks=["10.78.0.0/16"],
            dns_label="launchpad",
            freeform_tags=tags,
        ),
        opc_retry_token=token,
    ),
)
igw = create(
    "igw",
    lambda: all_items(
        network.list_internet_gateways, compartment_id=compartment, vcn_id=vcn
    ),
    lambda token: network.create_internet_gateway(
        m.CreateInternetGatewayDetails(
            compartment_id=compartment,
            vcn_id=vcn,
            display_name=name + "-igw",
            is_enabled=True,
            freeform_tags=tags,
        ),
        opc_retry_token=token,
    ),
)
route = create(
    "route",
    lambda: all_items(
        network.list_route_tables, compartment_id=compartment, vcn_id=vcn
    ),
    lambda token: network.create_route_table(
        m.CreateRouteTableDetails(
            compartment_id=compartment,
            vcn_id=vcn,
            display_name=name + "-route",
            freeform_tags=tags,
            route_rules=[
                m.RouteRule(
                    network_entity_id=igw,
                    destination="0.0.0.0/0",
                    destination_type="CIDR_BLOCK",
                )
            ],
        ),
        opc_retry_token=token,
    ),
)
security = create(
    "security",
    lambda: all_items(
        network.list_security_lists, compartment_id=compartment, vcn_id=vcn
    ),
    lambda token: network.create_security_list(
        m.CreateSecurityListDetails(
            compartment_id=compartment,
            vcn_id=vcn,
            display_name=name + "-security",
            freeform_tags=tags,
            ingress_security_rules=[
                m.IngressSecurityRule(
                    protocol="6",
                    source=spec["ssh_source_cidr"],
                    tcp_options=m.TcpOptions(
                        destination_port_range=m.PortRange(min=22, max=22)
                    ),
                )
            ],
            egress_security_rules=[
                m.EgressSecurityRule(protocol="all", destination="0.0.0.0/0")
            ],
        ),
        opc_retry_token=token,
    ),
)
subnet = create(
    "subnet",
    lambda: all_items(network.list_subnets, compartment_id=compartment, vcn_id=vcn),
    lambda token: network.create_subnet(
        m.CreateSubnetDetails(
            compartment_id=compartment,
            vcn_id=vcn,
            display_name=name + "-subnet",
            cidr_block="10.78.1.0/24",
            dns_label="demo",
            route_table_id=route,
            security_list_ids=[security],
            prohibit_public_ip_on_vnic=False,
            freeform_tags=tags,
        ),
        opc_retry_token=token,
    ),
)
oci.wait_until(
    network,
    network.get_subnet(subnet),
    "lifecycle_state",
    "AVAILABLE",
    max_wait_seconds=120,
)
cloud_init = """#cloud-config
package_update: true
packages:
  - python3.12
  - python3.12-pip
runcmd:
  - [mkdir, -p, /opt/launchpad]
"""
vm_key = "vm-ol9"
instance = create(
    vm_key,
    lambda: all_items(compute.list_instances, compartment_id=compartment),
    lambda token: compute.launch_instance(
        m.LaunchInstanceDetails(
            compartment_id=compartment,
            availability_domain=spec["availability_domain"],
            display_name=name + "-" + vm_key,
            shape="VM.Standard.E5.Flex",
            shape_config=m.LaunchInstanceShapeConfigDetails(ocpus=1, memory_in_gbs=8),
            source_details=m.InstanceSourceViaImageDetails(
                image_id=spec["image_id"], boot_volume_size_in_gbs=50
            ),
            create_vnic_details=m.CreateVnicDetails(
                subnet_id=subnet, assign_public_ip=True
            ),
            metadata={
                "ssh_authorized_keys": Path(spec["ssh_public_key"]).read_text(),
                "user_data": base64.b64encode(cloud_init.encode()).decode(),
            },
            agent_config=m.LaunchInstanceAgentConfigDetails(
                is_management_disabled=False,
                is_monitoring_disabled=False,
                plugins_config=[
                    m.InstanceAgentPluginConfigDetails(
                        name="Compute Instance Run Command", desired_state="ENABLED"
                    )
                ],
            ),
            freeform_tags=tags,
        ),
        opc_retry_token=token,
    ),
)
print(
    json.dumps(
        {
            "instance_id": instance,
            "state": compute.get_instance(instance).data.lifecycle_state,
        }
    )
)
