import asyncio
import json
import os
os.environ.setdefault('READER_USERNAME', 'test-reader')
os.environ.setdefault('READER_PASSWORD', 'test-reader-password')
from datetime import datetime, timedelta, timezone
import httpx
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from unter import mcp_server
from unter.analytics import stats

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
ZONES = [{'name': 'Centru', 'lat': 45.7537, 'lon': 21.2257}, {'name': 'Fabric', 'lat': 45.758, 'lon': 21.24},
         {'name': 'Iosefin', 'lat': 45.748, 'lon': 21.208}]


def bucket(zone, hour, **values):
    row = {'zone': zone, 'bucket': f'2026-11-04T{hour:02d}:00:00Z', 'requests': 0, 'assigned': 0, 'completed': 0,
           'cancelled': 0, 'unmatched': 0, 'open': 0, 'unmatched_rate': None, 'cancel_rate': None,
           'avg_wait_s': None, 'p90_wait_s': None, 'avg_price': None, 'arrivals': 0, 'offers': 0,
           'offers_accepted': 0, 'offers_rejected': 0, 'offers_expired': 0, 'drivers_offered': 0,
           'offer_reject_rate': None, 'offer_expiry_rate': None}
    return row | values


ROWS = [
    bucket('Iosefin', 8, requests=10, assigned=8, completed=6, unmatched=2, cancelled=1, open=1, unmatched_rate=0.2,
           cancel_rate=0.1, avg_wait_s=100.0, p90_wait_s=200.0, avg_price=20.0, arrivals=1, offers=20,
           offers_accepted=8, offers_rejected=6, offers_expired=6, drivers_offered=3, offer_reject_rate=0.3,
           offer_expiry_rate=0.3),
    bucket('Iosefin', 9, requests=30, assigned=22, completed=20, unmatched=6, cancelled=2, unmatched_rate=0.2,
           cancel_rate=0.067, avg_wait_s=200.0, p90_wait_s=400.0, avg_price=26.0, arrivals=3, offers=40,
           offers_accepted=22, offers_rejected=10, offers_expired=8, drivers_offered=5, offer_reject_rate=0.25,
           offer_expiry_rate=0.2),
    bucket('Fabric', 8, arrivals=4),
    bucket('Fabric', 9),
    bucket('Centru', 8),
    bucket('Centru', 9),
]
SUPPLY = {'as_of': '2026-11-04T12:00:00Z', 'position_max_age_seconds': 30, 'zones': [
    {'zone': 'Centru', 'available': 4, 'offered': 0, 'on_trip': 1, 'stale': 0, 'waiting_trips': 0},
    {'zone': 'Fabric', 'available': 2, 'offered': 1, 'on_trip': 0, 'stale': 1, 'waiting_trips': 0},
    {'zone': 'Iosefin', 'available': 0, 'offered': 1, 'on_trip': 3, 'stale': 0, 'waiting_trips': 2}]}
SURGE = [{'id': 's1', 'zone': 'Iosefin', 'multiplier': 1.5, 'starts_at': '2026-11-04T11:00:00Z',
          'ends_at': '2026-11-04T13:00:00Z', 'proposal_id': 'p1'}]
FLOWS = [{'origin': o, 'destination': d, 'trips': 0, 'completed': 0} for o in ('Centru', 'Fabric', 'Iosefin')
         for d in ('Centru', 'Fabric', 'Iosefin')]
FLOWS[7] = {'origin': 'Iosefin', 'destination': 'Fabric', 'trips': 5, 'completed': 4}
FLOWS[0] = {'origin': 'Centru', 'destination': 'Centru', 'trips': 2, 'completed': 2}


