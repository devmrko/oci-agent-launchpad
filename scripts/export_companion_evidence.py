"""Export verified local travel release snapshots for Companion's scoped read-only view."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import zipfile

from package_travel_demo import BUNDLE, verify, sha
from requirement_handoff import read, write_new


def export(directory, scope, trace_url, output):
    directory = Path(directory)
    summary = read(directory/'summary.json')
    if summary.get('status') != 'LOCAL_RELEASE_PASS' or not summary.get('source_unchanged'):
        raise ValueError('Completed local rehearsal required')
    if set(scope) != {'profile','tenancy','user','demo','region','compartment'}:
        raise ValueError('Exact Companion scope required')
    # The consumer independently validates links. No URLs are fetched here.
    from urllib.parse import urlsplit
    uri = urlsplit(trace_url)
    if uri.scheme not in {'http','https'} or not uri.hostname or uri.username or uri.password or uri.query or uri.fragment:
        raise ValueError('Expected plain monitoring URL')
    entries=[]
    for release in ('a','b'):
        archive=directory/f'release-{release}.zip'
        verify(archive)
        digest=sha(archive.read_bytes())
        if digest != summary['releases'][release]['archive_sha256']:
            raise ValueError('Archive differs from recorded execution')
        with zipfile.ZipFile(archive) as z:
            evidence=json.loads(z.read('test-evidence.json'))
            if evidence['status'] != 'PASS' or evidence.get('tests_executed') is not True or evidence.get('stable_during_run') is not True:
                raise ValueError('Passing test evidence required')
            for name, expected in evidence['files'].items():
                if sha(z.read(name)) != expected:
                    raise ValueError('Test evidence does not match packaged files')
            spec=z.read(BUNDLE+'/spec.md').decode()
        active=summary['active_release']==release
        runtime=('복구 후 선택된 A. 기록된 2박 계산은 200000원입니다.' if active else
                 'B 실행 확인 후 고의 파일 손상 실습을 수행했습니다. 최종 선택 버전은 A입니다.')
        entries.append({'scope':scope,'name':f'출장비 CLI · 릴리스 {release.upper()}',
                        'exportedAt':datetime.now(timezone.utc).isoformat(), 'specText':spec,
                        'stages':[
                            {'title':'요구 명세','status':'패키지에 포함','detail':'가상 출장비 규정. 아래 원문은 이 ZIP에 포함된 명세입니다.','digest':evidence['files'][BUNDLE+'/spec.md'],'url':None},
                            {'title':'테스트 근거','status':'기록된 PASS','detail':f"{evidence['recorded_at']} · 연결 테스트 {len(evidence['tests'])}개. ZIP 파일 해시와 일치하며 화면에서 재실행하지 않습니다.",'digest':sha(json.dumps(evidence,sort_keys=True).encode()),'url':None},
                            {'title':'실행 패키지','status':'ZIP 해시 확인','detail':f'release-{release}.zip · 명세·코드·테스트·검증 기록 포함','digest':digest,'url':None},
                            {'title':'실행·배포','status':'로컬 실행 기록 · OCI 미배포','detail':runtime+' 현재 서비스 상태를 조회한 결과는 아닙니다.','digest':None,'url':'/deployments'},
                            {'title':'Langfuse 실행 추적','status':'이 릴리스와 미연결','detail':'이 로컬 CLI는 모델 호출과 trace 전송을 하지 않았습니다. 아래 링크는 모니터링 도구를 여는 용도입니다.','digest':None,'url':trace_url}
                        ]})
    result={'schemaVersion':1,'entries':entries}
    write_new(output,result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--scope-file',required=True,type=Path,help='JSON object with the exact Companion scope')
    parser.add_argument('--langfuse-url',required=True)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    try:
        result=export(args.directory,read(args.scope_file),args.langfuse_url,args.output)
    except (OSError,ValueError,KeyError,TypeError,zipfile.BadZipFile):
        parser.exit(1,'Check completed release, hashes, scope and a new output path.\n')
    print(json.dumps({'status':'EXPORTED','entries':len(result['entries']),'live_cloud_queries':False}))


if __name__=='__main__':
    main()
