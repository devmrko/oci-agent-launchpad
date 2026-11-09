"""Create a deterministic private-source bundle for Companion python-v1."""
import argparse
import gzip
import hashlib
import io
import json
import re
import tarfile
import tomllib
from pathlib import Path
from package_sources import export


def package(foundation, foundation_revision, launchpad, launchpad_revision, output, example="service-desk"):
    if example not in {'service-desk', 'hello-agent'}:
        raise ValueError('Unsupported example')
    example_path = 'examples/' + example
    if output.exists():
        raise ValueError('Output already exists')
    fsha, library = export(foundation, foundation_revision, ['src', 'pyproject.toml', 'README.md'], 'project/dependencies/foundation/')
    lsha, source = export(launchpad, launchpad_revision, [example_path, 'deploy/function-build-tools.lock'], '')
    files = {}
    tools = None
    for name, data, mode in source:
        if name == 'deploy/function-build-tools.lock':
            tools = data.decode()
        elif name.startswith(example_path + '/'):
            files['project/' + name.removeprefix(example_path + '/')] = (data, mode)
    for name, data, mode in library:
        if name in files:
            raise ValueError('Duplicate bundled path')
        files[name] = (data, mode)
    app = tomllib.loads(files['project/pyproject.toml'][0].decode())['project']
    lib = tomllib.loads(files['project/dependencies/foundation/pyproject.toml'][0].decode())['project']
    if lib['name'] + '==' + lib['version'] not in app['dependencies']:
        raise ValueError('Foundation dependency does not match pinned source')
    if tools is None:
        raise ValueError('Committed build tools lock required')
    pins = {}
    for line in (files['project/requirements-memory.lock'][0].decode() + '\n' + tools).splitlines():
        if not line:
            continue
        if not re.fullmatch(r'[A-Za-z0-9_.-]+==[A-Za-z0-9_.+!-]+', line):
            raise ValueError('Exact dependency pins required')
        name, version = line.split('==')
        key = re.sub(r'[-_.]+', '-', name).lower()
        if key in pins and pins[key].split('==')[1] != version:
            raise ValueError('Conflicting dependency versions')
        pins[key] = line
    if re.sub(r'[-_.]+', '-', lib['name']).lower() in pins:
        raise ValueError('Private library must come from source')
    manifest = {'schema_version': 1, 'commit': lsha, 'foundation_commit': fsha}
    additions = {
        'source.json': json.dumps(manifest, sort_keys=True).encode(),
        'project/requirements-build.lock': ('\n'.join(pins[k] for k in sorted(pins))+'\n').encode(),
        'project/build-local.json': json.dumps({'schema_version': 1, 'packages': [
            {'path': 'dependencies/foundation', 'name': lib['name'], 'version': lib['version']}]}).encode(),
    }
    for name, data in additions.items():
        if name in files:
            raise ValueError('Generated manifest would replace source')
        files[name] = (data, 0o644)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as target:
        with gzip.GzipFile(filename='', mode='wb', fileobj=target, mtime=0) as stream:
            with tarfile.open(fileobj=stream, mode='w') as archive:
                for name, (data, mode) in sorted(files.items()):
                    info = tarfile.TarInfo(name)
                    info.size, info.mode, info.mtime = len(data), mode, 0
                    archive.addfile(info, io.BytesIO(data))
    return {**manifest, 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'compressed_bytes': output.stat().st_size, 'source_bytes': sum(len(v[0]) for v in files.values()),
            'entries': len(files), 'directory': 'project', 'artifact': 'dist/*.whl'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--foundation', type=Path, required=True)
    parser.add_argument('--foundation-revision', required=True)
    parser.add_argument('--launchpad', type=Path, default=Path('.'))
    parser.add_argument('--launchpad-revision', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--example', choices=['service-desk', 'hello-agent'], default='service-desk')
    args = parser.parse_args()
    print(json.dumps(package(args.foundation, args.foundation_revision, args.launchpad, args.launchpad_revision, args.output, args.example), indent=2))
