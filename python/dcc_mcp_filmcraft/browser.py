"""Owned browser session over Playwright's private pipe; static HTTP has no control routes."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import importlib.resources
import io
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZipFile

RUNTIME_SHA256 = "48d4f48728fa6b5c028612a4b7f59a5832ff38d430c6a7bd417a2c77d75ae4f9"
RUNTIME_URL = "https://github.com/storytold/filmcraft/releases/download/v0.7.2/filmcraft-web-0.7.2.zip"
MAX_ARCHIVE = 20 * 1024 * 1024
MAX_ARTIFACT = 32 * 1024 * 1024


class BrowserError(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def asset(name):
    packaged = importlib.resources.files("dcc_mcp_filmcraft").joinpath("assets", name)
    if packaged.is_file():
        return packaged.read_bytes()
    return (Path(__file__).resolve().parents[2] / "src" / name).read_bytes()


def runtime_files(archive):
    """Hash before unpacking; never extract archive paths onto the filesystem."""
    path = Path(archive)
    if path.stat().st_size > MAX_ARCHIVE:
        raise BrowserError("RUNTIME", "runtime ZIP exceeds the pinned distribution limit")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != RUNTIME_SHA256:
        raise BrowserError("RUNTIME", "official FilmCraft v0.7.2 runtime ZIP SHA-256 mismatch")
    files = {}
    with ZipFile(io.BytesIO(data)) as z:
        for entry in z.infolist():
            parts = Path(entry.filename).parts
            if entry.is_dir():
                continue
            if len(parts) != 2 or parts[0] != "filmcraft-web-0.7.2" or entry.file_size > 128 * 1024 * 1024:
                raise BrowserError("RUNTIME", "unexpected pinned runtime archive layout")
            files["/" + parts[1]] = z.read(entry)
    files["/dcc/index.js"] = asset("index.js")
    files["/dcc/mcp-bridge.js"] = asset("mcp-bridge.js")
    return files


class BrowserSession:
    """Owns exactly one rendered editor, never attaches to arbitrary URLs or CDP ports."""

    def __init__(self, archive, *, headless=False, executable=None, evidence_dir=None):
        self.archive = archive
        self.headless = headless
        self.executable = executable
        self.evidence_dir = Path(evidence_dir) if evidence_dir else None
        self.origin = None
        self.revoked = False
        self._artifacts = {}
        self._artifact_total = 0
        self._server = self._thread = self._pw = self._browser = self._context = self.page = None
        self._temp = None
        self._pipe = None

    async def start(self):
        from playwright.async_api import async_playwright

        files = runtime_files(self.archive)
        session = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                path = urlsplit(self.path).path
                if self.headers.get("Host") != urlsplit(session.origin).netloc or path not in files:
                    self.send_error(404)
                    return
                body = files[path]
                suffix = Path(path).suffix
                content_type = {
                    ".js": "text/javascript",
                    ".html": "text/html",
                    ".wasm": "application/wasm",
                    ".png": "image/png",
                }.get(suffix, "application/octet-stream")
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cross-Origin-Opener-Policy", "same-origin")
                self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *args):
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.origin = f"http://127.0.0.1:{self._server.server_port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        try:
            self._pw = await async_playwright().start()
            options = {
                "headless": self.headless,
                "args": ["--enable-unsafe-swiftshader", "--use-gl=angle", "--use-angle=swiftshader"],
            }
            if self.executable:
                options["executable_path"] = self.executable
            self._browser = await self._pw.chromium.launch(**options)
            context_options = {"viewport": {"width": 1280, "height": 800}}
            if self.evidence_dir:
                self.evidence_dir.mkdir(parents=True, exist_ok=True)
                context_options["record_video_dir"] = str(self.evidence_dir / "recording")
            self._context = await self._browser.new_context(**context_options)

            async def only_owned_origin(route):
                if route.request.url.startswith(self.origin + "/"):
                    await route.continue_()
                else:
                    await route.abort("blockedbyclient")

            await self._context.route("**/*", only_owned_origin)
            self.page = await self._context.new_page()
            await self.page.goto(self.origin + "/index.html?empty&norecover&fresh&cpu&webgl")
            await self.page.wait_for_function(
                "window.filmcraft && typeof window.filmcraft.commands === 'function'", timeout=120000
            )
            await self.page.evaluate("() => import('/dcc/mcp-bridge.js')")
            await self.page.wait_for_function("typeof window.__dccFilmcraftPipe === 'function'", timeout=15000)
            self._pipe = await self.page.evaluate_handle("() => window.__dccFilmcraftPipe")
            self.page.on("framenavigated", self._navigation)
            self.page.on("crash", lambda *_: self._revoke())
            self.page.on("close", lambda *_: self._revoke())
            return self
        except BaseException:
            await self.close()
            raise

    def _navigation(self, frame):
        if self.page and frame == self.page.main_frame:
            self._revoke()

    def _revoke(self):
        self.revoked = True

    def _guard(self):
        if self.revoked or not self.page or self.page.is_closed():
            raise BrowserError("SESSION", "original browser document lost; execution is permanently revoked")
        if urlsplit(self.page.url)._replace(path="", query="", fragment="").geturl() != self.origin:
            self._revoke()
            raise BrowserError("SESSION", "editor origin changed")

    def _store(self, data, kind):
        if len(data) > MAX_ARTIFACT:
            raise BrowserError("LIMIT", "artifact exceeds 32 MiB")
        key = hashlib.sha256(data).hexdigest()
        if key not in self._artifacts:
            if self._artifact_total + len(data) > 128 * 1024 * 1024:
                raise BrowserError("LIMIT", "session artifact budget exceeds 128 MiB")
            self._artifacts[key] = bytes(data)
            self._artifact_total += len(data)
        return {"artifact": key, "sha256": key, "size": len(data), "kind": kind}

    def _decode(self, value, kind="binary"):
        if isinstance(value, dict):
            if set(value) == {"$bytes"}:
                encoded = value["$bytes"]
                if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_ARTIFACT + 2) // 3):
                    raise BrowserError("LIMIT", "invalid or oversized artifact encoding")
                return self._store(base64.b64decode(encoded, validate=True), kind)
            return {k: self._decode(v, "fcproj" if k == "bytes" else kind) for k, v in value.items()}
        if isinstance(value, list):
            return [self._decode(v, kind) for v in value]
        return value

    async def call(self, operation, params):
        if operation == "read_artifact":
            data = self._artifacts.get(params["artifact"])
            if data is None:
                raise BrowserError("SESSION", "artifact is not owned by this session")
            offset, size = params["offset"], params["size"]
            if offset > len(data):
                raise BrowserError("INVALID_ARGUMENT", "offset exceeds artifact size")
            chunk = data[offset : offset + size]
            return {
                "ok": True,
                "result": {
                    "data": base64.b64encode(chunk).decode(),
                    "offset": offset,
                    "next_offset": offset + len(chunk),
                    "eof": offset + len(chunk) == len(data),
                    "size": len(data),
                },
            }
        if operation != "reconcile":
            self._guard()
        if operation in {"save_project", "read_export", "capture_view"}:
            allowance = 16 * 1024 * 1024 if operation == "save_project" else MAX_ARTIFACT
            if self._artifact_total + allowance > 128 * 1024 * 1024:
                raise BrowserError("LIMIT", "insufficient artifact capacity; operation was not dispatched")
        if operation == "capture_view":
            data = await self.page.screenshot(type="png")
            self._guard()
            return {"ok": True, "result": self._store(data, "png")}
        if operation == "import_media":
            try:
                raw = base64.b64decode(params["data"], validate=True)
            except ValueError as exc:
                raise BrowserError("INVALID_ARGUMENT", "media data must be valid base64") from exc
            if not 0 < len(raw) <= 16 * 1024 * 1024:
                raise BrowserError("LIMIT", "media size must be 1 byte through 16 MiB")
        try:
            result = await self._pipe.evaluate(
                "(pipe, request) => pipe(request)", {"operation": operation, "params": params}
            )
        except Exception as exc:
            self._revoke()
            raise BrowserError(
                "INDETERMINATE", "original browser realm is unavailable; outcome cannot be established"
            ) from exc
        if operation != "reconcile":
            self._guard()
        if result.get("code") == "SESSION":
            self._revoke()
        return self._decode(result)

    async def close(self):
        """Explicit process shutdown. Pending host effects are never claimed rolled back."""
        self._revoke()
        errors = []
        for attribute in ("_context", "_browser", "_pw"):
            resource = getattr(self, attribute)
            setattr(self, attribute, None)
            if resource:
                try:
                    method = resource.stop if attribute == "_pw" else resource.close
                    await asyncio.wait_for(method(), timeout=5)
                except BaseException as exc:
                    errors.append(str(exc))
        if self._server:
            server, self._server = self._server, None
            try:
                await asyncio.to_thread(server.shutdown)
            finally:
                server.server_close()
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
        if self._temp:
            self._temp.cleanup()
            self._temp = None
        self._artifacts.clear()
        self._artifact_total = 0
        return {"closed": True, "cleanup_errors": errors}
