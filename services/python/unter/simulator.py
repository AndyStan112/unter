"""Concurrent, stateful HTTP clients for an isolated Unter stack. No database writes."""
import argparse
import asyncio
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import random
import time
import uuid

import httpx
from dotenv import load_dotenv

TERMINAL = {'COMPLETED', 'CANCELLED', 'UNMATCHED'}
CONFLICTS = {
    'book': {'rider_has_open_trip'},
    'accept': {'offer_expired', 'offer_not_pending'},
    'reject': {'offer_expired', 'offer_not_pending'},
    'cancel': {'trip_not_cancellable'},
    'pickup': {'trip_not_assigned'},
    'complete': {'trip_not_picked_up'},
    'offline': {'driver_busy'},
}


def now():
    return datetime.now(timezone.utc).isoformat()


class SimulationFailure(RuntimeError):
    pass


class Recorder:
    def __init__(self, path):
        self.file = Path(path).open('x', encoding='utf-8')
        self.counts = Counter()
        self.latencies = defaultdict(lambda: deque(maxlen=10000))
        self.failures = 0
        self.started = time.monotonic()
        self.inflight = 0
        self.peak_inflight = 0

    def emit(self, kind, **values):
        self.file.write(json.dumps({'at': now(), 'kind': kind, **values}) + '\n')
        self.file.flush()

    def check(self, condition, name):
        self.emit('check', name=name, passed=bool(condition))
        if not condition:
            self.failures += 1
            raise SimulationFailure(name)

    def summary(self):
        elapsed = max(.001, time.monotonic() - self.started)
        return {
            'elapsed_seconds': round(elapsed, 3),
            'requests_per_second': round(sum(self.counts.values()) / elapsed, 3),
            'requests': dict(self.counts), 'failures': self.failures,
            'peak_inflight': self.peak_inflight,
            'latency_ms': {op: {'samples': len(values), 'p50': percentile(values, .5),
                                'p95': percentile(values, .95), 'max': round(max(values), 2)}
                           for op, values in self.latencies.items()},
        }


def percentile(values, fraction):
    return round(sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)], 2)


