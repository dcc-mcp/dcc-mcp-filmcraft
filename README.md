# DCC-MCP FilmCraft

Experimental, portable typed browser SDK for the **same visible FilmCraft WebAssembly editor**.
[中文](README.zh-CN.md)

This first implementation is a browser integration component, not a released Core
adapter or a replacement headless CLI. It exposes a bounded typed editing surface
and an optional explicitly authorized same-origin window-message bridge. It opens
no control socket, localhost gateway or server-side editor session.

## Verified scope

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
this SDK. Existing PhotoCraft/PdfCraft adapters remain separate repositories.
