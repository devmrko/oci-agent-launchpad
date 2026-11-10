"""Hello Agent release identity: hashes are provenance hints, not signatures."""
import hashlib
import json
from pathlib import Path
import re

RUNTIME_FILES = ('agent.py', 'hello_web.py', 'hello_telemetry.py', 'hello_release.py')
SUMMARY = ('release_id', 'spec_sha256', 'source_sha256', 'test_evidence_sha256')


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def validate(value):
    fields={'schema_version','agent_id','app_version','runtime_files',*SUMMARY}
    if not isinstance(value,dict) or set(value)!=fields:
        raise ValueError('Invalid Hello Agent release identity')
    if value['schema_version']!=1 or value['agent_id']!='hello-agent' or value['app_version']!='0.1.0':
        raise ValueError('Unsupported Hello Agent release identity')
    files=value['runtime_files']
    if not isinstance(files,dict) or set(files)!=set(RUNTIME_FILES):
        raise ValueError('Incomplete runtime file identity')
    if any(not isinstance(x,str) or re.fullmatch('[a-f0-9]{64}',x) is None
           for x in [*(value[k] for k in SUMMARY),*files.values()]):
        raise ValueError('Invalid release digest')
    if value['source_sha256']!=digest(files) or value['release_id']!=digest({k:v for k,v in value.items() if k!='release_id'}):
        raise ValueError('Release identity content changed')
    return value


def load(raw, directory=None):
    if raw is None:
        return None
    try:
        value=validate(json.loads(raw))
        root=Path(directory) if directory is not None else Path(__file__).resolve().parent
        for name,expected in value['runtime_files'].items():
            file=root/name
            if file.is_symlink() or hashlib.sha256(file.read_bytes()).hexdigest()!=expected:
                raise ValueError('Installed file differs from release identity')
        return {key:value[key] for key in SUMMARY}
    except (OSError,ValueError,KeyError,TypeError):
        raise ValueError('Hello Agent release identity does not match installed files') from None
