import os
import json
import smtplib
import pytest
from unter import mailer, report_email

SURGE = {'id': 'Iosefin:surge', 'zone': 'Iosefin', 'type': 'surge', 'reason': 'Riders wait <long> & give up.',
         'params': {'multiplier': 1.45, 'starts_at': '2026-11-04T11:00:00Z', 'ends_at': '2026-11-04T13:00:00Z'}}
BONUS = SURGE | {'id': 'Iosefin:incentive', 'type': 'incentive', 'reason': 'Drivers leave the zone.',
                 'params': {'bonus_per_trip': 9.5, 'starts_at': '2026-11-04T11:00:00Z', 'ends_at': '2026-11-04T13:00:00Z'}}
ZONE = {'zone': 'Iosefin', 'requests': 40, 'requests_per_hour': 1.67, 'unmatched_rate': 0.15, 'cancel_rate': None,
        'worst_p90_wait_s': 270.0, 'net_flow': -30, 'supply_now': {'available': 2}, 'demand_supply_ratio': 4.5,
        'active_surge': {'multiplier': 1.2}, 'active_incentive': None}
DATA = {'report_id': 'r-1', 'run_id': 'run-1', 'source': 'schedule', 'recipients': ['ops@example.com', 'lead@uni.ro'],
        'generated_at': '2026-11-04T10:20:00Z',
        'window': {'from': '2026-11-03T10:20:00.123456Z', 'to': '2026-11-04T10:20:00Z', 'hours': 24.0},
        'summary': 'Iosefin <b>needs</b> drivers.', 'proposals': [SURGE, BONUS],
        'skipped': [{'zone': 'Fabric', 'type': None, 'reason': 'only 5 requests (minimum 20)'}],
        'zones': [ZONE, {'zone': 'Centru', 'requests': 0, 'supply_now': {}}],
        'explained_by': 'model', 'model': 'gpt-test', 'note': None}
SMTP = mailer.Smtp(host='smtp.test', port=587, sender='Unter <reports@unter.test>')


def test_message_has_text_and_html_with_everything_escaped():
    message = report_email.build_message(DATA, SMTP.sender)
    assert message['To'] == 'ops@example.com, lead@uni.ro' and message['From'] == 'Unter <reports@unter.test>'
    assert message['Subject'] == 'Unter surge & incentive report, 04 Nov 2026 10:20 UTC: 2 proposal(s)'
    assert 'report-r-1' in message['Message-ID']
    text = message.get_body(('plain',)).get_content()
    html = message.get_body(('html',)).get_content()
    for body in (text, html):
        assert 'Surge x1.45' in body and 'Driver bonus 9.5 RON per trip' in body
        assert '04 Nov 2026 11:00–13:00 UTC' in body and 'Fabric' in body and 'only 5 requests' in body
        assert '15%' in body and '270 s' in body and 'surge x1.2' in body and 'approves proposals' in body
    assert 'Riders wait <long> & give up.' in text and 'Iosefin <b>needs</b> drivers.' in text
    assert '<long>' not in html and '&lt;long&gt; &amp; give up.' in html and '&lt;b&gt;needs' in html


def test_manual_runs_and_empty_reports_are_marked_in_the_subject():
    assert report_email.subject(DATA | {'source': 'manual', 'proposals': []}).endswith('no proposals [manual run]')
    text = report_email.text_body(DATA | {'proposals': [], 'skipped': []})
    assert 'No proposals for this window.' in text and 'SKIPPED' not in text


class FakeDb:
    """report_deliveries in memory, applying the same rules as the SQL in mailer.record/claim."""
    def __init__(self, status=None, attempts=0):
        self.row = None if status is None else {'status': status, 'attempts': attempts}

    def execute(self, sql, params):
        if sql.lstrip().startswith('INSERT INTO report_deliveries (report_id, status, attempts)'):  # claim
            if self.row and self.row['status'] in mailer.FINAL:
                return self._result(None)
            self.row = {'status': 'sending', 'attempts': (self.row or {'attempts': 0})['attempts'] + 1}
            return self._result({'attempts': self.row['attempts']})
        _, status, error, _ = params  # record
        if not self.row or self.row['status'] != 'sent':
            self.row = {'attempts': 0, **(self.row or {}), 'status': status, 'error': error}
        return self._result(None)

    def commit(self):
        pass

    @staticmethod
    def _result(row):
        return type('Cursor', (), {'fetchone': lambda _: row})()


def sender(fail=None):
    sent = []
    async def send(smtp, message):
        if fail:
            raise fail
        sent.append(message)
    return send, sent


async def test_sends_once_and_skips_duplicates():
    db, (send, sent) = FakeDb(), sender()
    assert await mailer.handle(db, {'data': DATA}, SMTP, send) == 'sent'
    assert await mailer.handle(db, {'data': DATA}, SMTP, send) == 'duplicate'
    assert len(sent) == 1 and db.row['status'] == 'sent' and db.row['attempts'] == 1


async def test_failures_retry_then_park():
    db, (send, sent) = FakeDb(), sender(fail=smtplib.SMTPRecipientsRefused({'ops@example.com': (550, b'no such user')}))
    outcomes = [await mailer.handle(db, {'data': DATA}, SMTP, send) for _ in range(mailer.MAX_ATTEMPTS + 1)]
    assert outcomes == ['failed'] * (mailer.MAX_ATTEMPTS - 1) + ['parked', 'duplicate']
    assert db.row['status'] == 'parked' and db.row['error'] == f'attempt {mailer.MAX_ATTEMPTS}: SMTPRecipientsRefused'
    assert 'ops@example.com' not in db.row['error'] and sent == []


