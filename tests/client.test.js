import test from 'node:test';
import assert from 'node:assert/strict';
import { FilmCraftClient, installMessageBridge } from '../src/index.js';
const ORIGIN = 'https://editor.example';
const SESSION = 'test-session-123456789';
const ids = ['project.inspect','sequence.inspect','file.newProject','file.newSequence','clip.rename','timeline.select','clip.speedDuration','edit.undo','edit.redo','file.saveAs','file.open','file.exportMedia','jobs.list','jobs.cancel'];
function fixture() {
  const calls = []; const project = { name:'Untitled', root:{id:1,children:[]}, dirty:false, activeSequence:2 };
  const handlers = new Map(); let fn;
  const host = { location:{origin:ORIGIN},document:{},File,addEventListener:(n,f)=>{fn=f},removeEventListener:()=>{fn=null} };
  host.filmcraft = {
    commands:async()=>ids.map(id=>({id})),
    execute:async(id,p)=>{calls.push([id,p]);if(handlers.has(id))return handlers.get(id)(p);if(id==='project.inspect')return structuredClone(project);if(id==='jobs.list')return [];return {};},
    inspect:async()=>({activeSequence:2}), info:()=>({compositor:'cpu'}), files:()=>[], readFile:async()=>new Uint8Array([1,2,3]),importFiles:async()=>({items:[1],errors:[]}),openProject:async()=>({}),
  };
  return {host,project,calls,handlers,emit:async(event)=>fn?.(event)};
}
const connect = (f,options={}) => FilmCraftClient.connect({window:f.host,expectedOrigin:ORIGIN,sessionId:SESSION,...options});
test('connects to explicit origin and reports real capability data',async()=>{const f=fixture(),c=await connect(f);assert.equal((await c.inspect()).name,'Untitled');assert.equal(c.info().compositor,'cpu');});
test('refuses wrong origin, bad session, and unavailable API',async()=>{const f=fixture();await assert.rejects(connect(f,{expectedOrigin:'https://other.example'}),{code:'ORIGIN'});await assert.rejects(connect(f,{sessionId:'short'}),{code:'SESSION'});delete f.host.filmcraft;await assert.rejects(connect(f),{code:'NOT_READY'});});
test('refuses stale document and API identity after navigation',async()=>{const f=fixture(),c=await connect(f);f.host.document={};await assert.rejects(c.inspect(),{code:'SESSION'});});
test('detects active project changed before edit',async()=>{const f=fixture(),c=await connect(f);f.project.name='Other';await assert.rejects(c.renameItem(2,'Name'),{code:'DOCUMENT'});assert.equal(f.calls.filter(([id])=>id==='clip.rename').length,0);});
test('requires empty clean project before creation',async()=>{const f=fixture(),c=await connect(f);f.project.dirty=true;await assert.rejects(c.createProject('Overwrite'),{code:'DOCUMENT'});});
test('validates ids, file sizes, extensions and safe paths',async()=>{const f=fixture(),c=await connect(f);await assert.rejects(c.renameItem(-1,'X'),{code:'INVALID_ARGUMENT'});await assert.rejects(c.importMedia({name:'a.mp4',size:20*1024*1024}),{code:'INVALID_ARGUMENT'});await assert.rejects(c.importMedia({name:'a.exe',size:1}),{code:'UNSUPPORTED'});await assert.rejects(c.save('../escape'),{code:'INVALID_ARGUMENT'});await assert.rejects(c.readExport('/secret.mp4'),{code:'SESSION'});});
test('pre-aborted mutation is never dispatched',async()=>{const f=fixture(),c=await connect(f);const a=new AbortController();a.abort();await assert.rejects(c.renameItem(2,'X',{signal:a.signal}),{code:'CANCELLED'});assert.equal(f.calls.filter(([id])=>id==='clip.rename').length,0);});
test('uncertain receipt survives intervening read-only calls',async()=>{const f=fixture(),c=await connect(f,{timeoutMs:10});let finish;f.handlers.set('clip.rename',()=>new Promise(r=>{finish=r}));await assert.rejects(c.renameItem(2,'X'),{code:'TIMEOUT'});await c.inspect();assert.deepEqual(c.reconcile(),{settled:false,uncertain:true});await assert.rejects(c.renameItem(2,'Y'),{code:'UNCERTAIN'});finish({renamed:true});await new Promise(r=>setTimeout(r,0));assert.equal(c.reconcile().ok,true);assert.equal(f.calls.filter(([id])=>id==='clip.rename').length,1);});
test('post-dispatch abort does not pretend to cancel host mutation',async()=>{const f=fixture(),c=await connect(f);let finish;f.handlers.set('clip.rename',()=>new Promise(r=>{finish=r}));const a=new AbortController(),p=c.renameItem(2,'X',{signal:a.signal});while(!finish)await new Promise(r=>setTimeout(r,0));a.abort();await assert.rejects(p,{code:'CANCELLED'});assert.equal(c.reconcile().uncertain,true);finish({});});
test('native snapshots are copied and refuse overwrite/unowned reopen',async()=>{const f=fixture(),c=await connect(f);const saved=await c.save('test');saved.bytes[0]=9;let reopened;f.handlers.set('file.open',async params=>{reopened=params.path});await c.reopen(saved.path);assert.equal(reopened,saved.path);await assert.rejects(c.save('test'),{code:'EXISTS'});await assert.rejects(c.reopen('/foreign.fcproj'),{code:'DOCUMENT'});});
test('export checks active sequence and supports bounded formats',async()=>{const f=fixture(),c=await connect(f);await assert.rejects(c.exportVideo({name:'x',sequence:4}),{code:'DOCUMENT'});await assert.rejects(c.exportVideo({name:'x',sequence:2,format:'unknown'}),{code:'UNSUPPORTED'});});
test('cancel cannot target jobs outside the client',async()=>{const c=await connect(fixture());await assert.rejects(c.cancelExport(44),{code:'SESSION'});});
test('cleanup preserves editor and removes SDK authority',async()=>{const f=fixture(),c=await connect(f);assert.equal((await c.close()).documentPreserved,true);await assert.rejects(c.inspect(),{code:'CLOSED'});assert.equal(f.project.name,'Untitled');});
test('message bridge pins origin, source, session, operation and replay',async()=>{const f=fixture();let calls=0;const sent=[],source={postMessage:(...v)=>sent.push(v)};const stop=installMessageBridge({hostWindow:f.host,controllerWindow:source,allowedOrigin:ORIGIN,sessionId:SESSION,handlers:{probe:()=>++calls}});const data={protocol:'dcc-craft/1',session:SESSION,id:'r1',operation:'probe'};const event={origin:ORIGIN,source,data};for(const e of [{...event,origin:'https://bad.example'},{...event,source:{}},{...event,data:{...data,session:'bad'}},{...event,data:{...data,operation:'__proto__'}}])await f.emit(e);assert.equal(calls,0);await f.emit(event);await f.emit(event);assert.equal(calls,1);assert.equal(sent[0][1],ORIGIN);stop();await f.emit({...event,data:{...data,id:'r2'}});assert.equal(calls,1);});
test('message bridge stops replying after navigation',async()=>{const f=fixture();let finish;const sent=[],source={postMessage:(...v)=>sent.push(v)};installMessageBridge({hostWindow:f.host,controllerWindow:source,allowedOrigin:ORIGIN,sessionId:SESSION,handlers:{probe:()=>new Promise(r=>{finish=r})}});const work=f.emit({origin:ORIGIN,source,data:{protocol:'dcc-craft/1',session:SESSION,id:'r1',operation:'probe'}});f.host.document={};finish({});await work;assert.equal(sent.length,0);});
test('same-name external project replacement is caught by revision lease',async()=>{const f=fixture(),c=await connect(f);f.project.revision=2;await assert.rejects(c.renameItem(2,'X'),{code:'DOCUMENT'});});
test('late export keeps its owned job and reserves filename immediately',async()=>{const f=fixture(),c=await connect(f,{timeoutMs:10});let finish;f.handlers.set('file.exportMedia',()=>new Promise(r=>{finish=r}));await assert.rejects(c.exportVideo({name:'same',sequence:2}),{code:'TIMEOUT'});finish({job:7});await new Promise(r=>setTimeout(r,0));assert.equal(c.reconcile().result.job,7);await assert.rejects(c.exportVideo({name:'same',sequence:2}),{code:'EXISTS'});await c.cancelExport(7);assert.equal(f.calls.find(([id])=>id==='file.exportMedia')[1].sequence,2);});
test('late save retains snapshot bookkeeping for reopen',async()=>{const f=fixture(),c=await connect(f,{timeoutMs:10});let finish;f.handlers.set('file.saveAs',()=>new Promise(r=>{finish=r}));await assert.rejects(c.save('late'),{code:'TIMEOUT'});finish({});await new Promise(r=>setTimeout(r,0));const r=c.reconcile();assert.equal(r.ok,true);await c.reopen(r.result.path);});
test('native reopen never imports a colliding /projects basename',async()=>{const f=fixture(),c=await connect(f);let imports=0;f.host.filmcraft.openProject=async()=>{imports++};f.host.filmcraft.files=()=>[{path:'/projects/test.fcproj',size:3}];const saved=await c.save('test');await c.reopen(saved.path);assert.equal(imports,0);assert.equal(f.calls.find(([id])=>id==='file.open')[1].path,saved.path);});
test('modified native save cannot be reopened',async()=>{const f=fixture(),c=await connect(f);const saved=await c.save('test');f.host.filmcraft.readFile=async()=>new Uint8Array([9,2,3]);await assert.rejects(c.reopen(saved.path),{code:'DOCUMENT'});});
test('cross-realm Uint8Array save is accepted and copied',async()=>{const {runInNewContext}=await import('node:vm');const f=fixture(),c=await connect(f);f.host.filmcraft.readFile=async()=>runInNewContext('new Uint8Array([1,2,3])');assert.deepEqual((await c.save('cross')).bytes,new Uint8Array([1,2,3]));});
test('session replacement during host mutation rejects result',async()=>{const f=fixture(),c=await connect(f);let finish;f.handlers.set('clip.rename',()=>new Promise(r=>{finish=r}));const pending=c.renameItem(2,'X');while(!finish)await new Promise(r=>setTimeout(r,0));f.host.document={};finish({});await assert.rejects(pending,{code:'SESSION'});});
test('close refuses live owned jobs instead of losing cancellation ownership',async()=>{const f=fixture(),c=await connect(f);f.handlers.set('file.exportMedia',async()=>({job:7}));await c.exportVideo({name:'active',sequence:2});f.handlers.set('jobs.list',async()=>[{id:7,finished:false}]);await assert.rejects(c.close(),{code:'BUSY'});await c.cancelExport(7);});
test('late selection receipt covers the requested retime, not just selection',async()=>{
  const f=fixture(),c=await connect(f,{timeoutMs:10});let finish;
  f.handlers.set('timeline.select',()=>new Promise(r=>{finish=r}));
  f.handlers.set('clip.speedDuration',async()=>({speed:0.5}));
  await assert.rejects(c.setPlaybackRate({sequence:2,clip:3,percent:50}),{code:'TIMEOUT'});
  assert.deepEqual(c.reconcile(),{settled:false,uncertain:true});
  finish({selection:[3]});await new Promise(r=>setTimeout(r,0));
  assert.deepEqual(c.reconcile(),{settled:true,uncertain:false,sessionId:SESSION,origin:ORIGIN,ok:true,result:{speed:0.5},error:undefined,code:undefined});
  assert.equal(f.calls.filter(([id])=>id==='clip.speedDuration').length,1);
});
test('abort during selection does not dispatch retime or claim successful retime',async()=>{
  const f=fixture(),c=await connect(f);let finish;const a=new AbortController();
  f.handlers.set('timeline.select',()=>new Promise(r=>{finish=r}));
  const pending=c.setPlaybackRate({sequence:2,clip:3,percent:50},{signal:a.signal});
  while(!finish)await new Promise(r=>setTimeout(r,0));a.abort();await assert.rejects(pending,{code:'CANCELLED'});
  finish({selection:[3]});await new Promise(r=>setTimeout(r,0));
  const receipt=c.reconcile();assert.equal(receipt.ok,false);assert.match(receipt.error,/retiming was not dispatched/);
  assert.equal(f.calls.filter(([id])=>id==='clip.speedDuration').length,0);
});
test('project changes during delayed selection prevent retime',async()=>{
  const f=fixture(),c=await connect(f);let finish;
  f.handlers.set('timeline.select',()=>new Promise(r=>{finish=r}));
  const pending=c.setPlaybackRate({sequence:2,clip:3,percent:50});
  while(!finish)await new Promise(r=>setTimeout(r,0));f.project.revision=3;finish({selection:[3]});
  await assert.rejects(pending,{code:'DOCUMENT'});assert.equal(f.calls.filter(([id])=>id==='clip.speedDuration').length,0);
});
test('missing retime capability never dispatches selection',async()=>{
  const f=fixture();f.host.filmcraft.commands=async()=>ids.filter(id=>id!=='clip.speedDuration').map(id=>({id}));
  const c=await connect(f);await assert.rejects(c.setPlaybackRate({sequence:2,clip:3,percent:50}),{code:'UNSUPPORTED'});
  assert.equal(f.calls.filter(([id])=>id==='timeline.select').length,0);
});
test('late failed import receipt includes validation and preserves bookkeeping',async()=>{
  const f=fixture(),c=await connect(f,{timeoutMs:10});let finish;
  f.host.filmcraft.importFiles=()=>new Promise(r=>{finish=r});
  await assert.rejects(c.importMedia({name:'bad.mp4',size:3}),{code:'TIMEOUT'});
  f.project.revision=3;finish({items:[],errors:['unsupported media']});await new Promise(r=>setTimeout(r,0));
  const receipt=c.reconcile();assert.equal(receipt.ok,false);assert.match(receipt.error,/unsupported media/);
  await c.renameItem(2,'Still usable');
});
for (const identity of ['document', 'filmcraft', 'origin', 'inaccessible']) {
  test(`late mutation receipt remains local after ${identity} loss and cannot revive the session`, async () => {
    const f=fixture(), c=await connect(f,{timeoutMs:10}); let finish;
    const original={document:f.host.document,filmcraft:f.host.filmcraft,location:f.host.location};
    f.handlers.set('clip.rename',()=>new Promise(resolve=>{finish=()=>{f.project.name='Applied';resolve({renamed:true});};}));
    await assert.rejects(c.renameItem(2,'Applied'),{code:'TIMEOUT'});
    if(identity==='origin') f.host.location={origin:'https://other.example'};
    else if(identity==='inaccessible') Object.defineProperty(f.host,'location',{configurable:true,get(){throw Error('inaccessible');}});
    else f.host[identity]={};
    // Reconciliation does not even inspect host properties while work is pending.
    assert.deepEqual(c.reconcile(),{settled:false,uncertain:true});
    finish(); await new Promise(r=>setTimeout(r,0));
    // An inaccessible host must not prevent reading the now-local receipt.
    for (const name of ['location','document','filmcraft']) Object.defineProperty(f.host,name,{configurable:true,get(){throw Error('receipt read host');}});
    c.sessionId='changed-public-session';
    const receipt=c.reconcile();
    assert.equal(receipt.settled,true);assert.equal(receipt.uncertain,false);assert.equal(receipt.ok,false);
    assert.equal(receipt.code,'SESSION');assert.equal(receipt.sessionId,SESSION);assert.equal(receipt.origin,ORIGIN);
    assert.match(receipt.error,/editor/);assert.equal(f.project.name,'Applied');
    for (const [name,value] of Object.entries(original)) Object.defineProperty(f.host,name,{configurable:true,writable:true,value});
    let filesCalls=0;original.filmcraft.files=()=>{filesCalls++;return [];};
    const callCount=f.calls.length;
    await assert.rejects(c.inspect(),{code:'SESSION'});
    await assert.rejects(c.renameItem(2,'Replay'),{code:'SESSION'});
    await assert.rejects(c.save('after-loss'),{code:'SESSION'});
    await assert.rejects(c.exportVideo({name:'after-loss',sequence:2}),{code:'SESSION'});
    await assert.rejects(c.readExport('/dcc/no-export.mp4'),{code:'SESSION'});
    assert.throws(()=>c.info(),{code:'SESSION'});
    await assert.rejects(c.close(),{code:'SESSION'});
    assert.equal(filesCalls,0);assert.equal(f.calls.length,callCount);
    assert.equal(f.calls.filter(([id])=>id==='clip.rename').length,1);
  });
}
test('identity loss observed by a read permanently revokes execution after restoration',async()=>{
  const f=fixture(),c=await connect(f),document=f.host.document;f.host.document={};
  await assert.rejects(c.inspect(),{code:'SESSION'});f.host.document=document;
  assert.deepEqual(c.reconcile(),{settled:true,uncertain:false});
  await assert.rejects(c.inspect(),{code:'SESSION'});
});
test('session failure without a timeout still retains its local mutation receipt',async()=>{
  const f=fixture(),c=await connect(f);let finish;
  f.handlers.set('clip.rename',()=>new Promise(r=>{finish=r}));const work=c.renameItem(2,'Applied');
  while(!finish)await new Promise(r=>setTimeout(r,0));f.host.document={};finish({renamed:true});
  await assert.rejects(work,{code:'SESSION'});const receipt=c.reconcile();
  assert.equal(receipt.ok,false);assert.equal(receipt.code,'SESSION');assert.equal(receipt.sessionId,SESSION);
});
test('identity replacement before scheduled dispatch is refused without calling the old API',async()=>{
  const f=fixture(),c=await connect(f),count=f.calls.length;
  const work=c.renameItem(2,'Never dispatched');f.host.filmcraft={};
  await assert.rejects(work,{code:'SESSION'});assert.equal(f.calls.length,count);
});
test('revocation during late save readback prevents the final host query after API restoration',async()=>{
  const f=fixture();let finish;
  f.host.filmcraft.readFile=()=>new Promise(r=>{finish=r});
  const c=await connect(f,{timeoutMs:10}),original=f.host.filmcraft;
  await assert.rejects(c.save('late-read'),{code:'TIMEOUT'});
  f.host.filmcraft={};await assert.rejects(c.inspect(),{code:'SESSION'});
  f.host.filmcraft=original;const count=f.calls.length;finish(new Uint8Array([1,2,3]));
  await new Promise(r=>setTimeout(r,0));assert.equal(f.calls.length,count);
  assert.equal(c.reconcile().code,'SESSION');
});
