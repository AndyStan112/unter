"""Test the harness itself; CI also runs it against the real Compose stack."""
import asyncio
import json

import httpx
import pytest

from unter.simulator import Recorder, SimulationFailure, Simulator


@pytest.fixture
def recorder(tmp_path):
    log = Recorder(tmp_path / 'evidence.jsonl')
    yield log
    log.file.close()


async def test_real_http_requests_overlap(recorder):
    """A serial client would deadlock at the server's two-request barrier."""
    arrived = 0
    gate = asyncio.Event()

    async def handler(reader, writer):
        nonlocal arrived
        await reader.readuntil(b'\r\n\r\n')
        arrived += 1
        if arrived == 2:
            gate.set()
        await gate.wait()
        writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}')
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handler, '127.0.0.1', 0)
    port = server.sockets[0].getsockname()[1]
    async with server, httpx.AsyncClient(base_url=f'http://127.0.0.1:{port}') as client:
        sim = Simulator(client, recorder, seed=42)
        results = await asyncio.wait_for(sim.race(
            lambda: sim.get('/one'), lambda: sim.get('/two')), timeout=3)
    assert results == [{}, {}]
    assert recorder.peak_inflight == 2
    assert recorder.failures == 0


@pytest.mark.parametrize(('status', 'body', 'allowed'), [
    (409, {'error': 'offer_expired'}, True),
    (409, {'error': 'offer_not_pending'}, True),
    (409, {'error': 'not_your_offer'}, False),
    (500, {'error': 'internal_error'}, False),
    (401, {'detail': 'Authentication required'}, False),
])
async def test_conflicts_are_operation_specific(recorder, status, body, allowed):
    async def respond(request):
        return httpx.Response(status, json=body)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url='http://test') as client:
        sim = Simulator(client, recorder, seed=42)
        if allowed:
            assert (await sim.post('accept', '/offers/o/accept'))[0] == 409
        else:
            with pytest.raises(SimulationFailure):
                await sim.post('accept', '/offers/o/accept')
        assert recorder.failures == int(not allowed)


async def test_shutdown_observes_inflight_booking(recorder):
    sent, finish = asyncio.Event(), asyncio.Event()

    async def respond(request):
        sent.set()
        await finish.wait()
        return httpx.Response(201, json={'id': 'trip', 'rider_id': 'rider'})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url='http://test') as client:
        sim = Simulator(client, recorder, seed=42)
        task = asyncio.create_task(sim.post('book', '/trips'))
        await sent.wait()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert sim.trips == {'trip': 'rider'}
        assert recorder.inflight == 0


async def test_failure_in_race_waits_for_other_bookings(recorder):
    async def respond(request):
        if request.url.path == '/bad':
            return httpx.Response(500, json={'error': 'internal_error'})
        await asyncio.sleep(.01)
        return httpx.Response(201, json={'id': 'trip', 'rider_id': 'rider'})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url='http://test') as client:
        sim = Simulator(client, recorder, seed=42)
        with pytest.raises(SimulationFailure):
            await sim.race(lambda: sim.post('book', '/bad'), lambda: sim.post('book', '/trips'))
        assert sim.trips == {'trip': 'rider'}
        assert recorder.inflight == 0


async def test_cleanup_completes_picked_up_trip_and_releases_driver(recorder):
    seen = []
    completed, offline = False, False

    async def respond(request):
        nonlocal completed, offline
        seen.append((request.method, request.url.path))
        if request.url.path == '/trips/t/complete':
            completed = True
        if request.url.path == '/drivers/d/offline':
            offline = True
        if request.url.path.startswith('/trips'):
            return httpx.Response(200, json={'status': 'COMPLETED' if completed else 'PICKED_UP',
                                           'rider_id': 'r', 'driver_id': 'd'})
        return httpx.Response(200, json={'status': 'OFFLINE' if offline else 'ON_TRIP',
                                       'current_trip_id': None if offline else 't'})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url='http://test') as client:
        sim = Simulator(client, recorder, seed=42)
        sim.trips = {'t': 'r'}
        sim.drivers = ['d']
        await sim.cleanup()
    assert seen.index(('POST', '/trips/t/complete')) < seen.index(('POST', '/drivers/d/offline'))
    assert recorder.failures == 0


def test_evidence_preserves_expected_conflicts_and_failures(recorder):
    recorder.latencies['accept'].extend([1, 2, 3, 100])
    recorder.counts['accept:409'] = 3
    recorder.check(True, 'one winner')
    with pytest.raises(SimulationFailure):
        recorder.check(False, 'inconsistent driver')
    summary = recorder.summary()
    assert summary['failures'] == 1
    assert summary['latency_ms']['accept']['p95'] == 100
    assert summary['requests']['accept:409'] == 3
    rows = [json.loads(line) for line in open(recorder.file.name)]
    assert [row['passed'] for row in rows] == [True, False]


async def test_preflight_refuses_active_foreign_driver_without_writes(recorder):
    writes = []

    async def respond(request):
        if request.method != 'GET':
            writes.append(request.url.path)
        if request.url.path == '/zones':
            return httpx.Response(200, json=[{'name': 'Centru', 'lat': 45.75, 'lon': 21.22}])
        return httpx.Response(200, json=[{'id': 'foreign', 'status': 'AVAILABLE'}])

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url='http://test') as client:
        sim = Simulator(client, recorder, seed=42)
        with pytest.raises(SimulationFailure, match='existing drivers offline'):
            await sim.setup(2, 1)
        await sim.cleanup()
    assert writes == []


async def test_cleanup_does_not_hide_driver_still_busy(recorder):
    async def respond(request):
        return httpx.Response(409, json={'error': 'driver_busy'}) if request.method == 'POST' else httpx.Response(
            200, json={'status': 'ON_TRIP', 'current_trip_id': 't'})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url='http://test') as client:
        sim = Simulator(client, recorder, seed=42)
        sim.drivers = ['d']
        with pytest.raises(SimulationFailure, match='all owned trips and drivers cleaned up'):
            await sim.cleanup()
    assert recorder.failures > 0
