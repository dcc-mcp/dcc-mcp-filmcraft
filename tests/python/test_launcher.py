"""Launcher location hints never grant installation, execution or GUI authority."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from dcc_mcp_filmcraft import cli, launcher


@pytest.fixture(autouse=True)
def isolated_discovery(monkeypatch):
    monkeypatch.delenv("FILMCRAFT_CLI", raising=False)
    monkeypatch.delenv("FILMCRAFT_LAUNCHER_DATA", raising=False)
    monkeypatch.setattr(launcher.shutil, "which", lambda _: None)
    monkeypatch.setattr(launcher, "data_directories", lambda: [])


def executable(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not executed")
    path.chmod(0o700)
    return path


def cli_name():
    return "filmcraft-cli.exe" if launcher.sys.platform == "win32" else "filmcraft-cli"


@pytest.mark.parametrize("layout", ["portable", "tree", "bundle"])
def test_launcher_finds_native_sibling_without_process_or_manifest_changes(monkeypatch, tmp_path, layout):
    data = tmp_path / "data"
    data.mkdir()
    install = tmp_path / "install"
    if layout == "portable":
        recorded = executable(install / "filmcraft.exe")
        root = install
    elif layout == "bundle":
        recorded = install / "FilmCraft.app"
        root = recorded / "Contents/MacOS"
    else:
        recorded = install
        root = install / "bin"
    expected = executable(root / cli_name())
    manifest = data / "installed.json"
    manifest.write_text(json.dumps({"apps": {"filmcraft": {"path": str(recorded)}}}), encoding="utf-8")
    original = manifest.read_bytes()
    monkeypatch.setattr(launcher, "data_directories", lambda: [data])
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("discovery started a process"))
    result = launcher.discover_native_cli()
    assert result.path == expected.resolve()
    assert result.source == "craft-launcher"
    assert manifest.read_bytes() == original
    assert result.status() == {
        "available": True,
        "source": "craft-launcher",
        "discovery_only": True,
        "binary_trust_verified": False,
        "gui_verified": False,
        "automatic_install": False,
    }


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        "[]",
        '{"apps":[]}',
        '{"apps":{"filmcraft":{"path":"relative/bin"}}}',
        '{"apps":{"filmcraft":{"path":42}}}',
        '{"apps":{"filmcraft":{"path":""}}}',
        '{"apps":{"photocraft":{"path":"/wrong-product"}}}',
        '{"apps":{"filmcraft":{"path":"/bad\\u0000path"}}}',
    ],
)
def test_malformed_manifest_is_only_absent_hint(monkeypatch, tmp_path, payload):
    (tmp_path / "installed.json").write_text(payload, encoding="utf-8")
    monkeypatch.setattr(launcher, "data_directories", lambda: [tmp_path])
    assert launcher._record_path(tmp_path) is None
    assert launcher.search_directories() == [tmp_path / "apps/filmcraft/bin", tmp_path / "apps/filmcraft"]
    assert launcher.discover_native_cli().path is None


def test_manifest_read_is_bounded_and_non_regular_rejected(tmp_path):
    manifest = tmp_path / "installed.json"
    manifest.write_bytes(b" " * (launcher.MAX_MANIFEST_BYTES + 1))
    assert launcher._record_path(tmp_path) is None
    manifest.unlink()
    manifest.mkdir()
    assert launcher._record_path(tmp_path) is None


def test_default_launcher_tree_and_appimage_not_unpacked(monkeypatch, tmp_path):
    image = tmp_path / "FilmCraft.AppImage"
    image.write_bytes(b"never unpacked")
    data = tmp_path / "launcher"
    data.mkdir()
    (data / "installed.json").write_text(json.dumps({"apps": {"filmcraft": {"path": str(image)}}}))
    expected = executable(data / "apps/filmcraft/bin" / cli_name())
    monkeypatch.setattr(launcher, "data_directories", lambda: [data])
    assert launcher.discover_native_cli().path == expected.resolve()
    assert image.read_bytes() == b"never unpacked"


def test_unreadable_recorded_tree_does_not_break_discovery(monkeypatch, tmp_path):
    recorded = tmp_path / "unreadable"
    (tmp_path / "installed.json").write_text(json.dumps({"apps": {"filmcraft": {"path": str(recorded)}}}))
    original = Path.is_dir

    def is_dir(path):
        if path == recorded:
            raise PermissionError("unreadable install tree")
        return original(path)

    monkeypatch.setattr(Path, "is_dir", is_dir)
    monkeypatch.setattr(launcher, "data_directories", lambda: [tmp_path])
    assert launcher.discover_native_cli().path is None


def test_explicit_then_environment_then_path_before_launcher(monkeypatch, tmp_path):
    explicit = executable(tmp_path / "explicit")
    environment = executable(tmp_path / "environment")
    in_path = executable(tmp_path / "path")
    monkeypatch.setenv("FILMCRAFT_CLI", str(environment))
    monkeypatch.setattr(launcher.shutil, "which", lambda _: str(in_path))
    monkeypatch.setattr(launcher, "search_directories", lambda: pytest.fail("overrode configured/PATH executable"))
    assert launcher.discover_native_cli(explicit) == launcher.NativeCliHint(explicit.resolve(), "argument")
    assert launcher.discover_native_cli() == launcher.NativeCliHint(environment.resolve(), "environment")
    monkeypatch.delenv("FILMCRAFT_CLI")
    assert launcher.discover_native_cli() == launcher.NativeCliHint(in_path.resolve(), "path")


def test_invalid_explicit_configuration_does_not_choose_another_binary(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher.shutil, "which", lambda _: pytest.fail("ignored explicit configuration"))
    with pytest.raises(ValueError, match="configured FilmCraft CLI"):
        launcher.discover_native_cli(tmp_path / "missing")
    monkeypatch.setenv("FILMCRAFT_CLI", str(tmp_path / "missing"))
    with pytest.raises(ValueError, match="configured FilmCraft CLI"):
        launcher.discover_native_cli()


def test_portable_data_override_and_platform_default(monkeypatch, tmp_path):
    # Undo the autouse stub to exercise the platform roots themselves.
    monkeypatch.undo()
    monkeypatch.setattr(launcher.sys, "platform", "linux")
    monkeypatch.setenv("FILMCRAFT_LAUNCHER_DATA", str(tmp_path / "portable"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert launcher.data_directories()[:2] == [tmp_path / "portable", tmp_path / "xdg/artcraft-launcher"]
    monkeypatch.setenv("FILMCRAFT_LAUNCHER_DATA", "relative")
    assert launcher.data_directories()[0] == tmp_path / "xdg/artcraft-launcher"


def test_status_does_not_launch_host_and_exposes_hint_limits(monkeypatch, capsys):
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("status started a host"))
    assert cli.main(["status"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["native_cli_discovery"]["available"] is False
    assert data["native_cli_discovery"]["discovery_only"] is True
    assert data["native_gui_adapter"] is False


def test_status_reports_invalid_configuration_without_launch(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("FILMCRAFT_CLI", str(tmp_path / "missing"))
    assert cli.main(["status"]) == 0
    discovery = json.loads(capsys.readouterr().out)["native_cli_discovery"]
    assert discovery["available"] is False
    assert discovery["configuration_error"]
    assert discovery["binary_trust_verified"] is False


def test_native_serve_uses_discovered_hint_but_requires_workspace(monkeypatch, tmp_path):
    chosen = executable(tmp_path / cli_name())
    monkeypatch.setattr(launcher.shutil, "which", lambda _: str(chosen))
    calls = []
    adapter = SimpleNamespace(close=lambda: calls.append("closed"))

    def launch(path, **kwargs):
        calls.append((path, kwargs))
        return adapter

    async def run_stdio(value):
        assert value is adapter
        calls.append("stdio")

    monkeypatch.setitem(
        sys.modules,
        "dcc_mcp_filmcraft.adapter",
        SimpleNamespace(FilmCraftAdapter=SimpleNamespace(launch_native=launch)),
    )
    monkeypatch.setitem(sys.modules, "dcc_mcp_filmcraft.server", SimpleNamespace(run_stdio=run_stdio))
    with pytest.raises(SystemExit):
        cli.main(["serve", "--mode", "native"])
    assert calls == []
    workspace = tmp_path / "owned-workspace"
    assert cli.main(["serve", "--mode", "native", "--workspace", str(workspace)]) == 0
    assert calls == [(chosen.resolve(), {"workspace": workspace, "evidence_dir": None}), "stdio", "closed"]


def test_browser_arguments_do_not_use_native_discovery(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "discover_native_cli", lambda *args: pytest.fail("browser discovered native runtime"))
    monkeypatch.setitem(sys.modules, "dcc_mcp_filmcraft.adapter", SimpleNamespace(FilmCraftAdapter=SimpleNamespace()))
    monkeypatch.setitem(sys.modules, "dcc_mcp_filmcraft.server", SimpleNamespace(run_stdio=None))
    with pytest.raises(SystemExit):
        cli.main(["serve", "--runtime-zip", str(tmp_path / "runtime.zip"), "--workspace", str(tmp_path)])
