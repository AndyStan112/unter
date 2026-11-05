from datetime import datetime, timezone
import pytest
from unter import report
from unter.report import Explanation, Reason

NOW = datetime(2026, 11, 4, 10, 20, tzinfo=timezone.utc)


def zone(name, **values):
    base = {'zone': name, 'requests': 40, 'requests_per_hour': 10.0, 'demand_supply_ratio': 0.5,
            'unmatched_rate': 0.0, 'cancel_rate': 0.0, 'avg_wait_s': 30.0, 'worst_p90_wait_s': 60.0, 'net_flow': 5,
            'offer_reject_rate': 0.05, 'offer_expiry_rate': 0.05, 'peak_bucket': None,
            'supply_now': {'available': 2, 'offered': 0, 'on_trip': 0, 'stale': 0, 'waiting_trips': 0},
            'active_surge': None, 'active_incentive': None}
    return base | values


BUSY = zone('Iosefin', demand_supply_ratio=4.5, unmatched_rate=0.15, worst_p90_wait_s=270.0, cancel_rate=0.15,
            net_flow=-30, offer_reject_rate=0.2, offer_expiry_rate=0.1)
SNAPSHOT = {'from': '2026-11-03T10:20:00Z', 'to': '2026-11-04T10:20:00Z', 'hours': 24.0,
            'zones': [zone('Centru'), zone('Fabric', requests=5), BUSY]}
GOOD = Explanation(summary='Iosefin is short of drivers.', reasons=[
    Reason(id='Iosefin:surge', reason='Riders wait long and many trips go unmatched.'),
    Reason(id='Iosefin:incentive', reason='Drivers leave Iosefin and rarely come back.')])


@pytest.fixture
def mcp(monkeypatch):
    windows = []
    async def snapshot(start, end):
        windows.append((start, end))
        return SNAPSHOT
    monkeypatch.setattr(report, 'read_snapshot', snapshot)
    return windows


@pytest.fixture
def model(monkeypatch):
    """The model's answer for the next build(); records every call."""
    calls, answer = [], {'value': GOOD}
    async def explain(plan, name):
        calls.append(plan)
        if isinstance(answer['value'], Exception):
            raise answer['value']
        return answer['value']
    monkeypatch.setattr(report, 'explain', explain)
    return calls, answer


def numbers(built):
    return {p['id']: p['params'] for p in built['proposals']}


async def test_fake_mode_uses_templates_and_no_model(mcp, model):
    built, tools = await report.build('fake', 'gpt-test', NOW)
    assert tools == ['zone_snapshot'] and model[0] == []
    assert mcp == [(datetime(2026, 11, 3, 10, 20, tzinfo=timezone.utc), NOW)]
    assert built['explained_by'] == 'template' and built['model'] is None and 'fake' in built['note']
    assert numbers(built) == {
        'Iosefin:surge': {'multiplier': 1.45, 'starts_at': '2026-11-04T11:00:00Z', 'ends_at': '2026-11-04T13:00:00Z'},
        'Iosefin:incentive': {'bonus_per_trip': 9.5, 'starts_at': '2026-11-04T11:00:00Z', 'ends_at': '2026-11-04T13:00:00Z'}}
    surge, incentive = built['proposals']
    assert 'x1.45' in surge['reason'] and '15%' in surge['reason'] and '270 s' in surge['reason']
    assert '9.5 RON' in incentive['reason'] and 'drain, low supply' in incentive['reason']
    assert '2 proposal(s) for Iosefin' in built['summary'] and 'Fabric (only 5 requests' in built['summary']
    assert built['window'] == {'from': SNAPSHOT['from'], 'to': SNAPSHOT['to'], 'hours': 24.0}
    assert [z['zone'] for z in built['zones']] == ['Centru', 'Fabric', 'Iosefin']


