"""Test-only public SDK recorder checks; no vendor, subprocess or network."""

import asyncio
import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("mcp_proof_evidence", Path(__file__).parents[1] / "mcp_evidence.py")
evidence_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evidence_module)


class Reply:
    def __init__(self, raw):
        self.raw = raw

    def model_dump(self, **_):
        return copy.deepcopy(self.raw)


def test_actual_api_attempts_results_and_discovery_are_separate_from_catalog_size(tmp_path):
    report = {"checks": []}
    recorder = evidence_module.McpEvidence(report, tmp_path)

    async def respond(raw):
        return Reply(raw)

    async def scenario():
        await recorder.capture("initialize", {}, lambda: respond({"serverInfo": {"name": "fixture"}}))
        await recorder.capture(
            "tools/list",
            {},
            lambda: respond(
                {
                    "tools": [
                        {"name": "filmcraft_reopen_project"},
                        {"name": "filmcraft_list_jobs"},
                    ]
                }
            ),
        )
        await recorder.capture("prompts/list", {}, lambda: respond({"prompts": []}))
        await recorder.capture("prompts/get", {"name": "fixture"}, lambda: respond({"messages": []}))
        raw = {
            "isError": False,
            "structuredContent": {"ok": True, "result": {"intentional_restart": {"completed": True, "generation": 2}}},
        }
        result = await recorder.capture(
            "tools/call", {"name": "filmcraft_reopen_project", "arguments": {}}, lambda: respond(raw)
        )
        assert isinstance(result, Reply) and result.raw == raw
        await recorder.capture(
            "tools/call",
            {"name": "filmcraft_list_jobs", "arguments": {}},
            lambda: respond({"isError": False, "structuredContent": {"ok": True, "result": []}}),
        )
        await recorder.capture(
            "tools/call",
            {"name": "filmcraft_execute_code", "arguments": {}},
            lambda: respond({"isError": True, "content": [{"type": "text", "text": "fixture unsupported tool"}]}),
        )

    asyncio.run(scenario())
    summary = report["mcp_call_summary"]
    assert summary["discovery"]["attempted"] == summary["discovery"]["returned"] == 4
    assert summary["tools_call"]["attempted"] == summary["tools_call"]["returned"] == 3
    assert summary["tools_call"]["successful"] == 2 and summary["tools_call"]["mcp_errors"] == 1
    assert summary["tools_call"]["registered_attempted"] == 2
    assert summary["tools_call"]["unregistered_negative_attempted"] == 1
    assert summary["confirmed_child_restarts"] == 1
    assert report["rpc_count_scope"]["native_internal_rpc_count"] is None
    assert len(report["mcp_rpc_events"]) == 7
    saved = json.loads((tmp_path / "mcp-report.json").read_text())
    assert saved["mcp_rpc_events"][-1]["response"]["isError"] is True


def test_sdk_exception_is_recorded_once_with_unknown_dispatch_and_no_replay(tmp_path):
    report, calls = {}, []
    recorder = evidence_module.McpEvidence(report, tmp_path)
    recorder.tool_names.add("filmcraft_inspect")

    async def fail():
        calls.append("one explicit SDK API attempt")
        raise RuntimeError("fixture connection lost")

    with pytest.raises(RuntimeError, match="connection lost"):
        asyncio.run(recorder.capture("tools/call", {"name": "filmcraft_inspect", "arguments": {}}, fail))
    assert len(calls) == 1
    assert report["mcp_call_summary"]["tools_call"]["attempted"] == 1
    assert report["mcp_call_summary"]["tools_call"]["returned"] == 0
    assert report["mcp_call_summary"]["tools_call"]["client_exceptions"] == 1
    assert report["mcp_rpc_events"][0]["error"]["message"] == "fixture connection lost"
    assert json.loads((tmp_path / "mcp-report.json").read_text())["mcp_rpc_events"][0]["state"] == "client_exception"


def test_recording_import_data_preserves_actual_input_and_reports_its_hash(tmp_path):
    recorder = evidence_module.McpEvidence({}, tmp_path)
    raw = b"original fixture bytes; unchanged"
    params = {"name": "filmcraft_import_media", "arguments": {"data": base64.b64encode(raw).decode()}}
    before = copy.deepcopy(params)

    async def call():
        assert params == before
        return Reply({"isError": False, "structuredContent": {"ok": True, "result": {"items": [1]}}})

    asyncio.run(recorder.capture("tools/call", params, call))
    assert params == before
    assert recorder.events[0]["parameters"]["arguments"]["data"] == {
        "decoded_bytes": len(raw),
        "decoded_sha256": hashlib.sha256(raw).hexdigest(),
    }
