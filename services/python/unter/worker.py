import asyncio
import json
import os
from contextlib import asynccontextmanager
import aio_pika
from fastapi import FastAPI
from .auth import BasicAuth
from .common import connect
from .migrate import upgrade_database
from . import push

ready = False


async def consume():
    global ready
    while True:
        try:
            connection = await aio_pika.connect_robust(
                host=os.getenv('RABBITMQ_HOST', 'rabbitmq'), login='unter',
                password=os.environ['RABBITMQ_PASSWORD'])
            async with connection:
                channel = await connection.channel()
                await channel.set_qos(prefetch_count=10)
                exchange = await channel.declare_exchange('unter.events', 'topic', durable=True)
                queue = await channel.declare_queue('unter.activity', durable=True)
                await queue.bind(exchange, routing_key='#')
                ready = True
                async with queue.iterator() as messages:
                    async for message in messages:
                        async with message.process(requeue=True):
                            event = json.loads(message.body)
                            with connect() as db:
                                inserted = db.execute('INSERT INTO activity(id, kind, payload) VALUES (%s,%s,%s::jsonb) ON CONFLICT DO NOTHING RETURNING id',
                                           (event['id'], event['kind'], json.dumps(event['data']))).fetchone()
                                if inserted:
                                    push.enqueue(db, event)
        except asyncio.CancelledError:
            raise
        except Exception:
            ready = False
            await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app):
    upgrade_database('activity')
    task = asyncio.create_task(consume())
    notifications = asyncio.create_task(push.sender())
    yield
    task.cancel()
    notifications.cancel()
    await asyncio.gather(task, notifications, return_exceptions=True)

app = FastAPI(lifespan=lifespan)
app.add_middleware(BasicAuth)
app.include_router(push.router)


@app.get('/healthz')
def health():
    from fastapi.responses import JSONResponse
    return JSONResponse({'status': 'ok' if ready else 'connecting'}, status_code=200 if ready else 503)


@app.get('/activity')
def activity():
    with connect() as db:
        return db.execute('SELECT * FROM activity ORDER BY created_at DESC LIMIT 50').fetchall()
