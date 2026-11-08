"""Surge and incentive report runner with a durable, dashboard-controlled cron schedule.

Each run reads core through the MCP server only (read-only), never writes to core, and stores its
report in its own `agent` database. See report.py for the pipeline.
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
import json
import os
import re
import uuid
from zoneinfo import ZoneInfo
from croniter import croniter
from fastapi import FastAPI, HTTPException
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from agno.utils.log import agent_logger

# Provider error text can contain request details. The dashboard records safe codes.
agent_logger.disabled = True
from .auth import BasicAuth
from .common import connect
from .migrate import upgrade_database
from . import outbox, report

UTC = timezone.utc
MODEL = os.getenv('OPENAI_MODEL', 'gpt-5-nano')
MODE = os.getenv('AGENT_MODE', 'live')
MAX_DAILY_RUNS = int(os.getenv('MAX_DAILY_RUNS', '30'))
RUN_TIMEOUT = 100
MAX_RECIPIENTS = 20
# Deliberately strict: no spaces, commas, quotes or angle brackets, so an address can't add mail headers.
EMAIL = re.compile(r'[^@\s,;<>"]+@[^@\s,;<>"]+\.[^@\s,;<>"]+')


class Schedule(BaseModel):
    cron: str = Field(default='0 * * * *', max_length=80)
    timezone: str = Field(default='Europe/Bucharest', max_length=80)
    enabled: bool = False
    # Report settings. Left out (None) keeps the stored value, so older clients don't erase them.
    window_hours: int | None = Field(default=None, ge=1, le=168)
    recipients: list[str] | None = Field(default=None, max_length=MAX_RECIPIENTS)

    @field_validator('recipients')
    @classmethod
    def validate_recipients(cls, values):
        if values is None:
            return None
        cleaned = []
        for value in values:
            value = value.strip().lower()
            if len(value) > 254 or not EMAIL.fullmatch(value):
                raise ValueError('Recipients must be plain email addresses')
            if value not in cleaned:
                cleaned.append(value)
        return cleaned

    @model_validator(mode='after')
    def validate_schedule(self):
        try:
            if len(self.cron.split()) != 5:
                raise ValueError()
            zone = ZoneInfo(self.timezone)
            next_time(self.cron, self.timezone)
            if not croniter.is_valid(self.cron):
                raise ValueError()
        except Exception:
            raise ValueError('Use a valid five-field cron and IANA timezone') from None
        return self


def next_time(cron, zone, now=None):
    base = (now or datetime.now(UTC)).astimezone(ZoneInfo(zone))
    return croniter(cron, base).get_next(datetime).astimezone(UTC)


def initialize():
    upgrade_database('agent')
    with connect() as db:
        db.execute("INSERT INTO schedule (id, cron, timezone, enabled, next_at) VALUES (1,'0 * * * *','Europe/Bucharest',false,%s) ON CONFLICT DO NOTHING",
                   (next_time('0 * * * *', 'Europe/Bucharest'),))
        # A killed process cannot complete its in-flight run; do not retry paid calls.
        db.execute("UPDATE runs SET status='interrupted', finished_at=now(), error='Run interrupted; not retried' WHERE status='running' AND started_at < now() - interval '3 minutes'")


def store_report(db, run_id, source, built, recipients):
    """The report and its report.ready event, in the caller's transaction: never one without the other."""
    report_id = uuid.uuid4()
    db.execute('INSERT INTO reports (id, run_id, window_from, window_to, report) VALUES (%s,%s,%s,%s,%s::jsonb)',
               (report_id, run_id, built['window']['from'], built['window']['to'], json.dumps(built, default=str)))
    outbox.add(db, 'report.ready', report.ready_event(report_id, run_id, source, built, recipients))
    return report_id


