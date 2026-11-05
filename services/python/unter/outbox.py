"""The agent's outbox: events stored with the report in one transaction, then published to RabbitMQ.

Same pattern and envelope as core (Outbox.java + Events.java): {"id", "kind", "data"} on the
unter.events topic exchange, routing key = kind, persistent, with publisher confirms. A row is marked
sent only after RabbitMQ confirmed it, so delivery is at least once: consumers skip ids they've seen.
"""
import asyncio
import json
import os
import uuid
import aio_pika
from .common import connect

EXCHANGE = 'unter.events'
BATCH = 50


def add(db, kind: str, data: dict) -> uuid.UUID:
    """Records an event in the caller's transaction; it is published once that commits."""
    event_id = uuid.uuid4()
    db.execute('INSERT INTO agent_outbox (id, kind, payload) VALUES (%s, %s, %s::jsonb)',
               (event_id, kind, json.dumps(data, default=str)))
    return event_id


def message(row: dict) -> aio_pika.Message:
    body = json.dumps({'id': str(row['id']), 'kind': row['kind'], 'data': row['payload']}).encode()
    return aio_pika.Message(body, content_type='application/json', message_id=str(row['id']),
                            delivery_mode=aio_pika.DeliveryMode.PERSISTENT)


async def publish_batch(db, exchange) -> int:
    """Publishes up to BATCH unsent events in order; each is marked sent once RabbitMQ confirmed it."""
    rows = db.execute('SELECT id, kind, payload FROM agent_outbox WHERE NOT sent ORDER BY seq LIMIT %s',
                      (BATCH,)).fetchall()
    db.commit()
    for row in rows:
        await exchange.publish(message(row), routing_key=row['kind'])
        db.execute('UPDATE agent_outbox SET sent = true WHERE id = %s', (row['id'],))
        db.commit()
    return len(rows)


async def publisher(poll_seconds: float = 1.0):
    """Runs for the life of the agent. RabbitMQ or database outages only delay events: unsent rows stay."""
    while True:
        try:
            connection = await aio_pika.connect_robust(host=os.getenv('RABBITMQ_HOST', 'rabbitmq'), login='unter',
                                                       password=os.environ['RABBITMQ_PASSWORD'])
            async with connection:
                channel = await connection.channel(publisher_confirms=True)
                exchange = await channel.declare_exchange(EXCHANGE, 'topic', durable=True)
                while True:
                    with connect() as db:
                        while await publish_batch(db, exchange) == BATCH:
                            pass
                    await asyncio.sleep(poll_seconds)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Never log the error: it can contain connection details. Unsent rows are retried.
            await asyncio.sleep(5)
