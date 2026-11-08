import os
os.environ.setdefault('SERVICE_USERNAME', 'test-service')
os.environ.setdefault('SERVICE_PASSWORD', 'test-password')
import json
import uuid
import pytest
from pydantic import ValidationError
from unter import outbox, report
from unter.agent import Schedule, store_report

BUILT = {'generated_at': '2026-11-04T10:20:00Z',
         'window': {'from': '2026-11-03T10:20:00Z', 'to': '2026-11-04T10:20:00Z', 'hours': 24.0},
         'summary': 'Iosefin is short of drivers.', 'proposals': [{'id': 'Iosefin:surge'}], 'skipped': [],
         'zones': [], 'explained_by': 'template', 'model': None, 'note': 'fake mode: no model call'}


class FakeDb:
    """Records statements and commits; answers SELECTs with the rows it was given."""
    def __init__(self, rows=()):
        self.rows, self.log = list(rows), []

    def execute(self, sql, params=()):
        self.log.append((' '.join(sql.split()), params))
        rows = self.rows if sql.lstrip().startswith('SELECT') else []
        return type('Cursor', (), {'fetchall': lambda _: rows, 'fetchone': lambda _: rows[0] if rows else None})()

    def commit(self):
        self.log.append(('COMMIT', None))


class FakeExchange:
    def __init__(self, fail_on=None):
        self.sent, self.fail_on = [], fail_on

    async def publish(self, message, routing_key):
        if routing_key == self.fail_on:
            raise ConnectionError('broker gone')
        self.sent.append((routing_key, json.loads(message.body), message.delivery_mode, message.message_id))


def test_recipients_are_cleaned_and_deduplicated():
    value = Schedule(recipients=[' Ops@Example.com', 'ops@example.com', 'team.lead+unter@uni.ro'], window_hours=12)
    assert value.recipients == ['ops@example.com', 'team.lead+unter@uni.ro'] and value.window_hours == 12
    assert Schedule().recipients is None and Schedule().window_hours is None  # left out: keep what is stored


@pytest.mark.parametrize('recipients', [
    ['not-an-email'], ['a@b'], ['two words@example.com'], ['a@example.com\nBcc: x@evil.com'],
    ['"Ops" <ops@example.com>'], ['a@example.com, b@example.com'], [f'{"x" * 250}@example.com'],
    [f'u{i}@example.com' for i in range(21)],
])
def test_bad_recipients_are_refused(recipients):
    with pytest.raises(ValidationError):
        Schedule(recipients=recipients)


@pytest.mark.parametrize('hours', [0, 169, -1])
def test_window_hours_are_bounded(hours):
    with pytest.raises(ValidationError):
        Schedule(window_hours=hours)


def test_report_and_event_are_written_in_one_transaction():
    db, run_id = FakeDb(), uuid.uuid4()
    report_id = store_report(db, run_id, 'schedule', BUILT, ['ops@example.com'])
    (insert_report, report_params), (insert_event, event_params) = db.log
    assert ('COMMIT', None) not in db.log, 'the caller commits both together'
    assert insert_report.startswith('INSERT INTO reports') and report_params[:4] == (
        report_id, run_id, BUILT['window']['from'], BUILT['window']['to'])
    assert json.loads(report_params[4]) == BUILT
    assert insert_event.startswith('INSERT INTO agent_outbox') and event_params[1] == 'report.ready'
    data = json.loads(event_params[2])
    assert data['report_id'] == str(report_id) and data['run_id'] == str(run_id) and data['source'] == 'schedule'
    assert data['recipients'] == ['ops@example.com'] and data['summary'] == BUILT['summary']
    assert data['proposals'] == BUILT['proposals']


def test_run_result_is_the_summary_with_a_pointer_to_the_report():
    text = report.run_result('r1', BUILT)
    assert text.startswith(BUILT['summary']) and 'Report r1: 1 proposal(s), text by template.' in text


async def test_publisher_sends_core_envelope_in_order_and_marks_each_sent():
    rows = [{'id': uuid.uuid4(), 'kind': 'report.ready', 'payload': {'report_id': str(n)}} for n in range(2)]
    db, exchange = FakeDb(rows), FakeExchange()
    assert await outbox.publish_batch(db, exchange) == 2
    assert [(key, body) for key, body, _, _ in exchange.sent] == [
        ('report.ready', {'id': str(r['id']), 'kind': 'report.ready', 'data': r['payload']}) for r in rows]
    assert all(mode == outbox.aio_pika.DeliveryMode.PERSISTENT and mid for _, _, mode, mid in exchange.sent)
    updates = [params for sql, params in db.log if sql.startswith('UPDATE agent_outbox')]
    assert updates == [(rows[0]['id'],), (rows[1]['id'],)]
    assert db.log[-1] == ('COMMIT', None)


async def test_an_unconfirmed_event_is_not_marked_sent():
    rows = [{'id': uuid.uuid4(), 'kind': 'report.ready', 'payload': {}},
            {'id': uuid.uuid4(), 'kind': 'report.failed', 'payload': {}}]
    db = FakeDb(rows)
    with pytest.raises(ConnectionError):
        await outbox.publish_batch(db, FakeExchange(fail_on='report.failed'))
    updates = [params for sql, params in db.log if sql.startswith('UPDATE agent_outbox')]
    assert updates == [(rows[0]['id'],)], 'the first stays sent, the second is retried later'
