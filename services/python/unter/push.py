"""Web Push delivery from durable activity events. No credentials in notification payloads."""
import asyncio
import base64
import json
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from .common import connect

router = APIRouter()
PUSH_HOSTS = ('fcm.googleapis.com', 'updates.push.services.mozilla.com', 'web.push.apple.com')


def valid_endpoint(endpoint):
    parsed = urlparse(endpoint)
    host = parsed.hostname or ''
    return (parsed.scheme == 'https' and not parsed.username and not parsed.password
            and parsed.port in (None, 443) and not parsed.fragment
            and (host in PUSH_HOSTS or host.endswith('.notify.windows.com')))


def identity(db):
    row = db.execute('SELECT * FROM push_identity WHERE id=1').fetchone()
    if row:
        return row
    key = ec.generate_private_key(ec.SECP256R1())
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()
    public = base64.urlsafe_b64encode(key.public_key().public_bytes(serialization.Encoding.X962,
                                   serialization.PublicFormat.UncompressedPoint)).rstrip(b'=').decode()
    db.execute('INSERT INTO push_identity VALUES (1,%s,%s) ON CONFLICT DO NOTHING', (private, public))
    return db.execute('SELECT * FROM push_identity WHERE id=1').fetchone()


@router.get('/push-key')
def public_key():
    with connect() as db:
        return {'public_key': identity(db)['public_key']}


class Subscription(BaseModel):
    role: Literal['driver', 'passenger']
    profile_id: uuid.UUID
    subscription: dict


@router.post('/push-subscriptions')
def subscribe(body: Subscription):
    data = body.subscription
    try:
        if (len(json.dumps(data)) > 4096 or not isinstance(data.get('endpoint'), str)
                or len(data['endpoint']) > 2048 or not valid_endpoint(data['endpoint'])):
            raise ValueError('Invalid endpoint')
        keys = data['keys']
        public = base64.urlsafe_b64decode(keys['p256dh'] + '===')
        if len(public) != 65:
            raise ValueError('Invalid public key')
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public)
        if len(base64.urlsafe_b64decode(keys['auth'] + '===')) != 16:
            raise ValueError('Invalid auth secret')
    except (KeyError, TypeError, ValueError):
        raise HTTPException(422, 'Invalid push subscription') from None
    with connect() as db:
        row = db.execute('''INSERT INTO push_subscriptions(id,endpoint,subscription,role,profile_id) VALUES (%s,%s,%s::jsonb,%s,%s)
            ON CONFLICT(endpoint) DO UPDATE SET subscription=EXCLUDED.subscription, role=EXCLUDED.role,
              profile_id=EXCLUDED.profile_id, updated_at=now() RETURNING id''',
            (uuid.uuid4(), data['endpoint'], json.dumps(data), body.role, body.profile_id)).fetchone()
    return {'id': str(row['id'])}


class Unsubscribe(BaseModel):
    endpoint: str = Field(max_length=2048)


@router.post('/push-unsubscribe')
def unsubscribe(body: Unsubscribe):
    with connect() as db:
        db.execute('DELETE FROM push_subscriptions WHERE endpoint=%s', (body.endpoint,))
    return {'status': 'disabled'}


def notification(event):
    kind, data = event['kind'], event['data']
    trip = data.get('trip') or {}
    if kind == 'trip.offered':
        offer = data['offer']
        return ('driver', offer['driver_id'], 'New ride request', 'Open Unter to review this offer.', offer['expires_at'])
    titles = {'trip.assigned': 'Your driver accepted', 'trip.picked_up': 'Your ride has started',
              'trip.completed': 'Ride completed · mock payment settled', 'trip.unmatched': 'No driver found',
              'trip.cancelled': 'Ride cancelled'}
    if kind not in titles or not trip:
        return None
    expires = (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()
    return ('passenger', trip['rider_id'], titles[kind], 'Open Unter for the latest ride status.', expires)


def enqueue(db, event):
    message = notification(event)
    if not message:
        return
    role, profile, title, body, expires = message
    targets = [(role, profile, title)]
    if event['kind'] == 'trip.cancelled' and event['data']['trip'].get('driver_id'):
        targets.append(('driver', event['data']['trip']['driver_id'], title))
    for role, profile, title in targets:
        payload = {'title': title, 'body': body, 'url': '/ride/' + role,
                   'tag': event['id'], 'expires_at': expires}
        db.execute('''INSERT INTO push_deliveries(event_id,subscription_id,payload,expires_at)
            SELECT %s,id,%s::jsonb,%s FROM push_subscriptions WHERE role=%s AND profile_id=%s
            ON CONFLICT DO NOTHING''', (event['id'], json.dumps(payload), expires, role, profile))


def send_batch():
    from pywebpush import webpush, WebPushException
    from py_vapid import Vapid
    from requests import RequestException
    with connect() as db:
        db.execute('DELETE FROM push_deliveries WHERE expires_at <= now() OR attempts >= 5')
        rows = db.execute('''SELECT d.*,s.subscription FROM push_deliveries d JOIN push_subscriptions s ON s.id=d.subscription_id
            WHERE next_attempt_at <= now() ORDER BY next_attempt_at LIMIT 20 FOR UPDATE OF d SKIP LOCKED''').fetchall()
        if not rows:
            return
        keys = identity(db)
        for row in rows:
            try:
                ttl = max(1, int((row['expires_at'] - datetime.now(timezone.utc)).total_seconds()))
                webpush(subscription_info=row['subscription'], data=json.dumps(row['payload']),
                        vapid_private_key=Vapid.from_pem(keys['private_key'].encode()), vapid_claims={'sub': 'https://unter.windogs.win'},
                        ttl=ttl, timeout=5)
            except (WebPushException, RequestException) as error:
                if error.response is not None and error.response.status_code in (404, 410):
                    db.execute('DELETE FROM push_subscriptions WHERE id=%s', (row['subscription_id'],))
                    continue
                db.execute('UPDATE push_deliveries SET attempts=attempts+1,next_attempt_at=now()+interval \'15 seconds\' WHERE event_id=%s AND subscription_id=%s',
                           (row['event_id'], row['subscription_id']))
                continue
            except (ValueError, TypeError, KeyError):
                # Corrupt restored subscriptions must not block delivery to other devices.
                db.execute('DELETE FROM push_subscriptions WHERE id=%s', (row['subscription_id'],))
                continue
            db.execute('DELETE FROM push_deliveries WHERE event_id=%s AND subscription_id=%s',
                       (row['event_id'], row['subscription_id']))


async def sender():
    while True:
        try:
            await asyncio.to_thread(send_batch)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass  # Delivery state stays durable. Never log subscription endpoints or private keys.
        await asyncio.sleep(2)
