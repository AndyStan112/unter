#!/usr/bin/env python3
"""Exercise the deployed stack. Default fake mode makes no provider calls."""
import asyncio
import os
import time
import httpx
from dotenv import load_dotenv
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
load_dotenv()
BASE = os.getenv('UNTER_URL', 'http://localhost:5180').rstrip('/')


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=120) as client:
        for _ in range(90):
            try:
                auth=(os.environ['ADMIN_USERNAME'],os.environ['ADMIN_PASSWORD'])
                ready=await client.get('/api/schedule',auth=auth)
                observations=await client.get('/api/observations',auth=auth)
                if ready.status_code==200 and observations.status_code==200: break
            except httpx.HTTPError: pass
            await asyncio.sleep(2)
        assert (await client.get('/api/schedule')).status_code==401
        assert (await client.post('/api/run')).status_code==401
        assert (await client.post('/mcp')).status_code==401
        client.auth=(os.environ['ADMIN_USERNAME'],os.environ['ADMIN_PASSWORD'])
        assert (await client.post('/api/run')).status_code==403
        client.headers['X-Unter-Request']='1'
        rows=(await client.get('/api/observations')).json()
        assert len(rows)==3 and {r['zone'] for r in rows}=={'Centru','Fabric','Iosefin'}
        schedule=(await client.get('/api/schedule')).json()
        assert not schedule['enabled']
        bad=await client.put('/api/schedule',json={'cron':'bad','timezone':'UTC','enabled':False})
        assert bad.status_code==422
        saved=await client.put('/api/schedule',json={'cron':'15 */2 * * *','timezone':'Europe/Bucharest','enabled':False,
                                                      'window_hours':6,'recipients':['Ops@Example.com']})
        assert saved.status_code==200 and saved.json()['cron']=='15 */2 * * *'
        assert saved.json()['window_hours']==6 and saved.json()['recipients']==['ops@example.com']
        bad=await client.put('/api/schedule',json={**{k:saved.json()[k] for k in ('cron','timezone','enabled')},'recipients':['x <a@b.c>']})
        assert bad.status_code==422
        # Clients that don't send report settings keep the stored ones.
        kept=await client.put('/api/schedule',json={k:saved.json()[k] for k in ('cron','timezone','enabled')})
        assert kept.json()['window_hours']==6 and kept.json()['recipients']==['ops@example.com']
        import base64
        header='Basic '+base64.b64encode(f"{os.environ['ADMIN_USERNAME']}:{os.environ['ADMIN_PASSWORD']}".encode()).decode()
        async with Client(StreamableHttpTransport(BASE+'/mcp', headers={'Authorization':header})) as mcp:
            tools=await mcp.list_tools()
            assert {t.name for t in tools}=={'list_zones','zone_demand','zone_flows','offer_stats','driver_supply','active_rules','zone_snapshot'}, 'MCP must expose read-only tools only'
            result=await mcp.call_tool('list_zones',{})
            assert 'Iosefin' in str(result)
        proposal=await client.post('/api/proposals',json={'zone':'Centru','reason':'Integration test only'})
        assert proposal.status_code==200
        pid=proposal.json()['id']
        for _ in range(30):
            events=await client.get('/api/activity')
            if events.status_code==200 and any(e['payload'].get('id')==pid for e in events.json()): break
            await asyncio.sleep(2)
        else: raise AssertionError('Proposal event did not reach activity worker')
        assert (await client.patch('/api/proposals/'+pid,json={'status':'rejected'})).status_code==200
        run=await client.post('/api/run')
        assert run.status_code==200, f'Run HTTP status {run.status_code}'
        record=run.json()
        assert record['status']=='completed', f"Agent failed: {record.get('error')}"
        assert record['tool_calls']==['zone_snapshot']
        stored=[r for r in (await client.get('/api/reports')).json() if r['run_id']==record['id']]
        assert len(stored)==1, 'a completed run stores exactly one report'
        report=stored[0]['report']
        assert report['summary'] and report['summary'] in record['result'] and report['window']['hours']==6
        assert {z['zone'] for z in report['zones']}=={'Centru','Fabric','Iosefin'}
        assert all(p['reason'] and p['params'] for p in report['proposals'])
        if record['mode']=='fake': assert report['explained_by']=='template'
        # report.ready goes agent outbox -> RabbitMQ -> activity worker, with the recipients.
        for _ in range(30):
            events=(await client.get('/api/activity')).json()
            ready=[e for e in events if e['kind']=='report.ready' and e['payload'].get('report_id')==stored[0]['id']]
            if ready: break
            await asyncio.sleep(2)
        else: raise AssertionError('report.ready did not reach the activity worker')
        assert ready[0]['payload']['recipients']==['ops@example.com'] and ready[0]['payload']['source']=='manual'
        assert any(r['published'] for r in (await client.get('/api/reports')).json() if r['id']==stored[0]['id'])
        # Decisions: the browser names a proposal; unknown ones are refused, rejections never touch core.
        decisions=f"/api/reports/{stored[0]['id']}/decisions"
        assert (await client.post(decisions,json={'proposal_id':'Atlantis:surge','decision':'approved'})).status_code==404
        assert (await client.post(decisions,json={'proposal_id':'x','decision':'maybe'})).status_code==422
        if report['proposals']:
            first=report['proposals'][0]['id']
            assert (await client.post(decisions,json={'proposal_id':first,'decision':'rejected'})).json()=={'status':'rejected'}
            assert (await client.post(decisions,json={'proposal_id':first,'decision':'approved'})).status_code==409
            again=[r for r in (await client.get('/api/reports')).json() if r['id']==stored[0]['id']][0]
            assert again['decisions'][first]['status']=='rejected'
        # The mailer records an outcome: 'sent' with SMTP (Mailpit in compose.dev.yaml), else 'not_configured'.
        for _ in range(30):
            delivery=next(r['delivery'] for r in (await client.get('/api/reports')).json() if r['id']==stored[0]['id'])
            if delivery and delivery['status'] in ('sent','not_configured'): break
            await asyncio.sleep(2)
        else: raise AssertionError(f'mailer did not record a delivery: {delivery}')
        if delivery['status']=='sent':
            async with httpx.AsyncClient(timeout=5) as mailpit:
                found=(await mailpit.get('http://localhost:8025/api/v1/search',params={'query':'to:ops@example.com'})).json()
            assert any('Unter surge & incentive report' in m['Subject'] for m in found['messages']), 'email not in Mailpit'
        if record['mode']=='fake':
            assert (await client.post('/api/run')).status_code in (409,429)
        await client.put('/api/schedule',json={'cron':'0 * * * *','timezone':'Europe/Bucharest','enabled':False,
                                               'window_hours':24,'recipients':[]})
    print('PASS: auth, CSRF, seeded data, remote MCP tools, schedule and report settings, outbox/RabbitMQ/worker, '
          'agent report run, stored report, report.ready event, mailer delivery, report decisions, run limit')

asyncio.run(main())
