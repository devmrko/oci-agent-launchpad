"""Service-desk adapter for the independent monitoring HTTP v1 contract."""
import os
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from python_foundation.security import current_actor
from python_foundation.database import SqlAlchemyUnitOfWork
from sqlalchemy import select, func, or_

from .models import Record
from . import __version__


def agent_id():
    value = os.environ.get('DESK_AGENT_ID', 'service-desk')
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', value):
        raise ValueError('Invalid DESK_AGENT_ID')
    return value


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def annotate(data):
    data['timestamp'] = now()
    data['agent_id'] = agent_id()
    data.setdefault('operation', 'chat')
    data['level'] = ('INFO' if data.get('status') == 'ok' else
                     'WARN' if data.get('error_code') in {'ACCESS_DENIED', 'VALIDATION_ERROR', 'INVALID_PLAN'} else 'ERROR')
    return data


def public(row):
    data = row.data
    result = {key: data.get(key) for key in ('timestamp', 'request_id', 'session_id', 'operation', 'status',
              'level', 'app_version', 'mode', 'elapsed_ms', 'error_code')}
    result.update(id=row.id, agent_id=data.get('agent_id', agent_id()))
    result['model'] = {k: data.get('model', {}).get(k) for k in
                       ('provider', 'model', 'region', 'elapsed_ms', 'input_tokens', 'output_tokens', 'finish_reason')}
    result['tools'] = [{k: event.get(k) for k in ('tool', 'stage', 'status', 'elapsed_ms', 'error_code')}
                       for event in data.get('tools', [])]
    result['steps'] = [x for x in data.get('steps', []) if isinstance(x, str)]
    result['memory'] = {k: data.get('memory', {}).get(k) for k in ('backend', 'count')}
    return result


def install(app, service):
    identifier = agent_id()
    router = APIRouter(prefix='/api/monitoring/v1', dependencies=[Depends(current_actor)])

    def check(identifier_in):
        if identifier_in != identifier:
            raise HTTPException(404, 'Agent not found')

    @router.get('/agents')
    def agents():
        return {'schema_version': 1, 'items': [{'id': identifier,
                'name': os.environ.get('DESK_AGENT_NAME', 'Service Desk'), 'version': __version__,
                'environment': os.environ.get('DESK_ENVIRONMENT', 'demo')}]}

    @router.get('/agents/{agent}/executions')
    def executions(agent: str, actor=Depends(current_actor), page: int = Query(1, ge=1, le=1000000),
                   page_size: int = Query(20, ge=1, le=100), status: str = Query('', max_length=30),
                   level: str = Query('', max_length=10), session_id: str = Query('', max_length=100),
                   request_id: str = Query('', max_length=100), since: str = '', until: str = '', snapshot: str = ''):
        check(agent)
        def date(value):
            try:
                dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    raise ValueError()
                return dt.astimezone(timezone.utc).isoformat(timespec='microseconds')
            except ValueError:
                raise HTTPException(422, 'Timezone-aware ISO date required')
        bound = date(snapshot) if snapshot else now()
        stamp = Record.data['timestamp'].as_string()
        conditions = [Record.owner == service.owner(actor), Record.kind == 'trace',
                      or_(Record.data['agent_id'].as_string() == identifier, Record.data['agent_id'].as_string().is_(None)),
                      or_(stamp <= bound, stamp.is_(None))]
        for key, value in [('status', status), ('level', level), ('session_id', session_id), ('request_id', request_id)]:
            if value:
                conditions.append(Record.data[key].as_string() == value)
        if since:
            conditions.append(stamp >= date(since))
        if until:
            conditions.append(stamp <= date(until))
        with SqlAlchemyUnitOfWork(service.factory) as u:
            total = u.session.scalar(select(func.count()).select_from(Record).where(*conditions))
            rows = u.session.scalars(select(Record).where(*conditions).order_by(stamp.desc().nullslast(), Record.id.desc())
                                     .offset((page-1)*page_size).limit(page_size))
            return {'schema_version': 1, 'items': [public(row) for row in rows], 'page': page,
                    'page_size': page_size, 'total': total, 'pages': (total+page_size-1)//page_size, 'snapshot': bound}

    @router.get('/agents/{agent}/executions/{execution}')
    def detail(agent: str, execution: str, actor=Depends(current_actor)):
        check(agent)
        with SqlAlchemyUnitOfWork(service.factory) as u:
            row = u.session.scalar(select(Record).where(Record.id == execution, Record.owner == service.owner(actor),
                                                        Record.kind == 'trace'))
            if row is None or row.data.get('agent_id', identifier) != identifier:
                raise HTTPException(404, 'Execution not found')
            return {'schema_version': 1, 'item': public(row)}
    app.include_router(router)
