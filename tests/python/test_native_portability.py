"""Offline policy and explicit Python-child probes, not native host evidence."""

import asyncio
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest
from mcp import McpError

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("native_portability_case", ROOT / "tests/native_portability.py")
case = importlib.util.module_from_spec(spec)
spec.loader.exec_module(case)


def template():
    return json.loads((case.FIXTURE / "project.fcproj").read_bytes())


def test_fixed_fixture_provenance_and_semantics():
    raw = case.read_regular(case.FIXTURE / "project.fcproj", case.MAX_PROJECT, case.TEMPLATE_SHA)
    value = case.inspect_project(raw)
    assert value["project"]["items"]["1"]["kind"]["Media"]["media"]["File"]["path"] == "media/source.mp4"
    assert len(case.read_regular(case.FIXTURE / "source.mp4", 21911, case.SOURCE_SHA)) == 21911
    manifest = json.loads((case.FIXTURE / "manifest.json").read_text())
    assert manifest["source_project_sha256"] == "0cd77b0e9221f3834f7279b4aa175a22edd6ac1ca3ea1c92e128c947a800c09f"
    assert manifest["transformation"]["all_other_json_fields_equal_to_original"] is True
    assert manifest["semantic_project_sha256"] == case.SEMANTIC_SHA
    assert "project.fcproj -text" in (case.FIXTURE / ".gitattributes").read_text()


@pytest.mark.parametrize(
    "path",
    [
        "/tmp/source.mp4",
        "../source.mp4",
        "media/../source.mp4",
        "C:/source.mp4",
        "\\\\host\\share\\source.mp4",
        "https://host/source.mp4",
        "media/other.mp4",
    ],
)
def test_reject_any_other_resource_reference(path):
    value = template()
    value["project"]["items"]["1"]["kind"]["Media"]["media"]["File"]["path"] = path
    with pytest.raises(ValueError):
        case.inspect_project(json.dumps(value).encode())


@pytest.mark.parametrize("change", ["proxy", "schema", "timing", "machine", "traversal"])
def test_reject_other_model_or_path_changes(change):
    value = template()
    if change == "proxy":
        value["project"]["items"]["1"]["kind"]["Media"]["proxy"] = {"File": {"path": "media/proxy.mp4"}}
    elif change == "schema":
        value["schema_version"] = 16
    elif change == "timing":
        value["project"]["items"]["8"]["kind"]["Sequence"]["settings"]["width"] = 200
    elif change == "machine":
        value["view"]["note"] = "/home/runner/work/secret"
    else:
        value["view"]["note"] = "../outside"
    with pytest.raises(ValueError):
        case.inspect_project(json.dumps(value).encode())


def test_read_and_write_new_are_bound(tmp_path):
    path = tmp_path / "file"
    case.write_new(path, b"exact")
    assert case.read_regular(path, 5, case.digest(b"exact")) == b"exact"
    with pytest.raises(FileExistsError):
        case.write_new(path, b"different")
    with pytest.raises(ValueError):
        case.read_regular(path, 4)
    with pytest.raises(ValueError):
        case.read_regular(path, 5, "0" * 64)
    with pytest.raises(ValueError):
        case.read_regular(tmp_path, 100)


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink fixture")
def test_read_rejects_symlink_and_fifo(tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"a")
    link = tmp_path / "link"
    link.symlink_to(source)
    with pytest.raises(ValueError):
        case.read_regular(link, 100)
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    with pytest.raises(ValueError):
        case.read_regular(fifo, 100)


def test_owned_a_isolation_and_directory_identity(tmp_path):
    a, b = tmp_path / "A", tmp_path / "B"
    a.mkdir()
    b.mkdir()
    ident = case.directory_identity(a)
    with pytest.raises(ValueError):
        case.move_owned_a(a, b, tmp_path, ident)
    with pytest.raises(ValueError):
        case.move_owned_a(a, tmp_path.parent / "outside", tmp_path, ident)
    isolated = tmp_path / "A-isolated"
    case.move_owned_a(a, isolated, tmp_path, ident)
    assert not a.exists() and case.directory_identity(isolated) == ident
    a.mkdir()
    with pytest.raises(ValueError):
        case.check_identity(a, ident)


def test_unique_live_routes_fail_closed():
    assert case.resolve_tool(["command_run"], "command_run") == "command_run"
    assert case.resolve_tool(["mcp__filmcraft__command_run"], "command_run") == "mcp__filmcraft__command_run"
    for names in ([], ["command_run", "filmcraft__command_run"], ["other_command_run"]):
        with pytest.raises(ValueError):
            case.resolve_tool(names, "command_run")


@pytest.mark.parametrize(
    "name,raw",
    [
        ("../outside", b"x"),
        ("/outside", b"x"),
        ("x.json", b'{"path":"/home/runner/work/a"}'),
        ("x.md", b"C:\\Users\\name\\file"),
        ("x.json", b'{"p":"P:\\\\codex\\\\file"}'),
    ],
)
def test_user_facing_scan_rejects_machine_paths_and_unsafe_names(name, raw):
    with pytest.raises(ValueError):
        case.scan_user_files({name: raw})


def test_user_facing_scan_accepts_relative_fixture_and_component_source_urls():
    case.scan_user_files(
        {
            "reopened.fcproj": (case.FIXTURE / "project.fcproj").read_bytes(),
            "licenses/reference.json": b'{"url":"https://github.com/storytold/filmcraft"}',
        }
    )


def test_component_license_bytes_and_receipts_are_pinned():
    files = case.license_files()
    assert len(files) == 5
    for name, expected in case.LICENSE_SHA.items():
        assert case.digest(files["licenses/" + name]) == expected
    case.scan_user_files(files)


