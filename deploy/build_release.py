"""Build and test a release from pinned repositories on Linux x86_64/Python 3.12."""

import argparse
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path

from package_release import package
from package_sources import package_sources


def run(*args, **kwargs):
    subprocess.run([str(a) for a in args], check=True, **kwargs)


def pinned_requirements(path):
    lines = path.read_text().splitlines()
    if not lines or any(not re.fullmatch(r'[A-Za-z0-9_.-]+==[A-Za-z0-9_.+!-]+', line) for line in lines):
        raise ValueError('Runtime lock must contain exact package pins only')
    return lines


def build(foundation, foundation_revision, launchpad, launchpad_revision, output, build_id, source_archive=None, source_sha256=None):
    if sys.version_info[:2] != (3, 12) or platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise ValueError('Build requires Linux x86_64 and Python 3.12')
    if output.exists():
        raise ValueError('Output already exists; choose a new build directory')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='launchpad-build-', dir=output.parent) as temporary:
        root = Path(temporary)
        if source_archive is None:
            provenance = package_sources(foundation, foundation_revision, launchpad, launchpad_revision, root / 'sources.tgz')
        else:
            shutil.copyfile(source_archive, root / 'sources.tgz')
            digest = hashlib.sha256((root / 'sources.tgz').read_bytes()).hexdigest()
            if not source_sha256 or digest != source_sha256:
                raise ValueError('Source archive checksum mismatch')
            provenance = {'source_sha256': digest}
        source = root / 'source'
        with tarfile.open(root / 'sources.tgz') as archive:
            for member in archive.getmembers():
                if not (member.isfile() or member.isdir()):
                    raise ValueError('Source archive contains unsupported entry')
            archive.extractall(source, filter='data')
        source_info = json.loads((source / 'source.json').read_text())
        if source_info.get('schema_version') != 1 or any(
            not re.fullmatch('[a-f0-9]{40}', source_info.get(key, ''))
            for key in ('foundation_commit', 'launchpad_commit')
        ):
            raise ValueError('Invalid source provenance')
        provenance.update({key: source_info[key] for key in ('foundation_commit', 'launchpad_commit')})
        app = source / 'launchpad/examples/service-desk'
        library = source / 'foundation'
        app_info = tomllib.loads((app / 'pyproject.toml').read_text())['project']
        library_info = tomllib.loads((library / 'pyproject.toml').read_text())['project']
        foundation_pin = library_info['name'] + '==' + library_info['version']
        if foundation_pin not in app_info['dependencies']:
            raise ValueError('Foundation source version does not match the app dependency')
        pins = pinned_requirements(app / 'requirements-memory.lock')
        wheels = root / 'wheels'
        wheels.mkdir()
        build_env = root / 'build-env'
        run(sys.executable, '-m', 'venv', build_env)
        bp = build_env / 'bin/python'
        run(bp, '-m', 'pip', 'install', 'pip==25.3', 'setuptools==80.9.0', 'wheel==0.45.1', 'hatchling==1.27.0')
        run(bp, '-m', 'pip', 'wheel', '--no-deps', '--no-build-isolation', '--wheel-dir', wheels, library, app)
        run(bp, '-m', 'pip', 'download', '--only-binary=:all:', '--no-deps', '--dest', wheels,
            '-r', app / 'requirements-memory.lock')
        requirements = root / 'requirements.txt'
        requirements.write_text('\n'.join(pins + [foundation_pin, app_info['name'] + '==' + app_info['version']]) + '\n')
        runtime = root / 'runtime'
        run(sys.executable, '-m', 'venv', runtime)
        rp = runtime / 'bin/python'
        run(rp, '-m', 'pip', 'install', '--no-index', '--find-links', wheels, '-r', requirements)
        run(rp, '-m', 'pip', 'check')
        run(rp, '-c', 'import service_desk.app; import python_foundation; import oracleagentmemory')
        # Test dependencies stay outside the runtime wheelhouse and release ZIP.
        run(bp, '-m', 'pip', 'install', '--no-index', '--find-links', wheels, '-r', requirements)
        run(bp, '-m', 'pip', 'install', 'pytest==9.2.0')
        run(bp, '-m', 'pytest', str(app / 'tests'), '-q', cwd=app)
        result = root / 'result'
        result.mkdir()
        hashes = package(wheels, requirements, result / 'release.zip')
        metadata = {
            'schema_version': 1, 'build_id': build_id, **provenance, **hashes,
            'app_version': app_info['version'], 'foundation_version': library_info['version'],
            'target': {'os': 'linux', 'architecture': 'x86_64', 'python': '3.12'},
            'verification': {'dependency_check': 'passed', 'imports': 'passed', 'example_tests': 'passed'},
        }
        (result / 'release.json').write_text(json.dumps(metadata, indent=2, sort_keys=True) + '\n')
        # Publish only a completely verified result. Never overwrite a prior output.
        if output.exists():
            raise ValueError('Output created concurrently; refusing to overwrite')
        result.rename(output)
        return metadata


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--foundation', type=Path)
    p.add_argument('--foundation-revision')
    p.add_argument('--launchpad', type=Path, default=Path('.'))
    p.add_argument('--launchpad-revision')
    p.add_argument('--source-archive', type=Path)
    p.add_argument('--source-sha256')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--build-id', required=True)
    a = p.parse_args()
    if a.source_archive:
        if not a.source_sha256 or a.foundation or a.foundation_revision or a.launchpad_revision:
            p.error('Source archive requires checksum and cannot be combined with repository revisions')
    elif not all((a.foundation, a.foundation_revision, a.launchpad_revision)):
        p.error('Both repositories and revisions are required')
    print(json.dumps(build(a.foundation.resolve() if a.foundation else None, a.foundation_revision,
                           a.launchpad.resolve(), a.launchpad_revision, a.output.resolve(), a.build_id,
                           a.source_archive, a.source_sha256)))


if __name__ == '__main__':
    main()
