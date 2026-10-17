"""Native private-stdio boundary tests; real binary checks are opt-in."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path

import pytest
from dcc_mcp_filmcraft.native import NativeError, NativeSession


def run(coro):
    return asyncio.run(coro)


class FakeProcess:
    returncode = None


class SessionHarness(NativeSession):
    def __init__(self, workspace):
        super().__init__("/not-executed/filmcraft-cli", workspace=workspace)
        self.session_dir.mkdir(parents=True, mode=0o700)
        self._directory_identity = self._identity(self.session_dir.lstat())
        self._process = self._original_process = FakeProcess()
        self._started = True
        self.commands_seen = []
        self.project = {
            "name": "Untitled",
            "revision": 1,
            "root": {"id": 0, "children": []},
            "path": None,
            "activeSequence": 8,
            "dirty": False,
        }
        self._project = ("Untitled", 0, None, 1)
        self.jobs = []
        self.sequence = {
            "durationFrames": 24,
            "settings": {
                "width": 160,
                "height": 90,
                "frame_rate": {"num": 12, "den": 1},
                "sample_rate": 48000,
                "audio_master": "Stereo",
            },
        }

    async def _command(self, command, params=None):
        self._guard()
        self.commands_seen.append((command, params))
        if command == "project.inspect":
            return dict(self.project)
        if command == "jobs.list":
            return self.jobs
        if command == "sequence.inspect":
            return self.sequence
        if command == "file.saveAs":
            Path(params["path"]).write_bytes(b"native-project")
            return {"saved": params["path"]}
        if command == "file.exportMedia":
            return {"job": 12}
        if command == "file.newProject":
            self.project["name"] = params["name"]
        return {}

    async def _tool(self, name, arguments):
        self._guard()
        self.commands_seen.append((name, arguments))
        return {"items": [1], "errors": []}


@pytest.fixture
def native(tmp_path):
    return SessionHarness(tmp_path)


def test_native_explicit_headless_capabilities(native):
    result = run(native.call("inspect", {}))["result"]
    assert result["capabilities"]["mode"] == "native-headless"
    assert result["capabilities"]["gui"] is False
    assert len(result["capabilities"]["supported_operations"]) == 18
    with pytest.raises(NativeError, match="no editor window") as error:
        run(native.call("capture_view", {}))
    assert error.value.code == "UNSUPPORTED"


@pytest.mark.parametrize(
    ("op", "params"),
    [
        ("execute", {"command": "file.open", "path": "/etc/passwd"}),
        ("save_project", {"name": "../secret"}),
        ("import_media", {"name": "../../secret.mp4", "data": "AAAA"}),
        ("inspect", {"path": "/etc/passwd"}),
        ("read_artifact", {"artifact": "a" * 64, "offset": -1, "size": 1}),
        ("read_artifact", {"artifact": "a" * 64, "offset": 0, "size": 262145}),
        ("set_playback_rate", {"sequence": 8, "clip": 10, "percent": 900}),
    ],
)
def test_invalid_inputs_never_dispatch(native, op, params):
    with pytest.raises(NativeError):
        run(native.call(op, params))
    assert native.commands_seen == []


def test_process_replacement_cannot_restore_authority(native):
    original = native._original_process
    native._process = FakeProcess()
    with pytest.raises(NativeError):
        run(native.call("inspect", {}))
    native._process = original
    with pytest.raises(NativeError):
        run(native.call("inspect", {}))
    with pytest.raises(NativeError):
        run(native.start())
    assert native.commands_seen == []


def test_directory_replacement_permanently_revokes(native):
    moved = native.session_dir.with_name("moved")
    native.session_dir.rename(moved)
    native.session_dir.mkdir()
    with pytest.raises(NativeError, match="directory identity"):
        run(native.call("inspect", {}))
    assert native.revoked
    assert native.commands_seen == []


def test_import_writes_only_owned_random_path(native):
    raw = b"original fixture"
    result = run(native.call("import_media", {"name": "user.mp4", "data": base64.b64encode(raw).decode()}))
    assert result["result"]["items"] == [1]
    _, args = next(row for row in native.commands_seen if row[0] == "media_import")
    path = Path(args["paths"][0])
    assert path.parent == native.session_dir
    assert path.name.startswith("media-") and path.suffix == ".mp4"
    assert path.read_bytes() == raw
    assert path.name in native._media


def test_import_bad_base64_does_not_dispatch(native):
    with pytest.raises(NativeError, match="valid base64"):
        run(native.call("import_media", {"name": "ok.mp4", "data": "!!!!"}))
    assert native.commands_seen == []


def test_native_project_change_is_rejected(native):
    native.project["revision"] += 1
    with pytest.raises(NativeError, match="revision changed"):
        run(native.call("rename_item", {"item": 1, "name": "Must not run"}))
    assert [c for c, _ in native.commands_seen] == ["project.inspect"]


def test_save_reopen_tamper_and_immutable_artifact(native):
    result = run(native.call("save_project", {"name": "snapshot"}))["result"]
    assert result["path"] == native._virtual("snapshot.fcproj")
    artifact = result["bytes"]["artifact"]
    original = native.session_dir / "snapshot.fcproj"
    original.write_bytes(b"tampered")
    with pytest.raises(NativeError, match="changed outside"):
        run(native.call("reopen_project", {"path": result["path"]}))
    restored = run(native.call("read_artifact", {"artifact": artifact, "offset": 0, "size": 262144}))
    assert base64.b64decode(restored["result"]["data"]) == b"native-project"
    assert hashlib.sha256(b"native-project").hexdigest() == artifact
    with pytest.raises(NativeError, match="overwrite"):
        run(native.call("save_project", {"name": "snapshot"}))
    assert not any(c == "file.open" for c, _ in native.commands_seen)


def test_owned_file_symlink_is_never_read(native, tmp_path):
    secret = tmp_path / "secret"
    secret.write_bytes(b"must not read")
    native._reserved.add("pretend.fcproj")
    (native.session_dir / "pretend.fcproj").symlink_to(secret)
    with pytest.raises(NativeError, match="symbolic link"):
        native._read_owned("pretend.fcproj", 1024)


def test_reopen_unowned_or_dirty_never_dispatches_open(native):
    with pytest.raises(NativeError, match="only this session"):
        run(native.call("reopen_project", {"path": "/etc/passwd"}))
    assert native.commands_seen == []
    result = run(native.call("save_project", {"name": "snapshot"}))["result"]
    native.project["dirty"] = True
    with pytest.raises(NativeError, match="save the current"):
        run(native.call("reopen_project", {"path": result["path"]}))
    assert not any(c == "file.open" for c, _ in native.commands_seen)


def test_export_requires_owned_successful_terminal_job(native):
    job = run(native.call("export_media", {"name": "movie", "sequence": 8, "format": "h264"}))["result"]
    with pytest.raises(NativeError, match="terminal"):
        run(native.call("read_export", {"path": job["path"]}))
    native.jobs = [{"id": 12, "finished": True, "result": {"error": "cancelled"}}]
    with pytest.raises(NativeError, match="did not succeed"):
        run(native.call("read_export", {"path": job["path"]}))
    native.jobs = [{"id": 12, "finished": True, "result": {"frames": 6}, "offlineMedia": [1]}]
    with pytest.raises(NativeError, match="did not succeed"):
        run(native.call("read_export", {"path": job["path"]}))
    native.jobs = [{"id": 12, "finished": True, "result": {"frames": 6}}]
    (native.session_dir / "movie.mp4").write_bytes(b"movie-bytes")
    artifact = run(native.call("read_export", {"path": job["path"]}))["result"]
    assert artifact["sha256"] == hashlib.sha256(b"movie-bytes").hexdigest()
    with pytest.raises(NativeError, match="not owned"):
        run(native.call("cancel_export", {"job": 99}))
    with pytest.raises(NativeError, match="not owned"):
        run(native.call("read_export", {"path": "/etc/passwd"}))


def test_disconnect_preserves_files_and_artifacts(native):
    result = run(native.call("save_project", {"name": "preserved"}))["result"]
    artifact = result["bytes"]["artifact"]
    native.jobs = [{"id": 12, "finished": False}]
    native._exports[native._virtual("active.mp4")] = ("active.mp4", 12)
    with pytest.raises(NativeError, match="active exports"):
        run(native.call("disconnect", {}))
    native.jobs[0]["finished"] = True
    closed = run(native.call("disconnect", {}))["result"]
    assert closed["documentPreserved"] and closed["filesPreserved"]
    assert (native.session_dir / "preserved.fcproj").read_bytes() == b"native-project"
    chunk = run(native.call("read_artifact", {"artifact": artifact, "offset": 0, "size": 5}))["result"]
    assert base64.b64decode(chunk["data"]) == b"nativ"
    with pytest.raises(NativeError, match="disconnected"):
        run(native.call("inspect", {}))


def test_lost_process_keeps_receipt_and_artifact(native):
    artifact = native._store(b"proof", "binary")
    native._receipt = {"settled": True, "uncertain": True, "operation": "rename_item", "origin": native.origin}
    native.revoked = True
    receipt = run(native.call("reconcile", {}))
    assert receipt["result"]["uncertain"] is True
    assert run(native.call("read_artifact", {"artifact": artifact["artifact"], "offset": 0, "size": 10}))["ok"]
    assert native.commands_seen == []


@pytest.mark.skipif(not os.environ.get("FILMCRAFT_NATIVE_CLI"), reason="official installed CLI opt-in")
def test_real_native_lifecycle(tmp_path):
    async def scenario():
        s = NativeSession(os.environ["FILMCRAFT_NATIVE_CLI"], workspace=tmp_path)
        try:
            await s.start()
            await s.call("create_project", {"name": "Real native proof"})
            snapshot = (await s.call("save_project", {"name": "proof"}))["result"]
            reopened = (await s.call("reopen_project", {"path": snapshot["path"]}))["result"]
            assert reopened["name"] == "proof"
            assert reopened["dirty"] is False
            await s.call("disconnect", {})
            assert (
                await s.call(
                    "read_artifact",
                    {
                        "artifact": snapshot["bytes"]["artifact"],
                        "offset": 0,
                        "size": 262144,
                    },
                )
            )["result"]["eof"]
        finally:
            await s.close()
        assert s._process.returncode == 0
        assert list(s.session_dir.glob("*.fcproj"))

    run(scenario())


class RecordingInput:
    def __init__(self):
        self.writes = []

    def write(self, data):
        self.writes.append(data)

    async def drain(self):
        pass


def bind_protocol_process(native, response):
    process = FakeProcess()
    process.stdin = RecordingInput()
    process.stdout = asyncio.StreamReader()
    if response is not None:
        process.stdout.feed_data(response)
        process.stdout.feed_eof()
    native._process = native._original_process = process
    return process


@pytest.mark.parametrize(
    "response",
    [
        b"",
        b"not-json\n",
        b'{"jsonrpc":"2.0","id":99,"result":{}}\n',
        b'{"jsonrpc":"2.0","id":true,"result":{}}\n',
        b'{"jsonrpc":"2.0","id":1}\n',
    ],
)
def test_transport_loss_or_wrong_identity_is_never_replayed(native, response):
    async def scenario():
        process = bind_protocol_process(native, response)
        with pytest.raises(NativeError) as error:
            await native._rpc("tools/call", {"name": "command_run", "arguments": {}})
        assert error.value.code == "INDETERMINATE"
        assert native.revoked
        assert len(process.stdin.writes) == 1
        with pytest.raises(NativeError, match="permanently revoked"):
            await native._rpc("tools/call", {})
        assert len(process.stdin.writes) == 1

    run(scenario())


@pytest.mark.parametrize("content", [None, [1], [{"type": "text", "text": "not-json"}]])
def test_tool_protocol_corruption_revokes_authority(native, content):
    async def scenario():
        reply = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"content": content}}).encode() + b"\n"
        bind_protocol_process(native, reply)
        with pytest.raises(NativeError) as error:
            await NativeSession._tool(native, "command_run", {})
        assert error.value.code == "INDETERMINATE"
        assert native.revoked

    run(scenario())


def test_bounded_protocol_notifications_are_skipped(native):
    async def scenario():
        reply = (
            b'{"jsonrpc":"2.0","method":"notifications/progress","params":{}}\n'
            b'{"jsonrpc":"2.0","id":1,"result":{"answer":42}}\n'
        )
        process = bind_protocol_process(native, reply)
        assert await native._rpc("ping", {}) == {"answer": 42}
        assert len(process.stdin.writes) == 1
        assert not native.revoked

    run(scenario())


def test_direct_inflight_cancellation_revokes_without_replay(native):
    async def scenario():
        process = bind_protocol_process(native, None)

        async def waiting_operation(_operation, _params):
            return await native._rpc("tools/call", {"name": "command_run", "arguments": {}})

        native._operate = waiting_operation
        task = asyncio.create_task(native.call("rename_item", {"item": 1, "name": "Once"}))
        await asyncio.sleep(0)
        assert len(process.stdin.writes) == 1
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert native.revoked
        receipt = (await native.call("reconcile", {}))["result"]
        assert receipt["settled"] and receipt["uncertain"]
        assert len(process.stdin.writes) == 1

    run(scenario())


@pytest.mark.skipif(not os.environ.get("FILMCRAFT_NATIVE_CLI"), reason="official installed CLI opt-in")
def test_real_process_loss_never_reacquires(tmp_path):
    async def scenario():
        s = NativeSession(os.environ["FILMCRAFT_NATIVE_CLI"], workspace=tmp_path)
        await s.start()
        try:
            saved = (await s.call("save_project", {"name": "rescue"}))["result"]
            pid = s._process.pid
            s._process.kill()
            await s._process.wait()
            with pytest.raises(NativeError, match="process lost"):
                await s.call("rename_item", {"item": 1, "name": "Never run"})
            assert s._process.pid == pid
            lost = (await s.call("reconcile", {}))["result"]
            assert lost["uncertain"] and lost["authorityRevoked"]
            with pytest.raises(NativeError, match="cannot be started"):
                await s.start()
            assert (
                await s.call(
                    "read_artifact",
                    {
                        "artifact": saved["bytes"]["artifact"],
                        "offset": 0,
                        "size": 262144,
                    },
                )
            )["result"]["eof"]
        finally:
            await s.close()
        assert (s.session_dir / "rescue.fcproj").exists()

    run(scenario())


@pytest.mark.parametrize(
    "field,value",
    [
        ("durationFrames", 1801),
        ("durationFrames", True),
        ("width", 5000),
        ("height", 5000),
        ("sample_rate", 192000),
        ("audio_master", "Surround51"),
    ],
)
def test_native_export_budget_rejects_before_dispatch(native, field, value):
    target = native.sequence if field == "durationFrames" else native.sequence["settings"]
    target[field] = value
    with pytest.raises(NativeError, match="export"):
        run(native.call("export_media", {"name": "bounded", "sequence": 8, "format": "wav"}))
    assert not any(command == "file.exportMedia" for command, _ in native.commands_seen)
    assert not native._reserved


def test_native_only_one_active_export(native):
    native._exports[native._virtual("first.mp4")] = ("first.mp4", 12)
    native.jobs = [{"id": 12, "finished": False}]
    with pytest.raises(NativeError, match="one native export"):
        run(native.call("export_media", {"name": "second", "sequence": 8, "format": "h264"}))
    assert not any(command == "file.exportMedia" for command, _ in native.commands_seen)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX named pipes")
def test_non_regular_owned_file_is_rejected_without_blocking(native):
    path = native._reserve("nonregular.mp4")
    os.mkfifo(path)
    with pytest.raises(NativeError, match="not regular"):
        native._read_owned(path.name, 1024)


@pytest.mark.skipif(os.name == "nt", reason="symlink privileges vary on Windows")
def test_dangling_link_cannot_reserve_an_output(native, tmp_path):
    target = tmp_path / "must-not-be-created.mp4"
    (native.session_dir / "reserved.mp4").symlink_to(target)
    with pytest.raises(NativeError, match="overwrite"):
        native._reserve("reserved.mp4")
    assert not target.exists()
    assert not native._reserved


def test_owned_read_rejects_directory_replacement_during_open(native, monkeypatch):
    path = native._reserve("result.mp4")
    path.write_bytes(b"owned output")
    original_open = os.open
    moved = native.session_dir.with_name("original-session")
    opened = []

    def replace_then_open(target, flags, *args, **kwargs):
        if Path(target) == path:
            native.session_dir.rename(moved)
            native.session_dir.mkdir()
            path.write_bytes(b"replacement directory bytes")
        fd = original_open(target, flags, *args, **kwargs)
        opened.append(fd)
        return fd

    monkeypatch.setattr(os, "open", replace_then_open)
    with pytest.raises(NativeError, match="directory identity") as error:
        native._read_owned(path.name, 1024)
    assert error.value.code == "SESSION"
    with pytest.raises(OSError):
        os.fstat(opened[0])
    assert native.revoked
    assert (moved / path.name).read_bytes() == b"owned output"
    native.session_dir.rename(native.session_dir.with_name("replacement-session"))
    moved.rename(native.session_dir)
    with pytest.raises(NativeError, match="permanently revoked"):
        run(native.call("inspect", {}))
    assert native.commands_seen == []


@pytest.mark.parametrize("nofollow", [True, False])
def test_owned_read_rejects_file_replacement_during_open(native, monkeypatch, nofollow):
    if not nofollow:
        monkeypatch.delattr(os, "O_NOFOLLOW", raising=False)
    path = native._reserve("result.mp4")
    path.write_bytes(b"owned output")
    replacement = native.session_dir / "replacement"
    replacement.write_bytes(b"other output")
    original_open = os.open

    def replace_then_open(target, flags, *args, **kwargs):
        if Path(target) == path:
            replacement.replace(path)
        return original_open(target, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", replace_then_open)
    with pytest.raises(NativeError, match="file identity") as error:
        native._read_owned(path.name, 1024)
    assert error.value.code == "SESSION"


@pytest.mark.parametrize("change", ["contents", "same_length", "file", "directory"])
def test_owned_read_rejects_mutation_during_read_and_closes_fd(native, monkeypatch, change):
    if os.name == "nt" and change in {"file", "directory"}:
        pytest.skip("Windows does not support these open-file replacement operations")
    path = native._reserve("result.mp4")
    path.write_bytes(b"owned output")
    original_fdopen = os.fdopen
    opened = []

    class ChangingReader:
        def __init__(self, descriptor, mode):
            self.file = original_fdopen(descriptor, mode)
            opened.append(descriptor)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.file.__exit__(*args)

        def fileno(self):
            return self.file.fileno()

        def read(self, limit):
            result = self.file.read(limit)
            if change == "contents":
                path.write_bytes(b"output changed during read")
            elif change == "same_length":
                before = path.stat()
                path.write_bytes(b"other output")
                assert path.stat().st_size == before.st_size
                # Keep the timestamp regression independent of filesystem clock
                # resolution; size alone cannot detect this same-length edit.
                os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000))
            elif change == "file":
                replacement = native.session_dir / "replacement"
                replacement.write_bytes(b"other output")
                replacement.replace(path)
            else:
                native.session_dir.rename(native.session_dir.with_name("original-session"))
                native.session_dir.mkdir()
                path.write_bytes(b"replacement directory bytes")
            return result

    monkeypatch.setattr(os, "fdopen", ChangingReader)
    with pytest.raises(NativeError, match="changed") as error:
        native._read_owned(path.name, 1024)
    assert error.value.code == "SESSION"
    assert native.revoked is (change == "directory")
    assert len(opened) == 1
    with pytest.raises(OSError):
        os.fstat(opened[0])
