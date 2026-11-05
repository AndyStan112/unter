"""The report pipeline: MCP zone_snapshot -> rules engine -> LLM reasons -> validation.

The rules engine decides every number. The model only writes a reason per proposal and a summary,
and its output is used only if it returns exactly the proposals it was given, each with a valid
reason. Otherwise the report falls back to template text, so a model problem never blocks a report.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from agno.agent import Agent
from agno.tools.mcp import MCPTools
from pydantic import BaseModel
from .analytics import rules, validate
from .auth import basic_header
from .model import CappedModel

WINDOW_HOURS = 24  # default; runs use report_settings.window_hours
MAX_SUMMARY = 2000
INSTRUCTIONS = """You write the text of a surge and incentive report for the Unter operations team.
You get candidate proposals that fixed rules computed from trip data, with the metrics behind each one.
- A surge multiplies the price riders pay in a zone. An incentive is a bonus in RON per trip for
  drivers in a zone; it does not change the rider's price.
- For every candidate id, write one reason: 2 to 4 plain sentences, at most 600 characters, explaining
  why it is proposed, using the metrics given. Rates are fractions (0.25 = 25 %), waits are seconds.
- Never change, suggest or invent multipliers, bonuses, times or other numbers.
- All times are UTC; if you mention one, write UTC after it.
- Write plain words for the metrics (drivers available, unmatched requests), never field names
  like available_drivers or internal scores like pressure or shortage score.
- Explain why the rules proposed each candidate. Don't argue against it, hedge it or make it
  conditional; the team decides whether to approve.
- Write a summary for the team, at most 1200 characters: which zones are under pressure, what is
  proposed, and anything notable among the skipped zones.
