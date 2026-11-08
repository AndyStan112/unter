import os
os.environ.setdefault('SERVICE_USERNAME', 'test-service')
os.environ.setdefault('SERVICE_PASSWORD', 'test-password')
os.environ.setdefault('ADMIN_USERNAME', 'test-admin')
os.environ.setdefault('ADMIN_PASSWORD', 'test-admin-password')
import json
import httpx
import pytest
from starlette.testclient import TestClient
from unter import gateway
from unter.auth import basic_header

REPORT = '1b4e28ba-2fa1-11d2-883f-0016d3cca427'
PROPOSAL = {'id': 'Iosefin:surge', 'zone': 'Iosefin', 'type': 'surge', 'reason': 'Long waits.', 'rule': 'pressure 1.45',
            'metrics': {'pressure': 1.45},
            'params': {'multiplier': 1.45, 'starts_at': '2026-11-04T11:00:00Z', 'ends_at': '2026-11-04T13:00:00Z'}}
ADMIN = {'Authorization': basic_header('ADMIN'), 'X-Unter-Request': '1'}


@pytest.fixture
def backends(monkeypatch):
    """Fake agent and core. answers[(method, path)] = (status, json) overrides a reply; calls records every request."""
    calls, answers = [], {}
    def reply(request):
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.host, request.url.path, body, dict(request.url.params)))
        assert request.headers['authorization'] == basic_header(), 'backends are called with the service login'
        key = (request.method, request.url.path)
        if key in answers:
            status, answer = answers[key]
            return httpx.Response(status, json=answer)
        if key == ('POST', '/decisions') and request.url.host == 'agent':
            return httpx.Response(200, json={'status': 'applying' if body['decision'] == 'approved' else 'rejected',
                                             'proposal': PROPOSAL})
        if key == ('POST', '/proposals'):
            return httpx.Response(200, json={'id': 'c0ffee00-0000-4000-8000-000000000001', 'status': 'pending'})
        if request.method == 'PATCH' and request.url.path.startswith('/proposals/'):
            return httpx.Response(200, json={'status': 'approved'})
        return httpx.Response(200, json={})
    real = httpx.AsyncClient
    monkeypatch.setattr(gateway.httpx, 'AsyncClient', lambda **kw: real(transport=httpx.MockTransport(reply), **kw))
    return calls, answers


def decide(body, report=REPORT, headers=ADMIN):
    with TestClient(gateway.app) as client:
        return client.post(f'/api/reports/{report}/decisions', json=body, headers=headers)


def steps(calls):
    return [(method, host, path) for method, host, path, _, _ in calls]


def test_approval_uses_the_stored_numbers_and_records_the_core_id(backends):
    calls, _ = backends
    response = decide({'proposal_id': 'Iosefin:surge', 'decision': 'approved', 'params': {'multiplier': 3}})
    assert response.status_code == 200 and response.json()['status'] == 'applied'
    assert steps(calls) == [('POST', 'agent', '/decisions'), ('POST', 'core', '/proposals'),
                            ('PATCH', 'core', '/proposals/c0ffee00-0000-4000-8000-000000000001'), ('PUT', 'agent', '/decisions')]
    created = calls[1][3]
    assert created['params'] == PROPOSAL['params'] and created['zone'] == 'Iosefin' and created['type'] == 'surge'
    assert created['reason'] == 'Long waits. (Unter report 1b4e28ba, Iosefin:surge)' and 'metrics' not in created
    assert calls[2][3] == {'status': 'approved'}
    assert calls[3][3] == {'report_id': REPORT, 'proposal_id': 'Iosefin:surge', 'status': 'applied',
                           'core_proposal_id': 'c0ffee00-0000-4000-8000-000000000001'}


def test_rejection_never_calls_core(backends):
    calls, _ = backends
    response = decide({'proposal_id': 'Iosefin:surge', 'decision': 'rejected'})
    assert response.status_code == 200 and response.json() == {'status': 'rejected'}
    assert steps(calls) == [('POST', 'agent', '/decisions')]


def test_already_decided_or_expired_stops_before_core(backends):
    calls, answers = backends
    answers[('POST', '/decisions')] = (409, {'detail': 'This proposal has already been decided'})
    response = decide({'proposal_id': 'Iosefin:surge', 'decision': 'approved'})
    assert response.status_code == 409 and response.json()['detail'] == 'This proposal has already been decided'
    assert steps(calls) == [('POST', 'agent', '/decisions')]


def test_core_refusal_releases_the_claim(backends):
    calls, answers = backends
    answers[('POST', '/proposals')] = (400, {'error': 'invalid_request', 'message': 'ends_at must be in the future'})
    response = decide({'proposal_id': 'Iosefin:surge', 'decision': 'approved'})
    assert response.status_code == 400 and response.json()['detail'] == 'Core refused the proposal: ends_at must be in the future'
    assert steps(calls)[-1] == ('DELETE', 'agent', '/decisions')
    assert calls[-1][4] == {'report_id': REPORT, 'proposal_id': 'Iosefin:surge'}


def test_failed_approval_is_recorded_as_created(backends):
    calls, answers = backends
    answers[('PATCH', '/proposals/c0ffee00-0000-4000-8000-000000000001')] = (500, {})
    response = decide({'proposal_id': 'Iosefin:surge', 'decision': 'approved'})
    assert response.status_code == 502 and 'Approve it under Proposals' in response.json()['detail']
    assert calls[-1][3]['status'] == 'created'


def test_long_reasons_fit_core_limit():
    reason = gateway.core_reason(PROPOSAL | {'reason': 'x' * 1000}, REPORT)
    assert len(reason) == 1000 and reason.endswith('(Unter report 1b4e28ba, Iosefin:surge)')


@pytest.mark.parametrize('body, report, headers, status', [
    ({'proposal_id': 'Iosefin:surge', 'decision': 'approved'}, REPORT, {'Authorization': basic_header('ADMIN')}, 403),
    ({'proposal_id': 'Iosefin:surge', 'decision': 'approved'}, REPORT, {'X-Unter-Request': '1'}, 401),
    ({'proposal_id': 'Iosefin:surge', 'decision': 'approved'}, REPORT, {'Authorization': basic_header(), 'X-Unter-Request': '1'}, 401),
    ({'proposal_id': 'Iosefin:surge', 'decision': 'maybe'}, REPORT, ADMIN, 422),
    ({'decision': 'approved'}, REPORT, ADMIN, 422),
    ({'proposal_id': 'Iosefin:surge', 'decision': 'approved'}, 'not-a-uuid', ADMIN, 404),
])
def test_bad_requests_reach_no_backend(backends, body, report, headers, status):
    assert decide(body, report, headers).status_code == status
    assert backends[0] == []


def test_decision_endpoints_of_the_agent_are_not_forwarded_from_the_browser(backends):
    with TestClient(gateway.app) as client:
        for method in ('POST', 'PUT', 'DELETE'):
            client.request(method, '/api/decisions', headers=ADMIN, json={})
    # Unknown paths go to core (which has no /decisions); the agent's decision endpoints are never reached.
    assert all(host != 'agent' for _, host, _, _, _ in backends[0])
