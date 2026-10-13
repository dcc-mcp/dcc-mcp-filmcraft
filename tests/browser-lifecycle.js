import { FilmCraftClient } from './dcc-sdk.js';
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const report={started:new Date().toISOString(),checks:[],runtime:null};
const assert=(ok,name,detail)=>{report.checks.push({name,ok,detail});if(!ok)throw Error(name+': '+JSON.stringify(detail));};
async function rejects(fn,code,name){try{await fn();assert(false,name,'unexpected success')}catch(error){assert(error.code===code,name,{code:error.code,message:error.message});}}
async function until(fn,name){const start=performance.now();while(!fn()){if(performance.now()-start>120000)throw Error(name+' timed out');await sleep(10);}}
try {
  await until(()=>{if(window.filmcraftLoad?.error)throw Error(window.filmcraftLoad.error);return window.filmcraftLoad?.readyMs;},'official runtime');
  const original=window.filmcraft;report.runtime=original.info();
  let release,applied=false,executeCalls=0,mutationCalls=0,filesCalls=0;
  const gate=new Promise(resolve=>{release=resolve;});
  // Test-only response gate installed before connection. Every command still
  // executes on the real official editor; no fabricated mutation response.
  const wrapped={...original,files:()=>{filesCalls++;return original.files();},execute:async(id,params)=>{
    executeCalls++;if(id==='file.newProject')mutationCalls++;
    const result=await original.execute(id,params);
    if(id==='file.newProject'){applied=true;await gate;}
    return result;
  }};
  window.filmcraft=wrapped;
  const sessionId='dcc-filmcraft-lifecycle-20261013';
  const client=await FilmCraftClient.connect({expectedOrigin:location.origin,sessionId,timeoutMs:500});
  await rejects(()=>client.createProject('Applied before identity loss'),'TIMEOUT','official mutation wait times out');
  await until(()=>applied,'real mutation application');
  assert((await original.execute('project.inspect',{})).name==='Applied before identity loss','real official project changed before receipt release');
  window.filmcraft={...wrapped};
  const before=executeCalls;
  const pending=client.reconcile();
  assert(pending.settled===false&&pending.uncertain===true,'pending receipt readable after API replacement',pending);
  assert(executeCalls===before,'pending reconciliation does not execute host commands');
  release();
  // Receipt polling is purely local and is the only SDK activity until settled.
  let receipt;await until(()=>{receipt=client.reconcile();return receipt.settled;},'late local receipt');
  assert(receipt.ok===false&&receipt.code==='SESSION'&&receipt.uncertain===false,'late receipt reports session loss without claiming cancellation',receipt);
  assert(receipt.sessionId===sessionId&&receipt.origin===location.origin,'late receipt keeps original session and origin provenance',receipt);
  assert(executeCalls===before,'settled reconciliation and revoked continuation execute no host commands');
  window.filmcraft=wrapped;
  await rejects(()=>client.inspect(),'SESSION','restoring the old API does not restore read authority');
  await rejects(()=>client.createProject('Must not appear'),'SESSION','restoring the old API does not restore mutation authority');
  await rejects(()=>client.save('must-not-save'),'SESSION','revoked save refuses before virtual-file access');
  await rejects(()=>client.close(),'SESSION','revoked close does not query host jobs');
  assert(executeCalls===before&&mutationCalls===1&&filesCalls===0,'timed-out mutation is never replayed or allowed file access after restoration',{executeCalls,mutationCalls,filesCalls});
  const project=await original.execute('project.inspect',{});
  assert(project.name==='Applied before identity loss','failed receipt does not imply rollback of the applied mutation',project);
  report.passed=true;
} catch(error) {report.passed=false;report.error=String(error.stack||error);}
report.finished=new Date().toISOString();
const panel=document.createElement('pre');panel.textContent=JSON.stringify(report,null,2);panel.style='position:fixed;inset:0;overflow:auto;background:#111d;color:white;padding:20px;z-index:99';document.body.append(panel);
const response=await fetch('/evidence/lifecycle-report.json',{method:'POST',body:JSON.stringify(report,null,2)});
if(!response.ok)throw Error('lifecycle evidence write failed');
document.title=report.passed?'PASS FilmCraft lifecycle':'FAIL FilmCraft lifecycle';
