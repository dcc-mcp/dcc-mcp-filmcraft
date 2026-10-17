# DCC-MCP FilmCraft

Experimental DCC-MCP Core adapter and genuine MCP stdio server for **FilmCraft Web/WASM and a native local engine**, with a typed browser SDK.
[中文](README.zh-CN.md)

The Python adapter uses DCC-MCP Core 0.20.44 and the official MCP SDK stdio transport. Browser mode exposes 19 bounded tools on one owned editor page. Native mode exposes 18 tools on one persistent, owned `filmcraft-cli mcp` process. Each mode has its own packaged skill and acceptance job. No generic code/command tool, control socket or HTTP command gateway is exposed. This is unreleased experimental integration work.

## Verified scope

The browser and native headless paths are tested separately. Native desktop GUI control is not implemented or qualified; a real cloud GUI launch failed to paint because its X11 shared-memory display was unavailable. Headless success does not establish GUI success. See the [19-operation mode comparison](docs/native-mode.md).


Official FilmCraft v0.7.2 browser ZIP, SHA-256
`48d4f48728fa6b5c028612a4b7f59a5832ff38d430c6a7bd417a2c77d75ae4f9`.
The official JS API forwards to the visible Rust `FilmcraftApp` control queue.

- Create an empty project, import bounded media, create a sequence and rename it
- Retime a video clip and linked audio, with undo/redo and timeline readback
- Save native `.fcproj` bytes, verify integrity and reopen the owned virtual path
- Export H.264/MP4 with audio and WAV, observe/cancel owned jobs, retrieve bytes
- Reject wrong origins, stale runtime identities, changed project revisions,
  unowned files/jobs, oversized inputs, filename traversal, duplicate paths,
  unauthorized messages and replays
- Preserve the document on disconnect; distinguish waiting cancellation from
  actual host cancellation; retain an uncertain operation receipt without replay

The POC uses original FFmpeg procedural calibration video/audio, not third-party
footage. See [acceptance evidence](docs/acceptance.md) and
[browser trust boundary and limitations](docs/browser-boundary.md).

## Run the Core-backed MCP server

```sh
python -m pip install .
python -m playwright install chromium
# Download the official runtime ZIP linked below. The adapter verifies its exact hash.
dcc-mcp-filmcraft serve --runtime-zip /path/to/filmcraft-web-0.7.2.zip
```

Configure an MCP client to launch that command over **stdio**. The default opens
one visible browser editor. `--headless` is an explicit automation/testing option;
`--evidence-dir /path` records that same page. `--chromium /path/to/chromium` can
select an installed compatible runtime. `dcc-mcp-filmcraft status` prints the
pinned runtime URL/hash and transport contract without opening a browser.

