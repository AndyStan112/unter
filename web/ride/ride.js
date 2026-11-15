const $ = id => document.getElementById(id);
const terminal = t => !t || ['COMPLETED','CANCELLED','UNMATCHED'].includes(t.status);
const labels = {REQUESTED:'Finding your driver',OFFERED:'Waiting for a driver to accept',ASSIGNED:'Your driver is on the way',PICKED_UP:'Enjoy the ride',COMPLETED:'You’ve arrived',CANCELLED:'Ride cancelled',UNMATCHED:'No driver available. Try again.'};
let saved;
try { saved = JSON.parse(localStorage.getItem('unter-ride') || '{}'); } catch { saved = {}; }
let role='passenger', profiles=saved.profiles || {}, tripIds=saved.tripIds || {}, zones=[], trip=null, driver=null, offer=null, busy=false, polling=false, gps=null, gpsWatch=null, lastLocation=0;
function persist(){localStorage.setItem('unter-ride',JSON.stringify({profiles,tripIds}));}
function notice(message=''){$('notice').textContent=message;}
async function api(path,method='GET',body){
  const response=await fetch('/api/'+path,{method,credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(12000),headers:{'Content-Type':'application/json','X-Unter-Request':'1'},...(body?{body:JSON.stringify(body)}:{})});
  const data=response.status===204?null:await response.json();
  if(!response.ok)throw new Error(data?.message || data?.detail || `Request failed (${response.status})`);
  return data;
}
function point(id){const z=zones[Number($(id).value)];if(!z)throw new Error('Wait for locations to load.');return {lat:z.lat,lon:z.lon};}
function locationText(p){return p?`${Number(p.lat).toFixed(4)}, ${Number(p.lon).toFixed(4)}`:'Location unavailable';}
function action(text,fn){const b=document.createElement('button');b.textContent=text;b.disabled=busy;b.onclick=()=>run(fn);$('trip-actions').append(b);}
function render(){
  const profile=profiles[role];
  for(const r of ['passenger','driver']){$(r).setAttribute('aria-pressed',String(role===r));$(r).disabled=busy;}
  $('profile').hidden=!!profile;$('workspace').hidden=!profile;
  $('profile').querySelector('button').textContent='Continue as '+role;
  if(!profile)return;
  $('greeting').textContent=`Hi, ${profile.name}`;
  $('booking').hidden=role!=='passenger'||!terminal(trip);
  $('driver-controls').hidden=role!=='driver';
  $('driver-status').textContent=driver?`Status: ${driver.status.toLowerCase().replaceAll('_',' ')}`:'Loading driver…';
  $('online').disabled=busy||!driver||driver.status!=='OFFLINE';
  $('offline').disabled=busy||!driver||['OFFLINE','ON_TRIP'].includes(driver.status);
  $('trip').hidden=!trip&&!offer;$('trip-actions').replaceChildren();
  const t=offer?.trip || trip;if(!t)return;
  $('trip-label').textContent=offer?'INCOMING REQUEST':'YOUR RIDE';
  $('trip-status').textContent=offer?'A passenger needs a ride':labels[t.status]||t.status;
  $('trip-route').textContent=`${t.zone || 'Pickup'} (${locationText(t.pickup)}) → ${locationText(t.dropoff)}`;
  const price=t.price ?? offer?.estimated_price;
  $('trip-price').textContent=price==null?'Fare confirmed when your driver accepts.':`${Number(price).toFixed(2)} RON${offer?' · estimated':''}`;
  $('trip-detail').textContent=offer?`Respond by ${new Date(offer.offer.expires_at).toLocaleTimeString()}`:t.driver_id?`Driver: ${t.driver_id.slice(0,8)}${driver?.position?' · '+locationText(driver.position):''}`:'';
  if(offer){
    const id=offer.offer.id;
    action('Accept ride',async()=>{const result=await api(`offers/${id}/accept`,'POST',{driver_id:profile.id});trip=result.trip;tripIds.driver=trip.id;persist();offer=null;});
    action('Decline',async()=>{await api(`offers/${id}/reject`,'POST',{driver_id:profile.id});offer=null;});
  }else if(role==='passenger'&&['REQUESTED','OFFERED','ASSIGNED'].includes(t.status))action('Cancel ride',async()=>{trip=await api(`trips/${t.id}/cancel`,'POST',{rider_id:profile.id});});
  else if(role==='driver'&&['ASSIGNED','PICKED_UP'].includes(t.status))action(t.status==='ASSIGNED'?'Confirm pickup':'Complete ride',async()=>{trip=await api(`trips/${t.id}/${t.status==='ASSIGNED'?'pickup':'complete'}`,'POST',{driver_id:profile.id});});
}
async function refresh(){
  if(!profiles[role])return;
  const profile=profiles[role];
  if(role==='driver'){
    driver=await api(`drivers/${profile.id}`);
    if(driver.status!=='OFFLINE'&&Date.now()-lastLocation>7000){await api(`drivers/${profile.id}/location`,'POST',gps || point('driver-zone'));lastLocation=Date.now();}
    if(driver.current_trip_id){tripIds.driver=driver.current_trip_id;persist();}
    offer=await api(`drivers/${profile.id}/offer`);
  }
  if(tripIds[role])trip=await api(`trips/${tripIds[role]}`);
  if(role==='passenger'&&trip?.driver_id&&!terminal(trip))driver=await api(`drivers/${trip.driver_id}`);
  $('connection').textContent='Live · updates every 2.5 seconds';render();
}
async function run(fn){if(busy||polling)return;busy=true;notice();render();document.querySelectorAll('form button').forEach(b=>b.disabled=true);
  try{await fn();await refresh();}catch(e){notice(e.message);}finally{busy=false;document.querySelectorAll('form button').forEach(b=>b.disabled=false);render();}}
