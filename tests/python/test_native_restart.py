"""Intentional owned-child restart with explicit Python fixture processes only."""

import asyncio
import base64
import sys
from pathlib import Path

import pytest
from dcc_mcp_filmcraft.adapter import FilmCraftAdapter
from dcc_mcp_filmcraft.browser import BrowserError, BrowserSession
from dcc_mcp_filmcraft.catalog import tools_for_mode
from dcc_mcp_filmcraft.native import NativeError, NativeSession


@pytest.fixture
def launch(monkeypatch, tmp_path):
    original = asyncio.create_subprocess_exec
    processes, second_environment = [], {}

    async def spawn(*_args, **kwargs):
        # The production path supplies the configured executable and all normal
        # isolation arguments. This test substitutes only an explicit test peer.
        if processes:
            assert processes[-1].returncode is not None, "old owned child must exit before another spawn"
        kwargs["env"] = dict(kwargs["env"])
        if processes:
            kwargs["env"].update(second_environment)
        process = await original(
            sys.executable, str(Path(__file__).parent / "fixtures/native_restart_peer.py"), **kwargs
        )
        processes.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)

    async def start():
        session = NativeSession(sys.executable, workspace=tmp_path)
        await session.start()
        await session.call("create_project", {"name": "Original fixture"})
        await session.call(
            "import_media", {"name": "original.wav", "data": base64.b64encode(b"own inert media").decode()}
        )
        saved = (await session.call("save_project", {"name": "same-work"}))["result"]
        return session, saved

    return start, processes, second_environment


def test_explicit_restart_ends_old_child_then_reopens_exact_save_and_media(launch):
    start, processes, _ = launch

    async def scenario():
        session, saved = await start()
        before = {name: (session.session_dir / name).read_bytes() for name in ["same-work.fcproj", *session._media]}
        try:
            default = await session.call("reopen_project", {"path": saved["path"]})
            assert "intentional_restart" not in default["result"] and len(processes) == 1
            result = (await session.call("reopen_project", {"path": saved["path"], "restart_native": True}))["result"]
            assert len(processes) == 2 and processes[0].pid != processes[1].pid
            assert processes[0].returncode is not None and processes[1].returncode is None
            assert result["path"] == saved["path"] and result["dirty"] is False
            assert result["intentional_restart"]["old_child_exited"] is True
            assert result["intentional_restart"]["generation"] == 2
            assert session.capabilities["intentional_restart"] is True
            assert session.capabilities["restart_recovery"] is False
            assert before == {name: (session.session_dir / name).read_bytes() for name in before}
            assert (session.session_dir / "home-restart-2").is_dir()
        finally:
            await session.close()
        assert all(process.returncode is not None for process in processes)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "failure", ["saved", "media", "dirty", "active", "missing_job", "directory", "workspace", "lost"]
)
def test_restart_preconditions_never_launch_replacement(launch, failure):
    start, processes, _ = launch

    async def scenario():
        session, saved = await start()
        try:
            if failure == "saved":
                (session.session_dir / "same-work.fcproj").write_bytes(b"changed")
            elif failure == "media":
                (session.session_dir / next(iter(session._media))).write_bytes(b"changed")
            elif failure == "dirty":
                await session.call("rename_item", {"item": 1, "name": "dirty"})
            elif failure == "active":
                await session.call("export_media", {"name": "active", "sequence": 8, "format": "wav"})
            elif failure == "missing_job":
                session._exports[session._virtual("missing.wav")] = ("missing.wav", 99)
            elif failure == "directory":
                # Windows retains the fixture child's current-directory handle;
                # inject the observed mismatching identity rather than forcing a
                # forbidden rename of its active CWD. Physical replacement also
                # has separate no-child coverage in test_native.py.
                session._directory_identity = (-1, -1)
            elif failure == "workspace":
                session._workspace_identity = (-1, -1)
            elif failure == "lost":
                processes[0].terminate()
                await processes[0].wait()
            with pytest.raises(NativeError):
                await session.call("reopen_project", {"path": saved["path"], "restart_native": True})
            assert len(processes) == 1
            assert session.revoked is (failure not in {"dirty", "active"})
        finally:
            await session.close()

    asyncio.run(scenario())


def test_changed_executable_fingerprint_revokes_without_replacement(launch, monkeypatch):
    start, processes, _ = launch

    async def scenario():
        session, saved = await start()
        monkeypatch.setattr(session, "_fingerprint_executable", lambda: ("changed", "different bytes"))
        try:
            with pytest.raises(NativeError, match="executable differs"):
                await session.call("reopen_project", {"path": saved["path"], "restart_native": True})
            assert session.revoked and len(processes) == 1 and processes[0].returncode is not None
        finally:
            await session.close()

    asyncio.run(scenario())


def test_unconfirmed_old_exit_never_starts_a_new_child(launch, monkeypatch):
    start, processes, _ = launch

    async def scenario():
        session, saved = await start()
        original = session._stop_owned_child

        async def not_closed():
            session._cleanup_errors.append("controlled old child exit remains unconfirmed")
            return {"closed": False, "cleanup_errors": ["controlled exit failure"]}

        monkeypatch.setattr(session, "_stop_owned_child", not_closed)
        try:
            with pytest.raises(NativeError, match="did not close cleanly"):
                await session.call("reopen_project", {"path": saved["path"], "restart_native": True})
            assert session.revoked and len(processes) == 1
            assert session._receipt["cleanup_errors"]
        finally:
            monkeypatch.setattr(session, "_stop_owned_child", original)
            await session.close()

    asyncio.run(scenario())


