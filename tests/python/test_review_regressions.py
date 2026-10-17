"""Boundary regressions with the real Core dispatcher and no external browser/network."""

from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import json
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest
from dcc_mcp_filmcraft import browser as browser_module
from dcc_mcp_filmcraft.adapter import FilmCraftAdapter
from dcc_mcp_filmcraft.browser import BrowserError, BrowserSession
from dcc_mcp_filmcraft.catalog import TOOLS


class FakeBrowser:
    origin = "http://127.0.0.1:49152"

    def __init__(self, *, blocked=None):
        self.calls = []
        self.threads = []
        self.blocked = set(blocked or ())
        self.entered = threading.Event()
        self.release = threading.Event()

    async def call(self, operation, params):
        self.calls.append((operation, params))
        self.threads.append(threading.get_ident())
        if operation in self.blocked:
            self.entered.set()
            while not self.release.is_set():
                await asyncio.sleep(0.001)
        if operation == "reconcile":
            return {"ok": True, "result": {"settled": True, "uncertain": False}}
        return {"ok": True, "result": {"operation": operation}}

    async def close(self):
        self.release.set()
        await asyncio.sleep(0.01)


@pytest.fixture
def adapter():
    instance = FilmCraftAdapter(FakeBrowser())
    try:
        yield instance
    finally:
        instance.close()


def wait_until(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("bounded wait did not settle")
        time.sleep(0.002)


def test_real_core_registry_contains_exact_bounded_catalog(adapter):
    assert {row["name"] for row in adapter.registry.list_actions_enabled()} == {spec["name"] for spec in TOOLS}
    assert adapter.dispatcher.skip_empty_schema_validation is False
    assert adapter.call("filmcraft_inspect", {})["ok"] is True
    assert adapter.browser.calls == [("inspect", {})]


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("filmcraft_inspect", {"code": "arbitrary code"}),
        ("filmcraft_inspect", 7),
        ("filmcraft_inspect_sequence", {"sequence": True}),
        ("filmcraft_inspect_sequence", {"sequence": 1.5}),
        ("filmcraft_inspect_sequence", {"sequence": 0}),
        ("filmcraft_inspect_sequence", {"sequence": 9007199254740992}),
        ("filmcraft_set_playback_rate", {"sequence": 1, "clip": 2, "percent": 401}),
        ("filmcraft_set_playback_rate", {"sequence": 1, "clip": 2, "percent": float("nan")}),
        ("filmcraft_save_project", {"name": "../overwrite"}),
        ("filmcraft_rename_item", {"item": 1, "name": "x" * 129}),
        ("filmcraft_export_media", {"name": "export", "sequence": 1, "format": "arbitrary"}),
        ("filmcraft_read_artifact", {"artifact": "../../secret", "offset": 0, "size": 1}),
        ("filmcraft_read_artifact", {"artifact": "a" * 64, "offset": -1, "size": 1}),
        ("filmcraft_read_artifact", {"artifact": "a" * 64, "offset": 0, "size": 262145}),
    ],
)
def test_invalid_arguments_never_reach_browser(adapter, name, arguments):
    result = adapter.call(name, arguments)
    assert result["ok"] is False
    assert result["code"] == "INVALID_ARGUMENT"
    assert adapter.browser.calls == []


@pytest.mark.parametrize("name", ["execute_code", "__proto__", "filmcraft_execute", "inspect"])
def test_unknown_tools_never_reach_browser(adapter, name):
    result = adapter.call(name, {})
    assert result["ok"] is False
    assert result["code"] == "UNSUPPORTED"
    assert adapter.browser.calls == []


def test_direct_core_no_argument_schema_is_not_skipped(adapter):
    with pytest.raises(ValueError, match="additional property"):
        adapter.dispatcher.dispatch("filmcraft_inspect", '{"code":"not allowed"}')
    assert adapter.browser.calls == []


def test_browser_operations_stay_on_one_owned_event_loop(adapter):
    caller_thread = threading.get_ident()
    for _ in range(3):
        assert adapter.call("filmcraft_inspect", {})["ok"]
    assert len(set(adapter.browser.threads)) == 1
    assert adapter.browser.threads[0] != caller_thread


