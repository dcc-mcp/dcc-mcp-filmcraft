import { FilmCraftClient, installMessageBridge } from '../src/index.js';
async function check() {
  const sdk = await FilmCraftClient.connect({ expectedOrigin: location.origin });
  const imported = await sdk.importMedia(new File(['media'], 'clip.mp4'));
  await sdk.createSequence({ name:'Timeline', fromItem:imported.items[0] });
  const project = await sdk.inspect();
  if (project.activeSequence !== null) await sdk.exportVideo({name:'result',sequence:project.activeSequence,format:'h264'});
  const receipt = sdk.reconcile();
  const provenance: [string | undefined, string | undefined, string | undefined] = [receipt.sessionId, receipt.origin, receipt.code];
  void provenance;
  const saved = await sdk.save('native'); await sdk.reopen(saved.path);
  // @ts-expect-error unsupported format
  await sdk.exportVideo({name:'result',sequence:2,format:'arbitrary'});
  // @ts-expect-error no unbounded arbitrary execute escape hatch
  await sdk.execute('file.open');
  const stop = installMessageBridge({hostWindow:window,controllerWindow:window,allowedOrigin:location.origin,sessionId:sdk.sessionId,handlers:{inspect:()=>sdk.inspect()}});
  stop(); await sdk.close();
}
void check;
