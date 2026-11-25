"""Read-only native CLI discovery; the official Craft Launcher owns installs.

An installed.json entry is a location hint, never binary provenance or GUI
identity. Discovery does not execute software, unpack packages or change files.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
from dataclasses import dataclass
from pathlib import Path

ENV_CLI = "FILMCRAFT_CLI"
ENV_LAUNCHER_DATA = "FILMCRAFT_LAUNCHER_DATA"
MAX_MANIFEST_BYTES = 1024 * 1024


@dataclass(frozen=True)
class NativeCliHint:
    path: Path | None
    source: str | None

    def status(self) -> dict:
        return {
            "available": self.path is not None,
            "source": self.source,
            "discovery_only": True,
            "binary_trust_verified": False,
            "gui_verified": False,
            "automatic_install": False,
        }


def data_directories() -> list[Path]:
    """Known launcher data roots, with an optional absolute portable override."""
    home = Path.home()
    configured = os.environ.get(ENV_LAUNCHER_DATA)
    roots = [Path(configured)] if configured and Path(configured).is_absolute() else []
    if sys.platform == "win32":
        roots.append(Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local")) / "ArtCraft Launcher")
    elif sys.platform == "darwin":
        roots.append(home / "Library/Application Support/ArtCraft Launcher")
    else:
        roots.extend(
            [
                Path(os.environ.get("XDG_DATA_HOME", home / ".local/share")) / "artcraft-launcher",
                home / ".var/app/ai.storyteller.artcraft-launcher/data/artcraft-launcher",
            ]
        )
    return list(dict.fromkeys(roots))


def _record_path(directory: Path) -> Path | None:
    try:
        manifest_path = directory / "installed.json"
        info = manifest_path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_MANIFEST_BYTES:
            return None
        with manifest_path.open("rb") as stream:
            raw = stream.read(MAX_MANIFEST_BYTES + 1)
        if len(raw) > MAX_MANIFEST_BYTES:
            return None
        value = json.loads(raw)["apps"]["filmcraft"]["path"]
        if not isinstance(value, str) or not value or "\x00" in value:
            return None
        path = Path(value)
        return path if path.is_absolute() else None
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        return None


def search_directories() -> list[Path]:
    """Native trees and portable/bundle siblings only; never unpack AppImages."""
    found = []
    for directory in data_directories():
        recorded = _record_path(directory)
        if recorded is not None:
            if recorded.name.lower() in {"filmcraft", "filmcraft.exe"}:
                found.append(recorded.parent)
            elif recorded.name == "FilmCraft.app":
                found.append(recorded / "Contents/MacOS")
            else:
                try:
                    if recorded.is_dir():
                        found.extend([recorded / "bin", recorded])
                except (OSError, ValueError):
                    pass
        tree = directory / "apps/filmcraft"
        found.extend([tree / "bin", tree])
    return list(dict.fromkeys(found))


def _usable(path: Path) -> bool:
    try:
        return path.is_file() and os.access(path, os.X_OK)
    except (OSError, ValueError):
        return False


def discover_native_cli(explicit: Path | None = None) -> NativeCliHint:
    """Prefer operator configuration, PATH, then official Launcher locations.

    Explicit configuration must be usable; an invalid configured executable is
    an error rather than permission to choose and run a different program.
    """
    configured = explicit if explicit is not None else os.environ.get(ENV_CLI)
    if configured is not None:
        candidate = Path(configured).expanduser()
        if not _usable(candidate):
            raise ValueError("configured FilmCraft CLI is not an executable file")
        return NativeCliHint(candidate.resolve(), "argument" if explicit is not None else "environment")
    name = "filmcraft-cli.exe" if sys.platform == "win32" else "filmcraft-cli"
    located = shutil.which(name)
    if located and _usable(Path(located)):
        return NativeCliHint(Path(located).resolve(), "path")
    for directory in search_directories():
        candidate = directory / name
        if _usable(candidate):
            return NativeCliHint(candidate.resolve(), "craft-launcher")
    return NativeCliHint(None, None)
