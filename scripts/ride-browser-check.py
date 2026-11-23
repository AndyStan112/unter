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
        await self.snapshot('map-check-failure')
        print('Browser state:', await self.evaluate('document.body.innerText.slice(-2500)'))
        raise AssertionError('Browser condition not met: '+expression)

    async def click(self, label):
        await self.command('Page.bringToFront')
        await self.wait("!document.querySelector('[aria-label=\"Loading Unter\"]')")
        expression = f"(()=>{{const candidates=[...document.querySelectorAll('button,[role=button]')].filter(b=>(b.textContent.trim()==={json.dumps(label)} || b.getAttribute('aria-label')==={json.dumps(label)}) && !b.disabled && b.offsetParent!==null);return candidates.find(el=>{{const r=el.getBoundingClientRect();return el.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))}})||candidates[0]}})()"
        await self.wait('!!('+expression+')')
        geometry = "(()=>{const el=("+expression+");if(!el)return null;el.scrollIntoView({block:'nearest'});const r=el.getBoundingClientRect();const x=r.x+r.width/2,y=r.y+r.height/2;return {x,y,visible:el.contains(document.elementFromPoint(x,y))}})()"
        point = None
        for _ in range(40):
            current = await self.evaluate(geometry)
            await asyncio.sleep(.12)
            next_point = await self.evaluate(geometry)
            if current and next_point and next_point['visible'] and abs(current['x']-next_point['x'])+abs(current['y']-next_point['y'])<1:
                point={key:next_point[key] for key in ('x','y')};break
        assert point, 'Control is covered or moving: '+label
        await self.command('Input.dispatchMouseEvent', {'type':'mousePressed','button':'left','clickCount':1,**point})
        await self.command('Input.dispatchMouseEvent', {'type':'mouseReleased','button':'left','clickCount':1,**point})

    async def drag(self, x, y, to_x, to_y):
        await self.command('Input.dispatchMouseEvent', {'type':'mousePressed','button':'left','buttons':1,'x':x,'y':y,'clickCount':1})
        for step in range(1,9):
            await self.command('Input.dispatchMouseEvent', {'type':'mouseMoved','button':'left','buttons':1,'x':x+(to_x-x)*step/8,'y':y+(to_y-y)*step/8})
            await asyncio.sleep(.04)
        await self.command('Input.dispatchMouseEvent', {'type':'mouseReleased','button':'left','x':to_x,'y':to_y,'clickCount':1})

    async def snapshot(self, name):
        await self.command('Page.bringToFront')
        await asyncio.sleep(.6)
        Path('.local').mkdir(exist_ok=True)
        shot=await self.command('Page.captureScreenshot', {'format':'png','captureBeyondViewport':False})
        Path(f'.local/{name}.png').write_bytes(base64.b64decode(shot['data']))

    async def layout(self):
        assert await self.evaluate("(()=>{const r=document.querySelector('[data-ride-map]').getBoundingClientRect();return r.width>=innerWidth-1 && r.height>=innerHeight-1})()"), 'Map must fill the viewport'
        assert await self.evaluate('document.documentElement.scrollWidth <= innerWidth && document.documentElement.scrollHeight <= innerHeight + 1'), 'The app must not scroll or overflow'
        assert await self.evaluate("(()=>{const r=document.querySelector('[data-ride-sheet]').getBoundingClientRect();return r.bottom<=innerHeight+1 && r.top>70})()"), 'The sheet must fit and leave the map visible'
        assert not await self.evaluate("/OSRM|Photon|MCP|Leaflet|shared login|straight-line|simulated|mock settled/.test(document.body.innerText)"), 'Implementation text must not appear in ride screens'

    async def fill(self, label, value):
        await self.evaluate(f"""(()=>{{const label=[...document.querySelectorAll('label')].find(l=>l.textContent.startsWith({json.dumps(label)}));
          const input=document.getElementById(label.htmlFor); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,{json.dumps(value)});
          input.dispatchEvent(new Event('input',{{bubbles:true}}));}})()""")


