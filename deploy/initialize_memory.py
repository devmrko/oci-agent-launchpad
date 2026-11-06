"""One-time schema setup on the demo VM using stdin secrets; no secrets printed."""
import json,sys,os,re,argparse
from pathlib import Path
import oracledb
from oracleagentmemory.core import OracleDBMemoryStore,SchemaPolicy

parser=argparse.ArgumentParser()
parser.add_argument('--settings')
parser.add_argument('--output',default='/etc/launchpad-memory.json')
parser.add_argument('--service-user',default='launchpad')
args=parser.parse_args()
cfg=json.load(sys.stdin)
if args.settings:
    settings=json.loads(Path(args.settings).read_text())
    if set(settings)-{'compartment','embedding_region','embedding_model','embedding_dimensions','store_id','schema_owner','user','namespace'}:
        raise ValueError('Unexpected memory setting')
    cfg.update(settings)
owner=cfg.get('schema_owner','LP_MEMORY_OWNER')
app_user=cfg.get('user','LP_MEMORY_APP')
store_id=cfg.get('store_id','LPMEM')
for value,cap in [(owner,30),(app_user,30),(store_id,16)]:
    if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,'+str(cap-1)+'}',value):raise ValueError('Invalid database identifier')
if owner==app_user:raise ValueError('Separate owner and runtime users required')
with oracledb.connect(user='ADMIN',password=cfg['admin'],dsn=cfg['dsn']) as con:
    with con.cursor() as cur:
        for name,key in [(owner,'owner'),(app_user,'runtime')]:
            cur.execute('SELECT COUNT(*) FROM ALL_USERS WHERE USERNAME=:name',name=name)
            if not cur.fetchone()[0]:
                password=cfg[key]
                if not password.isalnum():raise ValueError('Invalid generated password')
                cur.execute(f'CREATE USER {name} IDENTIFIED BY "{password}"')
        cur.execute(f'GRANT CREATE SESSION, CREATE TABLE, CREATE PROCEDURE, CREATE SEQUENCE, CREATE TRIGGER, CREATE JOB, CREATE PROPERTY GRAPH TO {owner}')
        cur.execute(f'ALTER USER {owner} QUOTA 1G ON DATA')
        cur.execute(f'GRANT CREATE SESSION TO {app_user}')
pool=oracledb.create_pool(user=owner,password=cfg['owner'],dsn=cfg['dsn'],min=1,max=2)
store=OracleDBMemoryStore(pool=pool,embedder=None,vector_dim=cfg.get('embedding_dimensions',1536),memory_store_id=store_id,schema_policy=SchemaPolicy.CREATE_IF_NECESSARY)
with pool.acquire() as con:
    with con.cursor() as cur:
        cur.execute('SELECT TABLE_NAME FROM USER_TABLES')
        for (name,) in cur.fetchall():
            if name.startswith(store_id+'_'):cur.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {name} TO {app_user}')
            elif name=='AGENT_MEMORY_STORES':cur.execute(f'GRANT SELECT ON {name} TO {app_user}')
        cur.execute("SELECT OBJECT_NAME,OBJECT_TYPE FROM USER_OBJECTS WHERE OBJECT_TYPE IN ('PROCEDURE','FUNCTION','PACKAGE','SEQUENCE','PROPERTY GRAPH')")
        for name,kind in cur.fetchall():
            if kind=='PROPERTY GRAPH':cur.execute(f'GRANT SELECT ON PROPERTY GRAPH {name} TO {app_user}')
            elif kind=='SEQUENCE':cur.execute(f'GRANT SELECT ON {name} TO {app_user}')
            else:cur.execute(f'GRANT EXECUTE ON {name} TO {app_user}')
pool.close()
# Fail before publishing a credential that cannot log in or read its store.
with oracledb.connect(user=app_user,password=cfg['runtime'],dsn=cfg['dsn']) as con:
    with con.cursor() as cur:
        cur.execute(f'SELECT COUNT(*) FROM {owner}.AGENT_MEMORY_STORES')
        cur.fetchone()
runtime={k:cfg[k] for k in ['dsn','compartment']};runtime.update(user=app_user,password=cfg['runtime'],schema_owner=owner,store_id=store_id)
for key in ['embedding_region','embedding_model','embedding_dimensions','namespace']:
    if key in cfg:runtime[key]=cfg[key]
p=Path(args.output)
with os.fdopen(os.open(p,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600),'w') as f:json.dump(runtime,f)
import pwd
os.chown(p,pwd.getpwnam(args.service_user).pw_uid,pwd.getpwnam(args.service_user).pw_gid)
print('Memory schema initialized; runtime credential configured.')