def test_wait_timeout_retains_single_flight_until_original_operation_settles():
    browser = FakeBrowser(blocked={"rename_item"})
    instance = FilmCraftAdapter(browser, wait_timeout=0.03)
    try:
        result = instance.call("filmcraft_rename_item", {"item": 1, "name": "Original"})
        assert result["code"] == "TIMEOUT"
        assert browser.entered.is_set()
        blocked = instance.call("filmcraft_rename_item", {"item": 1, "name": "Must not execute"})
        assert blocked["code"] in {"BUSY", "UNCERTAIN"}
        pending = instance.call("filmcraft_reconcile", {})
        assert pending["result"]["settled"] is False
        browser.release.set()
        wait_until(lambda: instance._receipt["settled"])
        settled = instance.call("filmcraft_reconcile", {})
        assert settled["ok"] is True
        assert settled["transport_receipt"]["operation"] == "rename_item"
        assert settled["transport_receipt"]["result"]["ok"] is True
        assert [op for op, _ in browser.calls].count("rename_item") == 1
    finally:
        browser.release.set()
        instance.close()


def test_reconcile_timeout_does_not_release_gate_while_original_reconcile_still_runs():
    browser = FakeBrowser(blocked={"reconcile"})
    instance = FilmCraftAdapter(browser, wait_timeout=0.03)
    try:
        result = instance.call("filmcraft_reconcile", {})
        assert result["ok"] is False
        assert browser.entered.is_set()
        blocked = instance.call("filmcraft_rename_item", {"item": 1, "name": "Must not overlap"})
        assert blocked["ok"] is False
        assert blocked["code"] in {"BUSY", "UNCERTAIN"}
        assert [operation for operation, _ in browser.calls] == ["reconcile"]
    finally:
        browser.release.set()
        instance.close()


class TimedOutMutationBrowser(FakeBrowser):
    async def call(self, operation, params):
        result = await super().call(operation, params)
        if operation == "rename_item":
            return {"ok": False, "code": "TIMEOUT", "error": "host operation may still apply"}
        return result


def test_old_reconcile_waiter_cannot_clear_newer_mutation_uncertainty(monkeypatch):
    browser = TimedOutMutationBrowser()
    instance = FilmCraftAdapter(browser)
    original_submit = instance._submit
    result_available = threading.Event()
    release_waiter = threading.Event()
    first = True

    class DelayedResult:
        """Expose the real completion callback before the original waiter resumes."""

        def __init__(self, future):
            self.future = future

        def add_done_callback(self, callback):
            self.future.add_done_callback(callback)

        def result(self, timeout=None):
            result = self.future.result(timeout=timeout)
            result_available.set()
            assert release_waiter.wait(5)
            return result

        def done(self):
            return self.future.done()

    def delayed_first_submit(coroutine):
        nonlocal first
        future = original_submit(coroutine)
        if first:
            first = False
            return DelayedResult(future)
        return future

    monkeypatch.setattr(instance, "_submit", delayed_first_submit)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as worker:
        old_reconciliation = worker.submit(instance.call, "filmcraft_reconcile", {})
        try:
            assert result_available.wait(3)
            wait_until(lambda: not instance._gate.locked())
            result = instance.call("filmcraft_rename_item", {"item": 1, "name": "New uncertain edit"})
            assert result["code"] == "TIMEOUT"
            wait_until(lambda: instance._receipt["settled"])
            newer_receipt = instance._receipt
            assert newer_receipt["uncertain"] is True
            release_waiter.set()
            assert old_reconciliation.result(timeout=3)["ok"] is True
            assert instance._receipt is newer_receipt
            assert newer_receipt["uncertain"] is True
        finally:
            release_waiter.set()
            old_reconciliation.result(timeout=3)
            instance.close()


def test_retained_reconcile_result_keeps_original_receipt_identity_across_retry():
    browser = TimedOutMutationBrowser(blocked={"reconcile"})
    instance = FilmCraftAdapter(browser, wait_timeout=0.03)
    try:
        old = instance.call("filmcraft_reconcile", {})
        assert old["code"] == "TIMEOUT"
        browser.release.set()
        wait_until(lambda: not instance._gate.locked())
        mutation = instance.call("filmcraft_rename_item", {"item": 1, "name": "Newer uncertain edit"})
        assert mutation["code"] == "TIMEOUT"
        wait_until(lambda: instance._receipt["settled"])
        newer_receipt = instance._receipt
        assert newer_receipt["uncertain"] is True
        instance.call("filmcraft_reconcile", {})
        reconciliations = [operation for operation, _ in browser.calls].count("reconcile")
        # Either retain this uncertainty while delivering the old receipt, or
        # perform a fresh SDK reconciliation. An old cached success cannot
        # establish the outcome of a mutation that had not yet been dispatched.
        assert newer_receipt["uncertain"] is True or reconciliations >= 2
    finally:
        browser.release.set()
        instance.close()


