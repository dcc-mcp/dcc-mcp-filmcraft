"""Opt-in official-MCP portability proof; no adapter authority or host attachment.

This closed fixture case is deliberately separate from Core adapter qualification.
It never imports NativeSession or injects its saved-handle registry.
"""

from __future__ import annotations

import argparse
import array
import asyncio
import copy
import hashlib
import json
import math
import os
import platform
import re
import stat
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import anyio
from mcp import ClientSession, types
from mcp.shared.message import SessionMessage

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/portable-handoff"
CLI_SHA = "05982fe44214f6174ffb54166d100e2362cf90811f2480235f3ecbaa0a3a75c2"
TEMPLATE_SHA = "2e583bcde1d91efe40edf43e730503155e8571e76bb9b362742f43ea498485b3"
SOURCE_SHA = "00ea011f98e63f9ecd325da87c4ad8de567bbd58539db0924edcef6b4129f5a5"
SEMANTIC_SHA = "8a6bf446e49a8aa1d7069af18a634898300cf42427ca96f5a5f5ed427cec98a1"
LICENSE_SHA = {
    "LICENSE-MIT": "d2d8416f0883694c23b473e26372506e9e11f5f41b55a92b7388dab921d9a207",
    "LICENSE-APACHE": "0d542e0c8804e39aa7f37eb00da5a762149dc682d7829451287e11b938e94594",
    "NOTICE": "5761787313b9d6c13dd5f03da2e04209ad7bd08eff8920edfd184141d791195c",
    "adapter-LICENSE-MIT": "4e151a6ceda527fe8c9bb1ccc56ed41d69f7621aba01d5f073d0aa1519ddc8a1",
}
MEDIA = "media/source.mp4"
MAX_PROJECT = 1024 * 1024
MAX_RPC = 4 * 1024 * 1024
MAX_OUTPUT = 32 * 1024 * 1024
COMMANDS = {
    "file.open",
    "file.saveAs",
    "project.inspect",
    "sequence.inspect",
    "media.findMissing",
    "media.status",
    "file.exportMedia",
    "jobs.list",
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_regular(path, limit, expected=None):
    """Read one exact regular file without following a final symlink or FIFO."""
    path = Path(path)
    before_path = path.lstat()
    if not stat.S_ISREG(before_path.st_mode) or before_path.st_size > limit:
        raise ValueError("regular bounded file required")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode) or (before.st_dev, before.st_ino) != (
            before_path.st_dev,
            before_path.st_ino,
        ):
            raise ValueError("file identity changed before read")
        raw = source.read(limit + 1)
        after = os.fstat(source.fileno())
    current = path.lstat()

    def key(info):
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns

    if len(raw) > limit or len(raw) != before.st_size or key(before) != key(after) or key(after) != key(current):
        raise ValueError("file changed while reading")
    if expected is not None and digest(raw) != expected:
        raise ValueError("file SHA-256 mismatch")
    return raw


def write_new(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())