@pytest.fixture
def core(monkeypatch):
    """A fake core: records every read and answers from the fixtures above."""
    calls = []
    async def fake_read(path, params=None):
        calls.append((path, params))
        if path == '/stats/zones':
            if params.get('zone') == 'Atlantis' or params['bucket'] not in stats.BUCKETS:
                raise AssertionError('the tool should have refused this before calling core')
            rows = [r for r in ROWS if params.get('zone') in (None, r['zone'])]
            return {'from': params['from'], 'to': params['to'], 'bucket': params['bucket'], 'rows': rows}
        if path == '/stats/flows':
            return {'from': params['from'], 'to': params['to'], 'flows': FLOWS}
        return {'/zones': ZONES, '/stats/supply': SUPPLY, '/surge': SURGE, '/incentives': []}[path]
    monkeypatch.setattr(mcp_server, 'core_read', fake_read)
    return calls


def call(tool, **args):
    async def run():
        async with Client(mcp_server.mcp) as client:
            return json.loads((await client.call_tool(tool, args)).content[0].text)
    return asyncio.run(run())


def test_window_defaults_to_last_24_hours_and_cuts_the_future():
    win = stats.window(now=NOW)
    assert (win.start, win.end) == (NOW - timedelta(hours=24), NOW)
    win = stats.window('2026-11-04T10:00:00+02:00', '2026-11-05T00:00:00Z', now=NOW)
    assert (win.start, win.end, win.hours) == (datetime(2026, 11, 4, 8, tzinfo=timezone.utc), NOW, 4.0)


@pytest.mark.parametrize('start, end, message', [
    ('yesterday', None, 'ISO-8601'),
    ('2026-11-04T08:00:00', None, 'offset'),
    ('2026-11-04T10:00:00Z', '2026-11-04T09:00:00Z', 'before end'),
    ('2026-10-28T11:00:00Z', None, '7 days'),
])
def test_window_rejects_bad_input(start, end, message):
    with pytest.raises(stats.InvalidArgument, match=message):
        stats.window(start, end, now=NOW)


def test_bucket_must_be_known_and_not_too_fine():
    week = stats.window('2026-10-28T12:00:00Z', now=NOW)
    assert stats.check_bucket('1h', week) == '1h'
    with pytest.raises(stats.InvalidArgument, match='one of'):
        stats.check_bucket('2h', week)
    with pytest.raises(stats.InvalidArgument, match='too many'):
        stats.check_bucket('15m', week)


def test_zone_snapshot_combines_demand_supply_and_rules(core):
    result = call('zone_snapshot', start='2026-11-04T08:00:00Z', end='2026-11-04T10:00:00Z')
    assert result['hours'] == 2.0 and [z['zone'] for z in result['zones']] == ['Centru', 'Fabric', 'Iosefin']
    iosefin = result['zones'][2]
    assert iosefin['requests'] == 40 and iosefin['unmatched'] == 8 and iosefin['unmatched_rate'] == 0.2
    assert iosefin['net_flow'] == 4 - 26 and iosefin['requests_per_hour'] == 20.0
    assert iosefin['avg_wait_s'] == round((100 * 8 + 200 * 22) / 30, 2) and iosefin['worst_p90_wait_s'] == 400.0
    assert iosefin['avg_price'] == round((20 * 6 + 26 * 20) / 26, 2)
    assert iosefin['offers_per_trip'] == 1.5 and iosefin['offer_reject_rate'] == round(16 / 60, 3)
    assert iosefin['offer_expiry_rate'] == round(14 / 60, 3) and iosefin['max_drivers_offered_per_bucket'] == 5
    assert iosefin['peak_bucket']['bucket'] == '2026-11-04T09:00:00Z' and iosefin['peak_bucket']['requests'] == 30
    # No driver available: the ratio divides by 1, not 0.
    assert iosefin['supply_now']['available'] == 0 and iosefin['demand_supply_ratio'] == 20.0
    assert iosefin['active_surge'] == {'multiplier': 1.5, 'starts_at': '2026-11-04T11:00:00Z',
                                       'ends_at': '2026-11-04T13:00:00Z'}
    assert iosefin['active_incentive'] is None
    fabric = result['zones'][1]
    assert fabric['requests'] == 0 and fabric['net_flow'] == 4 and fabric['unmatched_rate'] is None
    assert fabric['peak_bucket'] is None and fabric['demand_supply_ratio'] == 0.0
    assert ('/stats/zones', {'from': '2026-11-04T08:00:00+00:00', 'to': '2026-11-04T10:00:00+00:00',
                             'bucket': '1h'}) in core