- Return exactly the ids you were given, each once."""


class Reason(BaseModel):
    id: str
    reason: str


class Explanation(BaseModel):
    summary: str
    reasons: list[Reason]


class ExplanationRejected(ValueError):
    """The model's text didn't fit the proposals; the message is safe to store."""


def iso(moment: datetime) -> str:
    return rules.iso(moment)


async def read_snapshot(start: datetime, end: datetime) -> dict:
    """zone_snapshot through the MCP server, with the READER login (the only one the MCP server accepts)."""
    async with MCPTools(url=os.getenv('MCP_URL', 'http://mcp:8000/mcp'), transport='streamable-http',
                        header_provider=lambda: {'Authorization': basic_header('READER')},
                        include_tools=['zone_snapshot']) as tools:
        result = await tools.session.call_tool('zone_snapshot', {'start': iso(start), 'end': iso(end)})
    if result.isError:
        raise RuntimeError('zone_snapshot failed')
    return json.loads(result.content[0].text)


def percent(value) -> str:
    return '—' if value is None else f'{value:.0%}'


def template_reason(proposal: dict) -> str:
    m, p = proposal['metrics'], proposal['params']
    when = f"from {p['starts_at']} to {p['ends_at']}"
    if proposal['type'] == 'surge':
        wait = '—' if m.get('worst_p90_wait_s') is None else f"{m['worst_p90_wait_s']:.0f} s"
        return (f"Demand pressure in {proposal['zone']} is {m['pressure']} (1.0 = at target): "
                f"{m['requests_per_hour']} requests per hour for {m['available_drivers']} available drivers, "
                f"{percent(m['unmatched_rate'])} unmatched, worst hourly p90 wait {wait}. "
                f"Surge x{p['multiplier']} {when}.")
    refused = None if m.get('offer_reject_rate') is None else (m['offer_reject_rate'] or 0) + (m.get('offer_expiry_rate') or 0)
    return (f"Drivers are short in {proposal['zone']} ({', '.join(m['triggers']).replace('_', ' ')}): "
            f"net flow {m['net_flow']} trips over the window, {percent(refused)} of offers rejected or expired, "
            f"{m['available_drivers']} drivers available now. Bonus of {p['bonus_per_trip']} RON per trip {when}.")


def template_summary(plan: dict) -> str:
    proposals = plan['proposals']
    if not proposals:
        text = 'No zone needs a surge or a driver incentive for this window.'
    else:
        zones = sorted({p['zone'] for p in proposals})
        surges = sum(p['type'] == 'surge' for p in proposals)
        text = (f"{len(proposals)} proposal(s) for {', '.join(zones)}: {surges} surge(s) and "
                f"{len(proposals) - surges} driver incentive(s).")
    if plan['skipped']:
        text += ' Skipped: ' + '; '.join(f"{s['zone']} ({s['reason']})" for s in plan['skipped']) + '.'
    return text


def model_input(plan: dict) -> str:
    keep = ('id', 'zone', 'type', 'params', 'rule', 'metrics')
    return json.dumps({'window': plan['window'], 'candidates': [{k: p[k] for k in keep} for p in plan['proposals']],
                       'skipped': plan['skipped']}, default=str)


async def explain(plan: dict, model: str) -> Explanation:
    """One structured model call, no tools: the model can only write text."""
    agent = Agent(name='Unter report writer', telemetry=False, retries=0, output_schema=Explanation,
                  instructions=INSTRUCTIONS,
                  model=CappedModel(id=model, max_completion_tokens=4000, reasoning_effort='minimal', timeout=60,
                                    max_retries=0, retries=0, store=False))
    response = await agent.arun(model_input(plan))
    if not isinstance(response.content, Explanation):
        raise ExplanationRejected('the model returned no structured explanation')
    return response.content


def apply_explanation(plan: dict, explanation: Explanation, zones: set[str], now: datetime) -> list[dict]:
    """The rules engine's proposals with the model's reasons, or ExplanationRejected."""
    given = [r.id for r in explanation.reasons]
    expected = [p['id'] for p in plan['proposals']]
    if sorted(given) != sorted(expected):
        raise ExplanationRejected(f'the model returned ids {sorted(given)}, expected {sorted(expected)}')
    if not explanation.summary.strip() or len(explanation.summary) > MAX_SUMMARY:
        raise ExplanationRejected(f'the summary must be non-blank and at most {MAX_SUMMARY} characters')
    reasons = {r.id: r.reason.strip() for r in explanation.reasons}
    proposals = [p | {'reason': reasons[p['id']]} for p in plan['proposals']]
    for proposal in proposals:
        if errors := validate.problems(proposal, zones, now):
            raise ExplanationRejected(f"{proposal['id']}: {'; '.join(errors)}")
    return proposals


def safe_error(error: Exception) -> str:
    # Provider exceptions can contain request details; keep only their class, like agent.execute.
    return str(error)[:300] if isinstance(error, ExplanationRejected) else type(error).__name__


async def build(mode: str, model: str, now: datetime | None = None, window_hours: int = WINDOW_HOURS) -> tuple[dict, list[str]]:
    """One report and the MCP tools it read. Raises if the data can't be read or a proposal is invalid."""
    now = now or datetime.now(timezone.utc)
    snapshot = await read_snapshot(now - timedelta(hours=window_hours), now)
    plan = rules.propose(snapshot, now)
    zones = {z['zone'] for z in snapshot['zones']}
    proposals, summary, explained_by, note = None, None, 'model', None
    if not plan['proposals']:
        note = 'nothing to explain: no model call'
    elif mode == 'fake':
        note = 'fake mode: no model call'
    else:
        try:
            explanation = await explain(plan, model)
            proposals = apply_explanation(plan, explanation, zones, now)
            summary = explanation.summary.strip()
        except Exception as error:
            note = f'model text not used: {safe_error(error)}'
    if proposals is None:
        proposals = [p | {'reason': template_reason(p)} for p in plan['proposals']]
        summary, explained_by = template_summary(plan), 'template'
    for proposal in proposals:
        validate.check(proposal, zones, now)  # same rules as core's POST /proposals
    report = {'generated_at': plan['generated_at'],
              'window': {'from': snapshot['from'], 'to': snapshot['to'], 'hours': snapshot['hours']},
              'summary': summary, 'proposals': proposals, 'skipped': plan['skipped'], 'zones': snapshot['zones'],
              'explained_by': explained_by, 'model': model if explained_by == 'model' else None, 'note': note}
    return report, ['zone_snapshot']


def ready_event(report_id, run_id, source: str, built: dict, recipients: list[str]) -> dict:
    """The data of a report.ready event: the whole report, so consumers (the mailer) need no database."""
    return {'report_id': str(report_id), 'run_id': str(run_id), 'source': source, 'recipients': list(recipients), **built}


def run_result(report_id, built: dict) -> str:
    """The short text shown in the run history; the full report is in the reports table."""
    count = len(built['proposals'])
    return f"{built['summary']}\n\nReport {report_id}: {count} proposal(s), text by {built['explained_by']}."
