# Core-backed MCP acceptance

The Python package exposes a real stdio MCP server using official MCP SDK 1.30.0,
with 19 tools registered/dispatched through DCC-MCP Core 0.20.44. This is distinct
from the original direct-JavaScript acceptance in `acceptance.md`.

## Verified on 2026-10-13

- 35 Python boundary/regression tests with the real Core dispatcher, plus 36 SDK
  tests; Python lint/format, TypeScript consumer checks and package builds pass.
- 58 genuine MCP-client checks: protocol initialization (2025-11-25), tools/list,
  schema negatives, prompt discovery/read, create/import/edit/undo/redo, half-speed
  retiming, native .fcproj save/reopen, native MP4+audio and WAV exports, immutable
  chunked artifact readback, SHA-256 validation, same-page screenshot, disconnect.
- 8 independent official-runtime lifecycle checks: a real project mutation applied
  before its response timed out; original receipt stayed pending and later readable
  after API replacement; restoring the API never restored authority; no replay;
  replacing the page realm reported an indeterminate result.
- Pixel oracle: the 12 source frames become 24 frames, each repeated twice.
  Mean absolute RGB error is about 0.73/255 after H.264 compression.
- Separate MP4 AAC/WAV decoding verifies about 2 seconds, about 220 Hz and audible
  RMS from the 1-second/440-Hz original. This is not subjective listening acceptance.

The exact tested source hashes and media measurements are recorded in
`mcp-acceptance-receipt.json`. Generated media and browser recordings are retained
as acceptance artifacts, not embedded vendor/runtime binaries in the repository.

## Reproduce

```sh
python -m pip install -e '.[dev]'
python -m playwright install chromium
python -m pytest
python tests/mcp-e2e.py --runtime-zip /path/to/filmcraft-web-0.7.2.zip
python tests/mcp-lifecycle.py --runtime-zip /path/to/filmcraft-web-0.7.2.zip
```

Use FFmpeg/ffprobe on PATH. `--chromium` selects a compatible installed Chromium.
The ZIP is always checked against the official v0.7.2 SHA-256 before any execution.
The real runtime proof uses Chromium 140 / Playwright 1.55.0 and software WebGL2.
The default user CLI is headed; acceptance explicitly selects headless rendering.

## Limits

This is a bounded experimental integration, not all FilmCraft functionality or a
released desktop adapter. It does not attach to existing user tabs or register a
Core HTTP gateway. Native project reopen is same-session with media still present.
Tool calls must not overlap manual UI editing. Startup opens a new disposable page;
ending the stdio process closes it. `disconnect` alone preserves the page and files.
No arbitrary code, raw upstream command, OS-file read/write, external URL import,
new credential, publication, merge or deployment is performed by these tools.
