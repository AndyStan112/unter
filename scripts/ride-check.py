#!/usr/bin/env python3
"""On an isolated fake-agent stack: approvals, earnings, history, routes and push registration.

Run with COMPOSE_FILE=compose.yaml:compose.test.yaml for deterministic OSRM and Photon fixtures.
Creates test profiles, trips, rules and reports. Never run on a shared production stack.
"""
import asyncio
import base64
import json
import os
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import httpx
from dotenv import load_dotenv
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

load_dotenv()
BASE = os.getenv('UNTER_URL', 'http://localhost:5180')


def seed_report(report_id, proposal, status=None, core_id=None):
    program = '''import json,sys,uuid
from unter.common import connect
body=json.load(sys.stdin)
with connect() as db:
 run_id=uuid.uuid4()
 db.execute("INSERT INTO runs(id,source,status,mode,model,started_at) VALUES (%s,'fixture','succeeded','fake','fixture',now()-interval '1 day')",(run_id,))
 db.execute("INSERT INTO reports(id,run_id,window_from,window_to,report) VALUES (%s,%s,now()-interval '1 hour',now(),%s::jsonb)",
            (body['id'],run_id,json.dumps({'proposals':[body['proposal']], 'summary':'Integration test', 'zones':[]})))
 if body['status']:
  db.execute('INSERT INTO report_decisions(report_id,proposal_id,status,core_proposal_id) VALUES (%s,%s,%s,%s)',
             (body['id'],body['proposal']['id'],body['status'],body['core_id']))
'''
    # Program via -c has no secrets; fixture payload travels through stdin.
    result = subprocess.run(['docker','compose','exec','-T','agent','python','-c',program],
        input=json.dumps({'id': report_id, 'proposal': proposal, 'status': status, 'core_id': core_id}),
        text=True, capture_output=True)
    if result.returncode:
        raise AssertionError('Report fixture failed; container output suppressed')


