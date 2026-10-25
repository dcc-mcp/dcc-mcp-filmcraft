"""Real agent-protocol acceptance: MCP stdio -> Core -> the same official visible editor."""
import argparse
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--runtime-zip', type=Path)
parser.add_argument('--mode', choices=['browser', 'native'], default='browser')
parser.add_argument('--native-cli', type=Path)
parser.add_argument('--intentional-native-restart', action='store_true')
parser.add_argument('--chromium')
parser.add_argument('--output', type=Path, default=ROOT/'evidence/mcp')
args = parser.parse_args()
if args.intentional_native_restart and args.mode != 'native':
    parser.error('--intentional-native-restart is native-only')
args.output.mkdir(parents=True, exist_ok=True)
report = {'checks': [], 'mode': args.mode, 'transport': 'genuine MCP stdio', 'core_version': __import__('dcc_mcp_core').__version__}


def check(ok, name, detail=None):
    report['checks'].append({'name': name, 'ok': bool(ok), 'detail': detail})
    if not ok:
        raise AssertionError(name + ': ' + str(detail))


async def main():
    source = args.output/'source.mp4'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','lavfi','-i','testsrc2=size=160x90:rate=12','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','1','-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-c:a','aac','-b:a','64k','-movflags','+faststart',str(source)],check=True)
    if args.mode == 'native':
        if not args.native_cli:
            parser.error('--mode native requires --native-cli')
        command = ['-m','dcc_mcp_filmcraft.cli','serve','--mode','native','--native-cli',
                   str(args.native_cli.resolve()),'--workspace',str((args.output/'workspace').resolve()),
                   '--evidence-dir',str(args.output.resolve())]
    else:
        if not args.runtime_zip:
            parser.error('browser mode requires --runtime-zip')
        command = ['-m','dcc_mcp_filmcraft.cli','serve','--runtime-zip',str(args.runtime_zip.resolve()),
                   '--headless','--evidence-dir',str(args.output.resolve())]
        if args.chromium:
            command += ['--chromium', str(Path(args.chromium).resolve())]
    env = {**os.environ, 'PYTHONPATH': str(ROOT/'python')}
    params = StdioServerParameters(command=sys.executable,args=command,env=env)
    with (args.output/'stderr.log').open('w') as errlog:
        async with stdio_client(params, errlog=errlog) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                initialized = await client.initialize()
                report['protocol'] = initialized.protocolVersion
                tools = (await client.list_tools()).tools
                expected_count=18 if args.mode=='native' else 19
                check(len(tools)==expected_count,str(expected_count)+' typed Core-backed tools listed',[x.name for x in tools])
                check(all(x.inputSchema.get('additionalProperties') is False for x in tools),'all tool schemas reject extra properties')
                prompts=(await client.list_prompts()).prompts
                skill='filmcraft-native' if args.mode=='native' else 'filmcraft-browser'
                check([p.name for p in prompts]==[skill],'mode-specific MCP skill prompt discoverable')
                prompt=await client.get_prompt(skill)
                check('TIMEOUT' in prompt.messages[0].content.text,'skill prompt delivers safety workflow')
                async def call(name, parameters=None):
                    result = await client.call_tool('filmcraft_'+name, parameters or {})
                    check(not result.isError,'MCP '+name+' succeeds',result.structuredContent if result.isError else None)
                    return result.structuredContent['result']
                async def artifact(meta, filename):
                    data=bytearray();offset=0
                    while True:
                        result=await call('read_artifact',{'artifact':meta['artifact'],'offset':offset,'size':262144})
                        data.extend(base64.b64decode(result['data']));offset=result['next_offset']
                        if result['eof']:break
                    check(hashlib.sha256(data).hexdigest()==meta['sha256'],'artifact checksum '+filename)
                    (args.output/filename).write_bytes(data)
                for name, parameters in [('execute_code',{'code':'return 1'}),('inspect',{'code':'arbitrary'}),('set_playback_rate',{'sequence':1,'clip':1,'percent':True})]:
                    result=await client.call_tool('filmcraft_'+name,parameters)
                    check(result.isError,'rejected '+name+' invalid call')
                await call('create_project',{'name':'FilmCraft through real MCP'})
                imported=await call('import_media',{'name':'source.mp4','data':base64.b64encode(source.read_bytes()).decode()})
                await call('create_sequence',{'name':'Original MCP sequence','from_item':imported['items'][0]})
                project=await call('inspect');sequence=project['activeSequence']
                await call('rename_item',{'item':sequence,'name':'Edited through Core and MCP'})
                seq=await call('inspect_sequence',{'sequence':sequence})
                check(seq['name']=='Edited through Core and MCP','live edit readback')
                await call('undo');await call('redo')
                video=next(item for track in seq['video'] for item in track['items'])
                await call('set_playback_rate',{'sequence':sequence,'clip':video['clip'],'percent':50})
                retimed=await call('inspect_sequence',{'sequence':sequence})
                check(retimed['durationFrames']==seq['durationFrames']*2,'MCP retime doubles duration')
                saved=await call('save_project',{'name':'mcp-project'})
                await artifact(saved['bytes'],'project.fcproj')
                await call('reopen_project',{'path':saved['path']})
                reopened=await call('inspect_sequence',{'sequence':sequence})
                check(reopened['name']==retimed['name'] and reopened['durationFrames']==retimed['durationFrames'],'native reopen preserves edit and timing')
                if args.intentional_native_restart:
                    restarted=await call('reopen_project',{'path':saved['path'],'restart_native':True})
                    transition=restarted['intentional_restart']
                    report['intentional_native_restart']=transition
                    check(transition['completed'] and transition['old_child_exited'] and transition['generation']==2 and transition['runtime_identity_unchanged'],'owned native child exits before explicit same-save restart',transition)
                    fresh=await call('inspect_sequence',{'sequence':sequence})
                    persistent=('id','settings','duration','durationFrames','video','audio','markers')
                    check({key:fresh[key] for key in persistent}=={key:reopened[key] for key in persistent},'fresh owned native child retains same saved sequence and media timing')
                for fmt,filename in [('h264','export.mp4'),('wav','export.wav')]:
                    job=await call('export_media',{'name':'mcp-'+fmt,'sequence':sequence,'format':fmt})
                    deadline=time.monotonic()+120
                    while True:
                        jobs=await call('list_jobs');record=next(x for x in jobs if x['id']==job['job'])
                        if record['finished']:break
                        if time.monotonic()>deadline:raise TimeoutError('native export')
                        await asyncio.sleep(.1)
                    check(not record.get('error') and not record.get('result',{}).get('error'),'native '+fmt+' export terminal success')
                    meta=await call('read_export',{'path':job['path']})
                    await artifact(meta,filename)
                cancelled=await call('export_media',{'name':'mcp-cancelled','sequence':sequence,'format':'h264'})
                await call('cancel_export',{'job':cancelled['job']})
                deadline=time.monotonic()+30
                while True:
                    record=next(x for x in await call('list_jobs') if x['id']==cancelled['job'])
                    if record['finished']:break
                    if time.monotonic()>deadline:raise TimeoutError('cancelled export did not settle')
                    await asyncio.sleep(.1)
                check(record.get('result',{}).get('error')=='cancelled','MCP cancellation reaches native terminal cancelled state',record)
                rejected=await client.call_tool('filmcraft_read_export',{'path':cancelled['path']})
                check(rejected.isError,'cancelled export cannot become an artifact')
                await call('reconcile')
                if args.mode=='native':
                    rejected=await client.call_tool('filmcraft_capture_view',{})
                    check(rejected.isError,'native headless does not impersonate a GUI screenshot')
                else:
                    await artifact(await call('capture_view'),'visible-editor.png')
                await call('disconnect')
    for name in ['export.mp4','export.wav']:
        info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(args.output/name)]))
        (args.output/(name+'.ffprobe.json')).write_text(json.dumps(info,indent=2))
        check(1.95<=float(info['format']['duration'])<=2.1,name+' decoded duration')
        check(any(x['codec_type']=='audio' for x in info['streams']),name+' contains audio')
    import array, math
    def rgb(path):
        return subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-an','-pix_fmt','rgb24','-f','rawvideo','-'])
    source_rgb, export_rgb = rgb(source), rgb(args.output/'export.mp4')
    stride=160*90*3
    check(len(source_rgb)//stride==12 and len(export_rgb)//stride==24,'native MP4 contains 12 to 24 retimed frames')
    mae=sum(abs(export_rgb[i]-source_rgb[(i//stride//2)*stride+i%stride]) for i in range(len(export_rgb)))/len(export_rgb)
    check(mae<18,'each exported frame matches the source repeated twice',mae)
    audio={}
    for name in ['export.wav','export.mp4']:
        data=subprocess.check_output(['ffmpeg','-v','error','-i',str(args.output/name),'-ac','1','-ar','48000','-f','f32le','-'])
        samples=array.array('f');samples.frombytes(data);middle=samples[9600:-9600]
        hz=sum(a<=0<b for a,b in zip(middle,middle[1:]))/(len(middle)/48000)
        rms=math.sqrt(sum(x*x for x in middle)/len(middle))
        audio[name]={'duration':len(samples)/48000,'frequencyHz':hz,'rms':rms}
        check(1.95<=len(samples)/48000<=2.1 and 200<hz<240 and rms>.02,name+' independently decoded half-speed audio',audio[name])
    report['media_oracles']={'source_frames':12,'export_frames':24,'frame_repeat_mae':mae,'audio':audio}
    report['passed']=True


try:
    asyncio.run(main())
finally:
    (args.output/'mcp-report.json').write_text(json.dumps(report,indent=2))
print(json.dumps({'passed':report.get('passed',False),'checks':len(report['checks']),'output':str(args.output)}))
