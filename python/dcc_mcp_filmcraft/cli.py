"""Explicit stdio launch for a pinned, owned, visible FilmCraft browser session."""

import argparse
import asyncio
import json
from pathlib import Path

from . import __version__
from .browser import RUNTIME_SHA256, RUNTIME_URL


def main(argv=None):
    parser = argparse.ArgumentParser(prog="dcc-mcp-filmcraft")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="Print supported transport and runtime contract without opening the browser")
    serve = sub.add_parser("serve", help="Run genuine MCP stdio and one owned visible editor")
    serve.add_argument("--runtime-zip", type=Path, required=True, help="Official v0.7.2 ZIP; SHA-256 is mandatory")
    serve.add_argument(
        "--headless", action="store_true", help="Explicit automation mode; still the same rendered document"
    )
    serve.add_argument(
        "--chromium", type=str, help="Installed Chromium executable (otherwise Playwright-managed Chromium)"
    )
    serve.add_argument("--evidence-dir", type=Path, help="Explicit destination for browser recording")
    args = parser.parse_args(argv)
    if args.command == "status":
        print(
            json.dumps(
                {
                    "version": __version__,
                    "transport": "stdio",
                    "core_registry": True,
                    "runtime_url": RUNTIME_URL,
                    "runtime_sha256": RUNTIME_SHA256,
                    "headed_default": True,
                    "attaches_existing_browser": False,
                    "control_gateway": False,
                },
                indent=2,
            )
        )
        return 0
    from .adapter import FilmCraftAdapter
    from .server import run_stdio

    adapter = FilmCraftAdapter.launch(
        args.runtime_zip,
        headless=args.headless,
        executable=args.chromium,
        evidence_dir=args.evidence_dir,
    )
    try:
        asyncio.run(run_stdio(adapter))
    finally:
        adapter.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
