from dataclasses import replace
from datetime import datetime, timezone
import pytest
from unter.analytics import rules, validate

NOW = datetime(2026, 11, 4, 10, 20, tzinfo=timezone.utc)
STARTS, ENDS = '2026-11-04T11:00:00Z', '2026-11-04T13:00:00Z'
ZONES = {'Centru', 'Fabric', 'Iosefin'}


def zone(name='Iosefin', available=2, active_surge=None, active_incentive=None, **values):
    """A zone_snapshot entry: quiet by default, override the signals a case needs."""
    base = {'zone': name, 'requests': 40, 'requests_per_hour': 10.0, 'demand_supply_ratio': 0.5,
            'unmatched_rate': 0.0, 'cancel_rate': 0.0, 'avg_wait_s': 30.0, 'worst_p90_wait_s': 60.0,
            'net_flow': 5, 'offer_reject_rate': 0.05, 'offer_expiry_rate': 0.05, 'peak_bucket': None,
            'supply_now': {'available': available, 'offered': 0, 'on_trip': 0, 'stale': 0, 'waiting_trips': 0},
            'active_surge': active_surge, 'active_incentive': active_incentive}
    return base | values


# pressure = 0.4*(4.5/3) + 0.3*(0.15/0.10) + 0.2*(270/180) + 0.1*(0.15/0.15) = 1.45
# shortage = max(drain 30/40, refusals 0.3, unmatched 0.15 with 2 drivers) = 0.75 -> bonus 2 + 7.5 = 9.5
BUSY = dict(demand_supply_ratio=4.5, unmatched_rate=0.15, worst_p90_wait_s=270.0, cancel_rate=0.15, net_flow=-30,
            offer_reject_rate=0.2, offer_expiry_rate=0.1)
STRONG = {'multiplier': 1.8, 'starts_at': '2026-11-04T09:00:00Z', 'ends_at': '2026-11-04T14:00:00Z'}


def amounts(result):
    return {(p['zone'], p['type']): p['params'].get('multiplier', p['params'].get('bonus_per_trip'))
            for p in result['proposals']}


CASES = [
    ('busy zone: surge and incentive', [zone(**BUSY)], {}, {('Iosefin', 'surge'): 1.45, ('Iosefin', 'incentive'): 9.5}),
    ('quiet zone: nothing', [zone()], {}, {}),
    ('low sample: skipped', [zone(requests=19, **BUSY)], {}, {}),
    ('already active stronger surge: only the incentive', [zone(active_surge=STRONG, **BUSY)], {},
     {('Iosefin', 'incentive'): 9.5}),
    ('active surge weaker: proposed anyway', [zone(active_surge=STRONG | {'multiplier': 1.2}, **BUSY)], {},
     {('Iosefin', 'surge'): 1.45, ('Iosefin', 'incentive'): 9.5}),
    ('active surge ends before ours: proposed anyway', [zone(active_surge=STRONG | {'ends_at': '2026-11-04T12:00:00Z'}, **BUSY)],
     {}, {('Iosefin', 'surge'): 1.45, ('Iosefin', 'incentive'): 9.5}),
    ('active incentive as high: only the surge', [zone(active_incentive={'bonus_per_trip': 10.0, 'starts_at': STARTS,
                                                                         'ends_at': ENDS}, **BUSY)], {},
     {('Iosefin', 'surge'): 1.45}),
    # no p90 known (no trip assigned): pressure = 0.4*3 (capped) + 0.3*1 = 1.5, no incentive trigger -> paired incentive, score 0.5 -> 7.0
    ('surge without shortage: paired incentive', [zone(demand_supply_ratio=12.0, unmatched_rate=0.1, worst_p90_wait_s=None)], {},
     {('Iosefin', 'surge'): 1.5, ('Iosefin', 'incentive'): 7.0}),
    ('pairing off: surge only', [zone(demand_supply_ratio=12.0, unmatched_rate=0.1, worst_p90_wait_s=None)], {'pair_incentive_with_surge': False},
     {('Iosefin', 'surge'): 1.5}),
    ('drivers refuse the zone: incentive only', [zone(offer_reject_rate=0.3, offer_expiry_rate=0.2)], {},
     {('Iosefin', 'incentive'): 7.0}),
    ('unmatched with few drivers: incentive only', [zone(unmatched_rate=0.15, available=1)], {},
     {('Iosefin', 'incentive'): 3.5}),
    ('unmatched but drivers available: nothing', [zone(unmatched_rate=0.15, available=5)], {}, {}),
    ('extreme pressure: capped at 2.0 and 10 RON', [zone(demand_supply_ratio=50.0, unmatched_rate=0.9, worst_p90_wait_s=900.0,
                                                         cancel_rate=0.9, net_flow=-40)], {},
     {('Iosefin', 'surge'): 2.0, ('Iosefin', 'incentive'): 10.0}),
    # pressure = 0.4*(7.5/3) = 1.0 exactly -> raised to the 1.10 minimum
    ('pressure exactly at the threshold: minimum surge', [zone(demand_supply_ratio=7.5, worst_p90_wait_s=None)], {'pair_incentive_with_surge': False},
     {('Iosefin', 'surge'): 1.1}),
    ('pressure just below the threshold: nothing', [zone(demand_supply_ratio=7.4, worst_p90_wait_s=None)], {}, {}),
    ('several zones: each on its own', [zone(**BUSY), zone('Centru'), zone('Fabric', requests=3)], {},
     {('Iosefin', 'surge'): 1.45, ('Iosefin', 'incentive'): 9.5}),
]


