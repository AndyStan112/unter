const test = require('node:test');
const assert = require('node:assert/strict');
const publish = require('./publish-deployment.cjs');

test('Publishes a complete, source-SHA-pinned manifest snapshot without secret files', async()=>{
  let created;
  const github={rest:{git:{
    getTree:async()=>({data:{tree:[
      {path:'deploy/app/kustomization.yaml',type:'blob',mode:'100644',sha:'manifest'},
      {path:'deploy/app/core.yaml',type:'blob',mode:'100644',sha:'core'},
      {path:'.env',type:'blob',mode:'100644',sha:'NEVER'},
      {path:'services/source.py',type:'blob',mode:'100644',sha:'source'},
    ]}}),
    createTree:async(args)=>{created=args;return {data:{sha:'tree'}};},
    getRef:async()=>{throw Object.assign(new Error(),{status:404});},
    createCommit:async(args)=>{assert.deepEqual(args.parents,[]);return {data:{sha:'commit'}};},
    createRef:async(args)=>{assert.equal(args.ref,'refs/heads/deployments');},
  }, repos:{getContent:async()=>({data:{content:Buffer.from('images:\n  - name: core\n    newTag: dev\n  - name: python\n    newTag: dev\n').toString('base64')}})}}};
  await publish({github, context:{ref:'refs/heads/main',sha:'1234567890',repo:{owner:'o',repo:'r'}},core:{notice(){}}});
  assert.equal(created.tree.length,2);
  assert.ok(created.tree.every(e=>e.path.startsWith('deploy/app/')));
  assert.equal(created.base_tree,undefined);
  assert.match(created.tree[0].content,/newTag: 1234567890/);
});

test('Rejects untested source branches',async()=>{
  await assert.rejects(()=>publish({context:{ref:'refs/heads/deployments'}}),/main/);
});
