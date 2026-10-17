"""Bounded Core registry/dispatcher plus one private host-session event loop."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import threading
import uuid

from dcc_mcp_core import ToolDispatcher, ToolRegistry
from jsonschema import Draft202012Validator, ValidationError

from .browser import BrowserSession
from .catalog import tools_for_mode


class FilmCraftAdapter:
    """The adapter entrypoint. No Core HTTP gateway or generic execution tools are started."""

    def __init__(self, browser, *, wait_timeout=75):
        self.browser = browser
        self.session = browser
        self.mode = getattr(browser, "mode", "browser")
        self.skill_name = "filmcraft-browser" if self.mode == "browser" else "filmcraft-native"
        self.tool_specs = tools_for_mode(self.mode)
        self.wait_timeout = wait_timeout
        self.registry = ToolRegistry()
        self.dispatcher = ToolDispatcher(self.registry)
        self.dispatcher.skip_empty_schema_validation = False
        self._specs = {spec["name"]: spec for spec in self.tool_specs}
        self._validators = {spec["name"]: Draft202012Validator(spec["input_schema"]) for spec in self.tool_specs}
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="filmcraft-" + self.mode, daemon=True)
        self._gate = threading.Lock()
        self._receipt_lock = threading.Lock()
        self._receipt = None
        self._local = threading.local()
        self._future = None
        self._reconcile_future = None
        self._reconcile_original = None
        self._reconcile_lock = threading.Lock()
        self._closed = False
        self._thread.start()
        for spec in self.tool_specs:
            name = spec["name"]
            self.registry.register(
                name,
                description=spec["description"],
                dcc="filmcraft",
                skill_name=self.skill_name,
                input_schema=json.dumps(spec["input_schema"]),
                output_schema=json.dumps({"type": "object"}),
                execution="sync",
                thread_affinity="any",
                timeout_hint_secs=90,
            )
            self.dispatcher.register_handler(name, self._handler(spec["operation"]))

    @classmethod
    def launch(cls, archive, **kwargs):
        adapter = cls(BrowserSession(archive, **kwargs))
        try:
            adapter._submit(adapter.browser.start()).result(timeout=150)
            return adapter
        except BaseException:
            adapter.close()
            raise

    def _submit(self, coroutine):
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop)

    @classmethod
    def launch_native(cls, executable, *, workspace, evidence_dir=None):
        from .native import NativeSession

        adapter = cls(NativeSession(executable, workspace=workspace, evidence_dir=evidence_dir))
        try:
            adapter._submit(adapter.session.start()).result(timeout=150)
            return adapter
        except BaseException:
            adapter.close()
            raise

    def _handler(self, operation):
        return lambda params: self._execute(operation, params)

    def _reconcile(self):
        with self._receipt_lock:
            original_receipt = self._receipt
            receipt = dict(original_receipt) if original_receipt else None
        if receipt and not receipt["settled"]:
            return {"ok": True, "result": {**receipt, "uncertain": True}}
        future = self._reconcile_future
        if future is None:
            if not self._gate.acquire(blocking=False):
                return {"ok": False, "code": "BUSY", "error": "operation settlement is in progress"}
            future = self._submit(self.browser.call("reconcile", {}))
            self._reconcile_future = future
            self._reconcile_original = original_receipt
            future.add_done_callback(lambda _: self._gate.release())
        original_receipt = self._reconcile_original
        receipt = dict(original_receipt) if original_receipt else None
        try:
            result = future.result(timeout=self.wait_timeout)
            self._reconcile_future = None
            self._reconcile_original = None
            detail = result.get("result", {})
            if result.get("ok") and detail.get("settled") and not detail.get("uncertain"):
                with self._receipt_lock:
                    if self._receipt is original_receipt and original_receipt:
                        original_receipt["uncertain"] = False
            return {**result, "transport_receipt": receipt}
        except concurrent.futures.TimeoutError:
            return {
                "ok": False,
                "code": "TIMEOUT",
                "error": "original reconciliation is still active",
                "transport_receipt": receipt,
            }
        except Exception as exc:
            self._reconcile_future = None
            self._reconcile_original = None
            return {
                "ok": False,
                "code": getattr(exc, "code", "HOST"),
                "error": str(exc),
                "transport_receipt": receipt,
            }

    def _execute(self, operation, params):
        if self._closed:
            return {"ok": False, "code": "CLOSED", "error": "adapter has closed"}
        invocation = getattr(self._local, "invocation", None)
        if invocation:
            with invocation["lock"]:
                if invocation["cancelled"]:
                    return {"ok": False, "code": "CANCELLED", "error": "cancelled before dispatch; not run"}
        if operation == "read_artifact":
            # Cached immutable bytes remain rescuable even after the browser realm
            # is lost. This local read must not replace the original host receipt.
            try:
                return self._submit(self.browser.call(operation, params)).result(timeout=self.wait_timeout)
            except Exception as exc:
                return {"ok": False, "code": getattr(exc, "code", "HOST"), "error": str(exc)}
        if operation == "reconcile":
            if not self._reconcile_lock.acquire(blocking=False):
                return {"ok": False, "code": "BUSY", "error": "a reconciliation waiter is already active"}
            try:
                return self._reconcile()
            finally:
                self._reconcile_lock.release()
        if not self._gate.acquire(blocking=False):
            return {"ok": False, "code": "BUSY", "error": "one operation is active; it was not queued or replayed"}
        invocation = getattr(self._local, "invocation", None)
        invocation_lock = invocation["lock"] if invocation else threading.Lock()
        with invocation_lock:
            if invocation and invocation["cancelled"]:
                self._gate.release()
                return {"ok": False, "code": "CANCELLED", "error": "cancelled before host dispatch; not run"}
        with self._receipt_lock:
            if self._receipt and self._receipt.get("uncertain") and operation != "reconcile":
                self._gate.release()
                return {"ok": False, "code": "UNCERTAIN", "error": "reconcile the original operation before continuing"}
            receipt = {
                "request_id": str(uuid.uuid4()),
                "operation": operation,
                "origin": self.browser.origin,
                "settled": False,
                "uncertain": False,
            }
            self._receipt = receipt
        with invocation_lock:
            if invocation and invocation["cancelled"]:
                with self._receipt_lock:
                    receipt.update(settled=True, result={"ok": False, "code": "CANCELLED", "error": "not dispatched"})
                self._gate.release()
                return receipt["result"]
            if invocation:
                invocation["receipt"] = receipt
            future = self._submit(self.browser.call(operation, params))
            self._future = future

        def settled(done):
            try:
                result = done.result()
            except BaseException as exc:
                result = {"ok": False, "code": getattr(exc, "code", "HOST"), "error": str(exc)}
            with self._receipt_lock:
                receipt.update(settled=True, result=result)
                if result.get("code") in {"TIMEOUT", "CANCELLED", "SESSION", "INDETERMINATE"}:
                    receipt["uncertain"] = True
            self._gate.release()

        future.add_done_callback(settled)
        try:
            return future.result(timeout=self.wait_timeout)
        except concurrent.futures.TimeoutError:
            with self._receipt_lock:
                receipt["uncertain"] = True
            return {
                "ok": False,
                "code": "TIMEOUT",
                "error": "waiting ended; original operation remains active",
                "receipt": dict(receipt),
            }
        except Exception as exc:
            return {"ok": False, "code": getattr(exc, "code", "HOST"), "error": str(exc)}

    def call(self, name, arguments, *, _invocation=None):
        self._local.invocation = _invocation
        if name not in self._specs:
            return {"ok": False, "code": "UNSUPPORTED", "error": "tool is outside the typed FilmCraft allowlist"}
        try:
            self._validators[name].validate(arguments)
            params = json.dumps(arguments, allow_nan=False)
            return self.dispatcher.dispatch(name, params)["output"]
        except (ValueError, TypeError, KeyError, PermissionError, ValidationError) as exc:
            return {"ok": False, "code": "INVALID_ARGUMENT", "error": str(exc)}

    async def call_async(self, name, arguments):
        invocation = {"lock": threading.Lock(), "cancelled": False, "receipt": None}
        task = asyncio.create_task(asyncio.to_thread(self.call, name, arguments, _invocation=invocation))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            with invocation["lock"]:
                invocation["cancelled"] = True
                if invocation["receipt"]:
                    with self._receipt_lock:
                        invocation["receipt"]["uncertain"] = True
            raise

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self._submit(self.browser.close()).result(timeout=20)
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=5)
            if not self._thread.is_alive():
                self._loop.close()
