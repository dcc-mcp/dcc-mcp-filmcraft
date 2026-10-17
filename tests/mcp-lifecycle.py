"""Official-runtime transport lifecycle checks, through the Core adapter call path."""
import argparse
import asyncio
import json
from pathlib import Path
import time

from dcc_mcp_filmcraft.adapter import FilmCraftAdapter

parser=argparse.ArgumentParser()
parser.add_argument('--runtime-zip',type=Path,required=True)
parser.add_argument('--chromium')
parser.add_argument('--output',type=Path,default=Path('evidence/mcp-lifecycle.json'))
args=parser.parse_args();checks=[]
def check(ok,name,detail=None):
    checks.append({'ok':bool(ok),'name':name,'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
adapter=FilmCraftAdapter.launch(args.runtime_zip,headless=True,executable=args.chromium)
def evaluate(source):return adapter._submit(adapter.browser.page.evaluate(source)).result(timeout=10)
try:
    # Delay the response after the real mutation applies; never simulate host output.
    evaluate('''() => {
      window.__originalApi = window.filmcraft;
      const original = filmcraft.execute;
      window.__createCalls = 0;
      filmcraft.execute = async (id, params) => {
        const result = await original(id, params);
        if (id === 'file.newProject') {
          window.__createCalls++;
          await new Promise(resolve => setTimeout(resolve, 16500));
        }
        return result;
      };
    }''')
    result=adapter.call('filmcraft_create_project',{'name':'Real delayed MCP mutation'})
    check(result.get('code')=='TIMEOUT','wait timed out after real dispatch',result)
    check(evaluate('() => window.__createCalls')==1,'mutation dispatched exactly once')
    pending=adapter.call('filmcraft_reconcile',{})
    check(pending['result']['uncertain'] is True,'original browser receipt remains unsettled',pending)
    evaluate('() => { window.filmcraft = {}; }')
    time.sleep(2)
    receipt=adapter.call('filmcraft_reconcile',{})
    check(receipt['result'].get('code')=='SESSION' and receipt['result'].get('ok') is False,'revoked original receipt stays readable',receipt)
    evaluate('() => { window.filmcraft = window.__originalApi; }')
    refused=adapter.call('filmcraft_inspect',{})
    check(refused.get('code')=='SESSION','restoring API never restores authority',refused)
    check(evaluate('() => window.__createCalls')==1,'no replay after revocation')
    actual=evaluate("() => window.__originalApi.execute('project.inspect', {})")
    check(actual['name']=='Real delayed MCP mutation','failed receipt does not imply rollback',actual)
    # Navigation destroys the old realm. Reconcile must not query a replacement pipe.
    adapter._submit(adapter.browser.page.goto(adapter.browser.origin+'/index.html?empty&norecover&fresh&cpu&webgl')).result(timeout=20)
    lost=adapter.call('filmcraft_reconcile',{})
    check(lost.get('code')=='INDETERMINATE','destroyed realm reports indeterminate without replacement authority',lost)
finally:
    adapter.close()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({'passed':all(x['ok'] for x in checks),'checks':checks},indent=2))
print(json.dumps({'passed':True,'checks':len(checks)}))