def all_strings(value, pointer=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from all_strings(item, pointer + "/" + key.replace("~", "~0").replace("/", "~1"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from all_strings(item, pointer + "/" + str(index))
    elif isinstance(value, str):
        yield pointer, value


def resource_safe(value):
    return value == MEDIA


def license_files():
    directory = FIXTURE / "licenses"
    files = {"licenses/" + name: read_regular(directory / name, 1024 * 1024, sha) for name, sha in LICENSE_SHA.items()}
    raw = read_regular(directory / "source-receipts.json", 128 * 1024)
    receipts = json.loads(raw)
    if len(receipts) != 4 or {row["path"]: row["sha256"] for row in receipts} != {
        "licenses/" + name: sha for name, sha in LICENSE_SHA.items()
    }:
        raise ValueError("component license receipts differ from pinned sources")
    files["licenses/source-receipts.json"] = raw
    return files


def scan_user_files(files, forbidden_roots=()):
    for name, raw in files.items():
        if name.startswith(("/", "\\")) or "\\" in name or ".." in Path(name).parts or re.match(r"^[A-Za-z]:", name):
            raise ValueError("unsafe user-facing archive name")
        normalized = raw.lower().replace(b"\\\\", b"/").replace(b"\\", b"/")
        if any(prefix in normalized for prefix in (b"/home/runner/", b"p:/codex/", b"c:/users/")):
            raise ValueError("machine path in user-facing file: " + name)
        if any(str(root).lower().replace("\\", "/").encode() in normalized for root in forbidden_roots):
            raise ValueError("actual execution root in user-facing file: " + name)
        if name.endswith(".fcproj"):
            inspect_project(raw)


def inspect_project(raw):
    if len(raw) > MAX_PROJECT:
        raise ValueError("project exceeds fixed fixture budget")
    value = json.loads(raw)
    if value.get("format") != "filmcraft.project" or value.get("schema_version") != 15:
        raise ValueError("only the reviewed schema-15 project is admitted")
    project = copy.deepcopy(value["project"])
    media = project["items"]["1"]["kind"]["Media"]
    if media.get("proxy") is not None or media["media"] != {"File": {"path": MEDIA}}:
        raise ValueError("the single exact relative media reference is required")
    for pointer, text in all_strings(value):
        if re.match(r"^(?:[/\\]|[A-Za-z]:[/\\]|[A-Za-z][A-Za-z0-9+.-]*://)", text) or re.search(
            r"(?:^|[/\\])\.\.(?:[/\\]|$)", text
        ):
            raise ValueError("absolute, URI or traversal string in project: " + pointer)
        if any(x in text.replace("\\", "/").lower() for x in ("/home/runner/", ":/users/", ":/codex/")):
            raise ValueError("machine path in project: " + pointer)
    project["items"]["1"]["kind"]["Media"]["media"]["File"]["path"] = "<owned-media>"
    semantic = digest(json.dumps(project, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())
    if semantic != SEMANTIC_SHA:
        raise ValueError("non-path project semantics differ from the exact f1 work")
    return value


def directory_identity(path):
    info = Path(path).lstat()
    if not stat.S_ISDIR(info.st_mode) or Path(path).is_symlink():
        raise ValueError("owned ordinary directory required")
    return info.st_dev, info.st_ino


def check_identity(path, expected):
    if directory_identity(path) != expected:
        raise ValueError("owned directory identity changed")


def move_owned_a(a, isolated, parent, identity):
    a, isolated, parent = Path(a), Path(isolated), Path(parent)
    if a.parent != parent or isolated.parent != parent or isolated.exists() or isolated.is_symlink():
        raise ValueError("isolation requires two direct owned children")
    check_identity(a, identity)
    a.rename(isolated)
    if a.exists() or directory_identity(isolated) != identity:
        raise ValueError("old A directory was not isolated")


def resolve_tool(names, bare):
    allowed = {bare, "filmcraft__" + bare, "mcp__filmcraft__" + bare}
    matches = [name for name in names if name in allowed]
    if len(matches) != 1:
        raise ValueError("missing or ambiguous official MCP route: " + bare)
    return matches[0]


def tool_value(result):
    if result.isError:
        raise RuntimeError("official MCP returned an error: " + result.model_dump_json())
    if result.structuredContent is not None:
        return result.structuredContent
    texts = [x.text for x in result.content if x.type == "text"]
    if len(texts) != 1:
        raise ValueError("expected one official structured JSON response")
    return json.loads(texts[0])


class OfficialClient:
    """Public SDK over streams backed by a retained, exclusively owned Process."""

    def __init__(self, command, cwd, home, stderr, report, label):
        self.command, self.cwd, self.home = list(command), Path(cwd), Path(home)
        self.stderr, self.report, self.label = Path(stderr), report, label
        self.process = None
        self.events = report.setdefault("official_mcp_events", [])
        self.lifecycle = {"label": label, "cwd": str(cwd), "completed": False}
        report.setdefault("children", []).append(self.lifecycle)
        self.sequence = 0
        self.uncertain = False

    async def __aenter__(self):
        self.home.mkdir(exist_ok=False)
        env = {k: v for k, v in os.environ.items() if k in {"PATH", "SYSTEMROOT", "WINDIR", "LANG", "LC_ALL"}}
        env.update(
            HOME=str(self.home),
            XDG_CONFIG_HOME=str(self.home / "config"),
            XDG_DATA_HOME=str(self.home / "data"),
            XDG_CACHE_HOME=str(self.home / "cache"),
            FILMCRAFT_DATA_DIR=str(self.home / "data"),
            OMP_NUM_THREADS="1",
            RAYON_NUM_THREADS="2",
            TOKIO_WORKER_THREADS="2",
        )
        self.errfile = self.stderr.open("xb")
        try:
            self.process = await asyncio.create_subprocess_exec(
                *self.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=self.errfile,
                cwd=str(self.cwd),
                env=env,
                limit=MAX_RPC,
            )
            self.lifecycle["pid"] = self.process.pid
            self.read_send, self.read_receive = anyio.create_memory_object_stream(16)
            self.write_send, self.write_receive = anyio.create_memory_object_stream(16)
            self.reader = asyncio.create_task(self._read())
            self.writer = asyncio.create_task(self._write())
            self.session = ClientSession(self.read_receive, self.write_send)
            await self.session.__aenter__()
            self.session_entered = True
            return self
        except BaseException as primary:
            self.lifecycle["primary_error"] = repr(primary)
            try:
                await self._close()
            except BaseException as cleanup:
                self.lifecycle.setdefault("cleanup_errors", []).append(
                    {"phase": "startup cleanup", "error": repr(cleanup)}
                )
            raise

    async def _read(self):
        try:
            while line := await self.process.stdout.readline():
                if len(line) > MAX_RPC:
                    raise ValueError("official RPC response exceeds 4 MiB")
                await self.read_send.send(SessionMessage(types.JSONRPCMessage.model_validate_json(line)))
        except Exception as exc:
            try:
                await self.read_send.send(exc)
            except (anyio.BrokenResourceError, anyio.ClosedResourceError):
                pass
        finally:
            await self.read_send.aclose()

    async def _write(self):
        try:
            async with self.write_receive:
                async for message in self.write_receive:
                    raw = message.message.model_dump_json(by_alias=True, exclude_none=True).encode() + b"\n"
                    if len(raw) > MAX_RPC:
                        raise ValueError("official RPC request exceeds 4 MiB")
                    self.process.stdin.write(raw)
                    await self.process.stdin.drain()
        finally:
            self.process.stdin.close()

    async def capture(self, method, parameters, call):
        if self.uncertain:
            raise RuntimeError("unknown original result; official client permanently revoked")
        event = {
            "index": len(self.events) + 1,
            "child": self.label,
            "method": method,
            "parameters": parameters,
            "state": "started",
        }
        self.events.append(event)
        try:
            result = await asyncio.wait_for(call(), timeout=30)
            event.update(state="returned", response=result.model_dump(mode="json", by_alias=True, exclude_none=True))
            return result
        except BaseException as exc:
            self.uncertain = True
            event.update(state="client_exception", error=repr(exc), outcome="unknown; never retried")
            raise

    async def initialize(self):
        result = await self.capture("initialize", {}, self.session.initialize)
        identity = {
            "name": result.serverInfo.name,
            "version": result.serverInfo.version,
            "protocol": result.protocolVersion,
        }
        if identity["name"] != "filmcraft" or identity["version"] != "0.12.0":
            raise ValueError("official runtime identity differs")
        self.lifecycle["runtime_identity"] = identity
        tools, cursor, seen = [], None, set()
        for _ in range(32):
            result = await self.capture(
                "tools/list", {"cursor": cursor}, lambda cursor=cursor: self.session.list_tools(cursor=cursor)
            )
            tools.extend(tool.name for tool in result.tools)
            cursor = result.nextCursor
            if not cursor:
                break
            if cursor in seen:
                raise ValueError("repeated tool cursor")
            seen.add(cursor)
        else:
            raise ValueError("tool pagination exceeds 32 pages")
        if len(tools) > 1024 or len(tools) != len(set(tools)):
            raise ValueError("invalid tool catalog")
        self.run_tool = resolve_tool(tools, "command_run")
        listing = resolve_tool(tools, "command_list")
        commands = await self.call_tool(listing, {})
        if not isinstance(commands, list) or len(commands) > 2048:
            raise ValueError("invalid command catalog")
        ids = [x.get("id") for x in commands]
        if any(ids.count(name) != 1 for name in COMMANDS):
            raise ValueError("required official command not uniquely discovered")
        self.command_ids = set(ids)
        return identity

    async def call_tool(self, name, params):
        result = await self.capture(
            "tools/call", {"name": name, "arguments": params}, lambda: self.session.call_tool(name, params)
        )
        return tool_value(result)

    async def command_call(self, name, params=None):
        if name not in COMMANDS or name not in self.command_ids:
            raise ValueError("command outside this closed operator case")
        return await self.call_tool(self.run_tool, {"id": name, "params": params or {}})

    async def _close(self):
        errors = self.lifecycle.setdefault("cleanup_errors", [])
        if getattr(self, "session_entered", False):
            try:
                await self.session.__aexit__(None, None, None)
            except BaseException as exc:
                errors.append({"phase": "public SDK close", "error": repr(exc)})
        if hasattr(self, "write_send"):
            await self.write_send.aclose()
        if self.process is not None:
            self.process.stdin.close()
            try:
                await asyncio.wait_for(self.process.wait(), 5)
                self.lifecycle["forced_stop"] = False
            except asyncio.TimeoutError:
                self.lifecycle["forced_stop"] = True
                try:
                    self.process.terminate()
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(self.process.wait(), 3)
                except asyncio.TimeoutError:
                    try:
                        self.process.kill()
                    except ProcessLookupError:
                        pass
                    await self.process.wait()
            self.lifecycle.update(exited=self.process.returncode is not None, exit_code=self.process.returncode)
        for name in ("reader", "writer"):
            task = getattr(self, name, None)
            if task:
                if not task.done():
                    task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except BaseException as exc:
                    errors.append({"phase": name, "error": repr(exc)})
        if hasattr(self, "read_receive"):
            await self.read_receive.aclose()
        if hasattr(self, "errfile"):
            self.errfile.close()

    async def __aexit__(self, kind, primary, traceback):
        if primary is not None:
            self.lifecycle["primary_error"] = repr(primary)
        try:
            await self._close()
        except BaseException as exc:
            self.lifecycle.setdefault("cleanup_errors", []).append({"phase": "process cleanup", "error": repr(exc)})
            if primary is None:
                raise
        self.lifecycle["completed"] = (
            primary is None
            and self.lifecycle.get("exited")
            and self.lifecycle.get("exit_code") == 0
            and not self.lifecycle.get("forced_stop")
            and not self.lifecycle.get("cleanup_errors")
        )
        if primary is None and not self.lifecycle["completed"]:
            raise RuntimeError("owned child did not close cleanly")
        return False


def require(checks, condition, name, detail=None):
    checks.append({"name": name, "ok": bool(condition), "detail": detail})
    if not condition:
        raise AssertionError(name)


async def inspect_online(client, project_path, checks, report):
    opened = await client.command_call("file.open", {"path": str(project_path)})
    missing_count = opened.get("missingMedia")
    require(
        checks,
        type(missing_count) is int and missing_count == 0,
        client.label + " document-relative open has no missing media",
        opened,
    )
    missing = await client.command_call("media.findMissing")
    require(checks, missing.get("missing") == [], client.label + " official findMissing resolves all media", missing)
    status = await client.command_call("media.status", {"item": 1})
    report.setdefault("raw_media_status", {})[client.label] = status
    # Exact 0.12 source reads stored relative paths with fs::metadata for status,
    # unlike findMissing/render's document-relative MediaPool.follow. Never chdir
    # or copy an alias into B's third cwd to make that diagnostic say online.
    require(
        checks,
        isinstance(status, list) and len(status) == 1 and status[0].get("item") == 1 and status[0].get("path") == MEDIA,
        client.label + " status describes the exact relative media item",
        status,
    )
    report.setdefault("diagnostic_status_by_child", {})[client.label] = {
        "reported": status[0].get("status"),
        "consistent_with_find_missing": status[0].get("status") == "online",
    }
    inspected = await client.command_call("project.inspect")
    require(
        checks,
        inspected.get("dirty") is False and inspected.get("path") == str(project_path),
        client.label + " exact clean opened project",
        inspected,
    )
    return inspected


async def terminal_export(client, sequence, path, fmt, checks):
    if path.exists() or path.is_symlink():
        raise ValueError("export output must be new")
    result = await client.command_call(
        "file.exportMedia",
        {
            "path": str(path),
            "format": fmt,
            "sequence": sequence,
            "bitrateKbps": 1000,
            "bitrateMode": "cbr",
            "hardwareEncoding": "off",
            "range": "entire",
        },
    )
    job = result.get("job")
    if type(job) is not int or job < 1:
        raise ValueError("unidentified export outcome; no retry")
    deadline = time.monotonic() + 120
    while True:
        jobs = await client.command_call("jobs.list")
        record = next((x for x in jobs if x.get("id") == job), None)
        if record is None:
            raise ValueError("owned export terminal state missing")
        if record.get("finished") is True:
            break
        if time.monotonic() > deadline:
            raise TimeoutError("owned export did not settle; no retry")
        await asyncio.sleep(0.1)
    require(
        checks,
        not record.get("error") and not record.get("result", {}).get("error"),
        fmt + " export reaches successful terminal state",
        record,
    )
    require(checks, record.get("offlineMedia") == [], fmt + " export has no offline media", record)
    read_regular(path, MAX_OUTPUT)


def decode_oracles(source, movie, wave, internal, checks):
    def output(command, cap):
        raw = subprocess.check_output(command, timeout=60)
        if len(raw) > cap:
            raise ValueError("decoded output exceeds fixed fixture budget")
        return raw

    for path in (movie, wave):
        info = json.loads(
            output(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)], 1024 * 1024)
        )
        (internal / (path.name + ".ffprobe.json")).write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
        require(
            checks,
            1.95 <= float(info["format"]["duration"]) <= 2.1
            and any(s["codec_type"] == "audio" for s in info["streams"]),
            path.suffix + " decoded duration and audio",
        )
        if path == movie:
            videos = [s for s in info["streams"] if s["codec_type"] == "video"]
            require(
                checks,
                len(videos) == 1 and videos[0].get("width") == 160 and videos[0].get("height") == 90,
                "original decoded video dimensions",
            )
    rgb_command = ["ffmpeg", "-v", "error", "-i"]
    source_rgb = output(
        rgb_command + [str(source), "-an", "-frames:v", "13", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
        160 * 90 * 3 * 13 + 1,
    )
    movie_rgb = output(
        rgb_command + [str(movie), "-an", "-frames:v", "25", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
        160 * 90 * 3 * 25 + 1,
    )
    stride = 160 * 90 * 3
    require(checks, len(source_rgb) == stride * 12 and len(movie_rgb) == stride * 24, "original 12-to-24 frame count")
    mae = sum(
        abs(value - source_rgb[(i // stride // 2) * stride + i % stride]) for i, value in enumerate(movie_rgb)
    ) / len(movie_rgb)
    require(checks, mae < 18, "original repeated-frame MAE below 18", mae)
    audio = {}
    for path in (wave, movie):
        raw = output(
            ["ffmpeg", "-v", "error", "-i", str(path), "-t", "3", "-ac", "1", "-ar", "48000", "-f", "f32le", "-"],
            48000 * 4 * 3,
        )
        samples = array.array("f")
        samples.frombytes(raw)
        if sys.byteorder != "little":
            samples.byteswap()
        middle = samples[9600:-9600]
        if not middle:
            raise ValueError("decoded audio too short")
        hz = sum(a <= 0 < b for a, b in zip(middle, middle[1:], strict=False)) / (len(middle) / 48000)
        rms = math.sqrt(sum(x * x for x in middle) / len(middle))
        audio[path.name] = {"duration": len(samples) / 48000, "frequencyHz": hz, "rms": rms}
        require(
            checks,
            1.95 <= len(samples) / 48000 <= 2.1 and 200 < hz < 240 and rms > 0.02,
            path.suffix + " original independently decoded half-speed audio",
            audio[path.name],
        )
    return {"source_frames": 12, "export_frames": 24, "frame_repeat_mae": mae, "audio": audio}


async def run_case(executable, output, source_commit):
    if sys.platform != "linux" or platform.machine().lower() not in {"x86_64", "amd64"}:
        raise ValueError("qualification is Linux x86_64 only")
    if executable.is_symlink():
        raise ValueError("qualification executable must not be a symlink")
    executable = executable.resolve(strict=True)
    read_regular(executable, 80 * 1024 * 1024, CLI_SHA)
    template = read_regular(FIXTURE / "project.fcproj", MAX_PROJECT, TEMPLATE_SHA)
    source = read_regular(FIXTURE / "source.mp4", 21911, SOURCE_SHA)
    inspect_project(template)
    output = output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    owner = directory_identity(output)
    internal = output / "internal"
    internal.mkdir()
    report = {
        "source_commit": source_commit,
        "layer": "official CLI MCP closed operator case; no Core adapter bundle import",
        "core_adapter_calls": 0,
        "runtime_cli_sha256": CLI_SHA,
        "checks": [],
        "passed": False,
    }
    checks = report["checks"]
    a, b, third = output / "A", output / "B", output / "unrelated-cwd"
    for path in (a, b, third):
        path.mkdir()
    identity_a, identity_b, identity_third = map(directory_identity, (a, b, third))
    require(
        checks,
        len({identity_a, identity_b, identity_third}) == 3,
        "A, B and process-cwd directories have distinct identities",
    )
    write_new(a / "candidate.fcproj", template)
    write_new(a / MEDIA, source)
    identities = []
    try:
        read_regular(executable, 80 * 1024 * 1024, CLI_SHA)
        async with OfficialClient(
            [str(executable), "mcp", "--data-dir", str(internal / "home-A/data")],
            a,
            internal / "home-A",
            internal / "A.stderr.log",
            report,
            "A",
        ) as client:
            identities.append(await client.initialize())
            await inspect_online(client, a / "candidate.fcproj", checks, report)
            await client.command_call("file.saveAs", {"path": str(a / "project.fcproj")})
            saved_a = read_regular(a / "project.fcproj", MAX_PROJECT)
            inspect_project(saved_a)
            require(
                checks, (await client.command_call("project.inspect")).get("dirty") is False, "A official save is clean"
            )
            require(checks, await client.command_call("jobs.list") == [], "A has no unfinished owned jobs")
        require(
            checks, report["children"][0]["completed"], "A owned child exited before relocation", report["children"][0]
        )
        check_identity(output, owner)
        check_identity(a, identity_a)
        check_identity(b, identity_b)
        write_new(b / "project.fcproj", saved_a)
        write_new(b / MEDIA, read_regular(a / MEDIA, 21911, SOURCE_SHA))
        require(checks, read_regular(b / "project.fcproj", MAX_PROJECT) == saved_a, "A-to-B project copy is exact")
        move_owned_a(a, output / "A-isolated", output, identity_a)
        require(
            checks,
            not a.exists() and third != b and not (third / MEDIA).exists(),
            "A unavailable and B process cwd cannot supply the relative media",
        )
        check_identity(third, identity_third)
        read_regular(executable, 80 * 1024 * 1024, CLI_SHA)
        async with OfficialClient(
            [str(executable), "mcp", "--data-dir", str(internal / "home-B/data")],
            third,
            internal / "home-B",
            internal / "B.stderr.log",
            report,
            "B",
        ) as client:
            identities.append(await client.initialize())
            require(checks, identities[0] == identities[1], "fresh B negotiated identical official runtime")
            require(
                checks,
                report["children"][0]["pid"] != client.process.pid and report["children"][0]["exited"],
                "fresh B actual PID follows confirmed A exit",
            )
            await inspect_online(client, b / "project.fcproj", checks, report)
            sequence = await client.command_call("sequence.inspect", {"item": 8})
            report["sequence"] = sequence
            await client.command_call("file.saveAs", {"path": str(b / "reopened.fcproj")})
            inspect_project(read_regular(b / "reopened.fcproj", MAX_PROJECT))
            for fmt, name in (("h264", "export.mp4"), ("wav", "export.wav")):
                await terminal_export(client, 8, b / name, fmt, checks)
            jobs = await client.command_call("jobs.list")
            require(
                checks, all(row.get("finished") is True for row in jobs), "all B owned jobs terminal before close", jobs
            )
        require(
            checks,
            report["children"][1]["completed"],
            "B owned child exited after terminal exports",
            report["children"][1],
        )
        check_identity(output, owner)
        check_identity(b, identity_b)
        require(
            checks,
            read_regular(b / MEDIA, 21911, SOURCE_SHA) == source,
            "relocated source retains exact original bytes",
        )
        report["media_oracles"] = decode_oracles(b / MEDIA, b / "export.mp4", b / "export.wav", internal, checks)
        # The raw status remains evidence; semantic online proof is findMissing,
        # exact resource hashes and the independently decoded source signal.
        report["diagnostic_status_consistent"] = all(
            x["consistent_with_find_missing"] for x in report["diagnostic_status_by_child"].values()
        )
        report["official_status_diagnostic"] = {
            "source_limitation": (
                "0.12 media.status fs::metadata uses raw relative stored path; "
                "findMissing/render use document-relative MediaPool.follow"
            ),
            "raw_status_preserved": True,
            "api_comprehensive_health_qualified": False,
            "pre_execution_plan_amendment": "docs/source-guided-plan-amendment.md",
        }
        user = output / "user-facing"
        user.mkdir()
        user_files = {
            "reopened.fcproj": read_regular(b / "reopened.fcproj", MAX_PROJECT),
            MEDIA: source,
            "export.mp4": read_regular(b / "export.mp4", MAX_OUTPUT),
            "export.wav": read_regular(b / "export.wav", MAX_OUTPUT),
        }
        user_files.update(license_files())
        for name in ("reopened.fcproj", MEDIA):
            license_path = "../licenses/adapter-LICENSE-MIT" if name == MEDIA else "licenses/adapter-LICENSE-MIT"
            user_files[name + ".attribution"] = (
                "asset: "
                + name
                + "\nsource: original DCC-MCP procedural FilmCraft qualification work\nlicense: MIT\nlicense-file: "
                + license_path
                + "\nnotes: No vendor binary, fonts or artwork. Calibration acceptance sample, not promo.\n"
            ).encode()
        summary = {
            "adapter_source_commit": source_commit,
            "runtime": identities[1],
            "cli_sha256": CLI_SHA,
            "qualification": "official-MCP native file portability; not adapter cross-session import or GUI",
            "asset_references": [MEDIA],
            "media_oracles": report["media_oracles"],
            "diagnostic_status_consistent": report["diagnostic_status_consistent"],
            "api_comprehensive_health_qualified": False,
            "status_limitation": (
                "Official 0.12 media.status may misreport stored relative paths "
                "when cwd differs from the document folder; "
                "raw diagnostics retained separately. File portability is proved by official open/findMissing, "
                "exact resources and decoded signals."
            ),
            "files": [
                {"path": name, "bytes": len(raw), "sha256": digest(raw)} for name, raw in sorted(user_files.items())
            ],
        }
        user_files["validation.json"] = (json.dumps(summary, indent=2) + "\n").encode()
        user_files["README.md"] = (
            b"# FilmCraft portable calibration project\n\n"
            b"Open reopened.fcproj with the adjacent media/ folder. A new official Linux FilmCraft 0.12 CLI opened "
            b"this project from another directory while its process cwd was elsewhere, then saved and exported it. "
            b"Resources use document-relative paths. This is a procedural interoperability acceptance sample, "
            b"not a promotional film or GUI qualification. The DCC-MCP adapter does not yet expose cross-session "
            b"bundle import. Raw CI/host diagnostics and vendor binaries are excluded. Component license and "
            b"trademark/font/codec boundaries remain separate; see licenses/NOTICE.\n"
        )
        scan_user_files(user_files, (output, ROOT))
        for name, raw in sorted(user_files.items()):
            write_new(user / name, raw)
        report["user_facing_files"] = summary["files"]
        with zipfile.ZipFile(
            output / "filmcraft-portable-handoff.zip", "x", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for name, raw in sorted(user_files.items()):
                archive.writestr(name, raw)
        with zipfile.ZipFile(output / "filmcraft-portable-handoff.zip") as archive:
            require(
                checks,
                archive.testzip() is None and set(archive.namelist()) == set(user_files),
                "user-facing archive CRC and exact entry set",
            )
            require(
                checks,
                all(archive.read(name) == raw for name, raw in user_files.items()),
                "user-facing archive retains every admitted byte",
            )
        packed = read_regular(output / "filmcraft-portable-handoff.zip", 64 * 1024 * 1024)
        report["user_archive"] = {
            "name": "filmcraft-portable-handoff.zip",
            "bytes": len(packed),
            "sha256": digest(packed),
        }
        report["passed"] = True
    except BaseException as exc:
        report["primary_error"] = repr(exc)
        raise
    finally:
        events = report.get("official_mcp_events", [])
        report["actual_public_sdk_attempts"] = {
            name: sum(e["method"] == name for e in events) for name in ("initialize", "tools/list", "tools/call")
        }
        report["official_engine_command_attempts"] = sum(
            e["method"] == "tools/call" and "id" in e["parameters"].get("arguments", {}) for e in events
        )
        report["vendor_internal_rpc_count"] = None
        report["scope"] = (
            "SDK notifications and vendor-internal RPC are not counted; "
            "these official CLI calls are separate from historical Core adapter 36+4"
        )
        (internal / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-cli", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--adapter-source-commit", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.adapter_source_commit):
        parser.error("source commit must be the exact 40-hex candidate head")
    actual_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if actual_head != args.adapter_source_commit:
        parser.error("candidate source commit differs from the checked-out source")
    report = asyncio.run(run_case(args.native_cli, args.output, args.adapter_source_commit))
    print(
        json.dumps(
            {
                "file_portability_passed": report["passed"],
                "diagnostic_status_consistent": report["diagnostic_status_consistent"],
                "api_comprehensive_health_qualified": False,
                "checks": len(report["checks"]),
                "actual_public_sdk_attempts": report["actual_public_sdk_attempts"],
            }
        )
    )


if __name__ == "__main__":
    main()
