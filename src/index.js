/** Typed, bounded access to the official API in the visible FilmCraft WASM editor. */
export class BridgeError extends Error {
  constructor(code, message) { super(message); this.name = 'BridgeError'; this.code = code; }
}
const fail = (code, message) => { throw new BridgeError(code, message); };
const integer = (n, min, max, name) => { if (!Number.isSafeInteger(n) || n < min || n > max) fail('INVALID_ARGUMENT', `${name} must be an integer in ${min}..${max}`); return n; };
const label = (s) => { if (typeof s !== 'string' || !s.trim() || s.length > 128) fail('INVALID_ARGUMENT', 'name must contain 1..128 characters'); return s; };
const ownedPath = (root, name, ext) => {
  if (typeof name !== 'string' || !/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/.test(name)) fail('INVALID_ARGUMENT', 'filename must be a simple basename');
  return `${root}/${name}.${ext}`;
};
const key = (p) => JSON.stringify([p.name, p.root?.id, p.path, p.revision]);
const required = ['execute', 'commands', 'inspect', 'info', 'files', 'readFile', 'importFiles', 'openProject'];

/** No TCP, fetch proxy, persistent credential or arbitrary execute method is exposed. */
export class FilmCraftClient {
  #host; #document; #api; #origin; #sessionId; #revoked = null; #closed = false; #busy = false; #uncertain = false;
  #commands = new Set(); #project; #root; #jobs = new Set(); #saved = new Map(); #pending = null; #reserved = new Set();
  static async connect({ window: host = window, expectedOrigin, sessionId = crypto.randomUUID(), timeoutMs = 15000 } = {}) {
    if (typeof expectedOrigin !== 'string' || new URL(expectedOrigin).origin !== expectedOrigin || !/^https?:/.test(expectedOrigin)) fail('ORIGIN', 'an exact HTTP(S) origin is required');
    if (!/^[a-zA-Z0-9-]{16,80}$/.test(sessionId)) fail('SESSION', 'invalid session identifier');
    integer(timeoutMs, 1, 60000, 'timeoutMs');
    let actual;
    try { actual = host.location.origin; } catch { fail('ORIGIN', 'cross-origin editor refused'); }
    if (actual !== expectedOrigin) fail('ORIGIN', 'editor origin mismatch');
    const api = host.filmcraft;
    if (!api || required.some((x) => typeof api[x] !== 'function')) fail('NOT_READY', 'official FilmCraft browser API is unavailable');
    const client = new FilmCraftClient(host, api, expectedOrigin, sessionId, timeoutMs);
    const catalog = await client.#run(() => api.commands(), false);
    const rows = Array.isArray(catalog) ? catalog : catalog?.commands;
    if (!Array.isArray(rows)) fail('PROTOCOL', 'unrecognized command catalog');
    client.#commands = new Set(rows.map((c) => c.id));
    client.#project = key(await client.#query('project.inspect'));
    return client;
  }
  constructor(host, api, origin, sessionId, timeoutMs) {
    this.#host = host; this.#document = host.document; this.#api = api; this.#origin = origin;
    this.#sessionId = sessionId; this.sessionId = sessionId; this.timeoutMs = timeoutMs; this.#root = `/dcc/${sessionId}`;
  }
  #guard() {
    if (this.#closed) fail('CLOSED', 'client is closed');
    if (this.#revoked) fail('SESSION', this.#revoked);
    try {
      if (this.#host.location.origin !== this.#origin || this.#host.document !== this.#document || this.#host.filmcraft !== this.#api) {
        this.#revoked = 'editor navigated or API instance changed';
        fail('SESSION', this.#revoked);
      }
    } catch (e) {
      this.#revoked ||= 'editor session is no longer accessible';
      if (e instanceof BridgeError) throw e;
      fail('SESSION', this.#revoked);
    }
  }
  async #run(operation, mutation, signal) {
    this.#guard();
    if (this.#busy) fail('BUSY', 'one request at a time; no automatic mutation retries');
    if (mutation && this.#uncertain) fail('UNCERTAIN', 'prior mutation is unsettled; call reconcile before editing');
    if (signal?.aborted) fail('CANCELLED', 'cancelled before dispatch; not run');
    this.#busy = true;
    let timer, abort;
    const pending = Promise.resolve().then(() => { this.#guard(); return operation(); });
    const receipt = { sessionId: this.#sessionId, origin: this.#origin, settled: false, ok: false, value: undefined };
    pending.then(value => { receipt.settled = true; receipt.ok = true; receipt.value = value; }, error => { receipt.settled = true; receipt.value = error; });
    if (mutation) this.#pending = receipt;
    try {
      const value = await Promise.race([pending, new Promise((_, reject) => {
        timer = setTimeout(() => { if (mutation) this.#uncertain = true; reject(new BridgeError('TIMEOUT', 'request may still apply; it was not replayed')); }, this.timeoutMs);
        abort = () => { if (mutation) this.#uncertain = true; reject(new BridgeError('CANCELLED', 'cancelled waiting after dispatch; operation may still apply')); };
        signal?.addEventListener('abort', abort, { once: true });
      })]);
      this.#guard(); return value;
    } catch (e) {
      if (mutation && e?.code === 'SESSION') this.#uncertain = true;
      throw e;
    } finally { clearTimeout(timer); signal?.removeEventListener('abort', abort); this.#busy = false; }
  }
  #query(id, params = {}) {
    if (!this.#commands.has(id)) fail('UNSUPPORTED', `host command missing: ${id}`);
    return this.#run(() => this.#api.execute(id, params), false);
  }
  async #mutate(id, params = {}, { signal, sequence } = {}, completed = (value) => value) {
    if (!this.#commands.has(id)) fail('UNSUPPORTED', `host command missing: ${id}`);
    return this.#run(async () => {
      const before = await this.#api.execute('project.inspect', {});
      this.#guard();
      if (key(before) !== this.#project) fail('DOCUMENT', 'active project or revision changed outside this client');
      if (sequence !== undefined && before.activeSequence !== sequence) fail('DOCUMENT', 'active sequence changed outside this client');
      if (signal?.aborted) fail('CANCELLED', 'cancelled before host dispatch; not run');
      const result = await this.#api.execute(id, params);
      this.#guard();
      const value = await completed(result);
      this.#guard();
      const after = await this.#api.execute('project.inspect', {});
      this.#guard();
      this.#project = key(after);
      return value;
    }, true, signal);
  }
  async inspect() { return this.#query('project.inspect'); }
  async inspectSequence(sequence) { integer(sequence, 1, Number.MAX_SAFE_INTEGER, 'sequence'); return this.#query('sequence.inspect', { item: sequence }); }
  info() { this.#guard(); return this.#api.info(); }
  async createProject(name, options = {}) {
    label(name);
    const current = await this.inspect();
    if (current.root?.children?.length || current.dirty) fail('DOCUMENT', 'create requires an empty clean project; replacing work is not supported');
    await this.#mutate('file.newProject', { name }, options);
    const next = await this.inspect(); this.#project = key(next); return next;
  }
  async importMedia(file, options = {}) {
    this.#guard();
    if (!file || typeof file.name !== 'string' || !Number.isSafeInteger(file.size) || file.size < 1 || file.size > 16 * 1024 * 1024) fail('INVALID_ARGUMENT', 'one File of at most 16 MiB is required');
    if (!/\.(mp4|mov|webm|png|jpg|jpeg|wav)$/i.test(file.name)) fail('UNSUPPORTED', 'unsupported media extension');
    return this.#run(async () => {
      const before = await this.#api.execute('project.inspect', {}); this.#guard();
      if (key(before) !== this.#project) fail('DOCUMENT', 'active project changed');
      if (options.signal?.aborted) fail('CANCELLED', 'cancelled before host dispatch; not run');
      const result = await this.#api.importFiles(file); this.#guard();
      const after = await this.#api.execute('project.inspect', {}); this.#guard();
      this.#project = key(after);
      if (result?.errors?.length || !result?.items?.length) fail('IMPORT', JSON.stringify(result?.errors || 'import produced no items'));
      return result;
    }, true, options.signal);
  }
  async createSequence({ name, fromItem }, options = {}) {
    label(name); integer(fromItem, 1, Number.MAX_SAFE_INTEGER, 'fromItem');
    return this.#mutate('file.newSequence', { name, fromItem }, options);
  }
  async renameItem(item, name, options = {}) {
    integer(item, 1, Number.MAX_SAFE_INTEGER, 'item'); label(name);
    return this.#mutate('clip.rename', { item, name }, options);
  }
  async setPlaybackRate({ sequence, clip, percent }, options = {}) {
    integer(sequence, 1, Number.MAX_SAFE_INTEGER, 'sequence');
    integer(clip, 1, Number.MAX_SAFE_INTEGER, 'clip');
    integer(percent, 25, 400, 'percent');
    if (!this.#commands.has('clip.speedDuration')) fail('UNSUPPORTED', 'host command missing: clip.speedDuration');
    return this.#mutate('timeline.select', { clips: [clip] }, { ...options, sequence }, async () => {
      // Selection and retiming share one receipt, including after a wait timeout.
      // Selection does not increment the pinned host's project revision.
      const current = await this.#api.execute('project.inspect', {}); this.#guard();
      if (key(current) !== this.#project || current.activeSequence !== sequence) fail('DOCUMENT', 'active project or sequence changed during selection');
      if (options.signal?.aborted) fail('CANCELLED', 'selection may have applied; retiming was not dispatched');
      const result = await this.#api.execute('clip.speedDuration', { clips: [clip], speed: percent, reverse: false, ripple: true, interpolation: 'frameSampling' });
      this.#guard(); return result;
    });
  }
  async undo(options = {}) { return this.#mutate('edit.undo', {}, options); }
  async redo(options = {}) { return this.#mutate('edit.redo', {}, options); }
  async save(name, options = {}) {
    this.#guard();
    const path = ownedPath(this.#root, name, 'fcproj');
    if (this.#saved.has(path) || this.#api.files().some((f) => f.path === path)) fail('EXISTS', 'refusing to overwrite a virtual file');
    return this.#mutate('file.saveAs', { path }, options, async () => {
      const bytes = await this.#api.readFile(path);
      if (!ArrayBuffer.isView(bytes) || Object.prototype.toString.call(bytes) !== '[object Uint8Array]' || bytes.byteLength > 16 * 1024 * 1024) fail('PROTOCOL', 'invalid project export');
      this.#saved.set(path, new Uint8Array(bytes));
      return { path, bytes: new Uint8Array(bytes) };
    });
  }

  async reopen(path, options = {}) {
    const bytes = this.#saved.get(path);
    if (!bytes) fail('DOCUMENT', 'only unchanged native saves from this client may reopen');
    const current = await this.inspect();
    if (current.dirty) fail('DOCUMENT', 'save the current project before reopening');
    if (key(current) !== this.#project) fail('DOCUMENT', 'active project changed');
    const actual = await this.#run(() => this.#api.readFile(path), false);
    if (actual.byteLength !== bytes.byteLength || bytes.some((v, i) => actual[i] !== v)) fail('DOCUMENT', 'saved native file changed outside this client');
    return this.#mutate('file.open', { path }, options, async () => {
      const next = await this.#api.execute('project.inspect', {}); this.#guard(); return next;
    });
  }

  async exportVideo({ name, sequence, format = 'h264' }, options = {}) {
    this.#guard();
    integer(sequence, 1, Number.MAX_SAFE_INTEGER, 'sequence');
    if (!['h264', 'wav'].includes(format)) fail('UNSUPPORTED', 'POC exports only H.264/MP4 and WAV');
    const path = ownedPath(this.#root, name, format === 'wav' ? 'wav' : 'mp4');
    if (this.#reserved.has(path) || this.#api.files().some((f) => f.path === path)) fail('EXISTS', 'refusing to overwrite or reuse a reserved export path');
    this.#reserved.add(path);
    return this.#mutate('file.exportMedia', { path, format, sequence, bitrateKbps: 1000 }, { ...options, sequence }, result => {
      integer(result.job, 1, Number.MAX_SAFE_INTEGER, 'export job'); this.#jobs.add(result.job);
      return { job: result.job, path };
    });
  }
  async jobs() { return this.#query('jobs.list'); }
  async cancelExport(job) {
    if (!this.#jobs.has(job)) fail('SESSION', 'job is not owned by this client');
    return this.#query('jobs.cancel', { job });
  }
  async readExport(path) {
    this.#guard();
    if (typeof path !== 'string' || !this.#reserved.has(path) || !path.startsWith(`${this.#root}/`) || !/\.(mp4|wav)$/.test(path) || path.includes('..')) fail('SESSION', 'path is outside this session');
    const record = this.#api.files().find((f) => f.path === path);
    if (!record || record.size > 32 * 1024 * 1024) fail('LIMIT', 'export missing or over 32 MiB');
    return this.#run(async () => { const bytes = await this.#api.readFile(path); if (!ArrayBuffer.isView(bytes) || Object.prototype.toString.call(bytes) !== '[object Uint8Array]' || bytes.byteLength > 32 * 1024 * 1024) fail('LIMIT', 'invalid or oversized export bytes'); return new Uint8Array(bytes); }, false);
  }
  reconcile() {
    // Inspect only local state, even after navigation or API loss. Reading a
    // receipt never reacquires execution authority or cancels a host operation.
    if (this.#closed && !this.#uncertain) fail('CLOSED', 'client is closed');
    if (!this.#uncertain) return { settled: !this.#busy, uncertain: false };
    if (!this.#pending?.settled) return { settled: false, uncertain: true };
    const r = this.#pending; this.#uncertain = false;
    return { settled: true, uncertain: false, sessionId: r.sessionId, origin: r.origin, ok: r.ok, result: r.ok ? r.value : undefined, error: r.ok ? undefined : String(r.value), code: r.ok ? undefined : r.value?.code || 'HOST' };
  }
  async close() {
    this.#guard();
    if (this.#busy || this.#uncertain) fail('UNCERTAIN', 'settle pending work before closing');
    const jobs = await this.jobs();
    if (jobs.some((job) => this.#jobs.has(job.id) && !job.finished)) fail('BUSY', 'cancel and await active export jobs before closing');
    this.#saved.clear(); this.#jobs.clear(); this.#reserved.clear(); this.#closed = true;
    return { closed: true, documentPreserved: true, virtualFilesPreserved: true };
  }
}

/** Optional explicit same-origin window bridge. Does not secure untrusted same-origin scripts. */
export function installMessageBridge({ hostWindow, controllerWindow, allowedOrigin, sessionId, handlers }) {
  if (hostWindow.location.origin !== allowedOrigin || new URL(allowedOrigin).origin !== allowedOrigin || !/^https?:/.test(allowedOrigin)) fail('ORIGIN', 'exact same-origin controller required');
  if (!controllerWindow || !/^[a-zA-Z0-9-]{16,80}$/.test(sessionId)) fail('SESSION', 'controller and explicit session required');
  const hostDocument = hostWindow.document; let closed = false, busy = false; const seen = new Set();
  const listener = async (event) => {
    if (closed || hostWindow.document !== hostDocument || hostWindow.location.origin !== allowedOrigin || event.source !== controllerWindow || event.origin !== allowedOrigin) return;
    const m = event.data;
    if (!m || m.protocol !== 'dcc-craft/1' || m.session !== sessionId || typeof m.id !== 'string' || !/^[a-zA-Z0-9-]{1,80}$/.test(m.id)) return;
    if (typeof m.operation !== 'string' || !Object.hasOwn(handlers, m.operation)) return;
    if (seen.has(m.id) || seen.size >= 512 || busy) return;
    seen.add(m.id); busy = true;
    let response;
    try { response = { ok: true, result: await handlers[m.operation](m.params) }; }
    catch (e) { response = { ok: false, error: String(e?.message || e), code: e?.code || 'HOST' }; }
    finally { busy = false; }
    if (!closed && hostWindow.document === hostDocument && hostWindow.location.origin === allowedOrigin) controllerWindow.postMessage({ protocol: 'dcc-craft/1', session: sessionId, id: m.id, ...response }, allowedOrigin);
  };
  hostWindow.addEventListener('message', listener);
  return () => { closed = true; hostWindow.removeEventListener('message', listener); seen.clear(); };
}
