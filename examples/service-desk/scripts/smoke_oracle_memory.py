"""Synthetic actual-ADB validation; no memory text or credentials in output."""
import json
from uuid import uuid4
from python_foundation.agent_memory import MemoryInput,MemoryQuery
from python_foundation.security import Actor
from service_desk.memory_backend import resources

key=str(uuid4())
a=Actor('smoke',key,frozenset());b=Actor('smoke',key+'other',frozenset())
mem,pool,client=resources()
saved=mem.save(a,MemoryInput(text='[Synthetic test] The user prefers concise Korean answers about VPN troubleshooting.'))
client.close();pool.close()
mem,pool,client=resources()
found=mem.search(a,MemoryQuery(query='VPN help answer language preference'))
assert saved.id in [x.id for x in found]
assert mem.search(b,MemoryQuery(query='VPN help answer language preference')) == []
client.close();pool.close()
print(json.dumps({'result':'PASS','backend':'oracle-agent-memory','checks':['save','semantic-search','reconnect-persistence','owner-isolation']}))
