"""Compare Hello Agent identity across files, test evidence, responses and observations."""
from pathlib import Path
from build_hello_identity import identity_from_evidence, contract, APP_SPEC


def correlate(record, trace, identity=None, evidence=None, root=None):
    def result(code,status,detail):
        return {'code':code,'status':status,'detail':detail,'identity':None,'spec':None}
    if identity is None and evidence is None and root is None:
        return result('NOT_PROVIDED','릴리스 근거 미제공',
                      '배포·trace 기록과 별개로 명세·소스·검증 원본을 아직 대조하지 않았습니다.')
    if identity is None or evidence is None or root is None:
        return result('INCOMPLETE','대조 자료 누락','릴리스 JSON·명령 근거·소스 루트를 함께 제공해야 합니다.')
    try:
        contract.validate(identity)
    except (ValueError,TypeError,KeyError):
        return result('INVALID','릴리스 자료 오류','릴리스 JSON의 형식 또는 내용 해시가 올바르지 않습니다.')
    try:
        expected=identity_from_evidence(root,evidence)
    except (OSError,ValueError,TypeError,KeyError):
        return result('STALE','재검증 필요','검증한 파일이 바뀌었거나 현재 성공한 명령 근거를 확인할 수 없습니다.')
    if expected != identity or record['health'].get('version') != identity['app_version']:
        return result('MISMATCH','릴리스 불일치','릴리스 JSON과 현재 명세·소스·검증 기록 또는 앱 버전이 다릅니다.')
    wanted={k:identity[k] for k in contract.SUMMARY}
    values=[record['health'].get('release'),record['chat'].get('release')]
    values += [row.get('release') for row in trace['observations']]
    if any(row.get('release_invalid') for row in trace['observations']):
        return result('INVALID','릴리스 자료 오류','관측에 잘못된 형식의 릴리스 해시가 있습니다.')
    if any(not isinstance(value,dict) or not set(wanted)<=value.keys() for value in values):
        return result('MISSING','실행 식별 정보 누락','health·채팅·관측 중 릴리스 ID 또는 해시가 없는 기록이 있습니다.')
    if any(value != wanted for value in values):
        return result('MISMATCH','릴리스 불일치','health·채팅·관측이 같은 릴리스 ID와 해시를 가리키지 않습니다.')
    try:
        spec=(Path(root)/APP_SPEC).read_bytes()
        import hashlib
        if hashlib.sha256(spec).hexdigest()!=identity['spec_sha256']:
            return result('STALE','재검증 필요','명세를 읽는 동안 내용이 변경되었습니다.')
        text=spec.decode('utf-8')
    except (OSError,UnicodeError):
        return result('STALE','재검증 필요','해시로 확인한 명세 원문을 읽을 수 없습니다.')
    return {'code':'MATCHED','status':'명세·소스·검증 일치',
            'detail':'현재 파일과 명령 근거를 재검사했고 health·채팅·모든 관측의 릴리스 ID와 해시가 일치합니다. 이미지 내용 검증·전자서명·실시간 서비스 정상 판정은 아닙니다.',
            'identity':wanted,'spec':text}


def attach(entry, record, trace, identity=None, evidence=None, root=None):
    checked=correlate(record,trace,identity,evidence,root)
    entry['stages'][0]={'title':'릴리스 근거 대조','status':checked['status'],'detail':checked['detail'],
                        'digest':checked['identity']['release_id'] if checked['identity'] else None,'url':None}
    entry['specText']=checked['spec'] if checked['spec'] is not None else checked['detail']
    if checked['identity']:
        for title,key in [('업무 명세','spec_sha256'),('실행 소스 묶음','source_sha256'),('명령 검증 원본','test_evidence_sha256')]:
            entry['stages'].append({'title':title,'status':'릴리스와 일치','detail':'동일 릴리스의 원본 해시입니다. 명령 성공은 요구사항의 자동 승인이 아닙니다.',
                                    'digest':checked['identity'][key],'url':None})
    return entry
