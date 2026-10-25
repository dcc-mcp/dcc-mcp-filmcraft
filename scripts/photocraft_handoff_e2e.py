"""Opt-in PNG -> genuine Core MCP -> FilmCraft save/reopen/H.264 proof.

This never opens a GUI. The trusted launcher supplies an official CLI and its
previously verified hash. Only opaque, untagged RGB8 PNG is admitted by this
narrow oracle. A passed run does not establish OCIO, scene-linear, alpha or
general PhotoCraft consumer compatibility.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_INPUT = 16 * 1024 * 1024
MAX_DIMENSION = 4096
COLOR_CHUNKS = {"sRGB", "gAMA", "iCCP", "cHRM", "cICP"}
ORACLE = {
    "metric": "RGB8 mean absolute channel error against independently decoded input",
    "maximum_mae": 18,
    "sample_frames": "first, middle, last; duplicate indices removed",
    "geometry": "exact input width and height",
    "timing": "exact native sequence durationFrames and frame_rate",
    "alpha": "input opaque RGB8; H.264 output has no alpha",
    "color": "untagged input; declared encoded-sRGB numeric intent, no host profile assignment proved",
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def png_chunk(kind, payload):
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))


def calibration_png(width=160, height=96):
    """Original opaque RGB test bars/gradient, with no color-profile chunks."""
    colors = [(224, 48, 48), (48, 208, 64), (48, 80, 224), (224, 208, 48)]
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            if y < height * 3 // 4:
                rows.extend(colors[min(x * len(colors) // width, len(colors) - 1)])
            else:
                value = 24 + x * 208 // max(width - 1, 1)
                rows.extend((value, value, value))
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + png_chunk(b"IDAT", zlib.compress(rows))
        + png_chunk(b"IEND", b"")
    )


def inspect_png(data):
    """Validate the bounded PNG container before starting any native process."""
    if not 0 < len(data) <= MAX_INPUT or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("input must be a PNG at most 16 MiB")
    position, chunks, header, finished = 8, [], None, False
    while position < len(data):
        if len(data) - position < 12:
            raise ValueError("truncated PNG chunk")
        size = struct.unpack_from(">I", data, position)[0]
        end = position + 12 + size
        if end > len(data):
            raise ValueError("PNG chunk exceeds input")
        kind = data[position + 4 : position + 8]
        payload = data[position + 8 : end - 4]
        crc = struct.unpack_from(">I", data, end - 4)[0]
        if zlib.crc32(kind + payload) != crc:
            raise ValueError("PNG CRC mismatch")
        name = kind.decode("ascii", errors="strict")
        if not chunks and name != "IHDR":
            raise ValueError("PNG must start with IHDR")
        if name == "IHDR":
            if header is not None or size != 13:
                raise ValueError("invalid PNG IHDR")
            header = struct.unpack(">IIBBBBB", payload)
        chunks.append(name)
        position = end
        if name == "IEND":
            if size or position != len(data):
                raise ValueError("invalid PNG IEND or trailing bytes")
            finished = True
            break
    if not finished or header is None or "IDAT" not in chunks:
        raise ValueError("incomplete PNG")
    width, height, depth, color_type, compression, filtering, interlace = header
    if not (0 < width <= MAX_DIMENSION and 0 < height <= MAX_DIMENSION):
        raise ValueError("PNG dimensions exceed the bounded oracle")
    if (depth, color_type, compression, filtering, interlace) != (8, 2, 0, 0, 0) or "tRNS" in chunks:
        raise ValueError("this oracle admits only noninterlaced opaque RGB8 PNG")
    color_chunks = [name for name in chunks if name in COLOR_CHUNKS]
    if color_chunks:
        raise ValueError("tagged PNG requires a separate color-management oracle")
    return {
        "width": width,
        "height": height,
        "bit_depth": depth,
        "mode": "RGB8",
        "alpha": "absent",
        "color_chunks": color_chunks,
        "color_intent": "encoded-sRGB numeric intent declared by this test; input is untagged",
        "bytes": len(data),
        "sha256": sha256(data),
    }


def check(report, condition, name, detail=None):
    report["checks"].append({"name": name, "ok": bool(condition), "detail": detail})
    if not condition:
        raise AssertionError(name)


def sequence_content(value):
    """Upstream save/reopen clears transient selection, not sequence content."""
    return {key: item for key, item in value.items() if key != "selection"}


def run_output(command):
    return subprocess.check_output(command, stderr=subprocess.PIPE, timeout=120)


def decode_rgb(path, frame=None):
    command = ["ffmpeg", "-v", "error", "-threads", "1", "-i", str(path), "-an"]
    if frame is not None:
        command += ["-vf", f"select=eq(n\\,{frame})"]
    command += ["-frames:v", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    return run_output(command)


def decoded_oracle(report, input_path, video_path, sequence, output):
    """No FilmCraft APIs are used for the independent output checks."""
    probe = json.loads(
        run_output(
            ["ffprobe", "-v", "error", "-count_frames", "-show_streams", "-show_format", "-of", "json", str(video_path)]
        )
    )
    (output / "export.ffprobe.json").write_text(json.dumps(probe, indent=2), encoding="utf-8")
    video = next(row for row in probe["streams"] if row["codec_type"] == "video")
    source = report["input"]
    check(report, video["codec_name"] == "h264", "independently decoded H.264")
    check(
        report,
        (video["width"], video["height"]) == (source["width"], source["height"]),
        "export geometry equals PNG geometry",
    )
    settings = sequence["settings"]
    count = int(video["nb_read_frames"])
    expected = sequence["durationFrames"]
    rate = settings["frame_rate"]
    check(
        report,
        count == expected and count > 0,
        "decoded frame count equals native sequence",
        {"actual": count, "expected": expected},
    )
    actual_num, actual_den = map(int, video["avg_frame_rate"].split("/"))
    check(
        report,
        actual_num * rate["den"] == actual_den * rate["num"],
        "decoded frame rate equals native sequence",
    )
    expected_duration = expected * rate["den"] / rate["num"]
    duration = float(video.get("duration", probe["format"]["duration"]))
    check(
        report,
        abs(duration - expected_duration) <= 0.1,
        "decoded duration equals native sequence",
        {"actual": duration, "expected": expected_duration},
    )
    reference = decode_rgb(input_path)
    check(report, len(reference) == source["width"] * source["height"] * 3, "independent PNG decoder geometry")
    report["input"]["decoded_rgb_sha256"] = sha256(reference)
    metrics = []
    for index in sorted({0, count // 2, count - 1}):
        pixels = decode_rgb(video_path, index)
        check(report, len(pixels) == len(reference), f"decoded frame {index} byte count")
        mae = sum(abs(a - b) for a, b in zip(reference, pixels, strict=True)) / len(reference)
        metrics.append({"frame": index, "mae": mae, "decoded_rgb_sha256": sha256(pixels)})
        check(report, mae <= ORACLE["maximum_mae"], f"frame {index} satisfies predeclared RGB8 error bound", mae)
    report["decoded_output"] = {
        "codec": video["codec_name"],
        "pixel_format": video.get("pix_fmt"),
        "color_range": video.get("color_range"),
        "color_space": video.get("color_space"),
        "color_transfer": video.get("color_transfer"),
        "color_primaries": video.get("color_primaries"),
        "frame_count": count,
        "duration_seconds": duration,
        "sample_metrics": metrics,
        "alpha_preserved": False,
        "host_profile_assignment_verified": False,
        "ocio_verified": False,
        "scene_linear_verified": False,
    }


async def exercise(args, report, input_path, data):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    output = args.output
    command = [
        "-m",
        "dcc_mcp_filmcraft.cli",
        "serve",
        "--mode",
        "native",
        "--native-cli",
        str(args.native_cli.resolve()),
        "--workspace",
        str((output / "workspace").resolve()),
        "--evidence-dir",
        str(output.resolve()),
    ]
    env = {**os.environ, "PYTHONPATH": str(ROOT / "python")}
    env["DCC_MCP_DISABLE_DEFAULT_SKILL_PATHS"] = "1"
    env["DCC_MCP_LOG_DIR"] = str((output / "logs").resolve())
    parameters = StdioServerParameters(command=sys.executable, args=command, env=env)
    with (output / "mcp.stderr.log").open("w", encoding="utf-8") as errlog:
        async with stdio_client(parameters, errlog=errlog) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                initialized = await client.initialize()
                report["mcp_protocol"] = initialized.protocolVersion
                tools = (await client.list_tools()).tools
                check(report, len(tools) == 18, "18 typed native Core tools discoverable")
                check(
                    report,
                    all(row.inputSchema.get("additionalProperties") is False for row in tools),
                    "typed schemas reject extra properties",
                )

                async def call(operation, arguments=None):
                    result = await client.call_tool("filmcraft_" + operation, arguments or {})
                    report["mcp_calls"] += 1
                    check(
                        report,
                        not result.isError,
                        "MCP " + operation,
                        result.structuredContent if result.isError else None,
                    )
                    return result.structuredContent["result"]

                async def artifact(meta, filename):
                    chunks, offset = bytearray(), 0
                    while True:
                        part = await call(
                            "read_artifact", {"artifact": meta["artifact"], "offset": offset, "size": 262144}
                        )
                        check(report, part["offset"] == offset, "artifact chunk offset")
                        raw = base64.b64decode(part["data"], validate=True)
                        check(
                            report,
                            len(raw) <= 262144 and part["next_offset"] == offset + len(raw),
                            "artifact chunk bounds",
                        )
                        chunks.extend(raw)
                        offset = part["next_offset"]
                        check(report, len(chunks) <= 32 * 1024 * 1024, "artifact total bound")
                        if part["eof"]:
                            break
                        check(report, bool(raw), "artifact read advances")
                    check(
                        report,
                        len(chunks) == meta["size"] and sha256(chunks) == meta["sha256"],
                        "artifact bytes/hash " + filename,
                    )
                    with (output / filename).open("xb") as stream:
                        stream.write(chunks)
                    report["artifacts"].append({"name": filename, "size": len(chunks), "sha256": sha256(chunks)})

                initial = await call("inspect")
                capabilities = initial["capabilities"]
                report["actual_runtime_version"] = capabilities.get("runtime_version")
                check(
                    report,
                    capabilities["mode"] == "native-headless" and capabilities["gui"] is False,
                    "owned native engine; no desktop claim",
                )
                await call("create_project", {"name": "PhotoCraft PNG through Core MCP"})
                imported = await call(
                    "import_media", {"name": "photocraft-handoff.png", "data": base64.b64encode(data).decode("ascii")}
                )
                check(
                    report,
                    len(imported.get("items", [])) == 1 and not imported.get("errors"),
                    "one imported PNG media item",
                )
                await call("create_sequence", {"name": "PhotoCraft still sequence", "from_item": imported["items"][0]})
                project = await call("inspect")
                sequence_id = project["activeSequence"]
                sequence = await call("inspect_sequence", {"sequence": sequence_id})
                report["sequence_before_save"] = sequence
                settings = sequence["settings"]
                check(
                    report,
                    (settings["width"], settings["height"]) == (report["input"]["width"], report["input"]["height"]),
                    "native imported PNG geometry",
                )
                check(report, sequence["durationFrames"] > 0, "still image has nonempty native duration")
                saved = await call("save_project", {"name": "photocraft-still"})
                await artifact(saved["bytes"], "photocraft-still.fcproj")
                await call("reopen_project", {"path": saved["path"]})
                reopened = await call("inspect_sequence", {"sequence": sequence_id})
                report["sequence_after_reopen"] = reopened
                report["transient_selection_readback"] = {
                    "before": sequence.get("selection"),
                    "after": reopened.get("selection"),
                    "required_to_persist": False,
                }
                check(
                    report,
                    sequence_content(sequence) == sequence_content(reopened),
                    "native project save/reopen preserves sequence content, settings and timing",
                )
                job = await call(
                    "export_media", {"name": "photocraft-still", "sequence": sequence_id, "format": "h264"}
                )
                report["owned_export_job"] = job["job"]
                deadline = time.monotonic() + 120
                while True:
                    jobs = await call("list_jobs")
                    row = next((value for value in jobs if value["id"] == job["job"]), None)
                    if row is not None and row.get("finished"):
                        break
                    if time.monotonic() >= deadline:
                        raise TimeoutError("owned export not terminal; mutation is not retried")
                    await asyncio.sleep(0.1)
                report["export_terminal"] = row
                check(
                    report,
                    not row.get("error") and not (row.get("result") or {}).get("error") and not row.get("offlineMedia"),
                    "owned H.264 export reached successful terminal state",
                )
                await artifact(await call("read_export", {"path": job["path"]}), "photocraft-still.mp4")
                disconnected = await call("disconnect")
                check(
                    report,
                    disconnected["filesPreserved"] and disconnected["documentPreserved"],
                    "disconnect preserves owned files/document until process closes",
                )
    report["owned_mcp_context_closed"] = True
    # Check the exact bytes copied into the private engine workspace as well as
    # the original source. These are test-owned file reads, not new agent tools.
    media = list((output / "workspace").glob("*/media-*.png"))
    check(
        report,
        len(media) == 1 and sha256(media[0].read_bytes()) == report["input"]["sha256"],
        "native imported media bytes equal original PNG hash",
    )
    check(report, input_path.read_bytes() == data, "source PNG remains unchanged")
    decoded_oracle(report, input_path, output / "photocraft-still.mp4", sequence, output)
    report["capability_validation"] = {
        "png_import": True,
        "native_save_and_same_session_reopen": True,
        "h264_export_and_independent_decode": True,
        "general_consumer_contract_completed": False,
        "gui_validated": False,
        "cross_restart_relinking_validated": False,
    }
    report["passed"] = True


def argument_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-cli", type=Path, required=True)
    parser.add_argument("--expected-cli-sha256", required=True, help="Previously verified official executable SHA-256")
    parser.add_argument(
        "--input-png", type=Path, help="Authorized PhotoCraft PNG; absent generates an original test fixture"
    )
    parser.add_argument(
        "--expected-input-sha256", help="Required with --input-png; independent producer evidence SHA-256"
    )
    parser.add_argument("--output", type=Path, default=ROOT / "evidence" / "photocraft-handoff")
    return parser


def main(argv=None):
    args = argument_parser().parse_args(argv)
    if args.input_png and not args.expected_input_sha256:
        raise ValueError("--input-png requires --expected-input-sha256 from producer evidence")
    if not args.input_png and args.expected_input_sha256:
        raise ValueError("--expected-input-sha256 requires --input-png")
    args.output.mkdir(parents=True, exist_ok=False)
    report = {
        "schema_version": 1,
        "passed": False,
        "transport": "genuine MCP stdio -> Core typed dispatcher -> owned official native CLI MCP",
        "mode": "native-headless",
        "checks": [],
        "mcp_calls": 0,
        "artifacts": [],
        "oracle_declared_before_execution": dict(ORACLE),
        "input_origin": "external producer evidence"
        if args.input_png
        else "original procedural fixture; not PhotoCraft producer proof",
        "general_consumer_contract_completed": False,
    }
    try:
        if args.input_png:
            input_path = args.input_png.resolve()
            if input_path.stat().st_size > MAX_INPUT:
                raise ValueError("PNG exceeds 16 MiB")
            data = input_path.read_bytes()
            check(report, sha256(data) == args.expected_input_sha256, "input SHA-256 matches producer evidence")
        else:
            input_path = args.output / "procedural-source.png"
            data = calibration_png()
            with input_path.open("xb") as stream:
                stream.write(data)
        report["input"] = inspect_png(data)
        check(report, args.native_cli.is_file(), "configured official CLI exists")
        digest = hashlib.sha256()
        with args.native_cli.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        cli_hash = digest.hexdigest()
        report["native_cli_sha256"] = cli_hash
        check(report, cli_hash == args.expected_cli_sha256, "CLI SHA-256 matches trusted launcher evidence")
        import dcc_mcp_core

        report["core_version"] = dcc_mcp_core.__version__
        asyncio.run(exercise(args, report, input_path, data))
    except BaseException as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)[:1000]}
        raise
    finally:
        (args.output / "handoff-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "passed": report["passed"],
                    "checks": len(report["checks"]),
                    "mcp_calls": report["mcp_calls"],
                    "report": str(args.output / "handoff-report.json"),
                }
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