def test_restart_primary_error_survives_separate_cleanup_failure(launch, monkeypatch):
    start, processes, _ = launch

    async def scenario():
        session, saved = await start()
        original_stop = session._stop_owned_child
        calls = 0

        async def stop():
            nonlocal calls
            calls += 1
            if calls == 1:
                return await original_stop()
            raise RuntimeError("controlled cleanup error")

        async def fail_launch(**_):
            raise NativeError("RUNTIME", "controlled primary identity failure")

        monkeypatch.setattr(session, "_stop_owned_child", stop)
        monkeypatch.setattr(session, "_launch_owned_child", fail_launch)
        try:
            with pytest.raises(NativeError, match="primary identity failure"):
                await session.call("reopen_project", {"path": saved["path"], "restart_native": True})
            assert session.revoked and len(processes) == 1 and processes[0].returncode is not None
            assert "primary identity failure" in session._receipt["error"]
            assert any("controlled cleanup error" in value for value in session._receipt["cleanup_errors"])
        finally:
            monkeypatch.setattr(session, "_stop_owned_child", original_stop)
            await session.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "environment",
    [
        {"FILM_FIXTURE_VERSION": "0.7.2"},
        {"FILM_FIXTURE_EOF_OPEN": "1"},
        {"FILM_FIXTURE_NOOP_OPEN": "1"},
        {"FILM_FIXTURE_OPEN_DIRTY": "missing"},
        {"FILM_FIXTURE_OPEN_DIRTY": "null"},
        {"FILM_FIXTURE_OPEN_DIRTY": "zero"},
    ],
)
def test_replacement_identity_loss_or_failed_open_permanently_revokes_without_replay(launch, environment):
    start, processes, second = launch
    second.update(environment)

    async def scenario():
        session, saved = await start()
        try:
            with pytest.raises(NativeError):
                await session.call("reopen_project", {"path": saved["path"], "restart_native": True})
            assert session.revoked and len(processes) == 2
            assert all(process.returncode is not None for process in processes)
            with pytest.raises(NativeError, match="permanently revoked"):
                await session.call("reopen_project", {"path": saved["path"], "restart_native": True})
            assert len(processes) == 2
        finally:
            await session.close()

    asyncio.run(scenario())


def test_old_terminal_job_ids_cannot_cancel_new_child_job_with_reused_native_id(launch):
    start, _, _ = launch

    async def scenario():
        session, saved = await start()
        try:
            first = (await session.call("export_media", {"name": "old", "sequence": 8, "format": "wav"}))["result"]
            await session.call("cancel_export", {"job": first["job"]})
            await session.call("reopen_project", {"path": saved["path"], "restart_native": True})
            second = (await session.call("export_media", {"name": "new", "sequence": 8, "format": "wav"}))["result"]
            assert first["job"] == 1 and second["job"] != first["job"]
            with pytest.raises(NativeError, match="ended native child"):
                await session.call("cancel_export", {"job": first["job"]})
            rows = (await session.call("list_jobs", {}))["result"]
            assert next(row for row in rows if row["id"] == first["job"])["finished"] is True
            assert next(row for row in rows if row["id"] == second["job"])["finished"] is False
            await session.call("cancel_export", {"job": second["job"]})
            await session.call("reopen_project", {"path": saved["path"], "restart_native": True})
            third = (await session.call("export_media", {"name": "third", "sequence": 8, "format": "wav"}))["result"]
            assert len({first["job"], second["job"], third["job"]}) == 3
            await session.call("cancel_export", {"job": third["job"]})
        finally:
            await session.close()

    asyncio.run(scenario())


def test_restart_host_error_is_not_replaced_by_failed_project_state_readback(launch):
    start, processes, second = launch
    second["FILM_FIXTURE_OPEN_AND_STATE_ERROR"] = "1"

    async def scenario():
        session, saved = await start()
        try:
            with pytest.raises(NativeError, match="primary file.open refusal"):
                await session.call("reopen_project", {"path": saved["path"], "restart_native": True})
            assert session.revoked and len(processes) == 2
            assert all(process.returncode is not None for process in processes)
            assert "primary file.open refusal" in session._receipt["error"]
            assert any("secondary state readback refusal" in value for value in session._receipt["cleanup_errors"])
            assert session._receipt["uncertain"] is True
        finally:
            await session.close()

    asyncio.run(scenario())


def test_browser_catalog_and_direct_session_refuse_native_restart_without_launch():
    browser = next(row for row in tools_for_mode("browser") if row["operation"] == "reopen_project")
    native = next(row for row in tools_for_mode("native-headless") if row["operation"] == "reopen_project")
    assert "restart_native" not in browser["input_schema"]["properties"]
    assert native["input_schema"]["required"] == ["path"]
    assert native["input_schema"]["properties"]["restart_native"]["type"] == "boolean"
    session = BrowserSession("never-read.zip")
    with pytest.raises(BrowserError, match="unavailable in browser"):
        asyncio.run(session.call("reopen_project", {"path": "/unopened", "restart_native": True}))


def test_real_core_routes_native_optional_intent_and_browser_rejects_it():
    class Host:
        origin = "fixture://owned"

        def __init__(self, mode):
            self.mode, self.calls = mode, []

        async def call(self, operation, params):
            self.calls.append((operation, params))
            return {"ok": True, "result": {"fixture": True}}

        async def close(self):
            pass

    for mode in ("native-headless", "browser"):
        host = Host(mode)
        adapter = FilmCraftAdapter(host)
        try:
            result = adapter.call("filmcraft_reopen_project", {"path": "/owned", "restart_native": True})
            assert result["ok"] is (mode == "native-headless")
            assert len(host.calls) == (1 if mode == "native-headless" else 0)
        finally:
            adapter.close()