async def execute(source):
    """Session lock spans the paid call; every trigger shares the same budget checks."""
    db = connect()
    run_id = uuid.uuid4()
    try:
        locked = db.execute('SELECT pg_try_advisory_lock(83112) AS locked').fetchone()['locked']
        db.commit()
        if not locked:
            raise HTTPException(409, 'An agent run is already in progress')
        # No user-controlled prompt or model can bypass these limits.
        count = db.execute("SELECT count(*) AS n FROM runs WHERE started_at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'").fetchone()['n']
        recent = db.execute("SELECT count(*) AS n FROM runs WHERE started_at > now() - interval '30 seconds'").fetchone()['n']
        active = db.execute("SELECT count(*) AS n FROM runs WHERE status='running' AND started_at > now() - interval '3 minutes'").fetchone()['n']
        if count >= MAX_DAILY_RUNS:
            raise HTTPException(429, 'Daily run limit reached')
        if recent:
            raise HTTPException(429, 'Wait 30 seconds between runs')
        if active:
            raise HTTPException(409, 'An agent run is already in progress')
        db.execute("INSERT INTO runs(id,source,status,mode,model) VALUES (%s,%s,'running',%s,%s)",
                   (run_id, source, MODE, MODEL))
        settings = db.execute('SELECT window_hours, recipients FROM report_settings WHERE id=1').fetchone()
        db.commit()
        try:
            built, calls = await asyncio.wait_for(report.build(MODE, MODEL, window_hours=settings['window_hours']), RUN_TIMEOUT)
            report_id = store_report(db, run_id, source, built, settings['recipients'])
            db.execute("UPDATE runs SET status='completed',finished_at=now(),result=%s,tool_calls=%s::jsonb WHERE id=%s",
                       (report.run_result(report_id, built), json.dumps(calls), run_id))
        except asyncio.CancelledError:
            db.rollback()
            db.execute("UPDATE runs SET status='interrupted',finished_at=now(),error='Run interrupted; not retried' WHERE id=%s", (run_id,))
            db.commit()
            raise
        except Exception as error:
            # Provider exceptions can contain request details; persist only their class.
            code = getattr(error, 'status_code', None)
            safe = type(error).__name__ + (f' (HTTP {code})' if isinstance(code, int) else '')
            db.rollback()  # A failed report insert leaves the transaction aborted; nothing of it is kept.
            db.execute("UPDATE runs SET status='failed',finished_at=now(),error=%s WHERE id=%s", (safe, run_id))
        db.commit()
        return db.execute('SELECT * FROM runs WHERE id=%s', (run_id,)).fetchone()
    finally:
        db.close()  # Releases the advisory lock, including on failures.


async def scheduler():
    while True:
        try:
            with connect() as db:
                row = db.execute('SELECT * FROM schedule WHERE id=1 FOR UPDATE').fetchone()
                due = row['enabled'] and row['next_at'] <= datetime.now(UTC)
                if due:
                    # Skip missed slots; never replay a backlog of paid calls.
                    db.execute('UPDATE schedule SET next_at=%s WHERE id=1',
                               (next_time(row['cron'], row['timezone']),))
            if due:
                try:
                    await execute('schedule')
                except HTTPException:
                    pass  # Busy/rate-limited slots are skipped, not queued.
        except asyncio.CancelledError:
            raise
        except Exception:
            pass  # Transient DB outage: retry polling without logging secrets.
        await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app):
    initialize()
    tasks = [asyncio.create_task(scheduler()), asyncio.create_task(outbox.publisher())]
    yield
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

app = FastAPI(lifespan=lifespan)
app.add_middleware(BasicAuth)


@app.get('/healthz')
def health():
    with connect() as db:
        db.execute('SELECT 1')
    return {'status': 'ok'}


@app.get('/schedule')
def get_schedule():
    with connect() as db:
        row = db.execute('SELECT s.*, r.window_hours, r.recipients FROM schedule s, report_settings r '
                         'WHERE s.id=1 AND r.id=1').fetchone()
        return {**row, 'model': MODEL, 'mode': MODE, 'max_daily_runs': MAX_DAILY_RUNS}


@app.put('/schedule')
def save_schedule(value: Schedule):
    with connect() as db:
        db.execute('UPDATE schedule SET cron=%s, timezone=%s, enabled=%s, next_at=%s WHERE id=1',
                   (value.cron, value.timezone, value.enabled, next_time(value.cron, value.timezone)))
        db.execute('UPDATE report_settings SET window_hours=coalesce(%s, window_hours), '
                   'recipients=coalesce(%s, recipients) WHERE id=1', (value.window_hours, value.recipients))
    return get_schedule()


@app.get('/runs')
def runs():
    with connect() as db:
        return db.execute('SELECT * FROM runs ORDER BY started_at DESC LIMIT 50').fetchall()


