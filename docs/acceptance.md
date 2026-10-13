# Bounded browser acceptance — 2026-10-13

Official FilmCraft v0.7.2 web release, unchanged, SHA-256
`48d4f48728fa6b5c028612a4b7f59a5832ff38d430c6a7bd417a2c77d75ae4f9`.
Inspected source main `cee1feb185e675a108f78067f71ad86a640ace3d`; the released
v0.7.2 browser API source is byte-identical to that source. No upstream patches.

## Results

- 55 real browser assertions passed on Chromium 140.0.7339.16 with Playwright 1.55.0:
  42 existing media checks and 13 separately isolated lifecycle checks
- 36 Node unit/regression tests passed; syntax, TypeScript consumer checks and npm
  package dry-run passed
- Browser runtime: official static JS + WASM, same visible editor, WebGL2/CPU via
  SwiftShader, `?empty&norecover&fresh&cpu&webgl`; single-threaded cooperative runtime
- Created an empty project, imported original procedural video/audio, created and
  renamed a sequence, retimed video and linked audio to 50%, and verified undo/redo
- Native `.fcproj` save and integrity-checked same-session reopen preserved sequence,
  clip speeds and 24-frame duration (source had 12 frames)
- H.264 MP4 and WAV exports both decoded with audio, approximately two seconds
- Video oracle: every source frame repeated twice, mean absolute pixel error
  0.73046875 / 255 after re-encoding
- Decoded audio oracles independently check both outputs after retiming the
  original 440 Hz tone: WAV 2.0000 s / 219.375 Hz / RMS 0.124800; MP4 AAC
  2.0053 s / 219.892 Hz / RMS 0.124793. These are non-silence, duration and
  frequency checks, not subjective listening acceptance
- Delayed official-response tests prove a retime receipt covers both selection and
  actual speed change; invalid imports reconcile as errors; mid-selection abort
  does not dispatch the retime or claim it succeeded
- An isolated clean page gates a real official project mutation response until
  after timeout and API replacement. The project actually changed; local receipt
  polling reports `SESSION` with the original session/origin, without further
  commands. Restoring the old API permits neither read/mutation dispatch nor file
  access. The failed receipt does not claim host cancellation or rollback.
- Unit regressions also cover Document/origin loss, inaccessible host properties,
  no-timeout session failure, original provenance despite a changed public session
  field, and revocation during an asynchronous native-save continuation
- Real owned export cancellation reached terminal `result.error="cancelled"`
- Wrong origin/source/session, message replay, stale identity, traversal,
  duplicate paths, unowned native reopen, pre-dispatch abort, host error recovery
  and disconnect cleanup checked
- Before/after PNGs, full browser recording, source clip, `.fcproj`, MP4/WAV,
  console log, state readbacks and ffprobe reports retained with the deliverable;
  isolated lifecycle report, screenshot and recording retained separately

[Machine-readable receipt and exact code/test hashes](acceptance-receipt.json).
Browser unit fakes are not counted as real application tests.

## Limits

This is a bounded original-media integration POC, not a finished artistic Showcase,
full editor parity, a published Core adapter, WASI support or production readiness.
No atomic upstream revision compare-and-execute API exists: concurrent manual
editing/project switching is unsupported. Saved projects still reference imported
media; this same-session reopen test is not a portable media bundle or restart
relink test. GPU acceleration, broad format fidelity, huge projects and hostile
media parsers remain separate acceptance gates. See browser-boundary.md.

The default system Chromium was blocked by its required Unix profile socket.
Standard official Playwright headless-shell ran successfully without changing
network or host security policies. CI repeats these tests independently.
