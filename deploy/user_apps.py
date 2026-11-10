"""Single-operator local runtime for user-owned apps. Not an untrusted-code sandbox."""
import argparse
import fcntl
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import socket
import subprocess
import threading
import time
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

NAME=r'[a-z][a-z0-9-]{0,47}'
VERSION=r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}'


def check(value, pattern=NAME):
    if not isinstance(value,str) or re.fullmatch(pattern,value) is None:
        raise ValueError('Invalid app ID or version')
    return value


def argv(value):
    if not isinstance(value,list) or not value or len(value)>64 or any(not isinstance(v,str) or not v or len(v)>2048 or '\0' in v for v in value):
        raise ValueError('Expected a bounded argv array')
    return value


def manifest(value):
    required={'schema_version','id','version','files','build','run','health_path'}
    if not isinstance(value,dict) or not required<=set(value) or set(value)-required-{'invoke_path'} or value['schema_version']!=1:
        raise ValueError('Expected the documented app manifest fields')
    check(value['id']);check(value['version'],VERSION)
    files=value['files']
    if not isinstance(files,list) or not 1<=len(files)<=200 or len(set(files))!=len(files):
        raise ValueError('Explicit unique file list required')
    for name in files:
        if not isinstance(name,str) or not name or Path(name).is_absolute() or '..' in Path(name).parts or '\\' in name:
            raise ValueError('Invalid source path')
        if name=='release.json':raise ValueError('Reserved release receipt path')
        if any(part.startswith('.env') or part in {'.git','.oci','.aws'} or part.endswith(('.pem','.key')) for part in Path(name).parts):
            raise ValueError('Credential/configuration file refused')
    if not isinstance(value['build'],list) or len(value['build'])>10:
        raise ValueError('Expected up to ten build commands')
    for command in value['build']:argv(command)
    argv(value['run'])
    if not isinstance(value['health_path'],str) or re.fullmatch(r'/[A-Za-z0-9/_-]*',value['health_path']) is None:
        raise ValueError('Expected a relative HTTP health path')
    if 'invoke_path' in value and (not isinstance(value['invoke_path'],str) or re.fullmatch(r'/[A-Za-z0-9/_-]+',value['invoke_path']) is None):
        raise ValueError('Invalid invoke path')
    return value


def save(path,data):
    tmp=path.with_name(path.name+'.tmp')
    with os.fdopen(os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'w') as stream:
        json.dump(data,stream,ensure_ascii=False,indent=2)
    os.replace(tmp,path)


def environment():
    # Deliberately do not pass provider keys, credentials or proxy settings to apps.
    return {k:os.environ[k] for k in ('PATH','JAVA_HOME','LANG','SYSTEMROOT') if k in os.environ}


def stop_process(process):
    if process.poll() is None:
        try:os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError:return
        try:process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=3)


