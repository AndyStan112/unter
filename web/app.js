const $ = id => document.getElementById(id);
let scheduleLoaded = false, working = false, deferredInstall;
const date = value => new Date(value).toLocaleString(undefined, {dateStyle:'medium',timeStyle:'short'});
function node(tag, text, cls) { const el=document.createElement(tag); if(text!==undefined) el.textContent=text; if(cls) el.className=cls; return el; }
function notice(text) { $('notice').textContent=text; $('notice').hidden=!text; }
async function api(path, method='GET', body) {
  const response = await fetch('/api/'+path, {method, credentials:'same-origin', cache:'no-store', headers:{'Content-Type':'application/json','X-Unter-Request':'1'}, ...(body ? {body:JSON.stringify(body)} : {})});
  const data = await response.json();
  if(!response.ok) throw new Error(typeof data.detail==='string' ? data.detail : 'Please check the submitted values.');
  return data;
}
function empty(id, text) { $(id).replaceChildren(node('div',text,'empty')); }
function observations(rows) {
  $('zone-count').textContent=rows.length;
  $('observations').replaceChildren(...rows.map(row=> { const tr=node('tr'); [row.zone,row.demand,row.drivers,row.wait_minutes+' min'].forEach(v=>tr.append(node('td',v))); return tr; }));
  const selected=$('proposal-zone').value;
  $('proposal-zone').replaceChildren(...rows.map(row=>{const el=node('option',row.zone);el.value=row.zone;return el;}));
  if(selected) $('proposal-zone').value=selected;
}
function showSchedule(row) {
  $('automation').textContent=row.enabled?'On':'Paused';
  $('schedule-summary').textContent=row.enabled?row.cron:'Enable it when you’re ready';
  $('model-label').textContent=row.model+' · '+(row.mode==='fake'?'fake model, no API spend':'live OpenAI call');
  $('limits').textContent=`Limit: ${row.max_daily_runs} runs per UTC day, one at a time. 30 seconds between runs.`;
  if(!scheduleLoaded) { $('cron').value=row.cron; $('timezone').value=row.timezone; $('enabled').checked=row.enabled; scheduleLoaded=true; }
  $('next-run').textContent=row.enabled?'Next slot: '+date(row.next_at):'Schedule is paused. Manual runs remain available.';
}
function runs(rows) {
  $('run-count').textContent=rows.length;
  if(!rows.length) return empty('runs','No runs yet. Your first hello is one click away.');
  $('runs').replaceChildren(...rows.map(row=>{
    const el=node('article',undefined,'run'), heading=node('div',undefined,'item-heading');
    heading.append(node('span',row.status,'status '+row.status),node('span',row.source==='schedule'?'Scheduled run':'Manual run'),node('time',date(row.started_at)));
    el.append(heading,node('small',`${row.model} · ${row.mode} · MCP: ${(row.tool_calls||[]).join(', ')||'—'}`));
    if(row.result||row.error) el.append(node('pre',row.result||row.error));
    return el;
  }));
}
function activity(rows) {
  if(!rows.length) return empty('events','Waiting for the first event from RabbitMQ.');
  $('events').replaceChildren(...rows.map(row=>{const el=node('article',undefined,'event'), heading=node('div',undefined,'item-heading');heading.append(node('strong',row.kind),node('time',date(row.created_at)));el.append(heading,node('pre',JSON.stringify(row.payload,null,2)));return el;}));
}
function proposals(rows) {
  if(!rows.length) return empty('proposal-list','No proposals. The hello-world agent only reads example data.');
  $('proposal-list').replaceChildren(...rows.map(row=>{
    const el=node('article',undefined,'proposal'), heading=node('div',undefined,'item-heading');
    heading.append(node('strong',row.zone),node('span',row.status,'status'));el.append(heading,node('p',row.reason));
    if(row.status==='pending') { const actions=node('div',undefined,'actions');for(const status of ['approved','rejected']) { const button=node('button',status==='approved'?'Approve':'Reject','quiet');button.onclick=async()=>{button.disabled=true;try{await api('proposals/'+row.id,'PATCH',{status});await refresh();}catch(error){notice(error.message);}finally{button.disabled=false;}};actions.append(button);}el.append(actions); }
    return el;
  }));
}
async function refresh() {
  if(!navigator.onLine){$('connection').textContent='Offline';notice('You’re offline. Live data and agent actions need a connection.');return;}
  try {
    // Authenticate once before making the other requests.
    const data=await api('schedule');showSchedule(data);
    const results=await Promise.allSettled([['observations',observations],['runs',runs],['activity',activity],['proposals',proposals]].map(async([path,render])=>render(await api(path))));
    const errors=results.filter(r=>r.status==='rejected');
    $('connection').textContent=errors.length?'Some services unavailable':'Connected';
    if(errors.length) notice(errors.map(e=>e.reason.message).join(' '));
  }catch(error){$('connection').textContent='Disconnected';notice(error.message);}
}
document.querySelectorAll('.nav').forEach(button=>button.onclick=()=>{
  document.querySelectorAll('.nav').forEach(b=>b.classList.toggle('active',b===button));
  document.querySelectorAll('.view').forEach(view=>view.hidden=view.id!==button.dataset.view);
  $('breadcrumb').textContent=button.textContent.trim().slice(1).trim();
});
document.querySelectorAll('.run-button').forEach(button=>button.onclick=async()=>{
  if(working)return;working=true;notice('Reading MCP data and waiting for the model…');
  document.querySelectorAll('.run-button').forEach(b=>b.disabled=true);
  try { const result=await api('run','POST');notice(result.status==='completed'?'Hello world completed. See the response in Agent & schedule.':'Run '+result.status+': '+(result.error||'check history')); document.querySelector('[data-view=agent]').click();await refresh(); }
  catch(error){notice(error.message);}finally{working=false;document.querySelectorAll('.run-button').forEach(b=>b.disabled=false);}
});
$('schedule-form').onsubmit=async event=>{event.preventDefault();const button=event.submitter;button.disabled=true;try{const row=await api('schedule','PUT',{cron:$('cron').value,timezone:$('timezone').value,enabled:$('enabled').checked});scheduleLoaded=false;showSchedule(row);notice('Schedule saved.');}catch(error){notice(error.message);}finally{button.disabled=false;}};
$('proposal-form').onsubmit=async event=>{event.preventDefault();event.submitter.disabled=true;try{await api('proposals','POST',{zone:$('proposal-zone').value,reason:$('proposal-reason').value});$('proposal-reason').value='';notice('Test proposal created.');await refresh();}catch(error){notice(error.message);}finally{event.submitter.disabled=false;}};
$('refresh').onclick=()=>{notice('');refresh();};
window.addEventListener('online',refresh);window.addEventListener('offline',refresh);
window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();deferredInstall=event;$('install').hidden=false;});
$('install').onclick=async()=>{if(deferredInstall){await deferredInstall.prompt();deferredInstall=null;$('install').hidden=true;}};
if('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js');
refresh();
setInterval(()=>{if(!document.hidden&&!working)refresh();},30000);