for(const r of ['passenger','driver'])$(r).onclick=()=>run(async()=>{role=r;trip=null;driver=null;offer=null;render();});
$('profile').onsubmit=e=>{e.preventDefault();run(async()=>{const name=$('name').value.trim();if(!name)throw new Error('Enter your name.');profiles[role]=await api(role==='driver'?'drivers':'riders','POST',{name});persist();});};
$('booking').onsubmit=e=>{e.preventDefault();run(async()=>{const pickup=point('pickup'),dropoff=point('dropoff');if(pickup.lat===dropoff.lat&&pickup.lon===dropoff.lon)throw new Error('Choose a different destination.');trip=await api('trips','POST',{rider_id:profiles.passenger.id,pickup,dropoff});tripIds.passenger=trip.id;persist();});};
$('online').onclick=()=>run(async()=>{await api(`drivers/${profiles.driver.id}/location`,'POST',gps||point('driver-zone'));lastLocation=Date.now();await api(`drivers/${profiles.driver.id}/online`,'POST');});
$('offline').onclick=()=>run(()=>api(`drivers/${profiles.driver.id}/offline`,'POST'));
$('driver-zone').onchange=()=>{if(gpsWatch!==null)navigator.geolocation.clearWatch(gpsWatch);gpsWatch=null;gps=null;lastLocation=0;$('location-note').textContent='Selected zone center is being used as your location.';};
$('gps').onclick=()=>{if(!navigator.geolocation)return notice('GPS is unavailable in this browser. Select a zone instead.');if(gpsWatch!==null)navigator.geolocation.clearWatch(gpsWatch);gpsWatch=navigator.geolocation.watchPosition(pos=>{gps={lat:pos.coords.latitude,lon:pos.coords.longitude};$('location-note').textContent='Live GPS enabled. Select a zone to stop using GPS.';},()=>{gps=null;notice('Location unavailable. Select a zone or allow location access.');},{enableHighAccuracy:true,timeout:10000,maximumAge:0});};
async function start(){try{zones=await api('zones');for(const id of ['pickup','dropoff','driver-zone']){$(id).replaceChildren(...zones.map((z,i)=>{const o=document.createElement('option');o.value=i;o.textContent=z.name;return o;}));}if(zones.length>1)$('dropoff').value='1';await refresh();}catch(e){notice(e.message);}render();}
setInterval(async()=>{if(busy||polling)return;polling=true;try{await refresh();}catch(e){$('connection').textContent='Disconnected · retrying';notice(e.message);}finally{polling=false;}},2500);
start();

let installPrompt;
window.addEventListener('beforeinstallprompt', event => {
  event.preventDefault(); installPrompt=event; $('install').hidden=false;
});
$('install').onclick=async()=>{
  if(!installPrompt)return;
  await installPrompt.prompt(); installPrompt=null; $('install').hidden=true;
};
window.addEventListener('appinstalled',()=>{$('install').hidden=true;});
if('serviceWorker' in navigator)navigator.serviceWorker.register('/ride/sw.js',{scope:'/ride/'})
  .catch(()=>notice('Offline setup unavailable. You can still use the app while connected.'));
