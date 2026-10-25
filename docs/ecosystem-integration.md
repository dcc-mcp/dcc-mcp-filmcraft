# Ecosystem integration

FilmCraft already has an adapter in this repository. Reuse its typed Core
registry/dispatcher and official MCP SDK transport instead of duplicating the
official engine or its command catalog. The browser SDK continues to call the
official Web/WASM editor; native mode continues to own one private CLI process.

The current delivery adds read-only discovery of an existing official Craft
Launcher installation. It does not replace that Launcher's install/update UI.
Desktop control remains unqualified. An installed executable and a headless
export do not establish a visible editor's identity, lifecycle or permission.

The base Python distribution contains the adapter, both packaged Skills and
the existing JavaScript SDK. Native mode does not require a browser dependency;
the `browser` extra retains the pinned Playwright path. Use an operator-selected
shared DCC-MCP Runtime interpreter when one is provisioned. This repository has
no runtime downloader, interpreter switcher or second shared daemon.

Core gateway discovery remains a separate gap. This adapter currently supplies
Core-backed MCP stdio and the `dcc_mcp.adapters` entry point. It does not claim
that stdio registration automatically creates a Gateway Admin/Desktop row.
Creator guidance and shared Runtime lifecycle belong to their existing owners.

## Cross-application assets

PhotoCraft produces PNG bytes and a PhotoCraft-only `.pcraft` project. FilmCraft
accepts bounded media bytes and saves `.fcproj` with external media references.
Neither native project format establishes Photoshop binary compatibility or
packages every dependency. Preserve the whole owned FilmCraft session directory.

The new opt-in PNG acceptance script uses the public typed MCP tools. Its report
records actual import, timeline, native save/reopen and export results. A source
without ICC/sRGB/gAMA chunks has untagged color: an encoded sRGB intent is a test
assumption, not verified automatic color management. H.264 output is opaque and
lossy. No EXR, OCIO, scene-linear or alpha-preserving round-trip is implied.
Other CAD/DCC/Nuke consumers require their own native import and color evidence.

## Distribution readiness

The existing Python candidate is `dcc-mcp-filmcraft==0.1.0`, still unreleased.
Build a wheel and sdist from one reviewed commit and smoke-test the wheel in an
isolated interpreter before a release. A locally built wheel is not a PyPI
publication. This repository currently has no publishing workflow or configured
publisher evidence; do not infer ownership from a public project lookup.

PhotoCraft and PdfCraft already have separate package repositories and release
workflows. Reuse them. Do not create empty sibling packages to reserve names.
PyPI account creation, verified email, 2FA and any publisher authorization are
separate operator actions; testing browser navigation grants none of them.

Adapter source is MIT licensed. Official FilmCraft source uses MIT OR Apache-2.0;
vendor binaries, fonts/assets, trademarks and codec obligations need their own
review. Vendor software and original acceptance binaries are excluded from the
wheel and sdist.
