"""Checks a proposal against the rules of core's POST /proposals (Proposals.java), before it leaves the agent.

Reported proposals aren't sent to core by the agent, but an operator may approve them later as they are,
so they must already be valid. Keep this in step with Proposals.NewProposal and Proposals.params().
"""
from datetime import datetime, timezone
from decimal import Decimal

AMOUNTS = {'surge': ('multiplier', Decimal('1'), Decimal('3')),
           'incentive': ('bonus_per_trip', Decimal('0'), Decimal('20'))}
MAX_ZONE = 80
MAX_REASON = 1000


class InvalidProposal(ValueError):
    def __init__(self, proposal: dict, errors: list[str]):
        super().__init__(f"{proposal.get('zone')} {proposal.get('type')}: " + '; '.join(errors))
        self.errors = errors


def _time(params: dict, field: str, errors: list[str]) -> datetime | None:
    value = params.get(field)
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        parsed = None
    if parsed is None or parsed.tzinfo is None:
        errors.append(f'{field} must be an ISO-8601 time with an offset')
        return None
    return parsed


def _amount(params: dict, field: str, low: Decimal, high: Decimal, errors: list[str]) -> None:
    value = params.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f'{field} must be a number')
        return
    amount = Decimal(str(value))
    if not low <= amount <= high or -amount.normalize().as_tuple().exponent > 2:
        errors.append(f'{field} must be between {low} and {high}, with at most 2 decimals')


def problems(proposal: dict, zones: set[str], now: datetime | None = None, require_reason: bool = True) -> list[str]:
    """Everything wrong with a proposal ({zone, type, params, reason}); empty when core would accept it.

    require_reason=False checks a rules-engine candidate before the LLM has written its reason.
    """
    now = now or datetime.now(timezone.utc)
    errors = []
    zone = proposal.get('zone')
    if not isinstance(zone, str) or not zone.strip() or len(zone) > MAX_ZONE:
        errors.append(f'zone must be a non-blank name of at most {MAX_ZONE} characters')
    elif zone not in zones:
        errors.append(f'unknown zone {zone!r}')
    reason = proposal.get('reason')
    if require_reason or reason is not None:
        if not isinstance(reason, str) or not reason.strip() or len(reason) > MAX_REASON:
            errors.append(f'reason must be non-blank text of at most {MAX_REASON} characters')
    kind = proposal.get('type')
    if kind not in AMOUNTS:
        errors.append('type must be surge or incentive')
        return errors
    params = proposal.get('params')
    if not isinstance(params, dict):
        errors.append(f'params are required for a {kind} proposal')
        return errors
    field, low, high = AMOUNTS[kind]
    extra = set(params) - {field, 'starts_at', 'ends_at'}
    if extra:
        errors.append(f'unexpected params {sorted(extra)}')
    _amount(params, field, low, high, errors)
    starts, ends = _time(params, 'starts_at', errors), _time(params, 'ends_at', errors)
    if starts and ends:
        if ends <= starts:
            errors.append('ends_at must be after starts_at')
        if ends <= now:
            errors.append('ends_at must be in the future')
    return errors


def check(proposal: dict, zones: set[str], now: datetime | None = None, require_reason: bool = True) -> dict:
    """Returns the proposal, or raises InvalidProposal listing every problem."""
    errors = problems(proposal, zones, now, require_reason)
    if errors:
        raise InvalidProposal(proposal, errors)
    return proposal
