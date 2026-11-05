"""Emails each report.ready to its recipients (SERVICE_MODULE=mailer).

Consumes its own durable queue unter.reports, bound to report.ready on unter.events. Delivery state
lives in the agent database's report_deliveries table (the agent owns that database and its
migrations; the dashboard shows the state with each report):

- A report already 'sent' is acknowledged without sending again (at-least-once delivery upstream).
- A failed send is retried through unter.reports.retry, a queue without consumers whose messages
  expire after MAIL_RETRY_SECONDS and dead-letter back into unter.reports.
- After MAIL_MAX_ATTEMPTS failures the delivery is 'parked': no more retries, shown in the dashboard.
- No recipients: 'skipped'. No SMTP_HOST: 'not_configured'. Both are final.
"""
import asyncio
import json
import os
import smtplib
import ssl
from contextlib import asynccontextmanager
from dataclasses import dataclass
import aio_pika
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from .common import connect
from .report_email import build_message

QUEUE = 'unter.reports'
RETRY_QUEUE = 'unter.reports.retry'
MAX_ATTEMPTS = int(os.getenv('MAIL_MAX_ATTEMPTS', '5'))
RETRY_SECONDS = int(os.getenv('MAIL_RETRY_SECONDS', '60'))
FINAL = ('sent', 'skipped', 'not_configured', 'parked')
ready = False


@dataclass(frozen=True)
class Smtp:
    host: str
    port: int
    sender: str
    security: str = 'starttls'  # starttls | ssl | none (none only for a local catcher like Mailpit)
    user: str | None = None
    password: str | None = None
    timeout: float = 20

    @classmethod
    def from_env(cls) -> 'Smtp | None':
        if not os.getenv('SMTP_HOST'):
            return None
        security = os.getenv('SMTP_SECURITY') or 'starttls'  # Compose passes unset values as ''
        if security not in ('starttls', 'ssl', 'none'):
            raise ValueError('SMTP_SECURITY must be starttls, ssl or none')
        return cls(host=os.environ['SMTP_HOST'], port=int(os.getenv('SMTP_PORT') or ('465' if security == 'ssl' else '587')),
                   sender=os.getenv('MAIL_FROM') or 'unter-reports@localhost', security=security,
                   user=os.getenv('SMTP_USER') or None, password=os.getenv('SMTP_PASSWORD') or None)


def _send(smtp: Smtp, message) -> None:
    context = ssl.create_default_context()
    client_class = smtplib.SMTP_SSL if smtp.security == 'ssl' else smtplib.SMTP
    extra = {'context': context} if smtp.security == 'ssl' else {}
    with client_class(smtp.host, smtp.port, timeout=smtp.timeout, **extra) as client:
        if smtp.security == 'starttls':
            client.starttls(context=context)
        if smtp.user:
            client.login(smtp.user, smtp.password or '')
        client.send_message(message)


async def send_email(smtp: Smtp, message) -> None:
    await asyncio.to_thread(_send, smtp, message)


def safe_error(error: Exception) -> str:
    # SMTP errors can echo server text or addresses; keep the class and the SMTP code only.
    code = getattr(error, 'smtp_code', None)
    return type(error).__name__ + (f' (SMTP {code})' if isinstance(code, int) else '')


def record(db, report_id: str, status: str, error: str | None = None) -> None:
    """Sets the delivery state, never overwriting a 'sent' one."""
    db.execute("""INSERT INTO report_deliveries (report_id, status, last_error, sent_at)
                  VALUES (%s, %s, %s, CASE WHEN %s = 'sent' THEN now() END)
                  ON CONFLICT (report_id) DO UPDATE SET status = EXCLUDED.status, last_error = EXCLUDED.last_error,
                      sent_at = EXCLUDED.sent_at, updated_at = now()
                  WHERE report_deliveries.status <> 'sent'""", (report_id, status, error, status))
    db.commit()


