"""Real official WASM acceptance. No local MCP/control gateway. An isolated test page
writes only bounded evidence to its same-origin, loopback-only fixture server.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen
from zipfile import ZipFile
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://github.com/storytold/filmcraft/releases/download/v0.7.2/filmcraft-web-0.7.2.zip'
SHA256 = '48d4f48728fa6b5c028612a4b7f59a5832ff38d430c6a7bd417a2c77d75ae4f9'
parser = argparse.ArgumentParser()
parser.add_argument('--runtime-zip', type=Path)
parser.add_argument('--output', type=Path, default=ROOT / 'evidence')
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='filmcraft-e2e-') as td:
    work = Path(td)
    archive = args.runtime_zip or work / 'runtime.zip'
    if not args.runtime_zip:
        with urlopen(URL, timeout=120) as response:
            archive.write_bytes(response.read(20 * 1024 * 1024))
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == SHA256, 'Official runtime SHA-256 mismatch'
    with ZipFile(archive) as z:
        for item in z.infolist():
            assert not item.filename.startswith('/') and '..' not in Path(item.filename).parts
        z.extractall(work)
    site = work / 'filmcraft-web-0.7.2'
    shutil.copyfile(ROOT / 'src' / 'index.js', site / 'dcc-sdk.js')
    shutil.copyfile(ROOT / 'tests' / 'browser-acceptance.js', site / 'dcc-acceptance.js')
    html = (site / 'index.html').read_text().replace('</body>', '<script type="module" src="./dcc-acceptance.js"></script></body>')
    (site / 'test.html').write_text(html)
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=160x90:rate=12','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','1','-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-c:a','aac','-b:a','64k','-movflags','+faststart',str(site/'poc-source.mp4')],check=True)
    shutil.copyfile(site/'poc-source.mp4', args.output/'poc-source.mp4')
    names = {'project.fcproj','export.mp4','export.wav','visible-editor.png','before-editor.png','browser-report.json'}
    class Handler(SimpleHTTPRequestHandler):
        def end_headers(self):
            self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
            self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
            self.send_header('Cache-Control', 'no-store')
            super().end_headers()
        def do_POST(self):
            name = self.path.removeprefix('/evidence/')
            if self.headers.get('Origin') != base or self.path != '/evidence/' + name or name not in names:
                self.send_error(403); return
            try: size = int(self.headers.get('Content-Length', '0'))
            except ValueError: self.send_error(400); return
            if not 0 < size <= 32 * 1024 * 1024:
                self.send_error(413); return
            (args.output / name).write_bytes(self.rfile.read(size))
            self.send_response(204); self.end_headers()
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(site)))
    base = f'http://127.0.0.1:{server.server_port}'
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logs = []
    try:
        with sync_playwright() as pw:
            options = {'headless': True, 'args': ['--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader']}
            if os.getenv('CHROMIUM_PATH'): options['executable_path'] = os.environ['CHROMIUM_PATH']
            browser = pw.chromium.launch(**options)
            context = browser.new_context(viewport={'width':1280,'height':800}, record_video_dir=str(args.output/'recording'))
            page = context.new_page()
            page.on('console', lambda msg: logs.append({'type':msg.type,'text':msg.text}))
            page.on('pageerror', lambda error: logs.append({'type':'pageerror','text':str(error)}))
            page.goto(base + '/test.html?empty&norecover&fresh&cpu&webgl')
            page.wait_for_function("document.title.startsWith('PASS ') || document.title.startsWith('FAIL ')", timeout=300000)
            page.screenshot(path=str(args.output/'acceptance-page.png'))
            report=json.loads((args.output/'browser-report.json').read_text())
            report['browserVersion']=browser.version
            report['runtimeZipSha256']=SHA256
            report['sdkSha256']=hashlib.sha256((ROOT/'src/index.js').read_bytes()).hexdigest()
            (args.output/'browser-report.json').write_text(json.dumps(report,indent=2))
            context.close(); browser.close()
            assert report['passed'], json.dumps(report,indent=2)
        for name in ['export.mp4','export.wav']:
            raw=subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(args.output/name)],text=True)
            info=json.loads(raw); (args.output/(name+'.ffprobe.json')).write_text(raw)
            assert 1.95 <= float(info['format']['duration']) <= 2.1, 'export must contain the retimed two-second sequence'
            assert any(x['codec_type']=='audio' for x in info['streams']), f'{name}: no audio'
            if name.endswith('.mp4'): assert any(x['codec_type']=='video' for x in info['streams'])
        subprocess.run(['ffmpeg','-v','error','-i',str(args.output/'export.mp4'),'-f','null','-'],check=True)
        import array, math
        def rgb(path):
            return subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-an','-pix_fmt','rgb24','-f','rawvideo','-'])
        source_rgb, exported_rgb = rgb(site/'poc-source.mp4'), rgb(args.output/'export.mp4')
        stride=160*90*3
        assert len(source_rgb)//stride==12 and len(exported_rgb)//stride==24
        expected=sum(abs(exported_rgb[i]-source_rgb[(i//stride//2)*stride+i%stride]) for i in range(len(exported_rgb)))/len(exported_rgb)
        assert expected < 18, f'output frames must match each source frame repeated twice: MAE={expected}'
        audio_raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(args.output/'export.wav'),'-ac','1','-ar','48000','-f','f32le','-'])
        samples=array.array('f');samples.frombytes(audio_raw)
        middle=samples[9600:-9600]
        crossings=sum(a<=0<b for a,b in zip(middle,middle[1:]))
        frequency=crossings/(len(middle)/48000)
        rms=math.sqrt(sum(x*x for x in middle)/len(middle))
        assert 200 < frequency < 240 and rms>0.02, f'audio must be non-silent and half-speed: {frequency} Hz, RMS={rms}'
        (args.output/'media-oracles.json').write_text(json.dumps({'sourceFrames':12,'exportFrames':24,'retime':0.5,'frameRepeatMeanAbsoluteError':expected,'audioFrequencyHz':frequency,'audioRms':rms,'subjectiveListeningTested':False},indent=2))
        print(json.dumps({'passed':True,'checks':len(report['checks']),'browser':report['browserVersion'],'output':str(args.output)}))
    finally:
        (args.output/'browser-console.json').write_text(json.dumps(logs,indent=2))
        server.shutdown();server.server_close();thread.join(timeout=3)