def test_zone_demand_leaves_out_empty_buckets_and_filters_by_zone(core):
    result = call('zone_demand', start='2026-11-04T08:00:00Z', end='2026-11-04T10:00:00Z')
    assert [(r['zone'], r['bucket'][11:13]) for r in result['rows']] == [('Iosefin', '08'), ('Iosefin', '09'), ('Fabric', '08')]
    assert result['rows'][0]['net_flow'] == 1 - 6 and 'offers' not in result['rows'][0] and 'zero' in result['note']
    only = call('zone_demand', start='2026-11-04T08:00:00Z', end='2026-11-04T10:00:00Z', bucket='15m', zone='Iosefin')
    assert {r['zone'] for r in only['rows']} == {'Iosefin'} and core[-1][1]['zone'] == 'Iosefin'
    assert core[-1][1]['bucket'] == '15m'


def test_offer_stats(core):
    rows = call('offer_stats', start='2026-11-04T08:00:00Z', end='2026-11-04T10:00:00Z')['rows']
    assert [r['zone'] for r in rows] == ['Iosefin', 'Iosefin']
    assert rows[0]['offers_per_trip'] == 2.0 and rows[0]['offer_expiry_rate'] == 0.3 and 'requests' not in rows[0]


def test_zone_flows_drops_empty_pairs_and_filters_by_zone(core):
    assert len(call('zone_flows')['flows']) == 2
    flows = call('zone_flows', zone='Fabric')['flows']
    assert flows == [{'origin': 'Iosefin', 'destination': 'Fabric', 'trips': 5, 'completed': 4}]


def test_driver_supply_and_active_rules(core):
    assert [z['zone'] for z in call('driver_supply', zone='Iosefin')['zones']] == ['Iosefin']
    assert len(call('driver_supply')['zones']) == 3
    rules = call('active_rules')
    assert rules['Iosefin']['surge']['multiplier'] == 1.5 and rules['Fabric'] == {'surge': None, 'incentive': None}
    assert call('list_zones') == ZONES


@pytest.mark.parametrize('tool, args, message', [
    ('zone_demand', {'zone': 'Atlantis'}, 'unknown zone'),
    ('offer_stats', {'start': 'last week'}, 'ISO-8601'),
    ('zone_snapshot', {'start': '2026-01-01T00:00:00Z'}, '7 days'),
    ('zone_demand', {'bucket': '2h'}, '2h'),
])
def test_bad_arguments_come_back_as_tool_errors(core, tool, args, message):
    with pytest.raises(ToolError, match=message):
        call(tool, **args)
    assert not any(path.startswith('/stats/zones') for path, _ in core)


def test_core_400_becomes_a_tool_error(monkeypatch):
    async def refuse(path, params=None):
        request = httpx.Request('GET', 'http://core' + path)
        raise httpx.HTTPStatusError('bad', request=request, response=httpx.Response(
            400, json={'error': 'invalid_request', 'message': 'nope'}, request=request))
    monkeypatch.setattr(mcp_server, 'core_read', refuse)
    with pytest.raises(ToolError, match='core refused'):
        call('zone_flows')


def test_cancelled_and_open_requests_are_not_a_drain():
    # 25 requests, none completed: no driver left the zone, so net flow is 0, not -25.
    rows = [bucket('Iosefin', 9, requests=25, cancelled=12, open=13, cancel_rate=0.48)]
    summary = stats.zone_summary('Iosefin', rows, None, None, None, hours=24)
    assert summary['net_flow'] == 0 and stats.demand_rows(rows)[0]['net_flow'] == 0