def claim(db, report_id: str) -> int | None:
    """Starts an attempt and returns its number, or None when the report needs no (more) sending."""
    row = db.execute("""INSERT INTO report_deliveries (report_id, status, attempts) VALUES (%s, 'sending', 1)
                        ON CONFLICT (report_id) DO UPDATE SET status = 'sending',
                            attempts = report_deliveries.attempts + 1, updated_at = now()
                        WHERE report_deliveries.status NOT IN ('sent', 'skipped', 'not_configured', 'parked')
                        RETURNING attempts""", (report_id,)).fetchone()
    db.commit()
    return row['attempts'] if row else None


async def handle(db, event: dict, smtp: Smtp | None, send=None) -> str:
    """One report.ready. Returns the outcome; 'failed' means the caller schedules a retry."""
    data = event['data']
    report_id = data['report_id']
    if not data.get('recipients'):
        record(db, report_id, 'skipped', 'no recipients configured')
        return 'skipped'
    if smtp is None:
        record(db, report_id, 'not_configured', 'SMTP_HOST is not set')
        return 'not_configured'
    attempt = claim(db, report_id)
    if attempt is None:
        return 'duplicate'
    try:
        await (send or send_email)(smtp, build_message(data, smtp.sender))
    except Exception as error:
        status = 'parked' if attempt >= MAX_ATTEMPTS else 'failed'
        record(db, report_id, status, f'attempt {attempt}: {safe_error(error)}')
        return status
    record(db, report_id, 'sent')
    return 'sent'


def parse(body: bytes) -> dict | None:
    try:
        event = json.loads(body)
        str(event['data']['report_id'])
        return event
    except (ValueError, KeyError, TypeError):
        return None


async def process(message, retry_exchange, smtp: Smtp | None) -> str:
    """Acknowledges once the outcome is recorded; database or broker trouble requeues after a pause."""
    try:
        event = parse(message.body)
        if event is None:
            await message.ack()  # Unreadable: nothing could ever send it.
            return 'unreadable'
        with connect() as db:
            outcome = await handle(db, event, smtp)
        if outcome == 'failed':
            await retry_exchange.publish(aio_pika.Message(message.body, content_type='application/json',
                                                          message_id=message.message_id,
                                                          delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
                                         routing_key=RETRY_QUEUE)
        await message.ack()
        return outcome
    except asyncio.CancelledError:
        raise
    except Exception:
        await asyncio.sleep(5)  # don't spin on a database outage
        await message.nack(requeue=True)
        return 'requeued'


async def consume(smtp: Smtp | None):
    global ready
    while True:
        try:
            connection = await aio_pika.connect_robust(host=os.getenv('RABBITMQ_HOST', 'rabbitmq'), login='unter',
                                                       password=os.environ['RABBITMQ_PASSWORD'])
            async with connection:
                channel = await connection.channel(publisher_confirms=True)
                await channel.set_qos(prefetch_count=1)
                exchange = await channel.declare_exchange('unter.events', 'topic', durable=True)
                queue = await channel.declare_queue(QUEUE, durable=True)
                await queue.bind(exchange, routing_key='report.ready')
                await channel.declare_queue(RETRY_QUEUE, durable=True, arguments={
                    'x-message-ttl': RETRY_SECONDS * 1000, 'x-dead-letter-exchange': '',
                    'x-dead-letter-routing-key': QUEUE})
                ready = True
                async with queue.iterator() as messages:
                    async for message in messages:
                        await process(message, channel.default_exchange, smtp)
        except asyncio.CancelledError:
            raise
        except Exception:
            ready = False
            await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app):
    # Invalid SMTP settings stop the service at startup instead of failing every send.
    app.state.smtp = Smtp.from_env()
    task = asyncio.create_task(consume(app.state.smtp))
    yield
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

# No private endpoints, so no login: the mailer holds no credential for core or the other services.
app = FastAPI(lifespan=lifespan)


@app.get('/healthz')
def health():
    return JSONResponse({'status': 'ok' if ready else 'connecting', 'smtp': app.state.smtp is not None},
                        status_code=200 if ready else 503)
