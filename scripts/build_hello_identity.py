"""Prepare Hello Agent release identity from current, successful command evidence."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from command_evidence import inspect
from requirement_handoff import read, write_new

ROOT=Path(__file__).resolve().parents[1]
SPEC='specs/hello-release-identity/spec.md'
APP_SPEC='specs/hello-agent/spec.md'
MODULE=ROOT/'examples/hello-agent/hello_release.py'
spec=importlib.util.spec_from_file_location('hello_identity_contract',MODULE)
contract=importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


def prepare(root,evidence_path,output):
    root=Path(root).resolve()
    raw=Path(evidence_path).read_bytes()
    evidence=json.loads(raw)
    if not inspect(root,evidence)['usable_command_success']:
        raise ValueError('Current successful command evidence required')
    paths={name:'examples/hello-agent/'+name for name in contract.RUNTIME_FILES}
    required={SPEC,APP_SPEC,'examples/hello-agent/pyproject.toml','examples/hello-agent/test_release.py',*paths.values()}
    if not required <= evidence['files'].keys():
        raise ValueError('Release checks must include the specification and runtime files')
    files={name:evidence['files'][path] for name,path in paths.items()}
    result={'schema_version':1,'agent_id':'hello-agent','app_version':'0.1.0','runtime_files':files,
            'spec_sha256':evidence['files'][APP_SPEC],'source_sha256':contract.digest(files),
            'test_evidence_sha256':hashlib.sha256(raw).hexdigest()}
    result['release_id']=contract.digest(result)
    contract.validate(result)
    write_new(output,result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--evidence',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    try:
        result=prepare(a.root,a.evidence,a.output)
    except (OSError,ValueError,KeyError,TypeError):
        p.exit(1,'Check current evidence, required files and a new output path.\n')
    print(json.dumps({'status':'PREPARED','release_id':result['release_id'],'cloud_deployed':False}))

if __name__=='__main__':
    main()