async def main():
    async with httpx.AsyncClient(base_url=BASE, auth=(os.environ['ADMIN_USERNAME'],os.environ['ADMIN_PASSWORD'])) as client:
        response=await client.get('/api/schedule')
        response.raise_for_status()
        assert response.json()['mode']=='fake' and not response.json()['enabled'], 'Use an isolated fake stack with scheduling disabled'
    with tempfile.TemporaryDirectory(prefix='unter-ride-browser-', ignore_cleanup_errors=True) as profile:
        browser = subprocess.Popen([os.getenv('BROWSER','chromium-browser'),'--headless','--disable-gpu','--no-sandbox','--disable-background-timer-throttling','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows',
            f'--remote-debugging-port={PORT}', '--user-data-dir='+profile,'about:blank'],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        pages = []
        driver_id = rider_id = None
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
                    await page.click('Continue')
                    await page.wait("document.body.innerText.includes("+json.dumps('Go online' if role=='driver' else 'Where to?')+")")
                    await page.layout()
            driver, passenger = pages
            driver_id = await driver.evaluate("JSON.parse(localStorage.getItem('unter-ride')).profiles.driver.id")
            rider_id = await passenger.evaluate("JSON.parse(localStorage.getItem('unter-ride')).profiles.passenger.id")
            await driver.wait("[...document.querySelectorAll('button')].some(b=>b.textContent==='Go online' && !b.disabled)")
            await passenger.snapshot('map-passenger-idle')
            await driver.snapshot('map-driver-idle')
            await passenger.click('Choose pickup')
            await passenger.fill('Pickup address','Test address')
            await passenger.click('Search addresses')
            await passenger.click('Test address, Timișoara')
            await passenger.click('Choose destination')
            await passenger.click('Choose on map')
            await passenger.wait("document.body.innerText.includes('Set destination')")
            await passenger.drag(180,240,230,290)
            await passenger.click('Confirm location')
            await passenger.wait("document.body.innerText.includes('Pinned location')")
            await passenger.click('Choose destination')
            await passenger.click('Fabric')
            await passenger.wait("document.body.innerText.includes('12.50 RON')")
            handle=await passenger.evaluate("(()=>{const r=document.querySelector('[aria-label=\"Expand ride details\"]').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()")
            await passenger.drag(handle['x'],handle['y'],handle['x'],handle['y']-120)
            await passenger.wait("!!document.querySelector('[aria-label=\"Collapse ride details\"]')")
            await passenger.click('Collapse ride details')
            await passenger.layout()
            await passenger.snapshot('map-passenger-booking')
            for width,height in ((360,740),(430,932),(844,390),(1440,900),(390,844)):
                await passenger.command('Emulation.setDeviceMetricsOverride', {'width':width,'height':height,'deviceScaleFactor':1,'mobile':width<900})
                await asyncio.sleep(.3)
                await passenger.layout()
            await driver.click('Go online')
            await passenger.click('Request a ride')
            await driver.click('Accept ride')
            await driver.wait("document.body.innerText.includes('Confirm pickup')")
            await driver.wait("!!document.querySelector('[aria-label=\"Directions\"]')")
            await driver.snapshot('map-driver-pickup')
            await driver.click('Directions')
            await driver.wait("document.body.innerText.includes('Start navigation')")
            await driver.click('Close directions')
            await driver.click('Confirm pickup')
            await driver.click('Complete ride')
            await passenger.wait("document.body.innerText.includes('You’ve arrived')")
            await driver.wait("document.body.innerText.includes('You earned')")
            for role,page in zip(('driver','passenger'),pages):
                await page.layout()
                await page.click('Done')
                if role=='driver':
                    await page.click('Earnings')
                    await page.wait("document.body.innerText.includes('1 completed ride')")
                    await page.snapshot('map-driver-earnings')
                    await page.click('Close panel')
                await page.click('Open menu')
                await page.click('Your rides')
                await page.wait("document.body.innerText.includes('Completed')")
                await page.click('Close panel')
                await page.evaluate('window.__unterBeforeReload = true')
                await page.command('Page.reload')
                await page.wait("!window.__unterBeforeReload && document.readyState === 'complete'")
                await page.wait("!document.querySelector('[aria-label=\"Loading Unter\"]')")
                await page.layout()
                await page.click('Done')
                cached=await page.evaluate("(async()=>{const names=await caches.keys();return (await Promise.all(names.map(async n=>(await(await caches.open(n)).keys()).map(r=>new URL(r.url).pathname)))).flat()})()")
                assert not any(path.startswith(('/api','/mcp')) for path in cached)
            await driver.click('Go offline')
            print('PASS: full-screen map, draggable sheets, address/pin selection, phone/landscape/desktop layout, actual pointer interactions, complete ride, earnings/history panels, reload and cache isolation')
        finally:
            if driver_id:
                async with httpx.AsyncClient(base_url=BASE+'/api', auth=(os.environ['ADMIN_USERNAME'],os.environ['ADMIN_PASSWORD']), headers={'X-Unter-Request':'1'}, timeout=10) as client:
                    try:
                        trips=(await client.get('/trips',params={'riderId':rider_id})).json() if rider_id else []
                        for trip in trips:
                            if trip['status'] in ('REQUESTED','OFFERED','ASSIGNED'):
                                await client.post('/trips/'+trip['id']+'/cancel',json={'rider_id':rider_id})
                            elif trip['status']=='PICKED_UP' and trip['driver_id']==driver_id:
                                await client.post('/trips/'+trip['id']+'/complete',json={'driver_id':driver_id})
                        await client.post('/drivers/'+driver_id+'/offline')
                    except httpx.HTTPError:
                        print('Test cleanup needs attention for driver',driver_id)
            for page in pages:
                page.task.cancel()
                await page.ws.close()
            browser.terminate(); browser.wait(timeout=10)

asyncio.run(main())
