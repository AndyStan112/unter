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
  $('model-label').textContent=row.model+' · '+(row.mode==='fake'?'template text, no API spend':'live OpenAI call')+' · nothing changes until you approve';
  $('limits').textContent=`Limit: ${row.max_daily_runs} runs per UTC day, one at a time. 30 seconds between runs.`;
  if(!scheduleLoaded) { $('cron').value=row.cron; $('timezone').value=row.timezone; $('enabled').checked=row.enabled; $('window-hours').value=row.window_hours; $('recipients').value=(row.recipients||[]).join('\n'); scheduleLoaded=true; }
  $('next-run').textContent=row.enabled?'Next slot: '+date(row.next_at):'Schedule is paused. Manual runs remain available.';
}
function runs(rows) {
  if(!rows.length) return empty('runs','No runs yet. Your first report is one click away.');
  $('runs').replaceChildren(...rows.map(row=>{
    const el=node('article',undefined,'run'), heading=node('div',undefined,'item-heading');
    heading.append(node('span',row.status,'status '+row.status),node('span',row.source==='schedule'?'Scheduled run':'Manual run'),node('time',date(row.started_at)));
    el.append(heading,node('small',`${row.model} · ${row.mode} · MCP: ${(row.tool_calls||[]).join(', ')||'—'}`));
    if(row.result||row.error) el.append(node('pre',row.result||row.error));
    return el;
  }));
}
const percent = value => value===null||value===undefined ? '—' : Math.round(value*100)+'%';
const shown = value => value===null||value===undefined ? '—' : String(value);
const amount = p => p.type==='surge' ? `Surge ×${p.params.multiplier}` : `Driver bonus ${p.params.bonus_per_trip} RON / trip`;
const span = params => `${date(params.starts_at)} → ${new Date(params.ends_at).toLocaleTimeString(undefined,{timeStyle:'short'})}`;
const DELIVERY = {sent:'Emailed', sending:'Sending email', failed:'Email failed, retrying', parked:'Email failed', skipped:'No recipients', not_configured:'Email not configured'};
const DECISION = {applied:'Approved · rule active', created:'Created in core, approve it under Proposals', rejected:'Rejected', applying:'Applying…'};
const METRICS = [['Zone',z=>z.zone],['Requests',z=>z.requests],['Per hour',z=>z.requests_per_hour],['Unmatched',z=>percent(z.unmatched_rate)],['Cancelled',z=>percent(z.cancel_rate)],['Worst p90 wait',z=>z.worst_p90_wait_s==null?'—':Math.round(z.worst_p90_wait_s)+' s'],['Net flow',z=>z.net_flow],['Drivers now',z=>(z.supply_now||{}).available],['Demand/supply',z=>z.demand_supply_ratio]];
function badge(text, cls) { return node('span', text, 'status '+(cls||'')); }
function decide(row, proposal, decision, buttons) {
  return async()=>{
    if(decision==='approved' && !confirm(`Approve ${amount(proposal)} in ${proposal.zone}, ${span(proposal.params)}? This creates the rule in core.`)) return;
    buttons.forEach(b=>b.disabled=true);
    try { await api(`reports/${row.id}/decisions`,'POST',{proposal_id:proposal.id,decision}); notice(decision==='approved'?`Approved: ${amount(proposal)} in ${proposal.zone}.`:`Rejected ${proposal.zone} ${proposal.type}.`); await refresh(); }
    catch(error){notice(error.message);buttons.forEach(b=>b.disabled=false);}
  };
}
function proposalItem(row, proposal) {
  const el=node('div',undefined,'report-proposal'), heading=node('div',undefined,'item-heading');
  heading.append(node('strong',`${proposal.zone} · ${amount(proposal)}`),node('time',span(proposal.params)));
  el.append(heading,node('p',proposal.reason),node('small',`Rule: ${proposal.rule}`,'muted'));
  const decided=(row.decisions||{})[proposal.id], actions=node('div',undefined,'actions');
  if(decided) actions.append(badge(DECISION[decided.status]||decided.status, decided.status==='rejected'?'muted-status':decided.status==='created'?'failed':''));
  else if(new Date(proposal.params.ends_at)<=new Date()) actions.append(badge('Expired','muted-status'));
  else { const approve=node('button','Approve','primary small'), reject=node('button','Reject','quiet'), buttons=[approve,reject];
    approve.onclick=decide(row,proposal,'approved',buttons); reject.onclick=decide(row,proposal,'rejected',buttons); actions.append(approve,reject); }
  el.append(actions); return el;
}
function reportCard(row) {
  const r=row.report, el=node('article',undefined,'report'), heading=node('div',undefined,'item-heading'), badges=node('span',undefined,'badges');
  const delivery=row.delivery&&row.delivery.status;
  badges.append(badge(r.explained_by==='model'?'Text by '+r.model:'Template text','muted-status'),badge(delivery?DELIVERY[delivery]||delivery:(row.published?'Published':'Publishing…'),['failed','parked'].includes(delivery)?'failed':''));
  heading.append(node('strong',`${date(r.window.from)} → ${date(r.window.to)}`),badges);
  el.append(heading,node('p',r.summary));
  if(r.proposals.length) el.append(...r.proposals.map(p=>proposalItem(row,p)));
  else el.append(node('div','No proposals in this report.','muted'));
  if(r.skipped.length) el.append(node('small','Skipped: '+r.skipped.map(s=>`${s.zone} (${s.reason})`).join('; '),'muted block'));
  const details=node('details'), wrap=node('div',undefined,'table-wrap'), table=node('table'), head=node('tr'), body=node('tbody');
  METRICS.forEach(([title])=>head.append(node('th',title)));
  r.zones.forEach(z=>{const tr=node('tr');METRICS.forEach(([,show])=>tr.append(node('td',shown(show(z)))));body.append(tr);});
  const thead=node('thead'); thead.append(head); table.append(thead,body); wrap.append(table);
  details.append(node('summary',`Zone metrics · created ${date(row.created_at)}`+(delivery&&row.delivery.last_error?` · ${row.delivery.last_error}`:'')),wrap);
  el.append(details); return el;
}
function reports(rows) {
  const latest=rows[0];
  const open=latest?latest.report.proposals.filter(p=>!(latest.decisions||{})[p.id]&&new Date(p.params.ends_at)>new Date()).length:0;
  $('report-count').textContent=latest?open:'—';
  $('report-summary-label').textContent=latest?`Open proposals, of ${latest.report.proposals.length} in the latest report`:'No report yet';
  if(latest) $('latest-summary').textContent=latest.report.summary;
  if(!rows.length) return empty('report-list','No reports yet. Run one from the overview or set a schedule.');
  $('report-list').replaceChildren(...rows.map(reportCard));
}
function activity(rows) {
  if(!rows.length) return empty('events','Waiting for the first event from RabbitMQ.');
  $('events').replaceChildren(...rows.map(row=>{const el=node('article',undefined,'event'), heading=node('div',undefined,'item-heading');heading.append(node('strong',row.kind),node('time',date(row.created_at)));el.append(heading,node('pre',JSON.stringify(row.payload,null,2)));return el;}));
}
function proposals(rows) {
  if(!rows.length) return empty('proposal-list','No proposals in core yet. Approve one from a report, or create a test proposal.');
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
    const results=await Promise.allSettled([['observations',observations],['reports',reports],['runs',runs],['activity',activity],['proposals',proposals]].map(async([path,render])=>render(await api(path))));
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
  if(working)return;working=true;notice('Reading zone metrics and writing the report…');
  document.querySelectorAll('.run-button').forEach(b=>b.disabled=true);
  try { const result=await api('run','POST');notice(result.status==='completed'?'Report ready. Review its proposals below.':'Run '+result.status+': '+(result.error||'check history')); document.querySelector(result.status==='completed'?'[data-view=reports]':'[data-view=agent]').click();await refresh(); }
  catch(error){notice(error.message);}finally{working=false;document.querySelectorAll('.run-button').forEach(b=>b.disabled=false);}
});
$('schedule-form').onsubmit=async event=>{event.preventDefault();const button=event.submitter;button.disabled=true;try{const recipients=$('recipients').value.split(/[\n,;]+/).map(v=>v.trim()).filter(Boolean);const row=await api('schedule','PUT',{cron:$('cron').value,timezone:$('timezone').value,enabled:$('enabled').checked,window_hours:Number($('window-hours').value),recipients});scheduleLoaded=false;showSchedule(row);notice('Schedule saved.');}catch(error){notice(error.message);}finally{button.disabled=false;}};
$('proposal-form').onsubmit=async event=>{event.preventDefault();event.submitter.disabled=true;try{await api('proposals','POST',{zone:$('proposal-zone').value,reason:$('proposal-reason').value});$('proposal-reason').value='';notice('Test proposal created.');await refresh();}catch(error){notice(error.message);}finally{event.submitter.disabled=false;}};
$('refresh').onclick=()=>{notice('');refresh();};
window.addEventListener('online',refresh);window.addEventListener('offline',refresh);
window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();deferredInstall=event;$('install').hidden=false;});
$('install').onclick=async()=>{if(deferredInstall){await deferredInstall.prompt();deferredInstall=null;$('install').hidden=true;}};
if('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js');
refresh();
setInterval(()=>{if(!document.hidden&&!working)refresh();},30000);
