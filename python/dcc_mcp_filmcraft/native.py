"""Owned, persistent FilmCraft CLI MCP session. No control port or arbitrary host API."""

from __future__ import annotations

import asyncio
import base64
import copy
import hashlib
import json
import os
import stat
import uuid
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

from .browser import BrowserError
from .catalog import TOOLS, tools_for_mode

MAX_MEDIA = 16 * 1024 * 1024
MAX_ARTIFACT = 32 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024
MAX_RPC = 4 * 1024 * 1024
MAX_EXPORT_SECONDS = 60
MAX_EXPORT_FRAMES = 1800
MAX_EXPORT_PIXEL_FRAMES = 500_000_000
MAX_INTENTIONAL_RESTARTS = 8
NATIVE_VERSION = "0.12.0"
NATIVE_VERSIONS = frozenset({"0.7.2", NATIVE_VERSION})
NATIVE_LINUX_CLI_SHA256 = "05982fe44214f6174ffb54166d100e2362cf90811f2480235f3ecbaa0a3a75c2"
NATIVE_PROTOCOLS = frozenset({"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25", "2026-07-28"})
NativeError = BrowserError


def _key(project):
    return (project.get("name"), project.get("root", {}).get("id"), project.get("path"), project.get("revision"))


class NativeSession:
    """One owned native headless process; loss permanently revokes execution.

    ``executable`` and ``workspace`` are trusted launcher configuration, never MCP
    arguments. The upstream CLI is not an OS sandbox. Each session uses a new
    private directory and exposes only virtual handles for owned files. Disk
    files survive close; cached immutable artifacts survive typed disconnect.
    """

    mode = "native-headless"

    def __init__(self, executable, *, workspace, evidence_dir=None):
        self.executable = Path(executable).expanduser().resolve()
        self.workspace = Path(workspace).expanduser().resolve()
        self.evidence_dir = Path(evidence_dir).resolve() if evidence_dir else None
        self.session_id = str(uuid.uuid4())
        self.origin = f"native-stdio://{self.session_id}"
        self.session_dir = self.workspace / self.session_id
        self._virtual_root = f"/dcc/{self.session_id}"
        self.revoked = False
        self._started = False
        self._disconnected = False
        self._busy = False
        self._process = None
        self._original_process = None
        self._stderr_task = None
        self._stderr = bytearray()
        self._directory_identity = None
        self._workspace_identity = None
        self._runtime_identity = None
        self._runtime_fingerprint = None
        self._generation = 1
        self._job_aliases = {}
        self._job_native = {}
        self._archived_jobs = {}
        self._next_job_alias = 1
        self._cleanup_errors = []
        self._rpc_id = 0
        self._commands = set()
        self._project = None
        self._receipt = None
        self._saved = {}
        self._media = {}
        self._exports = {}
        self._reserved = set()
        self._artifacts = {}
        self._artifact_total = 0
        self._media_total = 0
        self._validators = {t["operation"]: Draft202012Validator(t["input_schema"]) for t in TOOLS}
        self._validators.update(
            {t["operation"]: Draft202012Validator(t["input_schema"]) for t in tools_for_mode(self.mode)}
        )
        self.capabilities = {
            "mode": self.mode,
            "gui": False,
            "transport": "owned-private-stdio",
            "supported_operations": [t["operation"] for t in TOOLS if t["operation"] != "capture_view"],
            "unsupported_operations": ["capture_view"],
            "restart_recovery": False,
            "intentional_restart": True,
            "intentional_restart_limit": MAX_INTENTIONAL_RESTARTS,
            "native_child_generation": self._generation,
            "arbitrary_commands": False,
        }

    async def start(self):
        if self._started or self.revoked:
            raise NativeError("SESSION", "a native session cannot be started or reacquired twice")
        self._started = True
        if not self.executable.is_file():
            self.revoked = True
            raise NativeError("RUNTIME", "configured FilmCraft CLI executable is missing")
        self.workspace.mkdir(parents=True, exist_ok=True)
        self._workspace_identity = self._identity(self.workspace.lstat())
        self.session_dir.mkdir(mode=0o700)
        self._directory_identity = self._identity(self.session_dir.lstat())
        home = self.session_dir / "home"
        home.mkdir(mode=0o700)
        try:
            self._runtime_fingerprint = self._fingerprint_executable()
            await self._launch_owned_child()
            return self
        except BaseException:
            try:
                await self.close()
            except BaseException as cleanup:
                self._cleanup_errors.append(f"startup cleanup: {type(cleanup).__name__}: {cleanup}")
            raise

    def _fingerprint_executable(self):
        """Bind an intentional restart to the unchanged trusted executable bytes."""
        descriptor = os.open(self.executable, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(descriptor, "rb") as source:
            before = os.fstat(source.fileno())
            if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= 128 * 1024 * 1024:
                raise NativeError("RUNTIME", "native executable is not a bounded regular file")
            digest = hashlib.sha256()
            count = 0
            while chunk := source.read(1024 * 1024):
                count += len(chunk)
                if count > 128 * 1024 * 1024:
                    raise NativeError("RUNTIME", "native executable grew while being verified")
                digest.update(chunk)
            after = os.fstat(source.fileno())

            def identity(value):
                return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns

            if identity(before) != identity(after) or identity(after) != identity(self.executable.lstat()):
                raise NativeError("RUNTIME", "native executable changed while being verified")
            return identity(after), digest.hexdigest()

    async def _launch_owned_child(self, expected_identity=None):
        """Start only our explicitly owned child, using the existing private directory."""
        self._guard_directory()
        home = self.session_dir / ("home" if self._generation == 1 else f"home-restart-{self._generation}")
        if self._generation > 1:
            home.mkdir(mode=0o700)
        if not stat.S_ISDIR(home.lstat().st_mode):
            raise NativeError("SESSION", "native configuration directory must be an owned directory")
        if self._fingerprint_executable() != self._runtime_fingerprint:
            raise NativeError("RUNTIME", "native executable changed before child startup")
        env = {k: v for k, v in os.environ.items() if k in {"PATH", "SYSTEMROOT", "WINDIR", "LANG", "LC_ALL"}}
        env.update(
            HOME=str(home),
            XDG_CONFIG_HOME=str(home / "config"),
            XDG_DATA_HOME=str(home / "data"),
            XDG_CACHE_HOME=str(home / "cache"),
            XDG_STATE_HOME=str(home / "state"),
            FILMCRAFT_DATA_DIR=str(home / "data"),
            OMP_NUM_THREADS="1",
            RAYON_NUM_THREADS="2",
            TOKIO_WORKER_THREADS="2",
        )
        self._process = await asyncio.create_subprocess_exec(
            str(self.executable),
            "mcp",
            "--data-dir",
            str(home / "data"),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.session_dir),
            env=env,
            limit=MAX_RPC,
        )
        self._original_process = self._process
        self._rpc_id, self._commands = 0, set()
        self._stderr_task = asyncio.create_task(self._drain_stderr(self._original_process))
        try:
            initialized = await asyncio.wait_for(
                self._rpc(
                    "initialize",
                    {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "dcc-mcp-filmcraft-native", "version": "0.1.0"},
                    },
                ),
                timeout=20,
            )
            info = self._validate_initialization(initialized)
            identity = (info["name"], info["version"], initialized["protocolVersion"])
            if expected_identity is not None and identity != expected_identity:
                raise NativeError("RUNTIME", "restarted native runtime identity differs from the original child")
            if self._fingerprint_executable() != self._runtime_fingerprint:
                raise NativeError("RUNTIME", "native executable changed during startup")
            self._process.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
            await self._process.stdin.drain()
            catalog = await asyncio.wait_for(self._tool("command_list", {}), timeout=20)
            if not isinstance(catalog, list):
                raise NativeError("PROTOCOL", "native command discovery did not return an array")
            self._commands = {row.get("id") for row in catalog if isinstance(row, dict)}
            self._project = _key(await asyncio.wait_for(self._command("project.inspect"), timeout=20))
            self.capabilities["runtime_version"] = info["version"]
            self.capabilities["intentional_restart"] = info["version"] == NATIVE_VERSION
            self.capabilities["mcp_protocol"] = initialized["protocolVersion"]
            self.capabilities["engine_command_count"] = len(self._commands)
            self._runtime_identity = identity
            self.capabilities["native_child_generation"] = self._generation
        except BaseException:
            self.revoked = True
            raise

    @staticmethod
    def _validate_initialization(initialized):
        """Validate negotiated identity before discovering or mutating a document.

        Version identity is a compatibility check, not binary provenance. The
        configured executable remains trusted operator input; the opt-in fetch
        helper separately verifies the published archive and extracted CLI.
        """
        if (
            not isinstance(initialized, dict)
            or not isinstance(initialized.get("protocolVersion"), str)
            or initialized["protocolVersion"] not in NATIVE_PROTOCOLS
        ):
            raise NativeError("PROTOCOL", "unsupported FilmCraft MCP protocol")
        info = initialized.get("serverInfo")
        if (
            not isinstance(info, dict)
            or info.get("name") != "filmcraft"
            or not isinstance(info.get("version"), str)
            or info.get("version") not in NATIVE_VERSIONS
        ):
            raise NativeError("RUNTIME", "expected FilmCraft MCP version 0.7.2 or 0.12.0")
        capabilities = initialized.get("capabilities")
        if not isinstance(capabilities, dict) or not isinstance(capabilities.get("tools"), dict):
            raise NativeError("PROTOCOL", "FilmCraft MCP tools capability is missing")
        return info

    @staticmethod
    def _identity(st):
        return (st.st_dev, st.st_ino)

    async def _drain_stderr(self, process):
        while True:
            chunk = await process.stderr.read(8192)
            if not chunk:
                return
            self._stderr.extend(chunk)
            del self._stderr[:-65536]

    def _guard_directory(self):
        try:
            workspace = self.workspace.lstat()
            current = self.session_dir.lstat()
        except OSError as exc:
            self.revoked = True
            raise NativeError("SESSION", "owned native directory is unavailable") from exc
        if (
            not stat.S_ISDIR(workspace.st_mode)
            or self._identity(workspace) != self._workspace_identity
            or not stat.S_ISDIR(current.st_mode)
            or self._identity(current) != self._directory_identity
        ):
            self.revoked = True
            raise NativeError("SESSION", "owned native directory identity changed")

    def _native_job_id(self, alias):
        generation, native = self._job_native.get(alias, (1, alias))
        return native if generation == self._generation else None

    def _job_alias(self, native):
        if type(native) is not int or not 1 <= native <= 9007199254740991:
            self.revoked = True
            raise NativeError("INDETERMINATE", "native job has no bounded identity")
        key = (self._generation, native)
        if key not in self._job_aliases:
            alias = native if self._generation == 1 else self._next_job_alias
            if alias > 9007199254740991:
                self.revoked = True
                raise NativeError("INDETERMINATE", "native job identity capacity exhausted")
            self._job_aliases[key] = alias
            self._job_native[alias] = key
            self._next_job_alias = max(self._next_job_alias, alias + 1)
        return self._job_aliases[key]

    def _map_jobs(self, jobs):
        if not isinstance(jobs, list) or any(not isinstance(row, dict) for row in jobs):
            self.revoked = True
            raise NativeError("INDETERMINATE", "native jobs response has an invalid shape")
        result, seen = [], set()
        for row in jobs:
            alias = self._job_alias(row.get("id"))
            if alias in seen:
                self.revoked = True
                raise NativeError("INDETERMINATE", "native jobs response repeats an identity")
            seen.add(alias)
            value = copy.deepcopy(row)
            value["id"] = alias
            result.append(value)
        return result

    def _verify_saved_media(self, saved):
        name, digest = saved
        if hashlib.sha256(self._read_owned(name, MAX_MEDIA)).hexdigest() != digest:
            raise NativeError("DOCUMENT", "saved project changed outside this client")
        for media, expected in self._media.items():
            if hashlib.sha256(self._read_owned(media, MAX_MEDIA)).hexdigest() != expected:
                raise NativeError("DOCUMENT", "imported media changed outside this client")

    async def _restart_and_reopen(self, saved):
        """Intentional transition from a healthy child, never lost-process recovery."""
        if self._generation > MAX_INTENTIONAL_RESTARTS:
            raise NativeError("LIMIT", "intentional native restart budget exhausted")
        if self._runtime_identity is None or self._runtime_fingerprint is None:
            self.revoked = True
            raise NativeError("SESSION", "original native runtime identity was not established")
        if self._runtime_identity[1] != NATIVE_VERSION:
            raise NativeError("UNSUPPORTED", "intentional native restart is reviewed only for FilmCraft 0.12.0")
        jobs = self._map_jobs(await self._command("jobs.list"))
        by_id = {row["id"]: row for row in jobs}
        for _, alias in self._exports.values():
            if self._native_job_id(alias) is None:
                continue
            row = by_id.get(alias)
            if row is None:
                self.revoked = True
                raise NativeError("INDETERMINATE", "owned export terminal state cannot be established")
            if row.get("finished") is not True:
                raise NativeError("BUSY", "intentional restart requires every owned export to be terminal")
        try:
            self._verify_saved_media(saved)
            if self._fingerprint_executable() != self._runtime_fingerprint:
                raise NativeError("RUNTIME", "native executable differs from the original child")
            self._guard()
            identity = self._runtime_identity
            self._archived_jobs.update(
                {
                    alias: copy.deepcopy(by_id[alias])
                    for _, alias in self._exports.values()
                    if self._native_job_id(alias) is not None
                }
            )
            stopped = await self._stop_owned_child()
            if not stopped["closed"] or stopped["cleanup_errors"]:
                raise NativeError("INDETERMINATE", "old owned native child did not close cleanly")
            old_exit = self._original_process.returncode
            self._guard_directory()
            self._verify_saved_media(saved)
            self._generation += 1
            await self._launch_owned_child(expected_identity=identity)
            current = await self._check_project()
            if current.get("dirty") is not False or current.get("root", {}).get("children") != []:
                raise NativeError("DOCUMENT", "new owned child must start with an empty clean project")
            self._verify_saved_media(saved)
            await self._mutate("file.open", {"path": str(self.session_dir / saved[0])})
            project = await self._command("project.inspect")
            if project.get("path") != str(self.session_dir / saved[0]) or project.get("dirty") is not False:
                raise NativeError("DOCUMENT", "new owned child did not reopen the verified clean save")
            self._verify_saved_media(saved)
            return {
                **project,
                "intentional_restart": {
                    "completed": True,
                    "old_child_exited": True,
                    "old_child_exit_code": old_exit,
                    "generation": self._generation,
                    "runtime_identity_unchanged": True,
                },
            }
        except BaseException:
            self.revoked = True
            try:
                await self._stop_owned_child()
            except BaseException as cleanup:
                self._cleanup_errors.append(f"restart cleanup: {type(cleanup).__name__}: {cleanup}")
            raise

    def _guard(self):
        if self.revoked:
            raise NativeError("SESSION", "original native process lost; execution is permanently revoked")
        if self._disconnected:
            raise NativeError("CLOSED", "native client disconnected; immutable artifacts remain readable")
        if not self._process or self._process is not self._original_process or self._process.returncode is not None:
            self.revoked = True
            raise NativeError("SESSION", "original native process lost; execution is permanently revoked")
        self._guard_directory()

    async def _rpc(self, method, params):
        self._guard()
        self._rpc_id += 1
        request_id = self._rpc_id
        request = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        raw = json.dumps(request, allow_nan=False, separators=(",", ":")).encode() + b"\n"
        if len(raw) > MAX_RPC:
            raise NativeError("LIMIT", "native protocol request exceeds its limit")
        try:
            self._process.stdin.write(raw)
            await self._process.stdin.drain()
            for _ in range(1024):
                line = await self._process.stdout.readline()
                if not line:
                    raise EOFError("native stdout closed")
                response = json.loads(line)
                if not isinstance(response, dict) or response.get("jsonrpc") != "2.0":
                    raise ValueError("invalid JSON-RPC envelope")
                if "id" not in response and "method" in response:
                    continue
                if type(response.get("id")) is not int or response["id"] != request_id:
                    raise ValueError("native response identity mismatch")
                self._guard()
                if "error" in response:
                    raise NativeError("HOST", str(response["error"])[:2000])
                if "result" not in response:
                    raise ValueError("native response has no result")
                return response["result"]
            raise ValueError("excessive native notifications")
        except NativeError:
            raise
        except (OSError, EOFError, ValueError, asyncio.IncompleteReadError) as exc:
            self.revoked = True
            raise NativeError("INDETERMINATE", "original native transport lost; operation was not replayed") from exc

    async def _tool(self, name, arguments):
        result = await self._rpc("tools/call", {"name": name, "arguments": arguments})
        try:
            if not isinstance(result, dict) or not isinstance(result.get("content"), list):
                raise ValueError("invalid native tool envelope")
            content = result["content"]
            if any(not isinstance(c, dict) for c in content):
                raise ValueError("invalid native content block")
            text = "\n".join(c.get("text", "") for c in content if c.get("type") == "text")
        except (TypeError, ValueError) as exc:
            self.revoked = True
            raise NativeError("INDETERMINATE", "invalid native tool response; execution revoked") from exc
        if result.get("isError"):
            raise NativeError("HOST", text[:2000])
        try:
            return json.loads(text)
        except (TypeError, ValueError) as exc:
            self.revoked = True
            raise NativeError("INDETERMINATE", "native tool did not return JSON text; execution revoked") from exc

    async def _command(self, command, params=None):
        if command not in self._commands:
            raise NativeError("UNSUPPORTED", f"native command missing: {command}")
        return await self._tool("command_run", {"id": command, "params": params or {}})

    async def _check_project(self, sequence=None):
        project = await self._command("project.inspect")
        if _key(project) != self._project:
            raise NativeError("DOCUMENT", "native project identity or revision changed outside this client")
        if sequence is not None and project.get("activeSequence") != sequence:
            raise NativeError("DOCUMENT", "active native sequence changed")
        return project

    async def _mutate(self, command, params=None, sequence=None):
        await self._check_project(sequence)
        primary = None
        try:
            return await self._command(command, params)
        except BaseException as exc:
            primary = exc
            raise
        finally:
            # A host error may still follow a partial edit. Record actual state;
            # no retry, synthetic rollback or guessed revision is used.
            if not self.revoked:
                try:
                    self._project = _key(await self._command("project.inspect"))
                except BaseException as state_error:
                    self.revoked = True
                    self._cleanup_errors.append(f"native state readback: {type(state_error).__name__}: {state_error}")
                    if primary is None:
                        if isinstance(state_error, asyncio.CancelledError):
                            raise
                        raise NativeError(
                            "INDETERMINATE", "native mutation state readback failed; never replay"
                        ) from state_error

    def _virtual(self, name):
        return f"{self._virtual_root}/{name}"

    def _reserve(self, name):
        self._guard_directory()
        if name in self._reserved or (self.session_dir / name).exists() or (self.session_dir / name).is_symlink():
            raise NativeError("EXISTS", "refusing to overwrite or reuse an owned file")
        if len(self._reserved) >= 128:
            raise NativeError("LIMIT", "session file-count budget exceeded")
        self._reserved.add(name)
        return self.session_dir / name

    def _read_owned(self, name, limit):
        self._guard_directory()
        if name not in self._reserved or Path(name).name != name:
            raise NativeError("SESSION", "file is not owned by this session")
        path = self.session_dir / name
        try:
            expected = path.lstat()
            if stat.S_ISLNK(expected.st_mode):
                raise NativeError("SESSION", "owned file was replaced by a symbolic link")
            if not stat.S_ISREG(expected.st_mode) or expected.st_size > limit:
                raise NativeError("LIMIT", "owned file is not regular or exceeds its size limit")
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
            with os.fdopen(fd, "rb") as f:
                # An absolute-path open can race with directory replacement.
                # Check the session again before reading any descriptor bytes,
                # and bind that descriptor to the regular file we inspected.
                self._guard_directory()
                info = os.fstat(f.fileno())
                if self._identity(info) != self._identity(expected):
                    raise NativeError("SESSION", "owned file identity changed while opening")
                if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
                    raise NativeError("LIMIT", "owned file is not regular or exceeds its size limit")
                data = f.read(limit + 1)
                self._guard_directory()
                after = os.fstat(f.fileno())
                current = path.lstat()
                if stat.S_ISLNK(current.st_mode) or self._identity(current) != self._identity(info):
                    raise NativeError("SESSION", "owned file identity changed while reading")
                if (info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (
                    after.st_size,
                    after.st_mtime_ns,
                    after.st_ctime_ns,
                ):
                    raise NativeError("SESSION", "owned file changed while reading")
        except OSError as exc:
            raise NativeError("SESSION", "owned file is unavailable") from exc
        if len(data) > limit:
            raise NativeError("LIMIT", "owned file exceeds its size limit")
        return data

    def _store(self, data, kind):
        if len(data) > MAX_ARTIFACT:
            raise NativeError("LIMIT", "artifact exceeds 32 MiB")
        key = hashlib.sha256(data).hexdigest()
        if key not in self._artifacts:
            if self._artifact_total + len(data) > MAX_TOTAL:
                raise NativeError("LIMIT", "session artifact budget exceeds 128 MiB")
            self._artifacts[key] = bytes(data)
            self._artifact_total += len(data)
        return {"artifact": key, "sha256": key, "size": len(data), "kind": kind}

    async def _export_budget(self, sequence):
        """Bound native work before creating another streaming export job."""
        jobs = await self._command("jobs.list")
        owned = {self._native_job_id(job) for _, job in self._exports.values()}
        if any(row.get("id") in owned and not row.get("finished") for row in jobs):
            raise NativeError("BUSY", "only one native export may run at a time")
        info = await self._command("sequence.inspect", {"item": sequence})
        settings = info.get("settings", {})
        rate = settings.get("frame_rate", {})
        values = [
            info.get("durationFrames"),
            settings.get("width"),
            settings.get("height"),
            rate.get("num"),
            rate.get("den"),
            settings.get("sample_rate"),
        ]
        if any(type(value) is not int or value < 1 for value in values):
            raise NativeError("LIMIT", "native sequence has no usable finite export budget")
        frames, width, height, numerator, denominator, sample_rate = values
        fps = numerator / denominator
        if (
            frames > MAX_EXPORT_FRAMES
            or frames / fps > MAX_EXPORT_SECONDS
            or fps > 60
            or width > 4096
            or height > 4096
            or width * height * frames > MAX_EXPORT_PIXEL_FRAMES
            or sample_rate > 48000
            or settings.get("audio_master") not in {"Stereo", "Mono"}
        ):
            raise NativeError("LIMIT", "native export exceeds duration, geometry or audio work limits")
        # Reserve room for one maximum-sized artifact against existing owned
        # files. This is admission control, not a filesystem quota.
        used = 0
        for name in self._reserved:
            try:
                entry = (self.session_dir / name).lstat()
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(entry.st_mode):
                raise NativeError("SESSION", "owned native file was replaced by a non-regular file")
            used += entry.st_size
        if used + MAX_ARTIFACT > MAX_TOTAL:
            raise NativeError("LIMIT", "insufficient owned-file export budget; no job dispatched")

    def _public(self, value):
        if isinstance(value, str):
            return value.replace(str(self.session_dir) + os.sep, self._virtual_root + "/").replace(
                str(self.session_dir), self._virtual_root
            )
        if isinstance(value, dict):
            return {k: self._public(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._public(v) for v in value]
        return value

    async def call(self, operation, params):
        if operation not in self._validators:
            raise NativeError("UNSUPPORTED", "operation is outside the typed allowlist")
        try:
            self._validators[operation].validate(params)
            json.dumps(params, allow_nan=False)
        except (ValidationError, ValueError, TypeError) as exc:
            raise NativeError("INVALID_ARGUMENT", "invalid typed native operation arguments") from exc
        if operation == "read_artifact":
            data = self._artifacts.get(params["artifact"])
            if data is None:
                raise NativeError("SESSION", "artifact is not owned by this session")
            offset, size = params["offset"], params["size"]
            if offset > len(data):
                raise NativeError("INVALID_ARGUMENT", "offset exceeds artifact size")
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
        if operation == "reconcile":
            receipt = dict(self._receipt) if self._receipt else {"settled": True, "uncertain": False}
            if self.revoked:
                # A guard can observe loss before creating the next receipt.
                # Never let an older successful operation establish recovery.
                receipt.update(uncertain=True, authorityRevoked=True)
            return {"ok": True, "result": self._public(receipt)}
        self._guard()
        if operation == "capture_view":
            raise NativeError("UNSUPPORTED", "native-headless has no editor window to capture")
        if self._busy:
            raise NativeError("BUSY", "one native operation at a time; no queue or replay")
        if operation in {"save_project", "read_export"} and self._artifact_total + MAX_ARTIFACT > MAX_TOTAL:
            raise NativeError("LIMIT", "insufficient immutable artifact capacity; not dispatched")
        self._busy = True
        receipt = {
            "operation": operation,
            "origin": self.origin,
            "sessionId": self.session_id,
            "settled": False,
            "uncertain": False,
        }
        self._receipt = receipt
        try:
            result = self._public(await self._operate(operation, params))
            receipt.update(settled=True, result=result, ok=True)
            return {"ok": True, "origin": self.origin, "sessionId": self.session_id, "result": result}
        except BaseException as exc:
            receipt.update(
                settled=True,
                ok=False,
                error=str(exc),
                code=getattr(exc, "code", "HOST"),
                uncertain=self.revoked or isinstance(exc, asyncio.CancelledError),
                cleanup_errors=list(self._cleanup_errors),
            )
            if isinstance(exc, asyncio.CancelledError):
                self.revoked = True
            raise
        finally:
            self._busy = False

    async def _operate(self, operation, p):
        if operation == "inspect":
            return {**await self._command("project.inspect"), "capabilities": self.capabilities}
        if operation == "inspect_sequence":
            return await self._command("sequence.inspect", {"item": p["sequence"]})
        if operation == "create_project":
            current = await self._check_project()
            if current.get("dirty") or current.get("root", {}).get("children"):
                raise NativeError("DOCUMENT", "create requires an empty clean project; replacing work is unsupported")
            await self._mutate("file.newProject", {"name": p["name"]})
            return await self._command("project.inspect")
        if operation == "import_media":
            if len(p["data"]) > 4 * ((MAX_MEDIA + 2) // 3):
                raise NativeError("LIMIT", "media encoding exceeds 16 MiB")
            try:
                raw = base64.b64decode(p["data"], validate=True)
            except ValueError as exc:
                raise NativeError("INVALID_ARGUMENT", "media data must be valid base64") from exc
            if not 0 < len(raw) <= MAX_MEDIA or self._media_total + len(raw) > 64 * 1024 * 1024:
                raise NativeError("LIMIT", "media exceeds per-file or 64 MiB session budget")
            await self._check_project()
            # Incoming names supply only a reviewed extension, never a host path.
            ext = Path(p["name"]).suffix.lower()
            name = f"media-{uuid.uuid4().hex}{ext}"
            path = self._reserve(name)
            with path.open("xb") as out:
                out.write(raw)
            self._media[name] = hashlib.sha256(raw).hexdigest()
            self._media_total += len(raw)
            try:
                result = await self._tool("media_import", {"paths": [str(path)]})
            finally:
                if not self.revoked:
                    self._project = _key(await self._command("project.inspect"))
            if result.get("errors") or not result.get("items"):
                raise NativeError("IMPORT", "native import did not produce a usable media item")
            return result
        if operation == "create_sequence":
            return await self._mutate("file.newSequence", {"name": p["name"], "fromItem": p["from_item"]})
        if operation == "rename_item":
            return await self._mutate("clip.rename", {"item": p["item"], "name": p["name"]})
        if operation == "set_playback_rate":
            await self._mutate("timeline.select", {"clips": [p["clip"]]}, p["sequence"])
            return await self._mutate(
                "clip.speedDuration",
                {
                    "clips": [p["clip"]],
                    "speed": p["percent"],
                    "reverse": False,
                    "ripple": True,
                    "interpolation": "frameSampling",
                },
                p["sequence"],
            )
        if operation in {"undo", "redo"}:
            return await self._mutate("edit." + operation)
        if operation == "save_project":
            name = p["name"] + ".fcproj"
            path = self._reserve(name)
            await self._mutate("file.saveAs", {"path": str(path)})
            data = self._read_owned(name, MAX_MEDIA)
            artifact = self._store(data, "fcproj")
            handle = self._virtual(name)
            self._saved[handle] = (name, artifact["sha256"])
            return {"path": handle, "bytes": artifact}
        if operation == "reopen_project":
            saved = self._saved.get(p["path"])
            if not saved:
                raise NativeError("DOCUMENT", "only this session's unchanged native save may reopen")
            try:
                current = await self._check_project()
            except BaseException:
                if p.get("restart_native", False):
                    self.revoked = True
                raise
            if p.get("restart_native", False) and type(current.get("dirty")) is not bool:
                self.revoked = True
                raise NativeError("INDETERMINATE", "current native project cleanliness cannot be established")
            if current.get("dirty"):
                raise NativeError("DOCUMENT", "save the current project before reopening")
            if p.get("restart_native", False):
                return await self._restart_and_reopen(saved)
            self._verify_saved_media(saved)
            await self._mutate("file.open", {"path": str(self.session_dir / saved[0])})
            return await self._command("project.inspect")
        if operation == "export_media":
            if len(self._exports) >= 32:
                raise NativeError("LIMIT", "session export-job budget exceeded")
            await self._check_project(p["sequence"])
            await self._export_budget(p["sequence"])
            name = p["name"] + (".wav" if p["format"] == "wav" else ".mp4")
            path = self._reserve(name)
            result = await self._mutate(
                "file.exportMedia",
                {
                    "path": str(path),
                    "format": p["format"],
                    "sequence": p["sequence"],
                    "bitrateKbps": 1000,
                    "bitrateMode": "cbr",
                    "hardwareEncoding": "off",
                    "range": "entire",
                },
                p["sequence"],
            )
            job = result.get("job")
            if type(job) is not int or job < 1:
                self.revoked = True
                raise NativeError("INDETERMINATE", "native export returned no identifiable job")
            handle = self._virtual(name)
            alias = self._job_alias(job)
            self._exports[handle] = (name, alias)
            return {"path": handle, "job": alias}
        if operation == "list_jobs":
            return [
                *copy.deepcopy(list(self._archived_jobs.values())),
                *self._map_jobs(await self._command("jobs.list")),
            ]
        if operation == "cancel_export":
            if p["job"] not in {job for _, job in self._exports.values()}:
                raise NativeError("SESSION", "export job is not owned by this session")
            native = self._native_job_id(p["job"])
            if native is None:
                raise NativeError("SESSION", "export belongs to an ended native child and is already terminal")
            return await self._command("jobs.cancel", {"job": native})
        if operation == "read_export":
            owned = self._exports.get(p["path"])
            if not owned:
                raise NativeError("SESSION", "export path is not owned by this session")
            name, job = owned
            native = self._native_job_id(job)
            if native is None:
                record = self._archived_jobs.get(job)
            else:
                jobs = await self._command("jobs.list")
                record = next((row for row in jobs if row.get("id") == native), None)
            if not record or not record.get("finished"):
                raise NativeError("BUSY", "export has not reached terminal state")
            if record.get("error") or (record.get("result") or {}).get("error") or record.get("offlineMedia"):
                raise NativeError("EXPORT", "native export did not succeed")
            return self._store(self._read_owned(name, MAX_ARTIFACT), Path(name).suffix[1:])
        if operation == "disconnect":
            owned_jobs = {self._native_job_id(job) for _, job in self._exports.values()}
            jobs = await self._command("jobs.list")
            if any(row.get("id") in owned_jobs and not row.get("finished") for row in jobs):
                raise NativeError("BUSY", "cancel and await active exports before disconnecting")
            self._disconnected = True
            return {
                "closed": True,
                "documentPreserved": True,
                "filesPreserved": True,
                "artifactsPreserved": True,
                "processStillRunning": True,
            }
        raise NativeError("UNSUPPORTED", "native operation is not implemented")

    async def close(self):
        """End the owned process; never remove imported media, saves or exports."""
        self.revoked = True
        result = await self._stop_owned_child()
        if self.evidence_dir:
            try:
                self.evidence_dir.mkdir(parents=True, exist_ok=True)
                (self.evidence_dir / f"native-{self.session_id}.stderr.log").write_bytes(self._stderr)
            except OSError as exc:
                result["cleanup_errors"].append(str(exc))
                self._cleanup_errors.append(str(exc))
        return result

    async def _stop_owned_child(self):
        """Close only our retained Process object and prove its exit before replacement."""
        errors = []
        process = self._original_process
        if process:
            try:
                if process.stdin:
                    process.stdin.close()
                try:
                    await asyncio.wait_for(process.wait(), timeout=3)
                except asyncio.TimeoutError:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=3)
                    except asyncio.TimeoutError:
                        process.kill()
                        await asyncio.wait_for(process.wait(), timeout=3)
            except (OSError, ProcessLookupError, asyncio.TimeoutError, RuntimeError) as exc:
                errors.append(str(exc))
        if self._stderr_task:
            try:
                await asyncio.wait_for(self._stderr_task, timeout=2)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._stderr_task.cancel()
                try:
                    await self._stderr_task
                except asyncio.CancelledError:
                    pass
            except (OSError, RuntimeError) as exc:
                errors.append(str(exc))
        closed = process is None or process.returncode is not None
        if not closed:
            errors.append("owned native child exit is not confirmed")
        self._cleanup_errors.extend(errors)
        return {"closed": closed, "filesPreserved": True, "cleanup_errors": errors}
