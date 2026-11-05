"""One-time schema setup on the demo VM using stdin secrets; no secrets printed."""
import json,sys,os
from pathlib import Path
import oracledb
from oracleagentmemory.core import OracleDBMemoryStore,SchemaPolicy

cfg=json.load(sys.stdin)
with oracledb.connect(user='ADMIN',password=cfg['admin'],dsn=cfg['dsn']) as con:
    with con.cursor() as cur:
        for name,key in [('LP_MEMORY_OWNER','owner'),('LP_MEMORY_APP','runtime')]:
            cur.execute('SELECT COUNT(*) FROM ALL_USERS WHERE USERNAME=:name',name=name)
            if not cur.fetchone()[0]:
                password=cfg[key]
                if not password.isalnum():raise ValueError('Invalid generated password')
                cur.execute(f'CREATE USER {name} IDENTIFIED BY "{password}"')
        cur.execute('GRANT CREATE SESSION, CREATE TABLE, CREATE PROCEDURE, CREATE SEQUENCE, CREATE TRIGGER, CREATE JOB, CREATE PROPERTY GRAPH TO LP_MEMORY_OWNER')
        cur.execute('ALTER USER LP_MEMORY_OWNER QUOTA 1G ON DATA')
        cur.execute('GRANT CREATE SESSION TO LP_MEMORY_APP')
pool=oracledb.create_pool(user='LP_MEMORY_OWNER',password=cfg['owner'],dsn=cfg['dsn'],min=1,max=2)
store=OracleDBMemoryStore(pool=pool,embedder=None,vector_dim=1536,memory_store_id='LPMEM',schema_policy=SchemaPolicy.CREATE_IF_NECESSARY)
with pool.acquire() as con:
    with con.cursor() as cur:
        cur.execute('SELECT TABLE_NAME FROM USER_TABLES')
        for (name,) in cur.fetchall():
            if name.startswith('LPMEM_'):cur.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {name} TO LP_MEMORY_APP')
            else:cur.execute(f'GRANT SELECT ON {name} TO LP_MEMORY_APP')
        cur.execute("SELECT OBJECT_NAME,OBJECT_TYPE FROM USER_OBJECTS WHERE OBJECT_TYPE IN ('PROCEDURE','FUNCTION','PACKAGE','SEQUENCE','PROPERTY GRAPH')")
        for name,kind in cur.fetchall():
            if kind=='PROPERTY GRAPH':cur.execute(f'GRANT SELECT ON PROPERTY GRAPH {name} TO LP_MEMORY_APP')
            elif kind=='SEQUENCE':cur.execute(f'GRANT SELECT ON {name} TO LP_MEMORY_APP')
            else:cur.execute(f'GRANT EXECUTE ON {name} TO LP_MEMORY_APP')
pool.close()
runtime={k:cfg[k] for k in ['dsn','compartment']};runtime.update(user='LP_MEMORY_APP',password=cfg['runtime'])
p=Path('/etc/launchpad-memory.json')
with os.fdopen(os.open(p,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'w') as f:json.dump(runtime,f)
import pwd
os.chown(p,pwd.getpwnam('launchpad').pw_uid,pwd.getpwnam('launchpad').pw_gid)
print('Memory schema initialized; runtime credential configured.')
