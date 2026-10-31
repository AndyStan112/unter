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
        saved=await client.put('/api/schedule',json={'cron':'15 */2 * * *','timezone':'Europe/Bucharest','enabled':False})
        assert saved.status_code==200 and saved.json()['cron']=='15 */2 * * *'
        import base64
        header='Basic '+base64.b64encode(f"{os.environ['ADMIN_USERNAME']}:{os.environ['ADMIN_PASSWORD']}".encode()).decode()
        async with Client(StreamableHttpTransport(BASE+'/mcp', headers={'Authorization':header})) as mcp:
            tools=await mcp.list_tools()
            assert {'list_observations','list_pending_proposals','create_proposal'} <= {t.name for t in tools}
            result=await mcp.call_tool('list_observations',{})
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
        assert 'list_observations' in record['tool_calls']
        assert 'Hello' in record['result'] and 'Iosefin' in record['result']
        if record['mode']=='fake':
            assert (await client.post('/api/run')).status_code in (409,429)
        await client.put('/api/schedule',json={'cron':'0 * * * *','timezone':'Europe/Bucharest','enabled':False})
    print('PASS: auth, CSRF, seeded data, remote MCP tools, schedule, outbox/RabbitMQ/worker, agent hello world, run limit')

asyncio.run(main())
