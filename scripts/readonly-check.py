#!/usr/bin/env python3
"""Prove that the READER login (held by the MCP server) can read core but never write to it.

Runs against the local Compose stack, inside the mcp container, with that container's own
credentials. core must answer every write attempt with 403 before touching the database.
The proposals list is compared before and after, as a check that nothing was written.
"""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]

PROGRAM = r'''
import os
import uuid
import httpx
from unter.auth import basic_header

assert not os.environ.get('SERVICE_PASSWORD'), 'The MCP container must not hold the SERVICE login'
core = httpx.Client(base_url=os.getenv('CORE_URL', 'http://core:8080'), timeout=15,
                    headers={'Authorization': basic_header('READER')})
for path in ['/zones', '/trips?limit=5', '/drivers', '/surge', '/incentives', '/proposals',
             '/stats/zones', '/stats/flows', '/stats/supply']:
    response = core.get(path)
    assert response.status_code == 200, f'GET {path} returned {response.status_code}'
print('PASS: READER login reads core')

before = core.get('/proposals').json()
some_id = str(uuid.uuid4())
ATTEMPTS = [
    ('POST', '/proposals', {'zone': 'Centru', 'reason': 'read-only check'}),
    ('PATCH', f'/proposals/{some_id}', {'status': 'approved'}),
    ('POST', '/riders', {'name': 'read-only check'}),
    ('POST', '/drivers', {'name': 'read-only check'}),
    ('POST', '/trips', {'rider_id': some_id, 'pickup': {'lat': 45.75, 'lon': 21.22}, 'dropoff': {'lat': 45.76, 'lon': 21.23}}),
    ('POST', f'/drivers/{some_id}/online', None),
    ('POST', f'/offers/{some_id}/accept', {'driver_id': some_id}),
    ('PUT', '/proposals', {}),
    ('DELETE', f'/proposals/{some_id}', None),
]
for method, path, body in ATTEMPTS:
    response = core.request(method, path, json=body)
    assert response.status_code == 403 and response.json()['error'] == 'read_only', \
        f'{method} {path} returned {response.status_code}'
assert core.get('/proposals').json() == before, 'proposals changed during the check'
print(f'PASS: core refused all {len(ATTEMPTS)} write attempts from the READER login; nothing changed')
'''

result = subprocess.run(['docker', 'compose', 'exec', '-T', 'mcp', 'python', '-'], input=PROGRAM,
                        text=True, capture_output=True, cwd=ROOT)
print(result.stdout, end='')
if result.returncode:
    print(result.stderr[-8000:])
    raise SystemExit(f'Read-only check failed (exit {result.returncode})')
