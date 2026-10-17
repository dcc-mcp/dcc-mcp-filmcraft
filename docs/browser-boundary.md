# Browser boundary

The API is an opt-in integration in an editor page controlled by its host. A
caller supplies the exact expected HTTP(S) origin. The SDK retains the Window,
Document and official API object identity; observed navigation, inaccessible host
state or API replacement permanently revokes execution for that client. Restoring
the old objects does not restore authority. Its random session identifier is ephemeral correlation, not a persistent
credential. No secrets, OAuth grants, OS paths or localhost command gateway exist.

The optional postMessage endpoint is installed only for an explicit controller
Window and exact same origin. It checks source, origin, protocol, session, request
ID, own-property operation allowlist, one active request and a bounded replay set.
Replies target only that exact origin. Uninstall removes the listener and drops
pending replies. It does not expose FilmCraft's arbitrary request/execute methods.

Same-origin malicious scripts already have direct access to window.filmcraft.
This wrapper does not sandbox them, fix XSS, authenticate a hostile same-origin
parent, or replace a host's CSP and deployment controls. Do not host untrusted
content on the editor origin. Cross-origin controllers are not supported.

## Document and operation safety

The SDK compares name/root/path/revision before edits; the upstream revision
increments on project replacement and edits. Sequence-sensitive operations check
and pass the explicit sequence where the upstream command accepts it. These are
optimistic checks: the upstream does not provide an atomic compare-and-execute
API, so simultaneous UI editing/switching remains unsupported. Use a single
controller and leave the UI idle while it runs. Do not claim transactional safety.

Mutations are not automatically retried. A timeout or AbortSignal stops waiting,
not the host operation. The original operation receipt and completion bookkeeping
remain alive. `reconcile()` reads only local receipt state, even after the host
becomes inaccessible or its Document/API changes. Settled receipts include their
original session ID and origin plus a structured error code; public session-field
changes cannot rewrite that provenance. Reading a receipt neither contacts the
host nor restores revoked authority. A `SESSION` error does not prove that a host
mutation failed to apply or was rolled back. `reconcile()` cannot clear uncertainty
based on an unrelated query.
The receipt covers the complete public operation, including import validation and
both selection and retiming. A timeout continues the original operation; abort
between phases leaves any completed selection in place and prevents retiming.
Pre-aborted calls do not dispatch a mutation. `cancelExport` targets only recorded
jobs; the caller must observe terminal state before closing. No generic queue
cancellation is claimed for upstream promises.

Native saves retain immutable copied bytes; reopen verifies the current owned
virtual file matches before calling file.open. It never passes a basename to
openProject, whose upstream import path could collide with /projects files.
Export paths are session-owned and reserved immediately, even while jobs run.
Readback requires a recorded export path and validates actual returned bytes.

## Bounds and unsupported capabilities

- One input file, at most 16 MiB, from a small reviewed extension set
- Native saves at most 16 MiB; exported bytes at most 32 MiB
- Playback speed 25–400%; no arbitrary JSON/command escape hatch
- Bounds are not a complete decompression-bomb or hostile-codec sandbox
- Official runtime is single-threaded cooperative browser WASM, not WASI
- Browser virtual storage/recovery/OPFS differs from desktop paths and restart recovery
- A native project references imported media; saving it does not package that media
- Reopen proof is same-session with the original media still available
- CPU/WebGL2 software path tested; WebGPU, hardware decode, huge projects, codecs,
  cross-restart media relinking and subjective audio quality are not broadly qualified
- H.264/AAC source/software licensing is distinct from patent or commercial codec
  licensing obligations; no legal clearance is implied

Cleanup releases the SDK's snapshots, job ownership and message listener. It
preserves user-visible project and virtual files, which may contain user edits.
Close the disposable test browser context to clean its temporary storage.
