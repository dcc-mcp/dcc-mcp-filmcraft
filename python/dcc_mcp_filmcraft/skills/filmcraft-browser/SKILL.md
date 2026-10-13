---
name: filmcraft-browser
description: Use genuine MCP tools backed by DCC-MCP Core to edit the same owned FilmCraft browser document and verify native and media outputs.
---

# FilmCraft MCP workflow

The `dcc-mcp-filmcraft serve` stdio process owns one FilmCraft browser page. Its
normal mode opens a visible editor; `--headless` is explicit automation mode with
screenshots and recordings. It never attaches to an unrelated existing tab or
creates a second hidden editor per call. Core's registry and dispatcher enforce
the bounded tool schemas. No arbitrary code or upstream command endpoint exists.

1. Call `filmcraft_inspect`. Create only in an empty clean project. Keep manual UI
   editing idle while a tool runs; upstream has no atomic compare-and-execute lock.
2. Import authorized media bytes with `filmcraft_import_media`; files are bounded
   to 16 MiB. No tool reads arbitrary OS paths or fetches arbitrary URLs.
3. Create a sequence from the returned item ID. Inspect sequence/clip IDs before
   renaming or changing playback rate. Read back edits, and use undo/redo as needed.
4. `filmcraft_save_project` creates a fresh native file and immutable artifact.
   `filmcraft_reopen_project` accepts only an unchanged save owned by this session.
   Imported media must remain available; .fcproj is not a packaged media bundle.
5. `filmcraft_export_media` queues native H.264/MP4 or WAV. Poll `filmcraft_list_jobs`
   until the specific owned job is terminal, and check both error and result.error.
   `filmcraft_read_export` creates an artifact, then `filmcraft_read_artifact` reads
   base64 chunks at most 256 KiB. Verify SHA-256 and actual decoded pixels/audio.
6. `filmcraft_capture_view` proves the actual rendered editor state. Read its PNG
   artifact through the same chunk API. Never treat an artifact ID as an OS path.
7. TIMEOUT/CANCELLED/SESSION/INDETERMINATE do not imply rollback. Never replay a
   mutation. Reconcile its original receipt. If the realm is destroyed, report
   the outcome as indeterminate; never recover authority from a replacement page.
8. Cancel only owned exports, then observe terminal state. `filmcraft_disconnect`
   closes the typed client and preserves the page/document/files. Stopping the
   stdio process closes its disposable browser; retrieve needed artifacts first.

19 tools are registered. `tools.yaml` describes their schemas; runtime-supported
upstream commands remain dynamically discovered by the browser SDK. Core HTTP
registration, gateway discovery, desktop TCP, WASI and restart recovery are not
implemented by this stdio adapter. Do not claim those capabilities.