@app.get('/reports')
def reports():
    """The 20 newest reports: whether report.ready reached RabbitMQ (published) and the email delivery state."""
    with connect() as db:
        return db.execute('SELECT r.id, r.run_id, r.created_at, r.window_from, r.window_to, r.report, '
                          "coalesce((SELECT bool_and(o.sent) FROM agent_outbox o WHERE o.payload->>'report_id' = r.id::text), false) AS published, "
                          "CASE WHEN d.report_id IS NOT NULL THEN json_build_object('status', d.status, 'attempts', d.attempts, "
                          "'last_error', d.last_error, 'updated_at', d.updated_at, 'sent_at', d.sent_at) END AS delivery, "
                          "coalesce((SELECT json_object_agg(x.proposal_id, json_build_object('status', x.status, "
                          "'core_proposal_id', x.core_proposal_id, 'decided_at', x.decided_at)) "
                          "FROM report_decisions x WHERE x.report_id = r.id), '{}'::json) AS decisions "
                          'FROM reports r LEFT JOIN report_deliveries d ON d.report_id = r.id '
                          'ORDER BY r.created_at DESC LIMIT 20').fetchall()


# Decisions on reported proposals. Called only by the gateway (not forwarded from the browser), which
# applies an approval in core under the operator's request. The agent itself never calls core.
STALE_CLAIM = timedelta(minutes=2)


class DecisionClaim(BaseModel):
    report_id: uuid.UUID
    proposal_id: str = Field(min_length=3, max_length=100)
    decision: Literal['approved', 'rejected']


class DecisionResult(BaseModel):
    report_id: uuid.UUID
    proposal_id: str = Field(min_length=3, max_length=100)
    status: Literal['applied', 'created']
    core_proposal_id: uuid.UUID


@app.post('/decisions')
def claim_decision(claim: DecisionClaim):
    """Claims one proposal of a stored report and returns it exactly as reported, numbers included.

    409 if it was already decided (or is being applied) or, for an approval, if its window is over.
    An 'applying' claim older than two minutes (the gateway died midway) can be claimed again.
    """
    with connect() as db:
        row = db.execute('SELECT report FROM reports WHERE id=%s', (claim.report_id,)).fetchone()
        proposal = next((p for p in (row or {}).get('report', {}).get('proposals', []) if p['id'] == claim.proposal_id), None)
        if proposal is None:
            raise HTTPException(404, 'This report has no such proposal')
        if claim.decision == 'approved' and datetime.fromisoformat(proposal['params']['ends_at']) <= datetime.now(UTC):
            raise HTTPException(409, 'This proposal has expired: its time window is over')
        status = 'applying' if claim.decision == 'approved' else 'rejected'
        claimed = db.execute("""INSERT INTO report_decisions (report_id, proposal_id, status) VALUES (%s, %s, %s)
                                ON CONFLICT (report_id, proposal_id) DO UPDATE SET status = EXCLUDED.status, decided_at = now()
                                WHERE report_decisions.status = 'applying' AND report_decisions.decided_at < now() - %s
                                RETURNING status""", (claim.report_id, claim.proposal_id, status, STALE_CLAIM)).fetchone()
        if claimed is None:
            raise HTTPException(409, 'This proposal has already been decided')
    return {'status': status, 'proposal': proposal}


@app.put('/decisions')
def complete_decision(result: DecisionResult):
    with connect() as db:
        row = db.execute("UPDATE report_decisions SET status=%s, core_proposal_id=%s, decided_at=now() "
                         "WHERE report_id=%s AND proposal_id=%s AND status='applying' RETURNING status",
                         (result.status, result.core_proposal_id, result.report_id, result.proposal_id)).fetchone()
    if row is None:
        raise HTTPException(409, 'No approval in progress for this proposal')
    return {'status': result.status, 'core_proposal_id': str(result.core_proposal_id)}


@app.delete('/decisions')
def release_decision(report_id: uuid.UUID, proposal_id: str):
    """Undoes a claim when core refused the proposal, so the operator can try again."""
    with connect() as db:
        db.execute("DELETE FROM report_decisions WHERE report_id=%s AND proposal_id=%s AND status='applying'",
                   (report_id, proposal_id))
    return {'released': True}


@app.post('/run')
async def run():
    return await execute('manual')
