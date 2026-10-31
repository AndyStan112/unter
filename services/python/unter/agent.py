"""Agno hello-world runner with a durable, dashboard-controlled cron schedule."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
import json
import os
import uuid
from zoneinfo import ZoneInfo
from croniter import croniter
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator
from agno.agent import Agent
from .model import HelloModel
from agno.tools.mcp import MCPTools
from agno.utils.log import agent_logger

# Provider error text can contain request details. The dashboard records safe codes.
agent_logger.disabled = True
from .auth import BasicAuth, basic_header
from .common import connect
from .migrate import upgrade_database

UTC = timezone.utc
MODEL = os.getenv('OPENAI_MODEL', 'gpt-5-nano')
MODE = os.getenv('AGENT_MODE', 'live')
MAX_DAILY_RUNS = int(os.getenv('MAX_DAILY_RUNS', '30'))
RUN_TIMEOUT = 100
TASK = 'Read list_observations exactly once. Reply Hello world! followed by the example rows, preserving their values. Do not propose or perform changes. Do not call any other tools.'


class Schedule(BaseModel):
    cron: str = Field(default='0 * * * *', max_length=80)
    timezone: str = Field(default='Europe/Bucharest', max_length=80)
    enabled: bool = False

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


async def hello():
    # Both modes exercise the real authenticated MCP -> Java -> database path.
    async with MCPTools(url=os.getenv('MCP_URL', 'http://mcp:8000/mcp'),
                        transport='streamable-http',
                        header_provider=lambda: {'Authorization': basic_header()},
                        include_tools=['list_observations']) as tools:
        if MODE == 'fake':
            rows = await tools.session.call_tool('list_observations', {})
            return 'Hello world! [FAKE MODEL: no API call]\n' + '\n'.join(
                item.text for item in rows.content if hasattr(item, 'text')), ['list_observations']
        agent = Agent(
            name='Unter hello world',
            model=HelloModel(id=MODEL, max_completion_tokens=1200,
                             reasoning_effort="minimal", timeout=40, max_retries=0, retries=0, store=False),
            tools=[tools], tool_call_limit=1,
            tool_choice={'type': 'function', 'function': {'name': 'list_observations'}},
            instructions=TASK, telemetry=False, retries=0,
        )
        response = await agent.arun('Show the example data from MCP. This is a connectivity test only.')
        calls = [call.tool_name for call in (response.tools or [])]
        if 'list_observations' not in calls:
            raise RuntimeError('MCP tool was not called')
        if not response.content:
            raise RuntimeError('Model returned no text')
        return str(response.content), calls


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
        db.commit()
        try:
            text, calls = await asyncio.wait_for(hello(), RUN_TIMEOUT)
            db.execute("UPDATE runs SET status='completed',finished_at=now(),result=%s,tool_calls=%s::jsonb WHERE id=%s",
                       (text, json.dumps(calls), run_id))
        except asyncio.CancelledError:
            db.execute("UPDATE runs SET status='interrupted',finished_at=now(),error='Run interrupted; not retried' WHERE id=%s", (run_id,))
            db.commit()
            raise
        except Exception as error:
            # Provider exceptions can contain request details; persist only their class.
            code = getattr(error, 'status_code', None)
            safe = type(error).__name__ + (f' (HTTP {code})' if isinstance(code, int) else '')
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
    task = asyncio.create_task(scheduler())
    yield
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

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
        row = db.execute('SELECT * FROM schedule WHERE id=1').fetchone()
        return {**row, 'model': MODEL, 'mode': MODE, 'max_daily_runs': MAX_DAILY_RUNS}


@app.put('/schedule')
def save_schedule(value: Schedule):
    with connect() as db:
        db.execute('UPDATE schedule SET cron=%s, timezone=%s, enabled=%s, next_at=%s WHERE id=1',
                   (value.cron, value.timezone, value.enabled, next_time(value.cron, value.timezone)))
    return get_schedule()


@app.get('/runs')
def runs():
    with connect() as db:
        return db.execute('SELECT * FROM runs ORDER BY started_at DESC LIMIT 50').fetchall()


@app.post('/run')
async def run():
    return await execute('manual')
