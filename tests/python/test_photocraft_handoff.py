"""Offline admission/oracle checks; these are not native consumer acceptance."""

import importlib.util
import struct
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "photocraft_handoff_e2e.py"
SPEC = importlib.util.spec_from_file_location("photocraft_handoff_e2e", SCRIPT)
handoff = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(handoff)


def test_procedural_source_is_bounded_untagged_rgb():
    data = handoff.calibration_png()
    result = handoff.inspect_png(data)
    assert result["width"] == 160
    assert result["height"] == 96
    assert result["alpha"] == "absent"
    assert result["color_chunks"] == []
    assert result["sha256"] == handoff.sha256(data)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: data[:-1],
        lambda data: data + b"extra",
        lambda data: b"not PNG",
        lambda data: data[:20] + b"x" + data[21:],
    ],
)
def test_corrupt_png_is_rejected_before_process_start(mutation):
    with pytest.raises(ValueError):
        handoff.inspect_png(mutation(handoff.calibration_png()))


@pytest.mark.parametrize("tag", [b"sRGB", b"gAMA", b"iCCP", b"cHRM", b"cICP", b"tRNS"])
def test_color_management_and_transparency_need_distinct_oracle(tag):
    data = handoff.calibration_png()
    with pytest.raises(ValueError, match="oracle"):
        handoff.inspect_png(data[:33] + handoff.png_chunk(tag, b"\0") + data[33:])


@pytest.mark.parametrize(
    "depth,color,width,height", [(16, 2, 160, 96), (8, 6, 160, 96), (8, 2, 4097, 96), (8, 2, 0, 96)]
)
def test_unqualified_png_contract_is_rejected(depth, color, width, height):
    data = handoff.calibration_png()
    header = handoff.png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, depth, color, 0, 0, 0))
    with pytest.raises(ValueError):
        handoff.inspect_png(data[:8] + header + data[33:])


def test_failed_check_cannot_mark_a_report_passed():
    report = {"passed": False, "checks": []}
    with pytest.raises(AssertionError):
        handoff.check(report, False, "simulated failed consumer readback")
    assert not report["passed"]
    assert report["checks"] == [{"name": "simulated failed consumer readback", "ok": False, "detail": None}]


def test_sequence_oracle_ignores_only_transient_selection():
    original = {"selection": [9], "durationFrames": 150, "settings": {"width": 160}, "video": [{"clip": 9}]}
    reopened = {**original, "selection": []}
    assert handoff.sequence_content(original) == handoff.sequence_content(reopened)
    for field, changed in [("durationFrames", 151), ("settings", {"width": 161}), ("video", [])]:
        assert handoff.sequence_content(original) != handoff.sequence_content({**reopened, field: changed})


def test_external_input_requires_producer_hash_without_creating_output(tmp_path):
    output = tmp_path / "not-created"
    with pytest.raises(ValueError, match="producer evidence"):
        handoff.main(
            [
                "--native-cli",
                "unused",
                "--expected-cli-sha256",
                "0" * 64,
                "--input-png",
                "unused.png",
                "--output",
                str(output),
            ]
        )
    assert not output.exists()


def test_mismatched_producer_hash_stops_before_native_cli(tmp_path):
    source = tmp_path / "source.png"
    source.write_bytes(handoff.calibration_png())
    output = tmp_path / "evidence"
    with pytest.raises(AssertionError, match="producer evidence"):
        handoff.main(
            [
                "--native-cli",
                "never-executed",
                "--expected-cli-sha256",
                "0" * 64,
                "--input-png",
                str(source),
                "--expected-input-sha256",
                "0" * 64,
                "--output",
                str(output),
            ]
        )
    import json

    report = json.loads((output / "handoff-report.json").read_text())
    assert report["passed"] is False
    assert report["mcp_calls"] == 0
    assert report["artifacts"] == []