class Simulator:
    def __init__(self, client, recorder, seed, pace=1.0):
        self.client, self.log = client, recorder
        self.seed, self.pace = seed, pace
        self.riders, self.drivers, self.trips = [], [], {}
        self.outcomes = Counter()
        self.zones = []
        self.started = time.monotonic()
        self.tag = f'sim-{uuid.uuid4().hex[:10]}'

    async def call(self, op, method, path, body=None):
        task = asyncio.create_task(self._call(op, method, path, body))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # Observe the final response and register committed bookings before cleanup.
            await task
            raise

    async def _call(self, op, method, path, body=None):
        start = time.monotonic()
        self.log.inflight += 1
        self.log.peak_inflight = max(self.log.peak_inflight, self.log.inflight)
        code, error = 0, None
        try:
            response = await self.client.request(method, path, json=body)
            code = response.status_code
            data = response.json() if response.content else None
            error = data.get('error') if isinstance(data, dict) else None
            accepted = code in (200, 201, 204) or (code == 409 and error in CONFLICTS.get(op, set()))
            if not accepted:
                raise SimulationFailure(f'{op}: HTTP {code}, error={error}')
            # Register every successful booking, including both responses if an invariant is broken.
            if op == 'book' and code == 201:
                self.trips[data['id']] = data['rider_id']
                self.log.emit('trip', id=data['id'], rider_id=data['rider_id'])
            return code, data
        except (httpx.HTTPError, ValueError, SimulationFailure) as exc:
            self.log.failures += 1
            self.log.emit('failure', operation=op, category=type(exc).__name__, status=code)
            raise SimulationFailure(f'{op} failed (see request log)') from None
        finally:
            elapsed = (time.monotonic() - start) * 1000
            self.log.inflight -= 1
            self.log.counts[f'{op}:{code}'] += 1
            self.log.latencies[op].append(elapsed)
            self.log.emit('request', operation=op, path=path.split('?')[0], status=code, error=error, latency_ms=round(elapsed, 2))

    async def get(self, path):
        return (await self.call('read', 'GET', path))[1]

    async def post(self, op, path, body=None):
        return await self.call(op, 'POST', path, body)

    def point(self, rng, hotspot=True):
        # A rotating hotspot receives 80% of pickups; the rest explore all zones.
        index = int((time.monotonic() - self.started) / (60 * self.pace)) % len(self.zones)
        zone = self.zones[index] if hotspot and rng.random() < .8 else rng.choice(self.zones)
        return {'lat': zone['lat'] + rng.uniform(-.001, .001),
                'lon': zone['lon'] + rng.uniform(-.001, .001)}

    def booking(self, rider, rng):
        return {'rider_id': rider, 'pickup': self.point(rng), 'dropoff': self.point(rng, False)}

    async def race(self, *calls):
        # Create all tasks before releasing them. Connections are pooled, not serialized.
        gate = asyncio.Event()
        async def fire(call):
            await gate.wait()
            return await call()
        tasks = [asyncio.create_task(fire(call)) for call in calls]
        gate.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                raise result
        return results

    async def setup(self, riders, drivers):
        self.zones = await self.get('/zones')
        self.log.check(bool(self.zones), 'zones available')
        # Targeted scenarios must not claim someone else's offer or affect existing traffic.
        existing = await self.get('/drivers')
        self.log.check(all(d['status'] == 'OFFLINE' for d in existing), 'isolated stack: existing drivers offline')
        for status in ('REQUESTED', 'OFFERED', 'ASSIGNED', 'PICKED_UP'):
            self.log.check(not await self.get(f'/trips?status={status}&limit=1'), f'isolated stack: no {status} trips')
        for kind, count, ids in [('riders', riders, self.riders), ('drivers', drivers, self.drivers)]:
            for i in range(count):
                _, actor = await self.post('create', f'/{kind}', {'name': f'{self.tag}-{kind}-{i}'})
                ids.append(actor['id'])
                self.log.emit('actor', role=kind, id=actor['id'])
        rng = random.Random(self.seed)
        for driver in self.drivers:
            await self.post('online', f'/drivers/{driver}/online')
            await self.post('location', f'/drivers/{driver}/location', self.point(rng))

    async def offer_for(self, trip):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            for driver in self.drivers:
                offer = await self.get(f'/drivers/{driver}/offer')
                if offer and offer['trip']['id'] == trip:
                    return driver, offer['offer']['id']
            await asyncio.sleep(.1)
        self.log.check(False, 'targeted scenario received an offer within 15s')

    async def settle(self, trip_id):
        trip = await self.get(f'/trips/{trip_id}')
        if trip['status'] == 'PICKED_UP':
            await self.post('complete', f'/trips/{trip_id}/complete', {'driver_id': trip['driver_id']})
        elif trip['status'] not in TERMINAL:
            await self.post('cancel', f'/trips/{trip_id}/cancel', {'rider_id': trip['rider_id']})

    async def targeted(self):
        rng = random.Random(self.seed)
        self.log.emit('scenario', name='scarce_supply')
        for driver in self.drivers[1:]:
            await self.post('offline', f'/drivers/{driver}/offline')
        bodies = [self.booking(rider, rng) for rider in self.riders]
        results = await self.race(*[lambda body=body: self.post('book', '/trips', body) for body in bodies])
        trips = [data for _, data in results]
        states = [await self.get(f'/trips/{trip["id"]}') for trip in trips]
        held = await self.get(f'/drivers/{self.drivers[0]}')
        offered = [trip for trip in states if trip['status'] == 'OFFERED']
        self.log.check(len(offered) == 1 and held['status'] == 'OFFERED'
                       and held['current_trip_id'] == offered[0]['id'],
                       'concurrent trips reserve the sole available driver once')
        for trip in trips:
            await self.settle(trip['id'])
        for driver in self.drivers:
            await self.post('online', f'/drivers/{driver}/online')
        for scenario in ('duplicate_booking', 'duplicate_accept', 'accept_cancel', 'accept_offline'):
            rider = self.riders[0]
            body = self.booking(rider, rng)
            self.log.emit('scenario', name=scenario)
            if scenario == 'duplicate_booking':
                results = await self.race(*[lambda: self.post('book', '/trips', body) for _ in range(8)])
                self.log.check(sum(code == 201 for code, _ in results) == 1, 'one winner for concurrent rider bookings')
                trip = next(data for code, data in results if code == 201)
            else:
                _, trip = await self.post('book', '/trips', body)
            trip_id = trip['id']
            driver, offer = await self.offer_for(trip_id)
            accept = lambda: self.post('accept', f'/offers/{offer}/accept', {'driver_id': driver})
            if scenario == 'duplicate_accept':
                results = await self.race(*[accept for _ in range(8)])
                self.log.check(sum(code == 200 for code, _ in results) == 1, 'one winner for duplicate accepts')
                assigned = await self.get(f'/trips/{trip_id}')
                held = await self.get(f'/drivers/{driver}')
                self.log.check(assigned['status'] == 'ASSIGNED' and assigned['driver_id'] == driver
                               and held['status'] == 'ON_TRIP' and held['current_trip_id'] == trip_id,
                               'accepted trip and driver agree')
            elif scenario == 'accept_cancel':
                await self.race(accept, lambda: self.post('cancel', f'/trips/{trip_id}/cancel', {'rider_id': rider}))
                cancelled = await self.get(f'/trips/{trip_id}')
                held = await self.get(f'/drivers/{driver}')
                self.log.check(cancelled['status'] == 'CANCELLED' and held['status'] == 'AVAILABLE'
                               and held['current_trip_id'] is None, 'cancel versus accept releases driver')
            elif scenario == 'accept_offline':
                results = await self.race(accept, lambda: self.post('offline', f'/drivers/{driver}/offline'))
                held = await self.get(f'/drivers/{driver}')
                accepted = results[0][0] == 200
                self.log.check((accepted and results[1][0] == 409 and held['status'] == 'ON_TRIP'
                                and held['current_trip_id'] == trip_id)
                               or (not accepted and results[1][0] == 200 and held['status'] == 'OFFLINE'
                                   and held['current_trip_id'] is None), 'accept versus offline has one consistent winner')
            await self.settle(trip_id)
            await self.post('online', f'/drivers/{driver}/online')

    async def rider(self, rider, index, deadline):
        rng = random.Random(self.seed + 1000 + index)
        while time.monotonic() < deadline:
            # Correlated rush minutes produce more demand against a fixed fleet.
            rush = int((time.monotonic() - self.started) / (30 * self.pace)) % 2 == 0
            await asyncio.sleep(rng.expovariate(1 / ((2 if rush else 8) * self.pace)))
            if time.monotonic() >= deadline:
                break
            _, trip = await self.post('book', '/trips', self.booking(rider, rng))
            trip_id = trip['id']
            patience = time.monotonic() + rng.uniform(8, 45) * self.pace
            while time.monotonic() < deadline:
                trip = await self.get(f'/trips/{trip_id}')
                if trip['status'] in TERMINAL:
                    break
                if trip['status'] in ('REQUESTED', 'OFFERED', 'ASSIGNED') and time.monotonic() > patience:
                    await self.post('cancel', f'/trips/{trip_id}/cancel', {'rider_id': rider})
                await asyncio.sleep(rng.uniform(.5, 1.5) * self.pace)

    async def driver(self, driver, index, deadline):
        rng = random.Random(self.seed + 2000 + index)
        ignored = None
        while time.monotonic() < deadline:
            await self.post('location', f'/drivers/{driver}/location', self.point(rng, False))
            state = await self.get(f'/drivers/{driver}')
            trip = state['current_trip_id']
            if state['status'] == 'AVAILABLE':
                if rng.random() < .05:
                    await self.post('offline', f'/drivers/{driver}/offline')
                    await asyncio.sleep(rng.uniform(.5, 2) * self.pace)
                    await self.post('online', f'/drivers/{driver}/online')
            elif state['status'] == 'OFFERED':
                pending = await self.get(f'/drivers/{driver}/offer')
                if pending and pending['offer']['id'] != ignored:
                    offer = pending['offer']['id']
                    choice = rng.random()
                    if choice < .12:
                        ignored = offer  # Allow a real server-side expiry, without shortening its clock.
                    else:
                        action = 'reject' if choice < .3 else 'accept'
                        await self.post(action, f'/offers/{offer}/{action}', {'driver_id': driver})
            elif state['status'] in ('ON_TRIP',):
                current = await self.get(f'/trips/{trip}')
                action = {'ASSIGNED': 'pickup', 'PICKED_UP': 'complete'}.get(current['status'])
                if action:
                    await asyncio.sleep(rng.uniform(.5, 3) * self.pace)
                    await self.post(action, f'/trips/{trip}/{action}', {'driver_id': driver})
            await asyncio.sleep(rng.uniform(.3, 1) * self.pace)

    async def snapshots(self, deadline, interval):
        while time.monotonic() < deadline:
            supply = await self.get('/stats/supply')
            # Restrict history windows even for a multi-day soak run.
            self.log.emit('snapshot', supply=supply, zones=await self.get('/stats/zones'))
            self.log.emit('progress', **self.log.summary())
            await asyncio.sleep(min(interval, max(0, deadline - time.monotonic())))

    async def workload(self, duration, interval):
        deadline = time.monotonic() + duration
        tasks = [asyncio.create_task(self.rider(rider, i, deadline)) for i, rider in enumerate(self.riders)]
        tasks += [asyncio.create_task(self.driver(driver, i, deadline)) for i, driver in enumerate(self.drivers)]
        tasks.append(asyncio.create_task(self.snapshots(deadline, interval)))
        # End the workload on time even if an actor is sleeping. Stop actors before cleanup.
        try:
            done, _ = await asyncio.wait(tasks, timeout=duration, return_when=asyncio.FIRST_EXCEPTION)
            for task in done:
                task.result()
        finally:
            # Finish requests already on the wire before cancelling sleeps, so a committed
            # booking cannot disappear from our ownership inventory on shutdown.
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def cleanup(self):
        failures = []
        for trip in self.trips:
            try:
                await self.settle(trip)
                final = await self.get(f'/trips/{trip}')
                self.log.check(final['status'] in TERMINAL, f'terminal trip {trip}')
                self.outcomes[final['status']] += 1
                self.log.emit('final_trip', id=trip, status=final['status'])
            except SimulationFailure:
                failures.append(trip)
        for driver in self.drivers:
            try:
                await self.post('offline', f'/drivers/{driver}/offline')
                final = await self.get(f'/drivers/{driver}')
                self.log.check(final['status'] == 'OFFLINE' and final['current_trip_id'] is None,
                               f'driver released {driver}')
            except SimulationFailure:
                failures.append(driver)
        self.log.check(not failures, 'all owned trips and drivers cleaned up')


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url', default=os.getenv('UNTER_URL', 'http://localhost:5180'))
    p.add_argument('--duration', type=float, default=300, help='random workload seconds, after targeted scenarios')
    p.add_argument('--riders', type=int, default=12)
    p.add_argument('--drivers', type=int, default=4)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--race-rounds', type=int, default=3)
    p.add_argument('--pace', type=float, default=1, help='actor delay multiplier; server timeouts stay unchanged')
    p.add_argument('--snapshot-interval', type=float, default=15)
    p.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[3] / '.local/simulations')
    return p