async def test_live_mode_uses_model_text_but_keeps_rule_numbers(mcp, model):
    built, _ = await report.build('live', 'gpt-test', NOW)
    plan, = model[0]
    assert [p['id'] for p in plan['proposals']] == ['Iosefin:surge', 'Iosefin:incentive']
    assert built['explained_by'] == 'model' and built['model'] == 'gpt-test' and built['note'] is None
    assert built['summary'] == GOOD.summary
    assert [p['reason'] for p in built['proposals']] == [r.reason for r in GOOD.reasons]
    assert numbers(built)['Iosefin:surge']['multiplier'] == 1.45


@pytest.mark.parametrize('answer, note', [
    (Explanation(summary='ok', reasons=GOOD.reasons[:1]), 'returned ids'),
    (Explanation(summary='ok', reasons=GOOD.reasons + [Reason(id='Centru:surge', reason='Invented.')]), 'returned ids'),
    (Explanation(summary='ok', reasons=GOOD.reasons[:1] * 2), 'returned ids'),
    (Explanation(summary='ok', reasons=[GOOD.reasons[0], Reason(id='Iosefin:incentive', reason='x' * 1001)]), 'reason must be'),
    (Explanation(summary='ok', reasons=[GOOD.reasons[0], Reason(id='Iosefin:incentive', reason='  ')]), 'reason must be'),
    (Explanation(summary=' ', reasons=GOOD.reasons), 'summary'),
    (report.ExplanationRejected('the model returned no structured explanation'), 'no structured'),
])
async def test_unusable_model_text_falls_back_to_templates(mcp, model, answer, note):
    model[1]['value'] = answer
    built, _ = await report.build('live', 'gpt-test', NOW)
    assert built['explained_by'] == 'template' and built['model'] is None and note in built['note']
    assert numbers(built)['Iosefin:incentive']['bonus_per_trip'] == 9.5
    assert all('RON' in p['reason'] or 'Surge' in p['reason'] for p in built['proposals'])


async def test_provider_errors_are_recorded_by_class_only(mcp, model):
    class APIError(Exception):
        pass
    model[1]['value'] = APIError('Bearer sk-secret in request headers')
    built, _ = await report.build('live', 'gpt-test', NOW)
    assert built['note'] == 'model text not used: APIError' and 'secret' not in str(built)


async def test_no_proposals_means_no_model_call(monkeypatch, model):
    async def quiet(start, end):
        return SNAPSHOT | {'zones': [zone('Centru'), zone('Fabric')]}
    monkeypatch.setattr(report, 'read_snapshot', quiet)
    built, _ = await report.build('live', 'gpt-test', NOW, window_hours=6)
    assert model[0] == [] and built['proposals'] == [] and built['note'].startswith('nothing to explain')
    assert built['summary'] == 'No zone needs a surge or a driver incentive for this window.'


def test_model_sees_candidates_but_not_raw_snapshot():
    plan = report.rules.propose(SNAPSHOT, NOW)
    text = report.model_input(plan)
    assert 'Iosefin:surge' in text and '"pressure": 1.45' in text and '"Centru"' not in text


async def test_explain_makes_one_structured_call_without_tools(monkeypatch):
    """The real Agno path against a fake OpenAI endpoint: one request, JSON schema output, no tools."""
    import json
    import httpx
    sent = []
    def openai(request):
        sent.append(json.loads(request.content))
        content = GOOD.model_dump_json()
        return httpx.Response(200, json={'id': 'c', 'object': 'chat.completion', 'created': 0, 'model': 'gpt-test',
                                         'choices': [{'index': 0, 'finish_reason': 'stop',
                                                      'message': {'role': 'assistant', 'content': content}}],
                                         'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}})
    real = report.CappedModel
    monkeypatch.setattr(report, 'CappedModel', lambda **kw: real(
        **kw, api_key='test', http_client=httpx.AsyncClient(transport=httpx.MockTransport(openai))))
    plan = report.rules.propose(SNAPSHOT, NOW)
    assert await report.explain(plan, 'gpt-test') == GOOD
    request, = sent
    assert request['model'] == 'gpt-test' and request['response_format']['type'] == 'json_schema'
    assert 'tools' not in request and 'Iosefin:surge' in request['messages'][-1]['content']
