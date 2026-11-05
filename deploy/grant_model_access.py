"""Grant this demo instance access to specified chat and embedding models."""
import json
from pathlib import Path
import oci

folder=Path('.run/oci-launchpad')
spec=json.loads((folder/'config.json').read_text())
state_path=folder/'state.json'
state=json.loads(state_path.read_text())
cfg=oci.config.from_file()
identity=oci.identity.IdentityClient(cfg)
subscriptions=identity.list_region_subscriptions(cfg['tenancy']).data
home=next(r.region_name for r in subscriptions if r.is_home_region)
cfg['region']=home
identity=oci.identity.IdentityClient(cfg)
name='oci-agent-launchpad-demo-runtime'
# A direct principal-ID condition avoids consuming a dynamic-group quota slot.
statement=("Allow any-user to use generative-ai-chat in compartment id "+spec['compartment_id']+
    " where ALL {request.principal.id = '"+state['vm-ol9']+"', target.model.id = 'google.gemini-2.5-flash-lite'}")
embedding=("Allow any-user to use generative-ai-text-embedding in compartment id "+spec['compartment_id']+
    " where ALL {request.principal.id = '"+state['vm-ol9']+"', target.model.id = 'cohere.embed-v4.0'}")
statements=[statement,embedding]
policies=oci.pagination.list_call_get_all_results(identity.list_policies,compartment_id=spec['compartment_id']).data
found=[x for x in policies if x.name==name]
if found:
    policy=found[0]
    if set(policy.statements) != set(statements):
        raise RuntimeError('Existing policy differs; manual review required')
else:
    policy=identity.create_policy(oci.identity.models.CreatePolicyDetails(compartment_id=spec['compartment_id'],
        name=name,description='Demo VM may invoke only Flash Lite chat; no resource administration',statements=statements)).data
state['runtime_policy']=policy.id
state_path.write_text(json.dumps(state,indent=2))
print('Single-instance chat and embedding policy recorded.')
