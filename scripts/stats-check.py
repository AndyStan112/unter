#!/usr/bin/env python3
"""Exercise core's /stats endpoints against the running stack with a small known scenario.

Through the gateway (admin login) it creates one rider trip Iosefin -> Fabric that a driver completes,
and one Centru trip the driver rejects and the rider then cancels. It then checks that the stats count
them where expected, and that the READER login can read the stats. Adds a few rows to the local
database, like integration.py does.
"""
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT/'.env')
BASE = os.getenv('UNTER_URL', 'http://localhost:5180').rstrip('/') + '/api'
CENTERS = {'Centru': (45.7537, 21.2257), 'Iosefin': (45.7480, 21.2080), 'Fabric': (45.7580, 21.2400)}

MCP_CHECK = """
import asyncio, json
from fastmcp import Client
from unter.mcp_server import mcp

async def main():
    async with Client(mcp) as client:
        async def call(tool, **args):
            return json.loads((await client.call_tool(tool, args)).content[0].text)
        zones = {z['zone']: z for z in (await call('zone_snapshot', start=START))['zones']}
        assert zones['Iosefin']['requests'] >= 1 and zones['Fabric']['arrivals'] >= 1, zones
        assert zones['Centru']['offer_reject_rate'] is not None, zones['Centru']
        flows = (await call('zone_flows', start=START, zone='Fabric'))['flows']
        assert any(f['origin'] == 'Iosefin' for f in flows), flows
        assert (await client.call_tool('zone_demand', {'zone': 'Atlantis'}, raise_on_error=False)).is_error

asyncio.run(main())
"""


def point(zone):
    lat, lon = CENTERS[zone]
    return {'lat': lat, 'lon': lon}


def main():
    api = httpx.Client(base_url=BASE, timeout=30, auth=(os.environ['ADMIN_USERNAME'], os.environ['ADMIN_PASSWORD']),
                       headers={'X-Unter-Request': '1'})
    def call(method, path, body=None, expect=(200, 201)):
        response = api.request(method, path, json=body)
        assert response.status_code in expect, f'{method} {path}: {response.status_code} {response.text[:300]}'
        return response.json() if response.content else None

    zones = {z['name']: (z['lat'], z['lon']) for z in call('GET', '/zones')}
    assert zones.keys() == CENTERS.keys(), f'unexpected zones {sorted(zones)}'
    CENTERS.update(zones)
    start = datetime.now(timezone.utc) - timedelta(seconds=5)

    # Bad input is refused with the usual error shape.
    for query in ['bucket=2h', 'from=yesterday', 'zone=Atlantis', f'from={start.isoformat()}&to={(start - timedelta(hours=1)).isoformat()}',
                  f'from={(start - timedelta(days=8)).isoformat()}']:
        response = api.get('/stats/zones?' + query.replace('+', '%2B'))
        assert response.status_code == 400 and 'error' in response.json(), f'{query}: {response.status_code}'

    driver = call('POST', '/drivers', {'name': 'Stats check driver'})['id']
    call('POST', f'/drivers/{driver}/online')
    call('POST', f'/drivers/{driver}/location', point('Iosefin'), expect=(204,))
    try:
        # 1. Iosefin -> Fabric, accepted and completed.
        rider = call('POST', '/riders', {'name': 'Stats check rider 1'})['id']
        trip = call('POST', '/trips', {'rider_id': rider, 'pickup': point('Iosefin'), 'dropoff': point('Fabric')}, expect=(201,))
        assert trip['zone'] == 'Iosefin' and trip['status'] == 'OFFERED', f'trip not offered: {trip["status"]}'
        offer = call('GET', f'/drivers/{driver}/offer')['offer']
        call('POST', f'/offers/{offer["id"]}/accept', {'driver_id': driver})
        call('POST', f'/trips/{trip["id"]}/pickup', {'driver_id': driver})
        call('POST', f'/trips/{trip["id"]}/complete', {'driver_id': driver})
        call('POST', f'/drivers/{driver}/location', point('Centru'), expect=(204,))

        # 2. Centru -> Centru, rejected by the only driver, then cancelled by the rider.
        rider = call('POST', '/riders', {'name': 'Stats check rider 2'})['id']
        trip = call('POST', '/trips', {'rider_id': rider, 'pickup': point('Centru'), 'dropoff': point('Centru')}, expect=(201,))
        assert trip['zone'] == 'Centru' and trip['status'] == 'OFFERED', f'trip not offered: {trip["status"]}'
        offer = call('GET', f'/drivers/{driver}/offer')['offer']
        call('POST', f'/offers/{offer["id"]}/reject', {'driver_id': driver})
        call('POST', f'/trips/{trip["id"]}/cancel', {'rider_id': rider})
    finally:
        api.post(f'/drivers/{driver}/offline')

    window = f'from={start.isoformat()}'.replace('+', '%2B')
    stats = call('GET', f'/stats/zones?{window}&bucket=1d')
    totals = {}
    for row in stats['rows']:
        zone = totals.setdefault(row['zone'], {})
        for key in ('requests', 'completed', 'cancelled', 'arrivals', 'offers', 'offers_accepted', 'offers_rejected'):
            zone[key] = zone.get(key, 0) + row[key]
    assert totals['Iosefin']['requests'] >= 1 and totals['Iosefin']['completed'] >= 1 and totals['Iosefin']['offers_accepted'] >= 1, totals
    assert totals['Fabric']['arrivals'] >= 1, totals
    assert totals['Centru']['cancelled'] >= 1 and totals['Centru']['offers_rejected'] >= 1, totals
    assert {row['zone'] for row in stats['rows']} == set(CENTERS), 'every zone must be listed, even without trips'
    one = call('GET', f'/stats/zones?{window}&bucket=15m&zone=Iosefin')
    assert one['rows'] and {row['zone'] for row in one['rows']} == {'Iosefin'} and one['bucket'] == '15m'
    flows = {(f['origin'], f['destination']): f for f in call('GET', f'/stats/flows?{window}')['flows']}
    assert len(flows) == 9 and flows[('Iosefin', 'Fabric')]['completed'] >= 1, flows
    supply = call('GET', '/stats/supply')
    assert {z['zone'] for z in supply['zones']} == set(CENTERS) and supply['position_max_age_seconds'] > 0
    print('PASS: /stats/zones, /stats/flows and /stats/supply count the scenario correctly and refuse bad input')

    # The READER login (held by the MCP server) can read the stats.
    program = ("import httpx, os\nfrom unter.auth import basic_header\n"
               "for path in ['/stats/zones', '/stats/flows', '/stats/supply']:\n"
               "    r = httpx.get(os.getenv('CORE_URL', 'http://core:8080') + path, headers={'Authorization': basic_header('READER')})\n"
               "    assert r.status_code == 200, (path, r.status_code)\n")
    result = subprocess.run(['docker', 'compose', 'exec', '-T', 'mcp', 'python', '-'], input=program, text=True,
                            capture_output=True, cwd=ROOT)
    assert result.returncode == 0, result.stderr[-2000:]
    print('PASS: the READER login reads all stats endpoints')

    # The MCP tools, run inside the mcp container against the real core, see the same scenario.
    program = MCP_CHECK.replace('START', repr(start.isoformat()))
    result = subprocess.run(['docker', 'compose', 'exec', '-T', 'mcp', 'python', '-'], input=program, text=True,
                            capture_output=True, cwd=ROOT)
    assert result.returncode == 0, result.stderr[-2000:]
    print('PASS: the MCP tools (zone_snapshot, zone_flows) report the scenario and refuse an unknown zone')


main()
