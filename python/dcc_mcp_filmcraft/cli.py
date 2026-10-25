"""Explicit stdio launch for an owned FilmCraft browser or native engine session."""

import argparse
import asyncio
import json
from pathlib import Path

from . import __version__
from .browser import RUNTIME_SHA256, RUNTIME_URL
from .launcher import NativeCliHint, discover_native_cli


def main(argv=None):
    parser = argparse.ArgumentParser(prog="dcc-mcp-filmcraft")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="Print supported modes and runtime contract without starting a host")
    serve = sub.add_parser("serve", help="Run genuine MCP stdio and one owned FilmCraft session")
    serve.add_argument("--mode", choices=["browser", "native"], default="browser")
    serve.add_argument("--runtime-zip", type=Path, help="Browser mode: official v0.7.2 ZIP, SHA-256 verified")
    serve.add_argument(
        "--native-cli",
        type=Path,
        help="Native mode: CLI path; otherwise FILMCRAFT_CLI, PATH, then Craft Launcher hints",
    )
    serve.add_argument(
        "--workspace", type=Path, help="Native mode: persistent root for a new private session directory"
    )
    serve.add_argument(
        "--headless", action="store_true", help="Explicit automation mode; still the same rendered document"
    )
    serve.add_argument(
        "--chromium", type=str, help="Installed Chromium executable (otherwise Playwright-managed Chromium)"
    )
    serve.add_argument("--evidence-dir", type=Path, help="Explicit destination for browser recording")
    args = parser.parse_args(argv)
    if args.command == "status":
        try:
            native_discovery = discover_native_cli().status()
        except ValueError:
            native_discovery = NativeCliHint(None, "environment").status()
            native_discovery["configuration_error"] = "configured CLI is not executable"
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
                    "modes": {
                        "browser": {"tools": 19, "visible_editor": True},
                        "native": {"tools": 18, "visible_editor": False, "process": "owned persistent CLI MCP"},
                    },
                    "native_gui_adapter": False,
                    "native_cli_discovery": native_discovery,
                },
                indent=2,
            )
        )
        return 0
    from .adapter import FilmCraftAdapter
    from .server import run_stdio

    if args.mode == "native":
        if not args.workspace:
            parser.error("native mode requires --workspace")
        if args.runtime_zip or args.headless or args.chromium:
            parser.error("browser runtime/headless/Chromium options cannot be used in native mode")
        try:
            native_cli = discover_native_cli(args.native_cli).path
        except ValueError as exc:
            parser.error(str(exc))
        if native_cli is None:
            parser.error("FilmCraft CLI not found; configure --native-cli or install an official native runtime")
        adapter = FilmCraftAdapter.launch_native(native_cli, workspace=args.workspace, evidence_dir=args.evidence_dir)
    else:
        if not args.runtime_zip:
            parser.error("browser mode requires --runtime-zip")
        if args.native_cli or args.workspace:
            parser.error("--native-cli and --workspace require --mode native")
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
