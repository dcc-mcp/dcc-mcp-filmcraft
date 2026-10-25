---
name: filmcraft-native
description: Use genuine Core-backed MCP tools to drive one owned native FilmCraft CLI engine, with original media and native project/export verification.
---

# FilmCraft native MCP workflow

The stdio launcher owns one persistent official `filmcraft-cli mcp` process.
This is a native headless engine, not a desktop GUI window or a browser editor.
The launcher requires an executable and a workspace; every session gets a fresh
private subdirectory. No tool accepts OS paths, arbitrary commands, URLs or code.
The operator can supply the CLI path or resolve it from FILMCRAFT_CLI, PATH and
read-only official Craft Launcher hints. These hints do not verify binary trust.
The native base package needs no Playwright/Chromium installation. Reuse the
operator-selected DCC-MCP Runtime interpreter; do not install another runtime.

1. Inspect the native session and its capabilities. Create only in an empty clean
   project, then import authorized base64 media bytes, at most 16 MiB per file.
2. Create a sequence from the returned item ID. Inspect the sequence and clips
   before renaming or retiming. Read back edits; exercise undo/redo as needed.
3. Save a new `.fcproj` and retrieve its immutable artifact. Reopen only an
   unchanged save from this session. Imported media remains in the session
   directory; a `.fcproj` alone does not contain the original media.
   For native 0.12.0 only, explicitly pass `restart_native: true` to end the
   healthy owned child and reopen that exact verified save in a new owned child.
   First save all edits and wait until every owned export is terminal. Save and
   all imported media hashes, workspace identity and runtime identity must match;
   unknown state revokes the session without replay. The default is same-process.
   The receipt confirms old-child exit and reports the new child generation.
   This is not loss recovery, arbitrary import or a cross-machine bundle. Old
   jobs retain terminal receipts; use newly returned opaque job IDs for new work.
4. Queue one native H.264/MP4 or WAV output at a time. Exports are limited to
   60 seconds, 1800 frames and 500 million pixel-frames; audio is mono/stereo
   at at most 48 kHz. Poll the owned job until terminal and
   check error/result.error before reading its bytes. Never replay an export.
5. Read artifacts in base64 chunks of at most 256 KiB and verify SHA-256. Check
   decoded frame count, picture content, audio and duration independently.
   When importing a PhotoCraft PNG, record its hash, dimensions and color tags.
   Untagged encoded sRGB intent is not an automatic color-management guarantee.
   H.264 is opaque/lossy; do not claim alpha, OCIO or scene-linear preservation.
6. TIMEOUT/CANCELLED/SESSION/INDETERMINATE does not mean rollback. Reconcile the
   original receipt. A lost process is never replaced to regain authority.
7. Cancel only this session's exports and wait for terminal state; disconnect
   returns BUSY while any owned export is active. A successful disconnect
   preserves saved files and cached artifacts. Read needed artifacts before
   stopping stdio; that stops the owned process and discards unsaved in-memory
   edits, while leaving the session's saved files and imported media on disk.

18 typed operations are exposed. `filmcraft_capture_view` is deliberately absent:
headless frame rendering is not a screenshot of a live GUI editor. Desktop control
and Web/WASM are different modes and require their own verification. The native
adapter does not attach to existing apps, open a control port, install runtimes,
expose generic upstream MCP tools, or add a Core HTTP gateway.
