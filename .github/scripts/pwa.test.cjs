const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync,existsSync} = require('node:fs');
const vm = require('node:vm');
function worker(path, names) {
  const events={},deleted=[],intercepted=[];
  let unregistered=false;
  const self={location:{origin:'https://unter.test'},registration:{unregister:async()=>unregistered=true},
    skipWaiting:async()=>{},clients:{claim:async()=>{}},addEventListener:(name,fn)=>events[name]=fn};
  vm.runInNewContext(readFileSync(path,'utf8'),{self,URL,Response,
    caches:{keys:async()=>names,delete:async name=>deleted.push(name)}});
  return {events,deleted,get unregistered(){return unregistered},
    fetch(path,method='GET'){
      events.fetch({request:{url:new URL(path,'https://unter.test').href,method},respondWith:value=>intercepted.push(value)});
      return intercepted.length;
    }};
}
test('ride manifest is scoped independently from dashboard',()=>{
  const manifest=JSON.parse(readFileSync('web/ride/manifest.webmanifest'));
  assert.equal(manifest.start_url,'/ride/');assert.equal(manifest.scope,'/ride/');assert.equal(manifest.id,'/ride/');
  assert(!readFileSync('web/index.html','utf8').includes('rel="manifest"'));
  assert(!existsSync('web/manifest.webmanifest'));
});
test('ride worker bypasses API, POSTs, dashboard, queries and external URLs',()=>{
  const h=worker('web/ride/sw.js',[]);
  for(const [path,method]of [['/api/trips','GET'],['/ride/','POST'],['/','GET'],['/app.js','GET'],['/ride/?secret=1','GET'],['https://other.test/ride/','GET']]){
    assert.equal(h.fetch(path,method),0,`${method} ${path}`);
  }
});
test('retirement removes only old dashboard caches and unregisters itself',async()=>{
  const h=worker('web/sw.js',['unter-shell-v1','unter-shell-v2','unter-ride-shell-v1','other-app']);
  let task;h.events.activate({waitUntil:value=>task=value});await task;
  assert.deepEqual(h.deleted,['unter-shell-v1','unter-shell-v2']);assert(h.unregistered);
});
test('ride activation preserves other application caches',async()=>{
  const h=worker('web/ride/sw.js',['unter-ride-shell-v0','unter-ride-shell-v1','other-app']);
  let task;h.events.activate({waitUntil:value=>task=value});await task;
  assert.deepEqual(h.deleted,['unter-ride-shell-v0']);assert(!h.unregistered);
});
