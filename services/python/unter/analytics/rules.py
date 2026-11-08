"""Deterministic rules: from a zone_snapshot to candidate surge and incentive proposals.

No LLM here. The numbers in a report always come from this module; the model only explains them.
Thresholds are starting values (docs/surge-incentive-agent-plan.md, section 6.1), kept in Thresholds so
the team can tune them in one place.
"""
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from . import validate


@dataclass(frozen=True)
class Thresholds:
    min_sample: int = 20                      # requests in the window; fewer is noise
    duration: timedelta = timedelta(hours=2)  # how long a proposed rule lasts, from the next full hour

    # Surge pressure: each signal divided by its target (1.0 = at target), capped, then weighted.
    weights: dict = field(default_factory=lambda: {
        'demand_supply': 0.4, 'unmatched': 0.3, 'p90_wait': 0.2, 'cancel': 0.1})
    target_demand_supply: float = 3.0         # requests per hour per available driver
    target_unmatched_rate: float = 0.10
    target_p90_wait_s: float = 180
    target_cancel_rate: float = 0.15
    signal_cap: float = 3.0                   # one extreme signal can't decide alone
    surge_min_pressure: float = 1.0
    surge_min: float = 1.10
    surge_max: float = 2.00                   # core allows up to 3.0; we stay lower (open question Q5)
    surge_step: float = 0.05

    # Incentive: any one trigger fires it.
    drain_share: float = 0.2                  # net_flow <= -20% of requests: the zone drains drivers
    refusal_rate: float = 0.4                 # offers rejected + expired
    low_supply_unmatched_rate: float = 0.15   # ... together with at most low_supply_drivers available
    low_supply_drivers: int = 2
    bonus_base: float = 2.0                   # RON; bonus = base + per_score * shortage score (0..1)
    bonus_per_score: float = 10.0
    bonus_min: float = 1.0
    bonus_max: float = 10.0
    bonus_step: float = 0.5
    pair_incentive_with_surge: bool = True    # drivers in surge zones earn more too


DEFAULT = Thresholds()


def step_round(value: float, step: float) -> float:
    """To the nearest step, halves up (not to even), as 2-decimal money."""
    return round(math.floor(value / step + 0.5) * step, 2)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def rule_window(now: datetime, cfg: Thresholds) -> tuple[datetime, datetime]:
    starts = now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return starts, starts + cfg.duration


def pressure(zone: dict, cfg: Thresholds) -> tuple[float, dict]:
    """Weighted surge pressure and the capped signals it came from."""
    signals = {
        'demand_supply': (zone.get('demand_supply_ratio') or 0) / cfg.target_demand_supply,
        'unmatched': (zone.get('unmatched_rate') or 0) / cfg.target_unmatched_rate,
        'p90_wait': (zone.get('worst_p90_wait_s') or 0) / cfg.target_p90_wait_s,
        'cancel': (zone.get('cancel_rate') or 0) / cfg.target_cancel_rate,
    }
    signals = {k: round(min(v, cfg.signal_cap), 3) for k, v in signals.items()}
    return round(sum(cfg.weights[k] * v for k, v in signals.items()), 3), signals


def shortage(zone: dict, cfg: Thresholds) -> tuple[float, list[str]]:
    """Shortage score (0..1) and which incentive triggers fired."""
    requests = zone['requests']
    drain = max(0, -zone.get('net_flow', 0)) / requests if requests else 0
    refusal = (zone.get('offer_reject_rate') or 0) + (zone.get('offer_expiry_rate') or 0)
    unmatched = zone.get('unmatched_rate') or 0
    available = (zone.get('supply_now') or {}).get('available', 0)
    triggers = []
    if drain >= cfg.drain_share:
        triggers.append('drain')
    if refusal >= cfg.refusal_rate:
        triggers.append('refusals')
    if unmatched >= cfg.low_supply_unmatched_rate and available <= cfg.low_supply_drivers:
        triggers.append('low_supply')
    return round(clamp(max(drain, refusal, unmatched), 0, 1), 3), triggers


def covered(active: dict | None, field_name: str, value: float, ends: datetime) -> bool:
    """An active rule at least as strong that lasts until the proposed one would end."""
    if not active or active.get(field_name) is None:
        return False
    return float(active[field_name]) >= value and datetime.fromisoformat(active['ends_at']) >= ends


def key_metrics(zone: dict) -> dict:
    keys = ('requests', 'requests_per_hour', 'demand_supply_ratio', 'unmatched_rate', 'cancel_rate',
            'avg_wait_s', 'worst_p90_wait_s', 'net_flow', 'offer_reject_rate', 'offer_expiry_rate', 'peak_bucket')
    return {k: zone.get(k) for k in keys} | {'available_drivers': (zone.get('supply_now') or {}).get('available', 0)}


def propose(snapshot: dict, now: datetime | None = None, cfg: Thresholds = DEFAULT) -> dict:
    """Candidate proposals for every zone in a zone_snapshot result, plus the zones skipped by a guard.

    Each candidate has the exact zone/type/params shape of core's POST /proposals (but no reason yet),
    an id the LLM must echo back, the rule that fired and the metrics behind it.
    """
    now = now or datetime.now(timezone.utc)
    starts, ends = rule_window(now, cfg)
    window = {'starts_at': iso(starts), 'ends_at': iso(ends)}
    zones = {z['zone'] for z in snapshot['zones']}
    proposals, skipped = [], []

    def add(zone, kind, field_name, value, rule, metrics):
        if covered(zone.get(f'active_{kind}'), field_name, value, ends):
            skipped.append({'zone': zone['zone'], 'type': kind, 'reason': f'an equal or stronger {kind} is already active'})
            return
        candidate = {'id': f"{zone['zone']}:{kind}", 'zone': zone['zone'], 'type': kind,
                     'params': {field_name: value, **window}, 'rule': rule, 'metrics': metrics}
        validate.check(candidate | {'reason': None}, zones, now, require_reason=False)
        proposals.append(candidate)

    for zone in snapshot['zones']:
        if zone['requests'] < cfg.min_sample:
            if zone['requests']:
                skipped.append({'zone': zone['zone'], 'type': None,
                                'reason': f"only {zone['requests']} request{'' if zone['requests'] == 1 else 's'} (minimum {cfg.min_sample})"})
            continue
        metrics = key_metrics(zone)
        level, signals = pressure(zone, cfg)
        score, triggers = shortage(zone, cfg)
        surging = level >= cfg.surge_min_pressure
        if surging:
            multiplier = clamp(step_round(level, cfg.surge_step), cfg.surge_min, cfg.surge_max)
            add(zone, 'surge', 'multiplier', multiplier, f'pressure {level} >= {cfg.surge_min_pressure}',
                metrics | {'pressure': level, 'signals': signals})
        if not triggers and surging and cfg.pair_incentive_with_surge:
            triggers, score = ['paired_with_surge'], round(clamp(level - 1, 0, 1), 3)
        if triggers:
            bonus = clamp(step_round(cfg.bonus_base + cfg.bonus_per_score * score, cfg.bonus_step),
                          cfg.bonus_min, cfg.bonus_max)
            add(zone, 'incentive', 'bonus_per_trip', bonus, f"triggers: {', '.join(triggers)}",
                metrics | {'shortage_score': score, 'triggers': triggers})
    return {'generated_at': iso(now), 'window': {'from': snapshot.get('from'), 'to': snapshot.get('to')},
            'proposals': proposals, 'skipped': skipped}
