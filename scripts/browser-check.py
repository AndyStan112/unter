"""Local Chromium/CDP smoke test. Secrets remain in memory; screenshots are ignored."""
import asyncio
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import httpx
from dotenv import load_dotenv
from websockets.asyncio.client import connect
load_dotenv()

async def main():
    base=os.getenv('UNTER_URL','http://localhost:5180')
    with tempfile.TemporaryDirectory(prefix='unter-browser-') as profile:
        browser=subprocess.Popen(['chromium-browser','--headless','--disable-gpu','--no-sandbox',
            '--remote-debugging-port=9337','--remote-allow-origins=http://localhost:9337',
            '--user-data-dir='+profile,'about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            async with httpx.AsyncClient() as http:
                for _ in range(30):
                    try:
                        pages=(await http.get('http://localhost:9337/json')).json()
                        break
                    except httpx.HTTPError: await asyncio.sleep(.3)
            async with connect(pages[0]['webSocketDebuggerUrl'],max_size=10_000_000) as ws:
                seq=0
                async def command(method,params=None):
                    nonlocal seq
                    seq+=1
                    await ws.send(json.dumps({'id':seq,'method':method,'params':params or {}}))
                    while True:
                        msg=json.loads(await ws.recv())
                        if msg.get('id')==seq:
                            if 'error' in msg: raise RuntimeError('Browser command failed: '+method)
                            return msg.get('result',{})
                async def evaluate(expression):
                    result=await command('Runtime.evaluate',{'expression':expression,'returnByValue':True,'awaitPromise':True})
                    if 'exceptionDetails' in result: raise AssertionError('Browser script error')
                    return result.get('result',{}).get('value')
                await command('Page.enable')
                await command('Network.enable')
                auth='Basic '+base64.b64encode(f"{os.environ['ADMIN_USERNAME']}:{os.environ['ADMIN_PASSWORD']}".encode()).decode()
                await command('Network.setExtraHTTPHeaders',{'headers':{'Authorization':auth}})
                await command('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1050,'deviceScaleFactor':1,'mobile':False})
                await command('Page.navigate',{'url':base})
                for _ in range(40):
                    if await evaluate("document.querySelector('#zone-count')?.textContent === '3'"):break
                    await asyncio.sleep(.5)
                else:raise AssertionError('Dashboard did not load seeded data')
                assert await evaluate("document.querySelector('#connection').textContent === 'Connected'")
                Path('.local').mkdir(exist_ok=True)
                shot=await command('Page.captureScreenshot',{'format':'png','captureBeyondViewport':True})
                Path('.local/dashboard-desktop.png').write_bytes(base64.b64decode(shot['data']))
                await evaluate("document.querySelector('[data-view=agent]').click()")
                assert await evaluate("!document.querySelector('#agent').hidden")
                await evaluate("document.querySelector('#cron').value='30 */3 * * *'; document.querySelector('#schedule-form').requestSubmit()")
                await asyncio.sleep(1)
                assert await evaluate("document.querySelector('#notice').textContent === 'Schedule saved.'")
                await evaluate("document.querySelector('#cron').value='0 * * * *'; document.querySelector('#schedule-form').requestSubmit()")
                await asyncio.sleep(1)
                await command('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
                await evaluate("document.querySelector('[data-view=overview]').click()")
                await asyncio.sleep(.5)
                assert await evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                shot=await command('Page.captureScreenshot',{'format':'png','captureBeyondViewport':True})
                Path('.local/dashboard-mobile.png').write_bytes(base64.b64decode(shot['data']))
                cached=await evaluate("(async()=>{await navigator.serviceWorker.ready; const keys=await caches.keys();return (await Promise.all(keys.map(async key=>(await (await caches.open(key)).keys()).map(r=>new URL(r.url).pathname)))).flat()})()")
                assert '/' in cached and not any(p.startswith(('/api','/mcp')) for p in cached)
                print('PASS: desktop/mobile UI, seeded data, schedule form, responsive layout, static-only PWA cache')
        finally:
            browser.terminate()
            browser.wait(timeout=10)

asyncio.run(main())
