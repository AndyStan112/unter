"""Argument checks and derived metrics behind the MCP analysis tools.

core's read-only /stats endpoints do the counting (docs/core-api-contract.md). This module only checks
what the model asks for and turns core's answers into compact summaries, without any I/O, so it can be
tested without a running core.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from fastmcp.exceptions import ToolError

BUCKETS = {'15m': timedelta(minutes=15), '1h': timedelta(hours=1), '6h': timedelta(hours=6), '1d': timedelta(days=1)}
DEFAULT_WINDOW = timedelta(hours=24)
MAX_WINDOW = timedelta(days=7)
MAX_BUCKETS = 200  # per zone; keeps a tool result small enough for the model's context

TRIP_FIELDS = ('requests', 'completed', 'cancelled', 'unmatched', 'open', 'unmatched_rate', 'cancel_rate',
               'avg_wait_s', 'p90_wait_s', 'avg_price', 'arrivals')
OFFER_FIELDS = ('offers', 'offers_accepted', 'offers_rejected', 'offers_expired', 'drivers_offered',
                'offer_reject_rate', 'offer_expiry_rate')
SUPPLY_FIELDS = ('available', 'offered', 'on_trip', 'stale', 'waiting_trips')
EMPTY_NOTE = 'Buckets left out had no activity: count them as zero.'


class InvalidArgument(ToolError):
    """A tool argument the model can fix. The message is shown to the model as the tool error."""


@dataclass(frozen=True)
class Window:
    start: datetime
    end: datetime

    @property
    def hours(self) -> float:
        return (self.end - self.start).total_seconds() / 3600

    def params(self) -> dict:
        return {'from': self.start.isoformat(), 'to': self.end.isoformat()}


def parse_time(value: str, name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise InvalidArgument(f'{name} must be an ISO-8601 time with an offset, e.g. 2026-11-03T08:00:00Z') from None
    if parsed.tzinfo is None:
        raise InvalidArgument(f'{name} needs a UTC offset, e.g. 2026-11-03T08:00:00Z')
    return parsed.astimezone(timezone.utc)


def window(start: str | None = None, end: str | None = None, now: datetime | None = None) -> Window:
    """[start, end), same rules as core: default the last 24 h, end cut at now, at most 7 days."""
    now = now or datetime.now(timezone.utc)
    stop = min(parse_time(end, 'end'), now) if end else now
    begin = parse_time(start, 'start') if start else stop - DEFAULT_WINDOW
    if begin >= stop:
        raise InvalidArgument('start must be before end (an end in the future is cut at now)')
    if stop - begin > MAX_WINDOW:
        raise InvalidArgument('the window can be at most 7 days')
    return Window(begin, stop)


def check_bucket(bucket: str, win: Window) -> str:
    if bucket not in BUCKETS:
        raise InvalidArgument(f'bucket must be one of {", ".join(BUCKETS)}')
    count = -(-(win.end - win.start) // BUCKETS[bucket])
    if count > MAX_BUCKETS:
        raise InvalidArgument(f'{count} buckets of {bucket} per zone is too many (at most {MAX_BUCKETS}): '
                              'use a larger bucket or a shorter window')
    return bucket


def check_zone(zone: str | None, zones: list[dict]) -> str | None:
    if zone is None:
        return None
    names = sorted(z['name'] for z in zones)
    if zone not in names:
        raise InvalidArgument(f'unknown zone {zone!r}; zones are {", ".join(names)}')
    return zone


def ratio(part, whole, digits=3):
    return round(part / whole, digits) if whole else None


def demand_rows(rows: list[dict]) -> list[dict]:
    """Trip metrics per zone x bucket, without empty buckets, plus net_flow.

    net_flow = arrivals - completed: completed trips ending in the zone minus completed trips starting there.
    Only completed trips move a driver, so cancelled or still-open requests don't count as a drain."""
    return [{'zone': r['zone'], 'bucket': r['bucket'], **{k: r[k] for k in TRIP_FIELDS},
             'net_flow': r['arrivals'] - r['completed']}
            for r in rows if r['requests'] or r['arrivals']]


def offer_rows(rows: list[dict]) -> list[dict]:
    """Offer metrics per zone x bucket, without buckets that had no offers."""
    return [{'zone': r['zone'], 'bucket': r['bucket'], **{k: r[k] for k in OFFER_FIELDS},
             'offers_per_trip': ratio(r['offers'], r['requests'], 2)}
            for r in rows if r['offers']]


def flow_rows(flows: list[dict], zone: str | None) -> list[dict]:
    return [f for f in flows if f['trips'] and (zone is None or zone in (f['origin'], f['destination']))]


def rule_view(rule: dict | None) -> dict | None:
    """An active surge rule or incentive without its ids: what applies and until when."""
    if rule is None:
        return None
    return {k: v for k, v in rule.items() if k not in ('id', 'zone', 'proposal_id')}


def by_zone(items: list[dict]) -> dict[str, dict]:
    return {item['zone']: item for item in items}


def zone_summary(zone: str, rows: list[dict], supply: dict | None, surge: dict | None, incentive: dict | None,
                 hours: float) -> dict:
    """One zone over the whole window, from its /stats/zones buckets, the supply snapshot and active rules."""
    rows = [r for r in rows if r['zone'] == zone]
    total = lambda key: sum(r[key] for r in rows)
    def weighted(key, weight):
        known = [r for r in rows if r[key] is not None and r[weight]]
        n = sum(r[weight] for r in known)
        return round(sum(float(r[key]) * r[weight] for r in known) / n, 2) if n else None

    requests, offers = total('requests'), total('offers')
    supply = {k: (supply or {}).get(k, 0) for k in SUPPLY_FIELDS}
    requests_per_hour = round(requests / hours, 2) if hours else 0.0
    p90s = [r['p90_wait_s'] for r in rows if r['p90_wait_s'] is not None]
    busiest = max(rows, key=lambda r: r['requests'], default=None)
    peak = None
    if busiest and busiest['requests']:
        peak = {k: busiest[k] for k in ('bucket', 'requests', 'unmatched_rate', 'cancel_rate', 'p90_wait_s')}
    return {
        'zone': zone,
        'requests': requests, 'completed': total('completed'), 'cancelled': total('cancelled'),
        'unmatched': total('unmatched'), 'open': total('open'), 'arrivals': total('arrivals'),
        'net_flow': total('arrivals') - total('completed'),
        'unmatched_rate': ratio(total('unmatched'), requests), 'cancel_rate': ratio(total('cancelled'), requests),
        'avg_wait_s': weighted('avg_wait_s', 'assigned'),
        'worst_p90_wait_s': max(p90s, default=None),
        'avg_price': weighted('avg_price', 'completed'),
        'requests_per_hour': requests_per_hour,
        'offers': offers, 'offers_per_trip': ratio(offers, requests, 2),
        'offer_reject_rate': ratio(total('offers_rejected'), offers),
        'offer_expiry_rate': ratio(total('offers_expired'), offers),
        'max_drivers_offered_per_bucket': max((r['drivers_offered'] for r in rows), default=0),
        'peak_bucket': peak,
        'supply_now': supply,
        'demand_supply_ratio': round(requests_per_hour / max(supply['available'], 1), 2),
        'active_surge': rule_view(surge), 'active_incentive': rule_view(incentive),
    }
