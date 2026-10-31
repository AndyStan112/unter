"""Verify an actual scheduled fake-model run, then restore the original schedule."""
import asyncio
import os
from datetime import datetime, timezone
import httpx
from dotenv import load_dotenv
load_dotenv()

async def main():
    async with httpx.AsyncClient(base_url=os.getenv('UNTER_URL','http://localhost:5180'),
        auth=(os.environ['ADMIN_USERNAME'],os.environ['ADMIN_PASSWORD']),
        headers={'X-Unter-Request':'1'},timeout=15) as client:
        previous=(await client.get('/api/schedule')).json()
        assert previous['mode']=='fake', 'Scheduled verification requires fake mode to avoid API spending'
        baseline={row['id'] for row in (await client.get('/api/runs')).json()}
        # Leave the manual-run cooldown behind before scheduling the next minute.
        await asyncio.sleep(31)
        try:
            response=await client.put('/api/schedule',json={'cron':'* * * * *','timezone':'Europe/Bucharest','enabled':True})
            assert response.status_code==200
            for _ in range(45):
                await asyncio.sleep(2)
                rows=(await client.get('/api/runs')).json()
                new=[r for r in rows if r['id'] not in baseline and r['source']=='schedule']
                if new and new[0]['status']!='running':
                    assert new[0]['status']=='completed',new[0]['error']
                    assert 'list_observations' in new[0]['tool_calls']
                    print('PASS: enabled cron triggered a completed Agno/MCP hello-world run')
                    return
            raise AssertionError('Scheduler did not complete a run')
        finally:
            await client.put('/api/schedule',json={k:previous[k] for k in ('cron','timezone','enabled')})

asyncio.run(main())