[Official FilmCraft v0.7.2 web ZIP](https://github.com/storytold/filmcraft/releases/download/v0.7.2/filmcraft-web-0.7.2.zip).
No automatic runtime download or install occurs. Python >=3.10; Core >=0.20.44,<0.21.
The wheel includes the exact JavaScript SDK/bridge, `tools.yaml` and workflow skill;
MCP clients can retrieve the `filmcraft-browser` prompt. Full JSON Schema validation
supplements Core's dispatcher, including regex and size restrictions.

Tools cover inspect, project creation, media import, sequence creation/rename,
retiming, undo/redo, native save/reopen, export jobs/cancellation, bounded artifact
chunks, screenshot, reconciliation and disconnect. Imports use authorized base64
bytes (<=16 MiB). Saves/exports return SHA-256 artifact IDs; retrieve chunks through
`filmcraft_read_artifact` (<=256 KiB each), never arbitrary OS paths. Native exports
must reach successful terminal state before readback.

Browser control uses Playwright's inherited private pipe and a retained function
handle in the original page realm. A loopback-only **static asset server** serves
only the hash-verified official runtime and adapter scripts; it has no commands,
uploads, filesystem browsing, proxy or cross-origin access. Navigation permanently
revokes execution. Reconciliation uses the original retained closure, never a
replacement tab; destroyed realms report indeterminate outcomes. Cancellation
before browser dispatch does not execute; cancellation/timeout after dispatch
retains the original receipt and never queues or retries a mutation.

This adapter owns a newly opened browser page; it does not attach to an arbitrary
existing user tab. `disconnect` preserves the page and virtual files. Ending the
stdio process closes its disposable browser, so retrieve necessary artifacts first.
Core gateway discovery, desktop TCP, restart recovery and WASI are not implemented.
See [MCP acceptance](docs/mcp-acceptance.md).

## Run the native local engine

```sh
dcc-mcp-filmcraft serve --mode native \
  --native-cli /path/to/filmcraft-cli --workspace /path/to/filmcraft-work
```

This launches the official CLI as one persistent native engine over a private
stdin/stdout pipe. It opens no window and no TCP control endpoint. The workspace
is trusted launcher configuration; each session creates a new private directory.
Agent tools receive only owned virtual handles and immutable artifact IDs, never
an arbitrary OS-file API. Saved `.fcproj`, media and exports remain on disk when
the adapter closes. Unsaved in-memory edits end with the owned process.

Use the official FilmCraft 0.7.2 CLI. The acceptance job verifies both the Linux
release archive and executable SHA-256 before use; the adapter never downloads a
runtime. The configured executable is trusted code, not an OS-sandboxed plugin.
Only Linux native runtime behavior is currently qualified; platform unit tests do
not establish actual macOS/Windows native-host coverage.

MCP clients receive `filmcraft-native` instead of `filmcraft-browser`. The same 18
editing/artifact operations are available. `filmcraft_capture_view` is absent:
a headless engine has no editor window to screenshot. Existing browser mode and
its screenshot operation are unchanged. Process loss permanently revokes the
native session; cached artifacts can still be rescued, but a replacement process
never inherits permission to continue an uncertain edit.

Native file reads bind the opened descriptor to the inspected file, recheck the
session directory and reject observed replacement or changes during the read
before publishing artifact bytes. This is not a sandbox for hostile concurrent
writers; keep the workspace operator-controlled.

[Native workflow, bounds and exact mode comparison](docs/native-mode.md).

## Use in the editor's origin

```js
import { FilmCraftClient } from './src/index.js';
const sdk = await FilmCraftClient.connect({expectedOrigin: location.origin});
await sdk.createProject('My film');
const media = await sdk.importMedia(fileInput.files[0]);
await sdk.createSequence({name: 'Main', fromItem: media.items[0]});
const project = await sdk.inspect();
const native = await sdk.save('my-film');
const job = await sdk.exportVideo({name: 'my-film', sequence: project.activeSequence});
// Observe sdk.jobs() until this job is finished, then sdk.readExport(job.path).
// Keep returned bytes or offer a browser download; paths are virtual, not OS paths.
```

Use one controller while the operation runs. Do not switch or edit projects
concurrently: upstream has no atomic compare-and-execute revision API. The SDK
provides conservative checks, not a lock on the UI. A timeout/abort after dispatch
may still apply; call `reconcile()` until the original operation settles. Receipts
include all phases and validation. Aborting after selection can leave selection
changed, but prevents a retime that has not yet dispatched. Reconciliation stays
local and readable after Document/API loss, with the original session/origin and
error code. Once identity loss is observed, that client's execution remains revoked
even if the old API is restored. A failed receipt does not imply rollback.

## Development

```sh
npm ci --ignore-scripts
npm run check && npm test && npm run typecheck
python -m pip install playwright==1.55.0
python -m playwright install --with-deps chromium
python tests/browser-e2e.py
```

FFmpeg/ffprobe must be on PATH. `CHROMIUM_PATH` can select a supported installed
browser; `--runtime-zip` reuses an already downloaded official ZIP after hash
verification. Acceptance writes its own artifacts under `evidence/`, including
before/after screenshots, a browser recording, native project, MP4/WAV, state
readbacks and media oracles. Binary artifacts are not committed or bundled into npm.

## ArtCraft family

[Verified inventory](docs/artcraft-inventory.json), dated October 13, 2026:
13 named Crafting Apps, 13 official browser ZIP releases, MIT OR Apache-2.0 root
source licenses. Marketing still lists only 12 browser apps. FilmCraft and
EffectCraft already expose live-document JS APIs; this does not mean every sibling
has the same API. Browser `wasm32-unknown-unknown` is distinct from WASI. Licenses of
fonts/assets/dependencies and codecs require their own review.

No upstream fork, release, merge, deployment or new credentials are created by
this integration. Existing PhotoCraft/PdfCraft adapters remain separate repositories.
