# FilmCraft: browser, native engine and desktop GUI

The two implemented execution modes share one reviewed Core tool registry/dispatcher architecture. They do not share a document or silently switch host. FilmCraft and EffectCraft remain distinct products/repositories.

## 19-operation comparison

| Typed operation | Web/WASM editor | Native headless CLI | Desktop GUI adapter |
|---|---|---|---|
| inspect | Tested | Tested; includes mode capabilities | Missing |
| inspect_sequence | Tested | Tested | Missing |
| create_project | Tested | Tested | Missing |
| import_media | Tested | Tested | Missing |
| create_sequence | Tested | Tested | Missing |
| rename_item | Tested | Tested | Missing |
| set_playback_rate | Tested | Tested, including linked audio | Missing |
| undo | Tested | Tested | Missing |
| redo | Tested | Tested | Missing |
| save_project | Tested | Tested | Missing |
| reopen_project | Tested | Tested | Missing |
| export_media | Tested | Tested, H.264/AAC and WAV | Missing |
| list_jobs | Tested | Tested | Missing |
| cancel_export | Tested | Tested, terminal cancellation | Missing |
| read_export | Tested | Tested | Missing |
| read_artifact | Tested | Tested | Missing |
| capture_view | Tested | Not exposed; no window exists | Missing |
| reconcile | Tested | Tested | Missing |
| disconnect | Tested | Tested | Missing |

Every operation has the `filmcraft_` prefix. Browser mode exposes 19 tools; native mode exposes 18. A headless render cannot substitute for the screenshot contract.

## Native implementation

`serve --mode native --native-cli PATH --workspace DIR` starts one official `filmcraft-cli mcp` process. Its inherited stdin/stdout pipes are private to the adapter. The adapter discovers the actual command catalog but forwards only reviewed typed operations. Generic upstream tools, arbitrary commands/code, existing-process attachment, URLs, and OS paths are not exposed to the agent.

The trusted launcher selects the executable and workspace. A fresh UUID session directory holds imported media, `.fcproj` files and native exports. Agent paths are opaque `/dcc/<session>/<name>` handles. Native saves do not embed imported media, so preserve the whole session directory if the project must reopen outside the active session.

Runtime and private process identity are checked, project identity/revision is checked before edits, and changed native save/media bytes are rejected before reopen. A lost process is never restarted to reacquire edit authority. One operation is active at a time. Timeout or caller cancellation does not mean rollback; the original receipt remains until reconciliation, and no uncertain edit is replayed.

Native file reads bind the opened descriptor to the inspected regular file and recheck the session directory before and after reading. Observed file replacement or size/timestamp changes reject the read before artifact publication; directory replacement permanently revokes the session. These checks do not provide an OS sandbox or a transaction against a hostile concurrent writer.

Imports are limited to 16 MiB each and 64 MiB total. There are at most 128 reserved file slots and 32 export jobs per session, with only one active export. Before dispatch, native export is limited to 60 seconds, 1800 frames, 4096-pixel dimensions and 500 million total pixel-frames; audio is mono/stereo at at most 48 kHz. H.264 uses fixed 1000 kbps CBR and software encoding. Admission reserves 32 MiB against 128 MiB of existing owned files. Captured artifacts are limited to 32 MiB each and 128 MiB total; chunks to 256 KiB. Existing files cannot be overwritten. Only owned successful terminal exports can be read; only owned jobs can be cancelled. Export files may exceed the readback limit on disk; this is not a disk quota or an OS sandbox. Use a dedicated operator-controlled workspace and trusted media/runtime.

Typed disconnect returns BUSY while any owned export is active; cancel or poll until terminal, then disconnect. A successful disconnect leaves the native process/document and files present. Immutable artifacts remain readable. Ending stdio closes the owned process, preserving saved files but ending unsaved in-memory edits. Retrieve artifact bytes and save needed work first.

## Reproducible native proof

The official v0.7.2 Linux x86_64 archive is [published by FilmCraft](https://github.com/storytold/filmcraft/releases/tag/v0.7.2). Both checksums are verified by the opt-in CI helper before execution:

- Archive SHA-256: `4171c4bf5f57fd29475655f8a6df4719feda8c8f3ed95b2475d8dc112ad3be86`
- CLI SHA-256: `33129b52859e83106b027d41fcbc65d994bb0b5db32cf1ad2b3187bd547c498c`

```sh
python -m pip install -e '.[dev]'
python scripts/fetch-native-runtime.py
python tests/mcp-e2e.py --mode native --native-cli runtime/filmcraft-cli --output evidence/native
FILMCRAFT_NATIVE_CLI="$PWD/runtime/filmcraft-cli" python -m pytest tests/python/test_native.py
```

FFmpeg/ffprobe must already be installed. The test creates original one-second calibration footage/audio, invokes genuine MCP through Core, saves/reopens the native project, and validates 50% retimed video/audio exports. It checks every source frame is repeated twice (12→24 frames), duration approximately two seconds and 440→220 Hz linked audio. Native cancellation must reach a real terminal cancelled state, and cancelled output cannot become an artifact. Unit/fake-host tests are not counted as real native acceptance. Linux is the actual tested host platform; macOS and Windows host runs remain separate work.

## Desktop GUI findings and remaining work

The official release also offers [native desktop control](https://github.com/storytold/filmcraft/blob/v0.7.2/docs/agents.md): `filmcraft --control PORT`, optionally driven by `filmcraft-cli mcp --bridge 127.0.0.1:PORT`. This is an unauthenticated loopback control channel, not the adapter's private stdio mode. No desktop-bridge option is exposed here.

A real official GUI window was launched in the dot-cloud desktop with isolated data, `--empty --no-recover`, and both default/software graphics. It failed to paint with `MESA: error: Failed to attach to x11 shm`. The app reported a control listener, but the execution workspace could not reach that desktop's loopback/display. Both test windows were closed. No security setting was weakened. This is a verified environment blocker, not a passing GUI screenshot, edit or export test. Desktop control integration requires a usable display and separate same-app lifecycle/ownership verification.
