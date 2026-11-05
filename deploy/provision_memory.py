"""Create one dedicated ADB; credentials never appear in output or source."""
import json, os, secrets
from pathlib import Path
import oci

root=Path('.run/oci-launchpad'); state_path=root/'state.json'
state=json.loads(state_path.read_text())
config=oci.config.from_file(); config['region']='ap-seoul-1'
client=oci.database.DatabaseClient(config)
if state.get('memory_adb'):
    db=client.get_autonomous_database(state['memory_adb']).data
else:
    secret_path=root/'adb-secrets.json'
    if secret_path.exists(): secret=json.loads(secret_path.read_text())
    else:
        secret={k:'Aa7'+secrets.token_hex(12) for k in ('admin','owner','runtime')}
        with os.fdopen(os.open(secret_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as f:json.dump(secret,f)
    details=oci.database.models.CreateAutonomousDatabaseDetails(
        compartment_id='ocid1.compartment.oc1..aaaaaaaam3amapwxz6nyciqzb2v2iwg66t22g47vabo5ilnghbsskooeop3q',
        db_name='LPMEMORY',display_name='oci-agent-launchpad-memory',db_workload='OLTP',db_version='26ai',
        compute_model='ECPU',compute_count=2,data_storage_size_in_gbs=20,
        is_auto_scaling_enabled=False,is_auto_scaling_for_storage_enabled=False,
        license_model='LICENSE_INCLUDED',is_mtls_connection_required=False,
        whitelisted_ips=['132.145.80.78/32'],admin_password=secret['admin'],
        freeform_tags={'project':'oci-agent-launchpad','purpose':'agent-memory-demo'})
    try: db=client.create_autonomous_database(details,opc_retry_token='launchpad-memory-20261105').data
    except oci.exceptions.ServiceError as e:
        print(json.dumps({'status':e.status,'code':e.code,'message':e.message}));raise SystemExit(1)
    state['memory_adb']=db.id;state_path.write_text(json.dumps(state,indent=2))
print(json.dumps({'id':db.id,'state':db.lifecycle_state,'version':db.db_version,'name':db.display_name}))