def test_user_scan_rejects_the_actual_execution_root():
    with pytest.raises(ValueError, match="actual execution root"):
        case.scan_user_files(
            {"note.md": b"unexpected /another-private-base/work/file"}, ("/another-private-base/work",)
        )


def test_explicit_fixture_child_public_sdk_and_clean_exit(tmp_path):
    async def run():
        report = {}
        peer = ROOT / "tests/python/fixtures/portable_peer.py"
        async with case.OfficialClient(
            [sys.executable, str(peer)], tmp_path, tmp_path / "home", tmp_path / "stderr", report, "fixture"
        ) as client:
            identity = await client.initialize()
            assert identity["version"] == "0.12.0"
            assert await client.command_call("jobs.list") == []
            pid = client.process.pid
        assert report["children"][0]["pid"] == pid
        assert report["children"][0]["completed"] is True
        assert report["children"][0]["exit_code"] == 0
        assert len(report["official_mcp_events"]) == 4

    asyncio.run(run())


def test_unknown_fixture_result_never_replayed_and_primary_retained(tmp_path):
    async def run():
        report = {}
        peer = ROOT / "tests/python/fixtures/portable_peer.py"
        with pytest.raises(McpError, match="Connection closed"):
            async with case.OfficialClient(
                [sys.executable, str(peer), "--early-eof"],
                tmp_path,
                tmp_path / "home",
                tmp_path / "stderr",
                report,
                "fixture",
            ) as client:
                await client.initialize()
                try:
                    await client.command_call("jobs.list")
                except Exception:
                    count = len(report["official_mcp_events"])
                    with pytest.raises(RuntimeError, match="permanently revoked"):
                        await client.command_call("jobs.list")
                    assert len(report["official_mcp_events"]) == count
                    raise
        assert report["official_mcp_events"][-1]["state"] == "client_exception"
        assert "primary_error" in report["children"][0]
        assert report["children"][0]["exited"] is True

    asyncio.run(run())


def test_plan_amendment_precedes_native_execution():
    text = (ROOT / "docs/source-guided-plan-amendment.md").read_text()
    assert "before any new vendor/native execution" in text
    assert "diagnostic_status_consistent" in text
    assert not any(
        "dcc_mcp_filmcraft" in line
        for line in (ROOT / "tests/native_portability.py").read_text().splitlines()
        if line.startswith(("import ", "from "))
    )


def test_raw_status_disagreement_is_preserved_without_claiming_online(tmp_path):
    class Fixture:
        label = "B"

        async def command_call(self, name, params=None):
            return {
                "file.open": {"missingMedia": 0},
                "media.findMissing": {"missing": []},
                "media.status": [{"item": 1, "path": case.MEDIA, "status": "missing"}],
                "project.inspect": {"dirty": False, "path": str(tmp_path / "project.fcproj")},
            }[name]

    checks, report = [], {}
    asyncio.run(case.inspect_online(Fixture(), tmp_path / "project.fcproj", checks, report))
    assert all(check["ok"] for check in checks)
    assert report["raw_media_status"]["B"][0]["status"] == "missing"
    assert report["diagnostic_status_by_child"]["B"]["consistent_with_find_missing"] is False


@pytest.mark.parametrize("dirty", [None, 0, "false"])
def test_open_readback_requires_actual_clean_boolean(tmp_path, dirty):
    class Fixture:
        label = "B"

        async def command_call(self, name, params=None):
            return {
                "file.open": {"missingMedia": 0},
                "media.findMissing": {"missing": []},
                "media.status": [{"item": 1, "path": case.MEDIA, "status": "missing"}],
                "project.inspect": {"dirty": dirty, "path": str(tmp_path / "project.fcproj")},
            }[name]

    with pytest.raises(AssertionError, match="exact clean opened project"):
        asyncio.run(case.inspect_online(Fixture(), tmp_path / "project.fcproj", [], {}))


@pytest.mark.parametrize("missing", [False, True, 0.0, [], {}, None, 1, -1, "absent"])
def test_open_missing_media_requires_strict_zero_integer(tmp_path, missing):
    class Fixture:
        label = "A"

        async def command_call(self, name, params=None):
            assert name == "file.open"
            return {} if missing == "absent" else {"missingMedia": missing}

    with pytest.raises(AssertionError, match="open has no missing media"):
        asyncio.run(case.inspect_online(Fixture(), tmp_path / "project.fcproj", [], {}))


def test_e399_completed_open_wire_value_is_zero_count_not_list():
    response = case.types.CallToolResult.model_validate(
        {
            "content": [{"type": "text", "text": '{"migrated":false,"missingMedia":0,"schemaVersion":15}'}],
            "isError": False,
        }
    )
    result = case.tool_value(response)
    assert type(result["missingMedia"]) is int and result["missingMedia"] == 0


@pytest.mark.parametrize("offline", [[], [{"item": 1}], None, 0, False])
def test_terminal_export_requires_explicit_empty_offline_list(tmp_path, offline):
    output = tmp_path / "synthetic-export.txt"

    class Fixture:
        async def command_call(self, name, params=None):
            if name == "file.exportMedia":
                output.write_bytes(b"synthetic unit output; not encoded media or vendor content")
                return {"job": 1}
            assert name == "jobs.list"
            return [{"id": 1, "finished": True, "result": {"frames": 24}, "offlineMedia": offline}]

    if offline == []:
        asyncio.run(case.terminal_export(Fixture(), 8, output, "h264", []))
    else:
        with pytest.raises(AssertionError, match="no offline media"):
            asyncio.run(case.terminal_export(Fixture(), 8, output, "h264", []))
