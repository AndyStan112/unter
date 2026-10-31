import os
os.environ.setdefault('SERVICE_USERNAME', 'test-service')
os.environ.setdefault('SERVICE_PASSWORD', 'test-password')
os.environ.setdefault('ADMIN_USERNAME', 'test-admin')
os.environ.setdefault('ADMIN_PASSWORD', 'test-admin-password')
from datetime import datetime, timezone
import pytest
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from unter.auth import BasicAuth, basic_header
from unter.agent import Schedule, next_time


def client():
    async def reply(request): return JSONResponse({'ok': True})
    app=Starlette(routes=[Route('/data', reply, methods=['GET','POST']),Route('/healthz',reply)])
    app.add_middleware(BasicAuth, kind='ADMIN', csrf=True)
    return TestClient(app)


def test_private_data_requires_auth_and_health_is_public():
    with client() as c:
        assert c.get('/data').status_code == 401
        assert c.get('/healthz').status_code == 200
        assert c.get('/data',headers={'Authorization':basic_header()}).status_code == 401
        assert c.get('/data',headers={'Authorization':basic_header('ADMIN')}).status_code == 200


def test_mutation_requires_csrf_header_even_with_browser_auth():
    with client() as c:
        headers={'Authorization':basic_header('ADMIN')}
        assert c.post('/data',headers=headers).status_code == 403
        headers['X-Unter-Request']='1'
        response=c.post('/data',headers=headers)
        assert response.status_code == 200
        assert 'no-store' in response.headers['cache-control']


@pytest.mark.parametrize('cron,zone',[('* * * * * *','UTC'),('bad','UTC'),('0 * * * *','Bad/Zone'),('99 * * * *','UTC')])
def test_invalid_schedule(cron,zone):
    with pytest.raises(ValidationError): Schedule(cron=cron,timezone=zone)


def test_timezone_and_next_slot():
    now=datetime(2026,10,31,8,15,tzinfo=timezone.utc)
    assert next_time('0 12 * * *','Europe/Bucharest',now)==datetime(2026,10,31,10,0,tzinfo=timezone.utc)
    assert not Schedule().enabled
