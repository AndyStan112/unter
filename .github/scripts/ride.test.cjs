const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const source = readFileSync('web/ride/ride.js', 'utf8');
const zoneRows = [{name:'Centru',lat:1,lon:2},{name:'Fabric',lat:3,lon:4}];
function harness(saved = {}) {
  const elements = new Map(), events = {}, calls = [], writes = [];
  function element() {
    return {value:'0',hidden:false,disabled:false,textContent:'',children:[],attributes:{},
      setAttribute(k,v){this.attributes[k]=v},append(v){this.children.push(v)},
      replaceChildren(...v){this.children=v},querySelector(){return this.button ||= element()}};
  }
  const get = id => {if(!elements.has(id))elements.set(id,element());return elements.get(id)};
  let driver = {id:'d1',name:'Dan',status:'OFFLINE',current_trip_id:null};
  let trip = {id:'t1',rider_id:'r1',driver_id:null,status:'OFFERED',zone:'Centru',pickup:zoneRows[0],dropoff:zoneRows[1]};
  let offer = null, delay, rejectNext = false;
  const navigator = {onLine:true};
  const ctx = vm.createContext({document:{getElementById:get,createElement:element,querySelectorAll:()=>[get('profile').querySelector('button'),get('booking').querySelector('button')]},
    localStorage:{getItem:()=>JSON.stringify(saved),setItem:(k,v)=>writes.push(JSON.parse(v))},
    navigator,window:{addEventListener:(k,v)=>events[k]=v},AbortSignal,Date,JSON,Number,String,Error,
    setInterval(){},fetch:async(url,opt)=>{
      calls.push([url,opt]);if(delay){const wait=delay;delay=null;await wait;}
      if(rejectNext){rejectNext=false;return {ok:false,status:409,json:async()=>({error:'offer_expired',message:'Offer expired'})}}
      let data;
      if(url==='/api/zones')data=zoneRows;
      else if(url==='/api/riders')data={id:'r1',name:'Ana'};
      else if(url==='/api/drivers')data=driver;
      else if(url.endsWith('/location'))data=null;
      else if(url.endsWith('/online')){driver.status='AVAILABLE';data=driver}
      else if(url.endsWith('/offline')){driver.status='OFFLINE';data=driver}
      else if(url.endsWith('/offer'))data=offer;
      else if(url.startsWith('/api/drivers/'))data=driver;
      else if(url.endsWith('/accept')){trip={...trip,driver_id:'d1',status:'ASSIGNED',price:15};driver.status='ON_TRIP';driver.current_trip_id='t1';data={trip,offer:offer.offer};offer=null}
      else if(url.endsWith('/reject')){data=offer.offer;offer=null;driver.status='AVAILABLE';driver.current_trip_id=null}
      else if(url.endsWith('/pickup')){trip.status='PICKED_UP';data=trip}
      else if(url.endsWith('/complete')){trip.status='COMPLETED';driver.status='AVAILABLE';driver.current_trip_id=null;data=trip}
      else if(url.endsWith('/cancel')){trip.status='CANCELLED';data=trip}
      else data=trip;
      return {ok:true,status:data===null?204:200,json:async()=>data};
    }});
  vm.runInContext(source,ctx);
  return {get,calls,writes,events,navigator,eval:code=>vm.runInContext(code,ctx),
    flush:()=>new Promise(resolve=>setImmediate(resolve)),
    delayNext:promise=>delay=promise,conflict:()=>rejectNext=true,
    incoming(){driver.status='OFFERED';driver.current_trip_id='t1';offer={offer:{id:'o1',expires_at:new Date(Date.now()+30000).toISOString()},trip,estimated_price:15}}};
}
const submit = h => h.get('profile').onsubmit({preventDefault(){}});
test('passenger creates profile, books, cancels and uses required request headers', async()=>{
  const h=harness();await h.flush();h.get('name').value='Ana';await submit(h);
  h.get('dropoff').value='1';await h.get('booking').onsubmit({preventDefault(){}});
  assert.equal(h.get('trip-status').textContent,'Waiting for a driver to accept');
  await h.get('trip-actions').children[0].onclick();
  assert.equal(h.get('trip-status').textContent,'Ride cancelled');
  assert.equal(h.get('booking').hidden,false);
  for(const [,opt]of h.calls){assert.equal(opt.headers['X-Unter-Request'],'1');assert.equal(opt.credentials,'same-origin')}
});
test('driver declines without retaining an unassigned trip, then accepts, picks up and completes',async()=>{
  const h=harness({role:'driver',profiles:{driver:{id:'d1',name:'Dan'}}});await h.flush();
  await h.get('online').onclick();assert.equal(h.get('driver-status').textContent,'Status: available');
  h.incoming();await h.eval('tick()');await h.get('trip-actions').children[1].onclick();
  assert.equal(h.get('trip').hidden,true);
  h.incoming();await h.eval('tick()');await h.get('trip-actions').children[0].onclick();
  assert.equal(h.get('trip-status').textContent,'Head to the pickup');
  await h.get('trip-actions').children[0].onclick();assert.equal(h.get('trip-status').textContent,'Enjoy the ride');
  await h.get('trip-actions').children[0].onclick();assert.equal(h.get('trip-status').textContent,'You’ve arrived');
  assert.equal(h.get('driver-status').textContent,'Status: available');
});
test('click during polling waits and runs instead of being dropped',async()=>{
  const h=harness();await h.flush();let release;h.delayNext(new Promise(r=>release=r));
  h.eval('zones=[];tick()');h.get('name').value='Ana';const pending=submit(h);
  release();await pending;assert.equal(h.get('workspace').hidden,false);
  assert.equal(h.calls.filter(([url])=>url==='/api/riders').length,1);
});
test('offline disables mutations and reconnection retries zone loading',async()=>{
  const h=harness();await h.flush();h.navigator.onLine=false;h.events.offline();
  assert.equal(h.get('profile').querySelector('button').disabled,true);
  const before=h.calls.length;await submit(h);assert.equal(h.calls.length,before);
  h.navigator.onLine=true;h.events.online();await h.flush();
  assert.equal(h.get('profile').querySelector('button').disabled,false);
});
test('409 refreshes state and displays the conflict',async()=>{
  const h=harness({role:'driver',profiles:{driver:{id:'d1',name:'Dan'}}});await h.flush();h.incoming();await h.eval('tick()');
  h.conflict();await h.get('trip-actions').children[0].onclick();
  assert.equal(h.get('notice').textContent,'Offer expired');
  assert.equal(h.get('trip-status').textContent,'A passenger needs a ride');
});
test('driver location heartbeat continues while passenger mode is displayed',async()=>{
  const h=harness({role:'driver',profiles:{driver:{id:'d1',name:'Dan'},passenger:{id:'r1',name:'Ana'}}});await h.flush();
  await h.get('online').onclick();await h.get('passenger').onclick();h.eval('lastLocation=0');await h.eval('tick()');
  assert(h.calls.filter(([url])=>url.endsWith('/location')).length>=2);
});
