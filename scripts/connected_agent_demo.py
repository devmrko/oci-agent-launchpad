"""Exercise real managed processes and MCP against a clearly labelled model API fixture."""
import argparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'deploy'))
from user_apps import Manager,stop_process


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    calls=[]
    class ModelFixture(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append(self.headers.get('Authorization'))
            message=body['messages'][-1]['content']
            value={'tool':'delete_everything','arguments':{}} if message=='reject tool' else {'tool':'multiply','arguments':{'a':6,'b':7}}
            raw=json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(value)}}],'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(raw)
    model=ThreadingHTTPServer(('127.0.0.1',0),ModelFixture)
    threading.Thread(target=model.serve_forever,daemon=True).start()
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));mcp_port=sock.getsockname()[1]
    log=(out/'mcp.log').open('wb')
    mcp=subprocess.Popen([sys.executable,str(ROOT/'examples/bring-your-agent/connected/calculator_mcp.py'),'--port',str(mcp_port)],stdout=log,stderr=log,start_new_session=True)
    manager=Manager(out/'state')
    try:
        deadline=time.monotonic()+10
        while True:
            try:
                with socket.create_connection(('127.0.0.1',mcp_port),timeout=.2):break
            except OSError:
                if mcp.poll() is not None or time.monotonic()>deadline:raise RuntimeError('MCP did not start')
                time.sleep(.1)
        source=out/'source';shutil.copytree(ROOT/'examples/bring-your-agent/connected',source)
        config=json.loads((source/'app.json').read_text());config['run'][0]=sys.executable
        (source/'app.json').write_text(json.dumps(config))
        secret=out/'key';secret.write_text('fixture-secret');secret.chmod(0o600)
        settings=out/'settings.json';settings.write_text(json.dumps({'env':{
            'AGENT_PROVIDER':'openai-compatible','AGENT_MODEL':'fixture-model',
            'AGENT_BASE_URL':f'http://127.0.0.1:{model.server_port}/v1',
            'AGENT_MCP_URL':f'http://127.0.0.1:{mcp_port}/mcp'},'secret_files':{'AGENT_API_KEY':str(secret)}}));settings.chmod(0o600)
        manager.configure('connected-agent',settings);manager.register(source);manager.deploy('connected-agent','v1')
        success=manager.invoke('connected-agent',{'message':'6 times 7'})
        assert success['status']=='SUCCEEDED',success
        assert success['response']['answer']=='42',success
        assert success['response']['usage']['total_tokens']==15
        assert [s['status'] for s in success['stages']]==['SUCCEEDED','SUCCEEDED']
        rejected=manager.invoke('connected-agent',{'message':'reject tool'})
        assert rejected['status']=='FAILED' and rejected['stages'][0]['error']=='MODEL_FAILED',rejected
        stop_process(mcp)
        tool_failure=manager.invoke('connected-agent',{'message':'6 times 7'})
        assert tool_failure['status']=='FAILED' and tool_failure['stages'][-1]['error']=='MCP_FAILED',tool_failure
        assert all(c=='Bearer fixture-secret' for c in calls)
        events=manager.requests('connected-agent');durable=json.dumps(events)+manager.logs('connected-agent','v1')['tail']
        assert 'fixture-secret' not in durable and '6 times 7' not in durable and 'reject tool' not in durable
        assert len(events)==3 and len({e['trace_id'] for e in events})==3
        result={'status':'CONNECTED_AGENT_PASS','model':'HTTP protocol fixture, not a real LLM',
                'mcp':'official SDK over HTTP, real process','result':42,
                'disallowed_tool_rejected':True,'mcp_failure_recorded':True,'secret_absent_from_logs':True,'requests':events}
        (out/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
    finally:
        manager.close();stop_process(mcp);log.close();model.shutdown();model.server_close()

if __name__=='__main__':main()