@pytest.mark.parametrize('name, zones, overrides, expected', CASES, ids=[c[0] for c in CASES])
def test_rules(name, zones, overrides, expected):
    result = rules.propose({'from': 'a', 'to': 'b', 'zones': zones}, NOW, replace(rules.DEFAULT, **overrides))
    assert amounts(result) == expected
    for proposal in result['proposals']:
        assert proposal['params']['starts_at'] == STARTS and proposal['params']['ends_at'] == ENDS
        assert proposal['id'] == f"{proposal['zone']}:{proposal['type']}" and proposal['rule'] and proposal['metrics']
        assert validate.problems(proposal | {'reason': 'x'}, ZONES, NOW) == []


def test_skipped_zones_say_why():
    result = rules.propose({'zones': [zone(requests=19, **BUSY), zone('Centru', requests=0),
                                      zone('Fabric', active_surge=STRONG, **BUSY)]}, NOW)
    assert result['skipped'] == [
        {'zone': 'Iosefin', 'type': None, 'reason': 'only 19 requests (minimum 20)'},
        {'zone': 'Fabric', 'type': 'surge', 'reason': 'an equal or stronger surge is already active'}]


def test_metrics_explain_the_proposal():
    surge, incentive = rules.propose({'zones': [zone(**BUSY)]}, NOW)['proposals']
    assert surge['metrics']['pressure'] == 1.45 and surge['metrics']['signals']['demand_supply'] == 1.5
    assert surge['metrics']['available_drivers'] == 2 and surge['rule'] == 'pressure 1.45 >= 1.0'
    assert incentive['metrics']['triggers'] == ['drain', 'low_supply'] and incentive['metrics']['shortage_score'] == 0.75


@pytest.mark.parametrize('now, starts', [
    (datetime(2026, 11, 4, 10, 0, tzinfo=timezone.utc), '2026-11-04T11:00:00Z'),
    (datetime(2026, 11, 4, 23, 59, tzinfo=timezone.utc), '2026-11-05T00:00:00Z'),
    (datetime(2026, 11, 4, 12, 30, tzinfo=timezone(rules.timedelta(hours=2))), '2026-11-04T11:00:00Z'),
])
def test_rules_start_at_the_next_full_hour(now, starts):
    assert rules.rule_window(now, rules.DEFAULT)[0] == datetime.fromisoformat(starts)


@pytest.mark.parametrize('value, step, expected', [(1.425, 0.05, 1.45), (1.424, 0.05, 1.4), (9.25, 0.5, 9.5), (9.24, 0.5, 9.0)])
def test_step_round_rounds_halves_up(value, step, expected):
    assert rules.step_round(value, step) == expected


VALID = {'zone': 'Iosefin', 'type': 'surge', 'reason': 'Busy evening.',
         'params': {'multiplier': 1.5, 'starts_at': STARTS, 'ends_at': ENDS}}
INCENTIVE = VALID | {'type': 'incentive', 'params': {'bonus_per_trip': 20, 'starts_at': STARTS, 'ends_at': ENDS}}


def params(**changes):
    return VALID | {'params': VALID['params'] | changes}


def test_valid_proposals_pass():
    assert validate.check(VALID, ZONES, NOW) is VALID
    assert validate.problems(INCENTIVE, ZONES, NOW) == []
    assert validate.problems(params(multiplier=3), ZONES, NOW) == []
    assert validate.problems(VALID | {'reason': None}, ZONES, NOW, require_reason=False) == []


@pytest.mark.parametrize('proposal, error', [
    (VALID | {'zone': 'Atlantis'}, 'unknown zone'),
    (VALID | {'zone': ' '}, 'zone must be'),
    (VALID | {'reason': ''}, 'reason'),
    (VALID | {'reason': 'x' * 1001}, 'reason'),
    (VALID | {'type': 'discount'}, 'type must be'),
    (VALID | {'params': None}, 'params are required'),
    (params(multiplier=0.9), 'between 1 and 3'),
    (params(multiplier=3.5), 'between 1 and 3'),
    (params(multiplier=1.234), 'at most 2 decimals'),
    (params(multiplier=True), 'must be a number'),
    (params(multiplier='1.5'), 'must be a number'),
    (INCENTIVE | {'params': INCENTIVE['params'] | {'bonus_per_trip': 20.5}}, 'between 0 and 20'),
    (INCENTIVE | {'params': INCENTIVE['params'] | {'bonus_per_trip': -1}}, 'between 0 and 20'),
    (INCENTIVE | {'params': {'multiplier': 1.5, 'starts_at': STARTS, 'ends_at': ENDS}}, 'unexpected params'),
    (params(ends_at=STARTS), 'after starts_at'),
    (params(starts_at='2026-11-04T08:00:00Z', ends_at='2026-11-04T09:00:00Z'), 'in the future'),
    (params(starts_at='2026-11-04T11:00:00'), 'with an offset'),
    (params(ends_at='tomorrow'), 'with an offset'),
])
def test_invalid_proposals_are_refused(proposal, error):
    with pytest.raises(validate.InvalidProposal, match=error):
        validate.check(proposal, ZONES, NOW)
