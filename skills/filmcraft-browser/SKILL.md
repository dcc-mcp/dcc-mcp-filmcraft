---
name: filmcraft-browser
description: Operate the same visible FilmCraft WASM project through the bounded typed browser SDK; verify native and media outputs.
---

# FilmCraft browser workflow

Use the SDK within the same trusted HTTP(S) origin as the official editor. Confirm
an empty project and exact origin before connecting. Never substitute a separate
headless CLI instance for a request about the visible browser document.

1. Connect with an explicit origin. Preserve client/session identity across calls.
2. Inspect current project and command support. Stop if the page/API/project changes.
3. Create only in an empty clean editor, import authorized File bytes, create a
   sequence, edit through typed methods and read back the actual sequence.
4. Save to a fresh simple basename, retain native bytes, reopen only that unchanged
   owned save in the same session. Media must remain available; this is not a bundle.
5. Export to a fresh owned path, observe jobs to completion, validate errors and
   retrieve bytes. Verify frame/audio content rather than only nonzero file size.
6. For timeout/abort, never replay. Reconcile the original receipt. Cancel only an
   owned export job and wait for terminal state before closing. Reconciliation is
   local even after Document/API loss; keep the original session/origin receipt.
   Observed identity loss permanently revokes this client, even after restoring the
   old API. A failed receipt does not establish host cancellation or rollback.
7. Close the SDK and optional message bridge; preserve the user's document/files.

Do not expose arbitrary window.filmcraft.execute/request, a public control port,
filesystem gateway or credentials. Do not drive concurrent UI edits: upstream lacks
atomic revision-checked commands. Cross-origin controllers are unsupported.

See README.md and docs/browser-boundary.md. This is a browser SDK skill, not a
desktop adapter. For Core-backed MCP stdio use the packaged Python skill at
python/dcc_mcp_filmcraft/skills/filmcraft-browser/SKILL.md and the README MCP section.