async def test_smtp_errors_keep_only_class_and_code():
    error = smtplib.SMTPAuthenticationError(535, b'5.7.8 bad password for user secret-user')
    assert mailer.safe_error(error) == 'SMTPAuthenticationError (SMTP 535)'


class GmailLikeServer(smtplib.SMTP):
    """Rejects the first auth method with 535, then drops the connection, as Gmail does."""

    def __init__(self, replies):
        super().__init__()  # no host: nothing connects
        self.ehlo_resp = b'smtp.example.com'
        self.esmtp_features = {'auth': ' PLAIN LOGIN'}
        self.replies = list(replies)

    def docmd(self, cmd, args=''):
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def test_rejected_login_is_reported_even_when_the_server_hangs_up():
    server = GmailLikeServer([(535, b'5.7.8 Username and Password not accepted'),
                              smtplib.SMTPServerDisconnected('Connection unexpectedly closed')])
    with pytest.raises(smtplib.SMTPAuthenticationError) as caught:
        mailer.login(server, 'user@example.com', 'app-password')
    assert mailer.safe_error(caught.value) == 'SMTPAuthenticationError (SMTP 535)'


def test_disconnect_without_a_rejection_stays_a_disconnect():
    server = GmailLikeServer([smtplib.SMTPServerDisconnected('Connection unexpectedly closed')])
    with pytest.raises(smtplib.SMTPServerDisconnected):
        mailer.login(server, 'user@example.com', 'app-password')


def test_accepted_login_passes():
    mailer.login(GmailLikeServer([(235, b'2.7.0 Accepted')]), 'user@example.com', 'app-password')


@pytest.mark.parametrize('data, smtp, outcome', [
    (DATA | {'recipients': []}, SMTP, 'skipped'),
    (DATA, None, 'not_configured'),
])
async def test_nothing_to_send(data, smtp, outcome):
    db, (send, sent) = FakeDb(), sender()
    assert await mailer.handle(db, {'data': data}, smtp, send) == outcome
    assert db.row['status'] == outcome and sent == []


class FakeMessage:
    def __init__(self, body):
        self.body, self.message_id, self.acked, self.nacked = body, 'm-1', False, None

    async def ack(self):
        self.acked = True

    async def nack(self, requeue):
        self.nacked = requeue


class FakeExchange:
    def __init__(self):
        self.sent = []

    async def publish(self, message, routing_key):
        self.sent.append((routing_key, json.loads(message.body)))


async def test_failed_send_goes_to_the_retry_queue_and_is_acknowledged(monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(mailer, 'connect', lambda: _context(db))
    monkeypatch.setattr(mailer, 'send_email', sender(fail=ConnectionRefusedError())[0])
    message, exchange = FakeMessage(json.dumps({'id': 'e-1', 'kind': 'report.ready', 'data': DATA}).encode()), FakeExchange()
    assert await mailer.process(message, exchange, SMTP) == 'failed'
    assert message.acked and exchange.sent == [(mailer.RETRY_QUEUE, json.loads(message.body))]


async def test_unreadable_messages_are_dropped():
    message = FakeMessage(b'not json')
    assert await mailer.process(message, FakeExchange(), SMTP) == 'unreadable' and message.acked


async def test_database_trouble_requeues(monkeypatch):
    def broken():
        raise OSError('database down')
    monkeypatch.setattr(mailer, 'connect', broken)
    monkeypatch.setattr(mailer.asyncio, 'sleep', _no_sleep)
    message = FakeMessage(json.dumps({'data': DATA}).encode())
    assert await mailer.process(message, FakeExchange(), SMTP) == 'requeued'
    assert message.nacked is True and not message.acked


@pytest.mark.parametrize('env, expected', [
    ({}, None),
    ({'SMTP_HOST': 'mailpit', 'SMTP_PORT': '1025', 'SMTP_SECURITY': 'none'}, ('mailpit', 1025, 'none')),
    ({'SMTP_HOST': 'smtp.uni.ro', 'SMTP_SECURITY': 'ssl'}, ('smtp.uni.ro', 465, 'ssl')),
    ({'SMTP_HOST': 'smtp.uni.ro'}, ('smtp.uni.ro', 587, 'starttls')),
    ({'SMTP_HOST': 'smtp.uni.ro', 'SMTP_PORT': '', 'SMTP_SECURITY': ''}, ('smtp.uni.ro', 587, 'starttls')),
    ({'SMTP_HOST': ''}, None),
])
def test_smtp_settings_from_env(monkeypatch, env, expected):
    for name in ('SMTP_HOST', 'SMTP_PORT', 'SMTP_SECURITY'):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    smtp = mailer.Smtp.from_env()
    assert (smtp and (smtp.host, smtp.port, smtp.security)) == expected


def test_unknown_smtp_security_is_refused(monkeypatch):
    monkeypatch.setenv('SMTP_HOST', 'smtp.uni.ro')
    monkeypatch.setenv('SMTP_SECURITY', 'tls-maybe')
    with pytest.raises(ValueError):
        mailer.Smtp.from_env()


class _context:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, *exc):
        return False


async def _no_sleep(_):
    pass
