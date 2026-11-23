"""Chromium smoke test of real passenger/driver UI on a disposable test stack.

No paid model or real payment calls. Uses browser-local profiles; leave other riders/drivers offline.
"""
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
BASE = os.getenv('UNTER_URL', 'http://localhost:5180').rstrip('/')
PORT = 9341


class Page:
    def __init__(self, ws):
        self.ws, self.seq, self.pending = ws, 0, {}
        self.task = asyncio.create_task(self.read())

    async def read(self):
        async for raw in self.ws:
            message = json.loads(raw)
            if 'id' in message:
                future = self.pending.pop(message['id'], None)
                if future and not future.done():
                    if 'error' in message: future.set_exception(RuntimeError('CDP command failed'))
                    else: future.set_result(message.get('result', {}))
            elif message.get('method') == 'Fetch.requestPaused':
                parameters = message['params']; request = parameters['request']
                # Attach authentication only to this app's origin, never to map tiles or navigation links.
                headers = request['headers']
                if request['url'].startswith(BASE + '/'):
                    raw = f"{os.environ['ADMIN_USERNAME']}:{os.environ['ADMIN_PASSWORD']}"
                    headers['Authorization'] = 'Basic ' + base64.b64encode(raw.encode()).decode()
                self.seq += 1
                await self.ws.send(json.dumps({'id':self.seq,'method':'Fetch.continueRequest', 'params':{
                    'requestId':parameters['requestId'], 'headers':[{'name':k,'value':str(v)} for k,v in headers.items()]}}))

    async def command(self, method, params=None):
        self.seq += 1; seq = self.seq
        future = asyncio.get_running_loop().create_future(); self.pending[seq] = future
        await self.ws.send(json.dumps({'id':seq,'method':method,'params':params or {}}))
        return await asyncio.wait_for(future, 30)

    async def evaluate(self, expression):
        result = await self.command('Runtime.evaluate', {'expression':expression,'returnByValue':True,'awaitPromise':True})
        assert 'exceptionDetails' not in result, 'Browser script failed'
        return result.get('result',{}).get('value')

    async def wait(self, expression):
        for _ in range(100):
            if await self.evaluate(expression): return
            await asyncio.sleep(.2)
        raise AssertionError('Browser condition not met: '+expression)

    async def click(self, label):
        await self.wait("!document.querySelector('[aria-label=\"Loading Unter\"]')")
        expression = f"[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==={json.dumps(label)} && !b.disabled)"
        await self.wait('!!('+expression+')')
        await self.evaluate(expression+'.click()')

    async def fill(self, label, value):
        await self.evaluate(f"""(()=>{{const label=[...document.querySelectorAll('label')].find(l=>l.textContent.startsWith({json.dumps(label)}));
          const input=document.getElementById(label.htmlFor); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,{json.dumps(value)});
          input.dispatchEvent(new Event('input',{{bubbles:true}}));}})()""")


async def main():
    with tempfile.TemporaryDirectory(prefix='unter-ride-browser-', ignore_cleanup_errors=True) as profile:
        browser = subprocess.Popen([os.getenv('BROWSER','chromium-browser'),'--headless','--disable-gpu','--no-sandbox',
            f'--remote-debugging-port={PORT}', '--user-data-dir='+profile,'about:blank'],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        pages = []
        try:
            async with httpx.AsyncClient() as http:
                for _ in range(40):
                    try:
                        await http.get(f'http://localhost:{PORT}/json/version'); break
                    except httpx.HTTPError: await asyncio.sleep(.2)
                for role in ('driver','passenger'):
                    target = (await http.put(f'http://localhost:{PORT}/json/new?about:blank')).json()
                    ws = await connect(target['webSocketDebuggerUrl'], max_size=10_000_000)
                    page = Page(ws); pages.append(page)
                    await page.command('Fetch.enable', {'patterns':[{'urlPattern':BASE+'/*'}]})
                    await page.command('Page.enable')
                    await page.command('Emulation.setDeviceMetricsOverride', {'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
                    await page.command('Page.navigate', {'url':BASE+'/ride/'+role})
                    await page.wait("!!document.querySelector('input[autocomplete=name]')")
                    await page.fill('Your name','Browser '+role)
                    await page.click('Continue as '+role)
                    await page.wait("document.body.innerText.includes("+json.dumps('Go online' if role=='driver' else 'Request a ride')+")")
            driver, passenger = pages
            await driver.click('Go online')
            await passenger.wait("document.body.innerText.includes('Estimated fare')")
            await passenger.fill('Pickup address','Test address')
            # Search is deliberate, never automatic typeahead.
            await passenger.evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent==='Search').click()")
            await passenger.wait("document.body.innerText.includes('Test address, Timișoara')")
            await passenger.evaluate("[...document.querySelectorAll('[role=button]')].find(b=>b.textContent.includes('Test address, Timișoara')).click()")
            await passenger.click('Request a ride')
            await driver.click('Accept ride')
            await driver.wait("document.body.innerText.includes('Road directions')")
            await driver.click('Confirm pickup')
            await driver.click('Complete ride')
            await driver.wait("document.body.innerText.includes('1 completed rides')")
            await passenger.wait("document.body.innerText.includes('mock paid')")
            for role,page in zip(('driver','passenger'), pages):
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), role+' overflows'
                assert await page.evaluate("document.body.innerText.includes('Recent rides')")
                await page.evaluate('window.__unterBeforeReload = true')
                await page.command('Page.reload')
                await page.wait("!window.__unterBeforeReload && document.readyState === 'complete'")
                await page.wait("!document.querySelector('[aria-label=\"Loading Unter\"]')")
                await page.wait("document.body.innerText.includes('1 completed rides')" if role == 'driver' else "document.body.innerText.includes('mock paid')")
                cached = await page.evaluate("(async()=>{const names=await caches.keys();return (await Promise.all(names.map(async n=>(await(await caches.open(n)).keys()).map(r=>new URL(r.url).pathname)))).flat()})()")
                assert not any(path.startswith(('/api','/mcp')) for path in cached)
                Path('.local').mkdir(exist_ok=True)
                shot=await page.command('Page.captureScreenshot',{'format':'png','captureBeyondViewport':True})
                Path(f'.local/ride-{role}-review.png').write_bytes(base64.b64decode(shot['data']))
            await driver.click('Go offline')
            print('PASS: mobile passenger/driver UI, address selection, fare estimate, road guidance, booking, acceptance, pickup, completion, mock balance/history, reload recovery and private-data cache exclusion')
        finally:
            for page in pages:
                page.task.cancel()
                await page.ws.close()
            browser.terminate(); browser.wait(timeout=10)

asyncio.run(main())
