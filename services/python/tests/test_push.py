import base64
from types import SimpleNamespace
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid
from pywebpush import webpush
from unter.push import valid_endpoint, notification


@pytest.mark.parametrize('endpoint', ['http://fcm.googleapis.com/a', 'https://localhost/a',
    'https://127.0.0.1/a', 'https://fcm.googleapis.com.evil.test/a',
    'https://user:password@fcm.googleapis.com/a', 'https://fcm.googleapis.com:444/a'])
def test_subscription_cannot_send_to_arbitrary_network_hosts(endpoint):
    assert not valid_endpoint(endpoint)


def test_offer_notification_uses_offer_driver_and_expiry():
    result = notification({'id': 'e1', 'kind': 'trip.offered', 'data': {
        'trip': {'rider_id': 'r1'}, 'offer': {'driver_id': 'd1', 'expires_at': '2030-01-01T12:00:00Z'}}})
    assert result[0:2] == ('driver', 'd1') and result[-1] == '2030-01-01T12:00:00Z'
    assert notification({'kind': 'report.ready', 'data': {}}) is None


def test_completed_trip_notifies_passenger_about_mock_settlement():
    result = notification({'id': 'e1', 'kind': 'trip.completed', 'data': {'trip': {'rider_id': 'r1'}}})
    assert result[0:2] == ('passenger', 'r1') and 'mock' in result[2]


def test_generated_pem_key_encrypts_and_signs_web_push_without_network():
    private = ec.generate_private_key(ec.SECP256R1())
    receiver = ec.generate_private_key(ec.SECP256R1())
    encode = lambda value: base64.urlsafe_b64encode(value).rstrip(b'=').decode()
    pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    subscription = {'endpoint': 'https://fcm.googleapis.com/test', 'keys': {
        'p256dh': encode(receiver.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)),
        'auth': encode(b'0123456789abcdef')}}
    calls = []
    class Session:
        def post(self, endpoint, **kwargs):
            calls.append((endpoint, kwargs))
            return SimpleNamespace(status_code=201, text='', headers={})
    webpush(subscription, data='{"title":"Ride update"}', vapid_private_key=Vapid.from_pem(pem),
            vapid_claims={'sub': 'https://unter.windogs.win'}, requests_session=Session(), ttl=30, timeout=5)
    assert len(calls) == 1 and calls[0][1]['headers']['Authorization'].startswith('vapid ')
    assert calls[0][1]['data'] != b'{"title":"Ride update"}'


@pytest.mark.parametrize('subscription', [
    {'endpoint': 123},
    {'endpoint': 'https://127.0.0.1/push', 'keys': {}},
    {'endpoint': 'https://fcm.googleapis.com/test', 'keys': {'p256dh': 'A' * 87, 'auth': 'A' * 22}},
])
def test_malformed_subscriptions_are_rejected_before_database_access(subscription):
    from fastapi import HTTPException
    from unter.push import Subscription, subscribe
    with pytest.raises(HTTPException) as caught:
        subscribe(Subscription(role='driver', profile_id='00000000-0000-4000-8000-000000000001', subscription=subscription))
    assert caught.value.status_code == 422
