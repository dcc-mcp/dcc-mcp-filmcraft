import { FilmCraftClient, installMessageBridge } from './dcc-sdk.js';
const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));
const report={started:new Date().toISOString(),checks:[],runtime:null};
const panel=document.createElement('pre');panel.id='dcc-result';panel.style='position:fixed;bottom:0;left:0;right:0;max-height:24vh;overflow:auto;background:#111d;color:white;margin:0;padding:10px;font:12px monospace;z-index:99;';document.body.append(panel);
const update=()=>panel.textContent=JSON.stringify(report,null,2);
const assert=(ok,name,detail)=>{report.checks.push({name,ok,detail});update();if(!ok)throw Error(name+': '+JSON.stringify(detail));};
async function upload(name,body){const r=await fetch('/evidence/'+name,{method:'POST',body});if(!r.ok)throw Error('evidence write failed '+name);}
async function rejects(fn,code,name){try{await fn();assert(false,name,'unexpected success')}catch(e){assert(e.code===code,name,{code:e.code,message:e.message});}}
try{
 let waited=0;while(!window.filmcraftLoad?.readyMs){if(window.filmcraftLoad?.error)throw Error(window.filmcraftLoad.error);if((waited+=100)>120000)throw Error('load timeout');await sleep(100);}
 report.runtime=filmcraft.info();report.load=filmcraftLoad;
 await rejects(()=>FilmCraftClient.connect({expectedOrigin:'https://wrong.invalid'}),'ORIGIN','wrong origin refused');
 const client=await FilmCraftClient.connect({expectedOrigin:location.origin,sessionId:'dcc-filmcraft-acceptance-20261013',timeoutMs:30000});
 report.initial=await client.inspect();update();
 await client.createProject('DCC browser same document');
 const source=await(await fetch('./poc-source.mp4')).blob();
 const imported=await client.importMedia(new File([source],'poc-source.mp4',{type:'video/mp4'}));
 assert(imported.items.length===1,'source media imported',imported);
 await client.createSequence({name:'Browser original',fromItem:imported.items[0]});
 const project=await client.inspect(), sequence=project.activeSequence;
 assert(Number.isInteger(sequence),'sequence created',project);
 await client.renameItem(sequence,'Browser edited');
 const renamed=await client.inspectSequence(sequence);
 assert(renamed.name==='Browser edited','same live sequence edited',renamed.name);
 await client.undo();assert((await client.inspectSequence(sequence)).name==='Browser original','undo changed live document');
 await client.redo();assert((await client.inspectSequence(sequence)).name==='Browser edited','redo restored edit');
 const originalTimeline=await client.inspectSequence(sequence);
 const videoClip=originalTimeline.video.flatMap(t=>t.items)[0].clip;
 const beforeShot=await filmcraft.screenshot();await upload('before-editor.png',Uint8Array.from(atob(beforeShot.pngBase64),c=>c.charCodeAt(0)));
 await client.setPlaybackRate({sequence,clip:videoClip,percent:50});
 const retimed=await client.inspectSequence(sequence);
 assert(retimed.durationFrames===originalTimeline.durationFrames*2,'retime doubled timeline duration',retimed.durationFrames);
 assert(retimed.video.flatMap(t=>t.items)[0].speed===0.5,'video retimed to half speed');
 assert(retimed.audio.flatMap(t=>t.items)[0].speed===0.5,'linked audio retimed together');
 await client.undo();assert((await client.inspectSequence(sequence)).durationFrames===originalTimeline.durationFrames,'retime undo restores duration');
 await client.redo();assert((await client.inspectSequence(sequence)).durationFrames===retimed.durationFrames,'retime redo restores duration');
 const ui=await filmcraft.inspect();report.visibleUI={project:ui.project,activeSequence:ui.activeSequence};report.sequence=await client.inspectSequence(sequence);
 assert(ui.activeSequence===sequence,'official visible UI shares sequence',report.visibleUI);
 const saved=await client.save('browser-project');await upload('project.fcproj',saved.bytes);
 assert(saved.bytes.length>100,'native project bytes saved',saved.bytes.length);
 await rejects(()=>client.save('../escape'),'INVALID_ARGUMENT','path traversal refused');
 await rejects(()=>client.save('browser-project'),'EXISTS','overwrite refused');
 await rejects(()=>client.reopen('/not-owned.fcproj'),'DOCUMENT','unowned reopen refused');
 const aborted=new AbortController();aborted.abort();await rejects(()=>client.renameItem(sequence,'SHOULD NOT APPEAR',{signal:aborted.signal}),'CANCELLED','pre-dispatch cancellation');
 assert((await client.inspectSequence(sequence)).name==='Browser edited','cancelled mutation did not apply');
 const reopened=await client.reopen(saved.path);assert(reopened.activeSequence===sequence,'native save reopened same sequence',reopened);
 assert((await client.inspectSequence(sequence)).name==='Browser edited','reopen preserved edit');
 assert((await client.inspectSequence(sequence)).durationFrames===retimed.durationFrames,'reopen preserved retimed timeline');
 for(const format of ['h264','wav']){
  const result=await client.exportVideo({name:'browser-'+format,sequence,format});let job;const start=performance.now();
  do{await sleep(100);job=(await client.jobs()).find(x=>x.id===result.job);if(performance.now()-start>120000)throw Error('export timed out '+format);}while(!job?.finished);
  assert(!job.error&&!job.result?.error,format+' export job succeeded',job);
  const bytes=await client.readExport(result.path);await upload(format==='wav'?'export.wav':'export.mp4',bytes);assert(bytes.length>100,format+' exported bytes read',bytes.length);
 }
 const cancelledExport=await client.exportVideo({name:'cancelled-export',sequence,format:'h264'});
 await client.cancelExport(cancelledExport.job);
 let cancelJob;const cancelStart=performance.now();do{await sleep(100);cancelJob=(await client.jobs()).find(j=>j.id===cancelledExport.job);if(performance.now()-cancelStart>30000)throw Error('cancel did not settle');}while(!cancelJob?.finished);
 assert(cancelJob.finished&&cancelJob.result?.error==='cancelled','owned export cancellation reaches terminal cancelled state',cancelJob);
 let calls=0;const detach=installMessageBridge({hostWindow:window,controllerWindow:window,allowedOrigin:location.origin,sessionId:client.sessionId,handlers:{probe:()=>{calls++;return 'ok'}}});
 const data={protocol:'dcc-craft/1',session:client.sessionId,id:'negative-test',operation:'probe',params:{}};
 window.dispatchEvent(new MessageEvent('message',{origin:'https://wrong.invalid',source:window,data}));
 window.dispatchEvent(new MessageEvent('message',{origin:location.origin,source:null,data}));
 window.dispatchEvent(new MessageEvent('message',{origin:location.origin,source:window,data:{...data,session:'wrong'}}));
 await sleep(50);assert(calls===0,'origin source session negatives rejected');
 window.postMessage({...data,id:'positive-test'},location.origin);await sleep(50);assert(calls===1,'authorized same-window request accepted');
 window.postMessage({...data,id:'positive-test'},location.origin);await sleep(50);assert(calls===1,'replay rejected');detach();
 window.postMessage({...data,id:'after-close'},location.origin);await sleep(50);assert(calls===1,'message listener removed');
 try{await filmcraft.execute('dcc.invalid.command',{});assert(false,'host error surfaced')}catch(e){assert(String(e).length>0,'host error surfaced',String(e));}
 assert((await client.inspectSequence(sequence)).name==='Browser edited','host stayed usable after error');
 const shot=await filmcraft.screenshot();await upload('visible-editor.png',Uint8Array.from(atob(shot.pngBase64),c=>c.charCodeAt(0)));
 await client.close();await rejects(()=>client.inspect(),'CLOSED','closed SDK refuses calls');
 assert((await filmcraft.execute('project.inspect')).activeSequence===sequence,'cleanup preserves visible user document');
 report.passed=true;
}catch(e){report.passed=false;report.error=String(e.stack||e);}
report.finished=new Date().toISOString();update();await upload('browser-report.json',JSON.stringify(report,null,2));document.title=report.passed?'PASS FilmCraft DCC acceptance':'FAIL FilmCraft DCC acceptance';
