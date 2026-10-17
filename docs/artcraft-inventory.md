# ArtCraft browser inventory

Verified 2026-10-13T17:25:24.432836+00:00. Read-only primary-source research.

## Findings

All 13 apps have official browser release assets as of this check. The marketing page still says 12 and excludes FilmCraft. All 13 manifests declare `MIT OR Apache-2.0`; both license texts exist. All packaging scripts target browser `wasm32-unknown-unknown`; no supported WASI application build was verified.

| App | Latest release | Browser artifact | Source license |
|---|---|---|---|
| [PhotoCraft](https://github.com/storytold/photocraft) | [v0.8.2](https://github.com/storytold/photocraft/releases/tag/v0.8.2) | [Web ZIP](https://github.com/storytold/photocraft/releases/download/v0.8.2/photocraft-web-0.8.2.zip) | [MIT OR Apache-2.0](https://github.com/storytold/photocraft/blob/main/Cargo.toml) |
| [VectorCraft](https://github.com/storytold/vectorcraft) | [v0.10.0](https://github.com/storytold/vectorcraft/releases/tag/v0.10.0) | [Web ZIP](https://github.com/storytold/vectorcraft/releases/download/v0.10.0/vectorcraft-web-0.10.0.zip) | [MIT OR Apache-2.0](https://github.com/storytold/vectorcraft/blob/main/Cargo.toml) |
| [FilmCraft](https://github.com/storytold/filmcraft) | [v0.7.2](https://github.com/storytold/filmcraft/releases/tag/v0.7.2) | [Web ZIP](https://github.com/storytold/filmcraft/releases/download/v0.7.2/filmcraft-web-0.7.2.zip) | [MIT OR Apache-2.0](https://github.com/storytold/filmcraft/blob/main/Cargo.toml) |
| [LightCraft](https://github.com/storytold/lightcraft) | [v0.7.1](https://github.com/storytold/lightcraft/releases/tag/v0.7.1) | [Web ZIP](https://github.com/storytold/lightcraft/releases/download/v0.7.1/lightcraft-web-0.7.1.zip) | [MIT OR Apache-2.0](https://github.com/storytold/lightcraft/blob/main/Cargo.toml) |
| [PdfCraft](https://github.com/storytold/pdfcraft) | [v0.7.1](https://github.com/storytold/pdfcraft/releases/tag/v0.7.1) | [Web ZIP](https://github.com/storytold/pdfcraft/releases/download/v0.7.1/pdfcraft-web-0.7.1.zip) | [MIT OR Apache-2.0](https://github.com/storytold/pdfcraft/blob/main/Cargo.toml) |
| [EffectCraft](https://github.com/storytold/effectcraft) | [v0.9.2](https://github.com/storytold/effectcraft/releases/tag/v0.9.2) | [Web ZIP](https://github.com/storytold/effectcraft/releases/download/v0.9.2/effectcraft-web-0.9.2.zip) | [MIT OR Apache-2.0](https://github.com/storytold/effectcraft/blob/main/Cargo.toml) |
| [DesignCraft](https://github.com/storytold/designcraft) | [v0.7.1](https://github.com/storytold/designcraft/releases/tag/v0.7.1) | [Web ZIP](https://github.com/storytold/designcraft/releases/download/v0.7.1/designcraft-web-0.7.1.zip) | [MIT OR Apache-2.0](https://github.com/storytold/designcraft/blob/main/Cargo.toml) |
| [FigCraft](https://github.com/storytold/figcraft) | [v0.5.1](https://github.com/storytold/figcraft/releases/tag/v0.5.1) | [Web ZIP](https://github.com/storytold/figcraft/releases/download/v0.5.1/figcraft-web-0.5.1.zip) | [MIT OR Apache-2.0](https://github.com/storytold/figcraft/blob/main/Cargo.toml) |
| [WordCraft](https://github.com/storytold/wordcraft) | [v0.6.1](https://github.com/storytold/wordcraft/releases/tag/v0.6.1) | [Web ZIP](https://github.com/storytold/wordcraft/releases/download/v0.6.1/wordcraft-web-0.6.1.zip) | [MIT OR Apache-2.0](https://github.com/storytold/wordcraft/blob/main/Cargo.toml) |
| [SoundCraft](https://github.com/storytold/soundcraft) | [v0.6.1](https://github.com/storytold/soundcraft/releases/tag/v0.6.1) | [Web ZIP](https://github.com/storytold/soundcraft/releases/download/v0.6.1/soundcraft-web-0.6.1.zip) | [MIT OR Apache-2.0](https://github.com/storytold/soundcraft/blob/main/Cargo.toml) |
| [DeckCraft](https://github.com/storytold/deckcraft) | [v0.6.1](https://github.com/storytold/deckcraft/releases/tag/v0.6.1) | [Web ZIP](https://github.com/storytold/deckcraft/releases/download/v0.6.1/deckcraft-web-0.6.1.zip) | [MIT OR Apache-2.0](https://github.com/storytold/deckcraft/blob/main/Cargo.toml) |
| [CADCraft](https://github.com/storytold/cadcraft) | [v0.6.2](https://github.com/storytold/cadcraft/releases/tag/v0.6.2) | [Web ZIP](https://github.com/storytold/cadcraft/releases/download/v0.6.2/cadcraft-web-0.6.2.zip) | [MIT OR Apache-2.0](https://github.com/storytold/cadcraft/blob/main/Cargo.toml) |
| [GridCraft](https://github.com/storytold/gridcraft) | [v0.6.1](https://github.com/storytold/gridcraft/releases/tag/v0.6.1) | [Web ZIP](https://github.com/storytold/gridcraft/releases/download/v0.6.1/gridcraft-web-0.6.1.zip) | [MIT OR Apache-2.0](https://github.com/storytold/gridcraft/blob/main/Cargo.toml) |

## Browser integration surfaces

### photocraft
No exported live-document JavaScript command dispatcher found in inspected main web shell.
Private WebShell; browser file picker/download/drag-drop and Services inbox. Native CLI/MCP and Rust API are separate integration surfaces. Add an in-process Rust/WASM bridge or operate real UI; do not claim a separate native headless session is the browser document.
Sources: [main.rs](https://github.com/storytold/photocraft/blob/main/apps/photocraft-web/src/main.rs), [web.rs](https://github.com/storytold/photocraft/blob/main/apps/photocraft-web/src/web.rs)

### vectorcraft
No exported live-document JavaScript command dispatcher found in inspected main web shell.
Private WebShell, browser file picker/download/inbox; main.rs explicitly excludes TCP server. WebGPU with WebGL2 fallback.
Sources: [main.rs](https://github.com/storytold/vectorcraft/blob/main/apps/vectorcraft-web/src/main.rs), [web.rs](https://github.com/storytold/vectorcraft/blob/main/apps/vectorcraft-web/src/web.rs)

### gridcraft
Existing same-origin iframe file bridge, no editing-command API in inspected bridge.
?host=parent and optional author. Receives gridcraft:open {name,bytes}; sends ready {version}, save {name,bytes}, dirty {dirty}, failed {error}. bytes ArrayBuffer/Uint8Array; output transferred ArrayBuffer. Save/Save As .xlsx and PDF exports reach parent. Both origin and parent identity checked.
Sources: [host.rs](https://github.com/storytold/gridcraft/blob/main/apps/gridcraft-web/src/host.rs), [main.rs](https://github.com/storytold/gridcraft/blob/main/apps/gridcraft-web/src/main.rs)

### pdfcraft
Existing same-origin iframe file bridge, no editing-command API in inspected bridge.
?host=parent and optional author. Receives pdfcraft:open {name,bytes}; sends ready {version}, save {name,saveAs,bytes}, dirty {dirty}, failed {error}. ?file= opens same-origin or CORS-enabled URL. Both origin and parent identity checked.
Sources: [main.rs](https://github.com/storytold/pdfcraft/blob/main/apps/pdfcraft-web/src/main.rs)

### filmcraft
Existing live-document browser JavaScript automation API, strongest quick POC candidate.
request sends ControlRequest to the live FilmcraftApp; execute maps to engine.execute. Action queue operates the same WebApp and replies are polled each UI frame. Promise result or rejection. File bytes are available through readFile as Uint8Array. Screenshot returns PNG base64, width, height.
Sources: [api.rs](https://github.com/storytold/filmcraft/blob/main/apps/filmcraft-web/src/api.rs), [lib.rs](https://github.com/storytold/filmcraft/blob/main/apps/filmcraft-web/src/lib.rs), [web.md](https://github.com/storytold/filmcraft/blob/main/docs/web.md), [smoke.mjs](https://github.com/storytold/filmcraft/blob/main/apps/filmcraft-web/tests/smoke.mjs)

### effectcraft
Existing live-document browser JavaScript automation API in inspected main source.
request and execute wrap exported WASM request and forward ControlRequest to real UI. Also files/readFile/addFile/info and browser persistence helpers. Release asset exists; API parity with release was not separately checked.
Sources: [api.rs](https://github.com/storytold/effectcraft/blob/main/apps/effectcraft-web/src/api.rs), [lib.rs](https://github.com/storytold/effectcraft/blob/main/apps/effectcraft-web/src/lib.rs)

## Blender

Official catalog lists native Windows, Windows ARM, macOS, Linux and source; no official browser/WASM or WASI release verified. This is a catalog/research finding, not proof no experimental work exists.
GNU GPL; official COPYING refers to doc/license/GPL-license.txt (GPL v2 text). Do not classify Blender as permissively licensed ArtCraft software.

Separate community Blender-to-WebAssembly port, explicitly rendering locally in browser with WebGPU. Demo source loads compressed WASM and assets, uses Emscripten and CPython assets; not the official Blender distribution.
Community requirements: WebGPU adapter; UI warns software rendering is extremely slow; SharedArrayBuffer/pthreads and cross-origin isolation; COOP: same-origin; COEP: require-corp in Vite dev/preview config; Substantial asset/WASM download and evolving fork rather than demonstrated desktop feature parity.
Demo: https://developer.puter.com/labs/blender-web/
Source: https://github.com/HeyPuter/blender-wasm

Different project uses a native GHOST backend to stream frames over WebSocket; not a local WASM build. https://github.com/jtydhr88/blender-web

## Limits

- Marketing page is stale: excludes FilmCraft browser support, yet official v0.7.2 release has a web ZIP and documented JS API.
- Marketing pages also lag latest release versions.
- All 13 root Cargo.toml declare MIT OR Apache-2.0 and both license files were retrieved; this is not a full dependency, asset, font, patent or trademark audit.
- Browser WASM is not WASI. All 13 packaging scripts cite wasm32-unknown-unknown. No WASI application support verified.
- Release existence and source inspection do not prove browser runtime reliability. See acceptance.md for separately recorded FilmCraft runtime tests.
