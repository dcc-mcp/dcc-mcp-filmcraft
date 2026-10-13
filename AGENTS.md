# dcc-mcp-filmcraft

Experimental browser SDK for the official FilmCraft WASM editor. This repository
is not a fork and does not ship the vendor binary. The JavaScript API operates
the same `FilmcraftApp` control queue that draws the visible editor.

Read README.md, docs/browser-boundary.md, then the relevant src/tests. Read the
upstream AGENTS.md before changing upstream source. No upstream patch is required.

- Keep command discovery runtime-driven. Typed methods may use a reviewed bounded
  subset, but never mirror the complete upstream command table.
- Keep origin, Window/Document/API identity, revision and request-session checks.
- Never expose a localhost gateway, arbitrary execute endpoint, secret, or token.
- Never replay an uncertain mutation. Keep its receipt and settle it explicitly.
- Use bytes in the browser virtual filesystem. Desktop CLI/stdin and WASI are
  different capabilities and cannot be claimed from this POC.
- Preserve user documents and virtual files when disconnecting. Cancel only jobs
  recorded by this client, then await terminal status before closing.
- Keep EN/ZH user guidance consistent. Use conventional commits and Draft PRs.
- No publish/release/merge/deployment is implied by a passing test.

Checks: `npm ci --ignore-scripts`, `npm run check`, `npm test`, `npm run typecheck`,
`npm pack --dry-run`. Real acceptance: `python tests/browser-e2e.py` after installing
Playwright 1.55.0, its Chromium runtime, and FFmpeg. This downloads only the official
pinned browser ZIP and verifies its SHA-256 before execution. Tests generate
original procedural media, retain screenshots/video and native/export artifacts,
and independently check retimed video pixels and audio samples.
