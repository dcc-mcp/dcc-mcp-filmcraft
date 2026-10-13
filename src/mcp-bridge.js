/** Private Playwright-pipe entrypoint. No operation accepts JavaScript or raw host commands. */
import { FilmCraftClient, BridgeError } from './index.js';
const sdk = await FilmCraftClient.connect({ expectedOrigin: location.origin });
const origin = location.origin, doc = document, sessionId = sdk.sessionId;
const exports = new Map();
const handlers = Object.freeze({
  inspect: () => sdk.inspect(),
  inspect_sequence: ({ sequence }) => sdk.inspectSequence(sequence),
  create_project: ({ name }) => sdk.createProject(name),
  import_media: ({ name, data }) => {
    const raw = atob(data), bytes = Uint8Array.from(raw, c => c.charCodeAt(0));
    return sdk.importMedia(new File([bytes], name));
  },
  create_sequence: ({ name, from_item }) => sdk.createSequence({ name, fromItem: from_item }),
  rename_item: ({ item, name }) => sdk.renameItem(item, name),
  set_playback_rate: ({ sequence, clip, percent }) => sdk.setPlaybackRate({ sequence, clip, percent }),
  undo: () => sdk.undo(),
  redo: () => sdk.redo(),
  save_project: ({ name }) => sdk.save(name),
  reopen_project: ({ path }) => sdk.reopen(path),
  export_media: async ({ name, sequence, format }) => {
    const result = await sdk.exportVideo({ name, sequence, format });
    exports.set(result.path, result.job); return result;
  },
  list_jobs: () => sdk.jobs(),
  cancel_export: ({ job }) => sdk.cancelExport(job),
  read_export: async ({ path }) => {
    const job = exports.get(path);
    if (!job) throw new BridgeError('SESSION', 'export is not owned by this bridge');
    const record = (await sdk.jobs()).find(x => x.id === job);
    if (!record?.finished) throw new BridgeError('BUSY', 'export has not reached terminal state');
    if (record.error || record.result?.error) throw new BridgeError('EXPORT', 'export did not succeed');
    return sdk.readExport(path);
  },
  reconcile: () => {
    const receipt = sdk.reconcile();
    if (receipt.ok && receipt.result?.path && receipt.result?.job) exports.set(receipt.result.path, receipt.result.job);
    return receipt;
  },
  disconnect: () => sdk.close(),
});
let revoked = false;
const serialize = value => {
  if (value instanceof Uint8Array) {
    let raw = '';
    for (let i = 0; i < value.length; i += 8192) raw += String.fromCharCode(...value.subarray(i, i + 8192));
    return { $bytes: btoa(raw) };
  }
  if (Array.isArray(value)) return value.map(serialize);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, serialize(v)]));
  return value;
};
Object.defineProperty(window, '__dccFilmcraftPipe', {
  configurable: false, writable: false, enumerable: false,
  value: async ({ operation, params }) => {
    try {
      if (location.origin !== origin || document !== doc) revoked = true;
      if (revoked && operation !== 'reconcile') throw new BridgeError('SESSION', 'original document lost');
      if (!Object.hasOwn(handlers, operation)) throw new BridgeError('UNSUPPORTED', 'operation is not in the typed allowlist');
      return { ok: true, sessionId, origin, result: serialize(await handlers[operation](params)) };
    } catch (error) {
      if (error?.code === 'SESSION') revoked = true;
      return { ok: false, sessionId, origin, code: error?.code || 'HOST', error: String(error?.message || error) };
    }
  },
});