async def main():
    auth = (os.environ['ADMIN_USERNAME'], os.environ['ADMIN_PASSWORD'])
    async with httpx.AsyncClient(base_url=BASE, auth=auth, headers={'X-Unter-Request':'1'}, timeout=30) as client:
        async def request(method, path, body=None):
            response = await client.request(method, '/api' + path, json=body)
            assert response.is_success, f'{method} {path}: HTTP {response.status_code}'
            return response.json() if response.status_code != 204 else None
        for _ in range(60):
            try:
                if (await client.get('/api/zones')).status_code==200 and (await client.get('/api/schedule')).status_code==200:
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1)
        else: raise AssertionError('Test stack did not become ready')
        schedule = await request('GET','/schedule')
        assert schedule['mode'] == 'fake' and not schedule['enabled'], 'Use a fake isolated stack with scheduling disabled'
        zones = await request('GET','/zones')
        zone, destination = zones[0], zones[1]
        pickup = {'lat':zone['lat'],'lon':zone['lon']}
        dropoff = {'lat':destination['lat'],'lon':destination['lon']}
        now = datetime.now(timezone.utc)
        params = {'starts_at':(now-timedelta(minutes=1)).isoformat(), 'ends_at':(now+timedelta(hours=1)).isoformat()}
        proposal = {'id': zone['name']+':incentive', 'zone':zone['name'],'type':'incentive',
                    'reason':'Integration bonus', 'params':params | {'bonus_per_trip':4.5}}
        report = str(uuid.uuid4())
        seed_report(report, proposal)
        decision = {'proposal_id':proposal['id'], 'decision':'approved'}
        results = await asyncio.gather(*(request('POST',f'/reports/{report}/decisions',decision) for _ in range(8)))
        ids = {result['core_proposal_id'] for result in results}
        assert len(ids)==1
        applied = await request('POST',f'/reports/{report}/decisions',decision)
        assert applied['core_proposal_id'] in ids
        assert (await client.post(f'/api/reports/{report}/decisions',json=decision | {'decision':'rejected'})).status_code==409
        assert len([p for p in await request('GET','/proposals') if p['id'] in ids])==1
        # Emulate core having committed while report bookkeeping was lost.
        recovering = str(uuid.uuid4()); reason = f"Integration bonus (Unter report {recovering[:8]}, {proposal['id']})"
        created = await request('POST','/report-approvals', {'report_id':recovering,'proposal_id':proposal['id'],
            'proposal':{k:v for k,v in (proposal | {'reason':reason}).items() if k!='id'}})
        seed_report(recovering, proposal, 'applying')
        for _ in range(100):
            listed = await request('GET','/reports')
            stored = next(row for row in listed if row['id']==recovering)
            if stored['decisions'].get(proposal['id'],{}).get('status')=='applied': break
            await asyncio.sleep(.25)
        else: raise AssertionError('Gateway did not automatically reconcile the interrupted approval')
        recovered = await request('POST',f'/reports/{recovering}/decisions',decision)
        assert recovered['core_proposal_id']==created['id']
        # Also adopt the previous release's partially-created core proposal.
        legacy = str(uuid.uuid4()); reason = f"Integration bonus (Unter report {legacy[:8]}, {proposal['id']})"
        pending = await request('POST','/proposals',{k:v for k,v in (proposal | {'reason':reason}).items() if k!='id'})
        seed_report(legacy, proposal, 'created', pending['id'])
        assert (await request('POST',f'/reports/{legacy}/decisions',decision))['core_proposal_id']==pending['id']
        # Permanent core identity also survives expiration; changed payloads conflict.
        short_report = str(uuid.uuid4())
        short = {k:v for k,v in proposal.items() if k!='id'}
        short['params'] = params | {'bonus_per_trip':4.5, 'ends_at':(datetime.now(timezone.utc)+timedelta(seconds=2)).isoformat()}
        short['reason'] = 'Short-window replay check'
        payload = {'report_id':short_report,'proposal_id':proposal['id'],'proposal':short}
        original = await request('POST','/report-approvals',payload)
        await asyncio.sleep(2.2)
        assert (await request('POST','/report-approvals',payload))['id']==original['id']
        changed = payload | {'proposal':short | {'params':short['params'] | {'bonus_per_trip':5}}}
        assert (await client.post('/api/report-approvals',json=changed)).status_code==409
        plan = await request('POST','/ride-plan' , {'pickup':pickup,'dropoff':dropoff})
        if 'compose.test.yaml' in os.getenv('COMPOSE_FILE',''):
            assert plan['route']['source']=='road' and plan['route']['distance_meters']==3000
            assert plan['route']['duration_seconds']==600 and plan['route']['steps']
            assert (await request('GET','/places?q=Test%20address'))[0]['label'].startswith('Test address')
            fallback = await request('POST','/ride-plan', {'pickup':{'lat':0,'lon':0},'dropoff':dropoff})
            assert fallback['route']['source']=='straight_line' and fallback['route']['duration_seconds'] is None
            assert fallback['route']['warning'] and not fallback['route']['steps']
        rider = await request('POST','/riders',{'name':'Earnings check '+str(uuid.uuid4())[:8]})
        driver = await request('POST','/drivers',{'name':'Balance check '+str(uuid.uuid4())[:8]})
        did, rid = driver['id'], rider['id']
        await request('POST',f'/drivers/{did}/location',pickup)
        await request('POST',f'/drivers/{did}/online')
        trip = await request('POST','/trips',{'rider_id':rid,'pickup':pickup,'dropoff':dropoff,
            'pickup_label':'Test pickup','dropoff_label':'Test destination'})
        offer = None
        for _ in range(30):
            offer = await request('GET',f'/drivers/{did}/offer')
            if offer: break
            await asyncio.sleep(.2)
        assert offer and offer['trip']['id']==trip['id']
        accepted = await request('POST',f"/offers/{offer['offer']['id']}/accept",{'driver_id':did})
        assert Decimal(str(accepted['trip']['driver_bonus']))==Decimal('4.5')
        # A later bonus change must not change the already-accepted trip.
        replacement = await request('POST','/proposals',{'zone':zone['name'],'type':'incentive','reason':'Changed after acceptance',
            'params':params | {'bonus_per_trip':9}})
        await request('PATCH',f"/proposals/{replacement['id']}",{'status':'approved'})
        await request('POST',f"/trips/{trip['id']}/pickup",{'driver_id':did})
        completed = await asyncio.gather(*(request('POST',f"/trips/{trip['id']}/complete",{'driver_id':did}) for _ in range(8)))
        assert all(t['status']=='COMPLETED' for t in completed)
        earnings = await request('GET',f'/drivers/{did}/earnings')
        expected = Decimal(str(completed[0]['price'])) + Decimal('4.5')
        assert Decimal(str(earnings['balance']))==expected and earnings['completed_trips']==1
        assert Decimal(str(earnings['today']))==expected and earnings['mode']=='mock'
        assert len(earnings['entries'])==1 and earnings['entries'][0]['payment_status']=='mock_settled'
        assert (await request('GET',f'/trips?riderId={rid}'))[0]['pickup_label']=='Test pickup'
        assert (await request('GET',f'/trips?driverId={did}'))[0]['id']==trip['id']
        cancelled = await request('POST','/trips',{'rider_id':rid,'pickup':pickup,'dropoff':dropoff})
        await request('POST',f"/trips/{cancelled['id']}/cancel",{'rider_id':rid})
        assert (await request('GET',f'/drivers/{did}/earnings'))['balance']==earnings['balance']
        await request('POST',f'/drivers/{did}/offline')
        key = await request('GET','/push-key')
        assert len(base64.urlsafe_b64decode(key['public_key']+'==='))==65
        assert (await request('GET','/push-key'))==key
        # Registration uses a valid generated receiver key; no notification is sent to this fixture.
        receiver=ec.generate_private_key(ec.SECP256R1())
        encode=lambda value:base64.urlsafe_b64encode(value).rstrip(b'=').decode()
        subscription={'endpoint':'https://fcm.googleapis.com/test-'+str(uuid.uuid4()), 'keys':{
            'p256dh':encode(receiver.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)),
            'auth':encode(os.urandom(16))}}
        dormant = str(uuid.uuid4())
        first = await request('POST','/push-subscriptions',{'role':'driver','profile_id':dormant,'subscription':subscription})
        assert first==await request('POST','/push-subscriptions',{'role':'driver','profile_id':dormant,'subscription':subscription})
        await request('POST','/push-unsubscribe',{'endpoint':subscription['endpoint']})
        print('PASS: concurrent/replayed/recovered/legacy approvals, road planning, locked bonuses, exactly-once mock settlement, driver balance, cancellation, history, push identity and subscriptions')

asyncio.run(main())
