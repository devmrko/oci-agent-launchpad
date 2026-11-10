"""Rehearse two user apps through the same authenticated local management API."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parents[1]


def demo(output,java_home):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    env=os.environ.copy()
    if java_home:env['PATH']=str(Path(java_home)/'bin')+os.pathsep+env['PATH']
    state=output/'state';client=build_opener(ProxyHandler({}));log=(output/'manager.log').open('wb')
    server=subprocess.Popen([sys.executable,str(ROOT/'deploy/user_apps.py'),'--state',str(state),'serve','--port','0'],env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
    try:
        deadline=time.monotonic()+10
        while not (state/'connection.json').exists():
            if server.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Management server failed to start')
            time.sleep(0.1)
        base=json.loads((state/'connection.json').read_text())['url'];token=(state/'operator-token').read_text()
        def call(action=None,**values):
            request=Request(base+('/command' if action else '/apps'),data=json.dumps(dict(action=action,**values)).encode() if action else None,
                            headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
            with client.open(request,timeout=150) as response:return json.load(response)
        try:
            client.open(base+'/apps',timeout=2)
            raise AssertionError('Anonymous management access allowed')
        except HTTPError as error:assert error.code==401
        results=[]
        for language in ('python','java'):
            source=output/language;shutil.copytree(ROOT/'examples/bring-your-agent'/language,source)
            original=json.loads((source/'app.json').read_text());app=original['id']
            call('register',source=str(source));v1=call('deploy',app=app,version='v1')
            with client.open(v1['url']+'/answer') as response:assert 'v1 result=42' in response.read().decode()
            source2=output/(language+'-v2');shutil.copytree(source,source2)
            config=dict(original,version='v2');(source2/'app.json').write_text(json.dumps(config))
            code=source2/('app.py' if language=='python' else 'App.java');code.write_text(code.read_text().replace('result=42','result=84'))
            call('register',source=str(source2));v2=call('deploy',app=app,version='v2')
            with client.open(v2['url']+'/answer') as response:assert 'v2 result=84' in response.read().decode()
            bad=output/(language+'-broken');shutil.copytree(source2,bad)
            badconfig=dict(config,version='broken',run=['python3','missing.py','{port}'] if language=='python' else ['java','-jar','missing.jar','{port}'])
            (bad/'app.json').write_text(json.dumps(badconfig));call('register',source=str(bad))
            try:
                call('deploy',app=app,version='broken');raise AssertionError('Broken release activated')
            except HTTPError as error:assert error.code==409
            retained=next(x for x in call() if x['id']==app)
            assert retained['version']=='v2' and retained['pid']==v2['pid'] and retained['port']==v2['port']
            restored=call('rollback',app=app);assert restored['version']=='v1' and restored['status']=='UP'
            with client.open(restored['url']+'/answer') as response:assert 'v1 result=42' in response.read().decode()
            logs=call('logs',app=app,version='v2');assert 'started v2' in logs['tail']
            results.append({'id':app,'built':'JAR' if language=='java' else 'Python source','v1':'PASS','v2':'PASS',
                            'failed_release_retained_pid':True,'rollback':'v1','logs_verified':True})
        report={'status':'USER_APPS_PASS','backend':'local-process','management_auth_checked':True,'apps':results,
                'cloud_deployed':False,'llm_called':False}
        (output/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
        return report
    finally:
        server.terminate()
        try:server.wait(timeout=10)
        except subprocess.TimeoutExpired:server.kill();server.wait()
        log.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);p.add_argument('--java-home',type=Path)
    a=p.parse_args();print(json.dumps(demo(a.output,a.java_home),ensure_ascii=False))