def test_cancellation_before_dispatch_does_not_later_execute_or_rewrite_previous_receipt():
    async def scenario():
        browser = FakeBrowser()
        instance = FilmCraftAdapter(browser)
        assert instance.call("filmcraft_inspect", {})["ok"]
        wait_until(lambda: instance._receipt["settled"])
        previous = dict(instance._receipt)
        browser.calls.clear()
        blocker_started = threading.Event()
        release_worker = threading.Event()
        loop = asyncio.get_running_loop()
        loop.set_default_executor(concurrent.futures.ThreadPoolExecutor(max_workers=1))

        def occupy_worker():
            blocker_started.set()
            assert release_worker.wait(5)

        occupied = loop.run_in_executor(None, occupy_worker)
        try:
            while not blocker_started.is_set():
                await asyncio.sleep(0.001)
            request = asyncio.create_task(
                instance.call_async("filmcraft_rename_item", {"item": 1, "name": "Cancelled before dispatch"})
            )
            # Give call_async and its to_thread submission a turn while the only
            # worker is demonstrably unavailable. No browser call can start.
            for _ in range(5):
                await asyncio.sleep(0)
            request.cancel()
            with pytest.raises(asyncio.CancelledError):
                await request
            assert instance._receipt == previous
        finally:
            release_worker.set()
            await occupied
            # A sentinel drains any older queued worker task deterministically.
            await loop.run_in_executor(None, lambda: None)
            await asyncio.sleep(0.01)
            instance.close()
        assert browser.calls == []

    asyncio.run(scenario())


