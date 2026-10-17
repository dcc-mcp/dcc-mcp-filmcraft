"""Mode-specific Core catalogs and launch validation, without native executables."""

import json
from importlib.resources import files

import pytest
from dcc_mcp_filmcraft.adapter import FilmCraftAdapter
from dcc_mcp_filmcraft.catalog import TOOLS, tools_for_mode
from dcc_mcp_filmcraft.cli import main
from dcc_mcp_filmcraft.server import build_server


class NativeStub:
    mode = "native-headless"
    origin = "native-stdio://owned-test-process"

    def __init__(self):
        self.calls = []

    async def call(self, operation, params):
        self.calls.append((operation, params))
        return {"ok": True, "result": {"mode": self.mode}}

    async def close(self):
        pass


def test_native_core_catalog_omits_gui_capture_and_generic_commands():
    host = NativeStub()
    adapter = FilmCraftAdapter(host)
    try:
        names = {row["name"] for row in adapter.registry.list_actions_enabled()}
        assert len(names) == 18
        assert names == {spec["name"] for spec in TOOLS} - {"filmcraft_capture_view"}
        assert adapter.skill_name == "filmcraft-native"
        assert adapter.session is host
        assert adapter.call("filmcraft_capture_view", {})["code"] == "UNSUPPORTED"
        assert adapter.call("command_run", {"id": "file.new"})["code"] == "UNSUPPORTED"
        assert not host.calls
        assert adapter.call("filmcraft_inspect", {})["ok"]
        assert host.calls == [("inspect", {})]
    finally:
        adapter.close()


@pytest.mark.parametrize("mode", ["browser", "native-headless"])
def test_packaged_catalog_matches_mode_and_does_not_mutate_browser(mode):
    before = json.dumps(TOOLS, sort_keys=True)
    selected = tools_for_mode(mode)
    skill = "filmcraft-browser" if mode == "browser" else "filmcraft-native"
    expected = [{k: v for k, v in row.items() if k != "operation"} for row in selected]
    actual = json.loads(files("dcc_mcp_filmcraft").joinpath("skills", skill, "tools.yaml").read_text())
    assert actual["tools"] == expected
    selected[0]["description"] = "changed copy"
    assert json.dumps(TOOLS, sort_keys=True) == before


def test_unknown_mode_rejected():
    with pytest.raises(ValueError, match="unsupported"):
        tools_for_mode("arbitrary-existing-desktop")


def test_native_mcp_server_builds_with_mode_specific_tools():
    adapter = FilmCraftAdapter(NativeStub())
    try:
        server = build_server(adapter)
        assert server.name == "dcc-mcp-filmcraft"
        assert "headless" in files("dcc_mcp_filmcraft").joinpath("skills", adapter.skill_name, "SKILL.md").read_text()
    finally:
        adapter.close()


@pytest.mark.parametrize(
    "args",
    [
        ["serve"],
        ["serve", "--mode", "native"],
        ["serve", "--mode", "native", "--native-cli", "binary"],
        ["serve", "--mode", "native", "--native-cli", "binary", "--workspace", "work", "--headless"],
        ["serve", "--runtime-zip", "runtime.zip", "--workspace", "work"],
    ],
)
def test_invalid_mode_combinations_fail_before_launch(args):
    with pytest.raises(SystemExit) as caught:
        main(args)
    assert caught.value.code == 2


def test_status_is_explicit_about_headless_and_gui(capsys):
    assert main(["status"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["modes"]["native"]["tools"] == 18
    assert result["modes"]["native"]["visible_editor"] is False
    assert result["native_gui_adapter"] is False
    assert result["modes"]["browser"]["tools"] == 19