async def run(args):
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / f'{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}.jsonl'
    log = Recorder(path)
    log.emit('start', seed=args.seed, duration=args.duration, riders=args.riders, drivers=args.drivers,
             pace=args.pace, race_rounds=args.race_rounds, snapshot_interval=args.snapshot_interval)
    print(f'Simulator evidence: {path}', flush=True)
    failed = False
    limits = httpx.Limits(max_connections=max(32, args.riders + args.drivers + 8))
    async with httpx.AsyncClient(base_url=args.url.rstrip('/') + '/api/', timeout=20, limits=limits,
                                auth=(os.environ['ADMIN_USERNAME'], os.environ['ADMIN_PASSWORD']),
                                headers={'X-Unter-Request': '1'}) as client:
        sim = Simulator(client, log, args.seed, args.pace)
        try:
            await sim.setup(args.riders, args.drivers)
            for round_number in range(1, args.race_rounds + 1):
                log.emit('race_round', number=round_number)
                await sim.targeted()
            await sim.workload(args.duration, args.snapshot_interval)
        except (Exception, asyncio.CancelledError) as exc:
            failed = True
            if not isinstance(exc, (SimulationFailure, asyncio.CancelledError)):
                log.failures += 1
            log.emit('aborted', category=type(exc).__name__)
        finally:
            try:
                await sim.cleanup()
            except Exception as exc:
                failed = True
                log.failures += 1
                log.emit('cleanup_failure', category=type(exc).__name__)
            summary = {**log.summary(), 'trip_outcomes': dict(sim.outcomes)}
            log.emit('summary', **summary, passed=not failed and log.failures == 0)
            log.file.close()
    print(json.dumps(summary, indent=2))
    return int(failed or log.failures > 0)


def main():
    load_dotenv(Path(__file__).resolve().parents[3] / '.env')
    p = parser()
    args = p.parse_args()
    if (not math.isfinite(args.duration) or args.duration < 0 or args.riders < 2 or args.drivers < 1
            or args.race_rounds < 1 or not math.isfinite(args.pace) or args.pace <= 0
            or not math.isfinite(args.snapshot_interval) or args.snapshot_interval <= 0):
        p.error('duration must be finite and nonnegative; riders must be >= 2; drivers, race rounds, pace and snapshot interval must be positive')
    if not os.getenv('ADMIN_USERNAME') or not os.getenv('ADMIN_PASSWORD'):
        p.error('set ADMIN_USERNAME and ADMIN_PASSWORD in the environment or .env')
    try:
        raise SystemExit(asyncio.run(run(args)))
    except KeyboardInterrupt:
        raise SystemExit(130) from None


if __name__ == '__main__':
    main()