class FakePipe:
    def __init__(self, *, result=None, error=None):
        self.result = result
        self.error = error
        self.requests = []

    async def evaluate(self, expression, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return self.result


class OwnedPage:
    url = FakeBrowser.origin + "/index.html"

    def is_closed(self):
        return False

    async def evaluate(self, *args):
        raise AssertionError("must not dynamically acquire a replacement document pipe")


def owned_session(*, result=None):
    session = BrowserSession("unused-pinned-runtime.zip")
    session.origin = FakeBrowser.origin
    session.page = OwnedPage()
    session._pipe = FakePipe(result=result)
    return session


def test_reconcile_after_revocation_uses_original_handle_without_reacquiring_authority():
    receipt = {"settled": True, "uncertain": False, "ok": False, "code": "SESSION"}
    session = owned_session(result={"ok": True, "result": receipt})
    session.revoked = True
    assert asyncio.run(session.call("reconcile", {}))["result"] == receipt
    assert session._pipe.requests == [{"operation": "reconcile", "params": {}}]
    with pytest.raises(BrowserError) as failure:
        asyncio.run(session.call("rename_item", {"item": 1, "name": "Forbidden"}))
    assert failure.value.code == "SESSION"
    assert len(session._pipe.requests) == 1


def test_destroyed_original_realm_is_indeterminate_and_never_uses_new_document():
    session = owned_session()
    session._pipe.error = RuntimeError("Execution context was destroyed")
    with pytest.raises(BrowserError) as failure:
        asyncio.run(session.call("reconcile", {}))
    assert failure.value.code == "INDETERMINATE"
    assert session.revoked is True
    assert len(session._pipe.requests) == 1


def test_artifact_store_copies_bytes_and_enforces_per_artifact_bound(monkeypatch):
    monkeypatch.setattr(browser_module, "MAX_ARTIFACT", 4)
    session = owned_session()
    original = bytearray(b"abcd")
    stored = session._store(original, "binary")
    original[0] = 0
    assert session._artifacts[stored["artifact"]] == b"abcd"
    with pytest.raises(BrowserError) as failure:
        session._store(b"abcde", "binary")
    assert failure.value.code == "LIMIT"


def test_oversized_encoded_artifact_is_refused_before_base64_allocation(monkeypatch):
    monkeypatch.setattr(browser_module, "MAX_ARTIFACT", 3)
    encoded = base64.b64encode(b"1234").decode()

    def must_not_decode(*args, **kwargs):
        raise AssertionError("oversized encoded artifact reached decoder")

    monkeypatch.setattr(browser_module.base64, "b64decode", must_not_decode)
    with pytest.raises(BrowserError) as failure:
        owned_session()._decode({"$bytes": encoded})
    assert failure.value.code == "LIMIT"


def test_full_artifact_budget_rejects_save_before_host_mutation():
    session = owned_session(result={"ok": True, "result": {"path": "/dcc/test/native.fcproj"}})
    session._artifact_total = 128 * 1024 * 1024
    with pytest.raises(BrowserError) as failure:
        asyncio.run(session.call("save_project", {"name": "native"}))
    assert failure.value.code == "LIMIT"
    assert session._pipe.requests == []


def test_cached_artifact_read_is_bounded_and_survives_document_revocation():
    session = owned_session()
    ref = session._store(b"abcdef", "binary")
    session.revoked = True
    result = asyncio.run(session.call("read_artifact", {"artifact": ref["artifact"], "offset": 2, "size": 2}))
    assert base64.b64decode(result["result"]["data"]) == b"cd"
    assert result["result"]["next_offset"] == 4
    assert result["result"]["eof"] is False
    assert session._pipe.requests == []


def test_cleanup_continues_after_context_close_failure_and_releases_cached_artifacts():
    events = []

    class Context:
        async def close(self):
            events.append("context")
            raise RuntimeError("context already disconnected")

    class Browser:
        async def close(self):
            events.append("browser")

    class Playwright:
        async def stop(self):
            events.append("playwright")

    class Server:
        def shutdown(self):
            events.append("server_shutdown")

        def server_close(self):
            events.append("server_close")

    class Thread:
        def join(self, timeout):
            events.append("thread_join")

    session = owned_session()
    session._context, session._browser, session._pw = Context(), Browser(), Playwright()
    session._server, session._thread = Server(), Thread()
    session._store(b"private cached content", "binary")
    try:
        asyncio.run(session.close())
    except RuntimeError:
        # Reporting the first cleanup failure is fine, but every later resource
        # must still be attempted and no cached media may remain referenced.
        pass
    assert events == ["context", "browser", "playwright", "server_shutdown", "server_close", "thread_join"]
    assert session._artifacts == {}
    assert session._artifact_total == 0


def test_actual_js_bridge_refuses_pending_or_failed_export_readback():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required to evaluate the actual JavaScript bridge")
    bridge = Path(__file__).resolve().parents[2] / "src" / "mcp-bridge.js"
    script = r"""
import { readFile } from 'node:fs/promises';
let source = await readFile(process.argv[1], 'utf8');
source = source.replace("import { FilmCraftClient, BridgeError } from './index.js';", '');
let record = { id: 7, finished: false }, reads = 0;
const path = '/dcc/owned-session-123456/export.mp4';
const sdk = {
  sessionId: 'owned-session-123456',
  exportVideo: async () => ({ path, job: 7 }),
  jobs: async () => [record],
  readExport: async () => { reads++; return new Uint8Array([1, 2, 3]); },
};
class BridgeError extends Error {
  constructor(code, message) { super(message); this.code = code; }
}
globalThis.window = {};
globalThis.location = { origin: 'http://127.0.0.1:49152' };
globalThis.document = {};
await new Function('FilmCraftClient', 'BridgeError', `return (async () => {${source}})()`)(
  { connect: async () => sdk }, BridgeError,
);
const call = (operation, params = {}) => window.__dccFilmcraftPipe({ operation, params });
const queued = await call('export_media', { name: 'export', sequence: 1, format: 'h264' });
const pending = await call('read_export', { path });
record = { id: 7, finished: true, result: { error: 'cancelled' } };
const cancelled = await call('read_export', { path });
const readsBeforeSuccess = reads;
record = { id: 7, finished: true, result: {} };
const completed = await call('read_export', { path });
console.log(JSON.stringify({ queued, pending, cancelled, completed, readsBeforeSuccess, reads }));
"""
    completed = subprocess.run(
        [node, "--input-type=module", "-e", script, str(bridge)],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    result = json.loads(completed.stdout)
    assert result["queued"]["ok"] is True
    assert result["pending"]["code"] == "BUSY"
    assert result["cancelled"]["code"] == "EXPORT"
    assert result["readsBeforeSuccess"] == 0
    assert result["completed"]["ok"] is True
    assert result["reads"] == 1


def test_cached_artifact_read_preserves_uncertain_host_receipt():
    browser = BrowserSession("unused.zip")
    meta = browser._store(b"recoverable saved output", "binary")
    browser.revoked = True
    instance = FilmCraftAdapter(browser)
    original = {"request_id": "original", "operation": "rename_item", "settled": True, "uncertain": True}
    instance._receipt = original
    try:
        result = instance.call("filmcraft_read_artifact", {"artifact": meta["artifact"], "offset": 0, "size": 64})
        assert base64.b64decode(result["result"]["data"]) == b"recoverable saved output"
        assert instance._receipt is original
        assert original["uncertain"] is True
    finally:
        instance.close()
