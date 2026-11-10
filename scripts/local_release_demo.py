"""Rehearse verified travel ZIP execution and local CLI rollback; no cloud deployment."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

from package_travel_demo import APP, BUNDLE, FILES, build, sha, verify
from requirement_handoff import read, write_new
from spec_evidence import execute


def runtime_matches(directory):
    manifest = read(directory / 'PACKAGE.json')
    return all((directory/name).is_file() and not (directory/name).is_symlink()
               and sha((directory/name).read_bytes()) == expected
               for name, expected in manifest['files'].items())


def smoke(directory, *arguments):
    result = subprocess.run([sys.executable, '-S', str(directory/APP/'cli.py'), *arguments],
                            cwd=directory, capture_output=True, text=True, timeout=10)
    return {'exit_code': result.returncode, 'stdout': result.stdout.strip()}


def active_smoke(output):
    release = read(output/"current.json")["release"]
    if release not in {"a", "b"}:
        raise ValueError("Unknown active release")
    return smoke(output/("runtime-"+release), "2")


def calculation_ok(result):
    try:
        value = json.loads(result['stdout'])
        return result['exit_code'] == 0 and value['amount'] == 200000 and value['model_used'] is False
    except (ValueError, KeyError, TypeError):
        return False


def unpack(archive, destination):
    verify(archive)
    destination.mkdir()
    with zipfile.ZipFile(archive) as contents:
        contents.extractall(destination)
    if not runtime_matches(destination):
        raise ValueError('Extracted files differ from package')


def demo(root, output):
    root, output = Path(root).resolve(), Path(output)
    output.mkdir(mode=0o700)  # Refuse an existing directory before touching any files.
    output = output.resolve()
    source = output/'source'
    source.mkdir()
    for name in FILES:
        target = source/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root/name, target)
    original = {name: sha((root/name).read_bytes()) for name in FILES}
    evidence_a = execute(source, BUNDLE, output/'evidence-a.json')
    archive_a = output/'release-a.zip'
    package_a = build(source, evidence_a, archive_a)
    runtime_a = output/'runtime-a'
    unpack(archive_a, runtime_a)
    a_smoke = smoke(runtime_a, '2')
    if not calculation_ok(a_smoke):
        raise ValueError('Initial release did not start correctly')
    write_new(output/'current.json', {'release': 'a'})

    # Make a small, testable requirement change only in the copied project.
    with (source/BUNDLE/'spec.md').open('a') as f:
        f.write('\nREQ-006 추가 조건: CLI --version은 숙박 일수 없이 travel-demo-b를 출력하고 0으로 종료합니다.\n')
    with (source/BUNDLE/'design.md').open('a') as f:
        f.write('\n로컬 릴리스 실습: argparse version action으로 --version을 추가하고 기존 계산을 유지합니다.\n')
    with (source/BUNDLE/'tasks.md').open('a') as f:
        f.write('\n로컬 합성 변경: --version 실패 테스트, 구현, 재검증, 패키징·복구 실습.\n')
    with (source/APP/'test_cli.py').open('a') as f:
        f.write('\n    def test_release_version(self):\n        result = self.invoke("--version")\n        self.assertEqual(result.returncode, 0)\n        self.assertEqual(result.stdout.strip(), "travel-demo-b")\n')
    mapping_path = source/BUNDLE/'traceability.json'
    mapping = read(mapping_path)
    next(r for r in mapping['requirements'] if r['id'] == 'REQ-006')['tests'].append(
        {'path': f'{APP}/test_cli.py', 'case': 'CliTests.test_release_version'})
    mapping_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2)+'\n')
    red = execute(source, BUNDLE, output/'evidence-b-red.json')
    if red['status'] != 'NOT_PASSED':
        raise ValueError('New acceptance test must fail before implementation')
    cli = source/APP/'cli.py'
    text = cli.read_text()
    marker = '    args = parser.parse_args(argv)'
    if text.count(marker) != 1:
        raise ValueError('Unsupported CLI source revision')
    cli.write_text(text.replace(marker, '    parser.add_argument("--version", action="version", version="travel-demo-b")\n'+marker))
    evidence_b = execute(source, BUNDLE, output/'evidence-b.json')
    archive_b = output/'release-b.zip'
    package_b = build(source, evidence_b, archive_b)
    runtime_b = output/'runtime-b'
    unpack(archive_b, runtime_b)
    b_smoke, version = smoke(runtime_b, '2'), smoke(runtime_b, '--version')
    if not calculation_ok(b_smoke) or version != {'exit_code': 0, 'stdout': 'travel-demo-b'}:
        raise ValueError('Candidate did not pass runtime checks')
    (output/'current.json').write_text(json.dumps({'release':'b'})+'\n')

    # Deliberate local fault after installing a correctly verified package.
    (runtime_b/APP/'cli.py').write_text('raise SystemExit(9)\n')
    damaged_matches = runtime_matches(runtime_b)
    failure = active_smoke(output)
    if damaged_matches or failure['exit_code'] != 9:
        raise ValueError('Injected fault not observed')
    if sha(archive_a.read_bytes()) != package_a['archive_sha256'] or not runtime_matches(runtime_a):
        raise ValueError('Previous release cannot be trusted for rollback')
    recovered = smoke(runtime_a, '2')
    if not calculation_ok(recovered):
        raise ValueError('Previous release failed recovery check')
    (output/'current.json').write_text(json.dumps({'release':'a'})+'\n')
    recovered = active_smoke(output)
    if not calculation_ok(recovered):
        raise ValueError('Selected rollback release failed')
    unchanged = original == {name: sha((root/name).read_bytes()) for name in FILES}
    result = {'status':'LOCAL_RELEASE_PASS' if unchanged else 'SOURCE_CHANGED',
              'synthetic_fault':True, 'deployment_performed':False, 'source_unchanged':unchanged,
              'releases':{'a':{**package_a, 'evidence':'evidence-a.json', 'smoke':a_smoke},
                          'b':{**package_b, 'evidence':'evidence-b.json', 'smoke':b_smoke, 'version':version}},
              'new_acceptance_before_implementation':red['status'],
              'fault':{'runtime_files_match':damaged_matches, 'smoke':failure},
              'rollback':{'release':'a', 'files_match':runtime_matches(runtime_a), 'smoke':recovered},
              'active_release':read(output/'current.json')['release']}
    write_new(output/'summary.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = demo(Path(__file__).resolve().parents[1], args.output)
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        parser.exit(1, 'Local release rehearsal failed; inspect new output and recorded evidence.\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'LOCAL_RELEASE_PASS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