def run_build(command,root,log,timeout):
    process=subprocess.Popen(command,cwd=root,env=environment(),stdin=subprocess.DEVNULL,
                             stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    try:
        if process.wait(timeout=timeout)!=0:raise ValueError('Build failed; inspect the build log')
    except subprocess.TimeoutExpired:
        raise ValueError('Build timed out') from None
    finally:stop_process(process)


def hashes(root):
    result={};total=0
    for path in sorted(root.rglob('*')):
        if path.is_symlink():raise ValueError('Symlink in release')
        if path.is_file() and path!=root/'release.json':
            total+=path.stat().st_size
            if total>64*1024*1024 or len(result)>=2000:raise ValueError('Release exceeds local runtime limit')
            result[path.relative_to(root).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    return result


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def healthy(port,path):
    try:
        with build_opener(ProxyHandler({}),NoRedirect()).open('http://127.0.0.1:'+str(port)+path,timeout=0.5) as response:
            return response.status==200
    except (OSError,ValueError):return False


class Manager:
    def __init__(self,state):
        self.state=Path(state).resolve();self.state.mkdir(parents=True,exist_ok=True,mode=0o700)
        (self.state/'apps').mkdir(exist_ok=True);(self.state/'logs').mkdir(exist_ok=True)
        (self.state/'config').mkdir(exist_ok=True,mode=0o700)
        (self.state/'requests').mkdir(exist_ok=True,mode=0o700)
        self.active={};self.previous={};self.lock=threading.RLock();self.inflight=set()

    def release(self,app,version):
        return self.state/'apps'/check(app)/check(version,VERSION)

    def register(self,source):
        source=Path(source).resolve(strict=True)
        value=manifest(json.loads((source/'app.json').read_text()))
        target=self.release(value['id'],value['version'])
        with self.lock:
            if target.exists():raise ValueError('Version already registered')
            target.parent.mkdir(exist_ok=True)
            staging=target.parent/('.incoming-'+secrets.token_hex(8));staging.mkdir(mode=0o700)
            try:
                for name in value['files']:
                    path=source/name
                    if not path.resolve().is_relative_to(source) or any(p.is_symlink() for p in (path,*path.parents)) or not path.is_file():
                        raise ValueError('Source must be a regular local file')
                    if path.stat().st_size>16*1024*1024:raise ValueError('Source file too large')
                    dest=staging/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
                    dest.chmod(0o700 if path.stat().st_mode & 0o111 else 0o600)
                logpath=self.state/'logs'/f'{value["id"]}-{value["version"]}-build.log'
                with os.fdopen(os.open(logpath,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'wb') as log:
                    deadline=time.monotonic()+120
                    for command in value['build']:
                        remaining=deadline-time.monotonic()
                        if remaining<=0:raise ValueError('Build timed out')
                        run_build(command,staging,log,remaining)
                fingerprint=hashes(staging)
                if not fingerprint:raise ValueError('Empty release')
                save(staging/'release.json',{'manifest':value,'files':fingerprint})
                os.rename(staging,target)
            except BaseException:
                shutil.rmtree(staging);raise
        return {'id':value['id'],'version':value['version'],'status':'REGISTERED','files':len(fingerprint)}

    def deploy(self,app,version):
        with self.lock:
            root=self.release(app,version);receipt=json.loads((root/'release.json').read_text());value=manifest(receipt['manifest'])
            if value['id']!=app or value['version']!=version or hashes(root)!=receipt['files']:
                raise ValueError('Registered release changed; register a new version')
            with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            env=environment();env.update(self.runtime_env(app));env.update(PORT=str(port),APP_VERSION=version,BIND_HOST='127.0.0.1',PYTHONDONTWRITEBYTECODE='1')
            command=[s.replace('{port}',str(port)) for s in value['run']]
            logpath=self.state/'logs'/f'{app}-{version}-runtime.log'
            log=os.fdopen(os.open(logpath,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600),'ab');process=None
            try:
                process=subprocess.Popen(command,cwd=root,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                deadline=time.monotonic()+8
                while process.poll() is None:
                    if healthy(port,value['health_path']):break
                    if time.monotonic()>deadline:raise ValueError('Readiness timed out; previous version retained')
                    time.sleep(0.1)
                if process.poll() is not None:raise ValueError('App exited; previous version retained')
                previous=self.active.get(app)
                self.active[app]={'process':process,'version':version,'port':port,'health_path':value['health_path'],'invoke_path':value.get('invoke_path')}
                if previous:
                    if previous['version']!=version:self.previous[app]=previous['version']
                    stop_process(previous['process'])
            except BaseException:
                if process is not None:stop_process(process)
                raise
            finally:log.close()
            return self.status(app)

    def status(self,app=None):
        with self.lock:
            names=[check(app)] if app else sorted(p.name for p in (self.state/'apps').iterdir() if p.is_dir())
            result=[]
            for name in names:
                current=self.active.get(name)
                item={'id':name,
                      'version':None,'status':'STOPPED','previous':self.previous.get(name)}
                item['versions']=sorted(p.parent.name for p in (self.state/'apps'/name).glob('*/release.json'))
                if current:
                    item.update(version=current['version'],port=current['port'],pid=current['process'].pid,
                                url=f'http://127.0.0.1:{current["port"]}',status='UP' if current['process'].poll() is None and healthy(current['port'],current['health_path']) else 'DOWN')
                result.append(item)
            return result[0] if app else result

    def rollback(self,app):
        check(app)
        with self.lock:
            if app not in self.previous:raise ValueError('No previous healthy version')
            return self.deploy(app,self.previous[app])

    def stop(self,app):
        check(app)
        with self.lock:
            current=self.active.pop(app,None)
            if current:stop_process(current['process'])
            return self.status(app)

    def logs(self,app,version,kind='runtime'):
        check(app);check(version,VERSION)
        if kind not in {'build','runtime'}:raise ValueError('Invalid log kind')
        path=self.state/'logs'/f'{app}-{version}-{kind}.log'
        with path.open('rb') as stream:
            stream.seek(0,2);size=stream.tell();stream.seek(max(0,size-16384));text=stream.read().decode(errors='replace')
        return {'id':app,'version':version,'kind':kind,'tail':text,'truncated':size>16384}

    def configure(self,app,source):
        check(app)
        source=Path(source)
        value=self.read_private(source)
        self.validate_config(value)
        # Resolve all references before installing a new configuration.
        self.resolve_env(value)
        with self.lock:save(self.state/'config'/f'{app}.json',value)
        return {'id':app,'status':'CONFIGURED','effective':'next deployment'}

    @staticmethod
    def read_private(path):
        path=Path(path)
        if not path.is_absolute() or path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
            raise ValueError('Configuration and secrets require private regular files (0600)')
        if path.stat().st_size>65536:raise ValueError('Configuration too large')
        return json.loads(path.read_text())

    @staticmethod
    def validate_config(value):
        if not isinstance(value,dict) or set(value)!={'env','secret_files'}:raise ValueError('Expected env and secret_files')
        reserved={'PATH','HOME','JAVA_HOME','JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH','NODE_OPTIONS','BASH_ENV','ENV','PORT','APP_VERSION','BIND_HOST'}
        for group in ('env','secret_files'):
            if not isinstance(value[group],dict) or len(value[group])>64:raise ValueError('Invalid runtime environment')
            for key,item in value[group].items():
                if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}',key) or key in reserved or key.startswith(('LD_','DYLD_','PYTHON')):
                    raise ValueError('Reserved or invalid environment name')
                if not isinstance(item,str) or len(item)>16384 or '\0' in item:raise ValueError('Invalid environment value')
        if set(value['env']) & set(value['secret_files']):raise ValueError('Duplicate environment name')

    @staticmethod
    def resolve_env(value):
        result=dict(value['env'])
        for key,name in value['secret_files'].items():
            path=Path(name)
            if not path.is_absolute() or path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077 or path.stat().st_size>16384:
                raise ValueError('Secret reference must be a private regular file (0600)')
            item=path.read_text().rstrip('\r\n')
            if not item or '\0' in item:raise ValueError('Invalid secret value')
            result[key]=item
        return result

    def runtime_env(self,app):
        path=self.state/'config'/f'{check(app)}.json'
        if not path.exists():return {}
        value=self.read_private(path);self.validate_config(value)
        return self.resolve_env(value)

    def invoke(self,app,payload):
        check(app)
        encoded=json.dumps(payload).encode()
        if len(encoded)>4096:raise ValueError('Request too large')
        with self.lock:
            current=self.active.get(app)
            if not current or current['process'].poll() is not None:raise ValueError('App is not running')
            if not current.get('invoke_path'):raise ValueError('App has no invoke_path')
            if app in self.inflight:raise ValueError('App already processing a request')
            self.inflight.add(app)
            port,version,path=current['port'],current['version'],current['invoke_path']
        trace_id=secrets.token_hex(16);start=time.monotonic()
        event={'trace_id':trace_id,'app':app,'version':version,'time':datetime.now(timezone.utc).isoformat()}
        result=None
        try:
            request=Request(f'http://127.0.0.1:{port}'+path,data=encoded,
                headers={'Content-Type':'application/json','X-Request-ID':trace_id})
            with build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=45) as response:
                raw=response.read(65537)
                if len(raw)>65536:raise ValueError('Response too large')
                result=json.loads(raw)
                event.update(status='SUCCEEDED',http_status=response.status)
        except HTTPError as error:
            # Never log provider/app bodies or automatically replay an operation.
            event.update(status='FAILED',http_status=error.code,error='APP_HTTP_ERROR')
            try:
                raw=error.read(65537)
                if len(raw)<=65536:result=json.loads(raw)
            except (OSError,ValueError):pass
            finally:error.close()
        except (OSError,ValueError):
            event.update(status='FAILED',error='TIMEOUT_OR_INVALID_RESPONSE')
        finally:
            with self.lock:self.inflight.discard(app)
        if isinstance(result,dict) and result.get('trace_id')==trace_id:
            if isinstance(result.get('telemetry'),str) and result.get('telemetry') in {'exported','failed','disabled'}:event['telemetry']=result['telemetry']
            stages=result.get('stages',[])
            if isinstance(stages,list):
                event['stages']=[{k:v for k,v in item.items() if (k=='stage' and isinstance(v,str) and v in {'model','mcp.multiply'}) or (k=='status' and isinstance(v,str) and v in {'SUCCEEDED','FAILED'}) or (k=='error' and isinstance(v,str) and v in {'MODEL_FAILED','MCP_FAILED'}) or (k=='duration_ms' and type(v) is int and 0<=v<=60000)} for item in stages[:10] if isinstance(item,dict)]
        event['duration_ms']=round((time.monotonic()-start)*1000)
        with self.lock:
            events=self.requests(app)
            save(self.state/'requests'/f'{app}.json',(events+[event])[-100:])
        return dict(event,response=result)

    def requests(self,app):
        path=self.state/'requests'/f'{check(app)}.json'
        return json.loads(path.read_text()) if path.exists() else []

    def close(self):
        for app in list(self.active):self.stop(app)


def serve(state,port):
    manager=Manager(state)
    guard=(manager.state/'server.lock').open('a');fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
    token=secrets.token_urlsafe(32)
    token_path=manager.state/'operator-token'
    with os.fdopen(os.open(token_path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'w') as stream:stream.write(token)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):self.handle_request()
        def do_POST(self):self.handle_request()
        def handle_request(self):
            try:
                if self.headers.get('Host') not in {f'127.0.0.1:{server.server_port}',f'localhost:{server.server_port}'}:
                    self.respond(403,{'error':'Host not allowed'});return
                if not secrets.compare_digest(self.headers.get('Authorization',''),'Bearer '+token):
                    self.respond(401,{'error':'Authentication required'});return
                if self.command=='GET' and self.path=='/apps':self.respond(200,manager.status());return
                if self.command!='POST' or self.path!='/command':self.respond(404,{'error':'Not found'});return
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=8192:raise ValueError('Invalid request size')
                args=json.loads(self.rfile.read(size));op=args.pop('action')
                if op not in {'register','deploy','rollback','stop','logs','configure','invoke','requests'}:raise ValueError('Unsupported operation')
                self.respond(200,getattr(manager,op)(**args))
            except (ValueError,KeyError,TypeError,OSError,subprocess.SubprocessError) as error:
                self.respond(409,{'error':str(error)[:300] if isinstance(error,ValueError) else 'Operation failed; inspect local configuration and logs'})
        def respond(self,code,data):
            payload=json.dumps(data,ensure_ascii=False).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    save(manager.state/'connection.json',{'url':f'http://127.0.0.1:{server.server_port}'})
    print(json.dumps({'status':'READY','url':f'http://127.0.0.1:{server.server_port}','token_file':str(token_path)}),flush=True)
    def interrupted(signum,frame):raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM,interrupted)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();manager.close();guard.close()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--state',type=Path,required=True)
    sub=p.add_subparsers(dest='action',required=True)
    s=sub.add_parser('serve');s.add_argument('--port',type=int,default=8096)
    s=sub.add_parser('register');s.add_argument('source',type=Path)
    s=sub.add_parser('configure');s.add_argument('app');s.add_argument('source',type=Path)
    s=sub.add_parser('invoke');s.add_argument('app');s.add_argument('payload',type=json.loads)
    sub.add_parser('requests').add_argument('app')
    s=sub.add_parser('deploy');s.add_argument('app');s.add_argument('version')
    for name in ('rollback','stop'):sub.add_parser(name).add_argument('app')
    sub.add_parser('status')
    s=sub.add_parser('logs');s.add_argument('app');s.add_argument('version');s.add_argument('--kind',choices=['build','runtime'],default='runtime')
    args=p.parse_args()
    if args.action=='serve':
        serve(args.state,args.port);return
    data=vars(args).copy();state=data.pop('state')
    if args.action in {'register','configure'}:data['source']=str(args.source.resolve())
    url=json.loads((state/'connection.json').read_text())['url'];token=(state/'operator-token').read_text()
    request=Request(url+('/apps' if args.action=='status' else '/command'),data=None if args.action=='status' else json.dumps(data).encode(),
                    headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    try:
        with build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=150) as response:print(response.read().decode())
    except Exception as error:
        from urllib.error import HTTPError
        if isinstance(error,HTTPError):p.exit(1,error.read().decode()+'\n')
        p.exit(1,'Management connection unavailable.\n')

if __name__=='__main__':main()
