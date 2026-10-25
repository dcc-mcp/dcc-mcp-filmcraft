"""Test-only recording around public SDK methods, never a transport or replay path."""

import base64
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path


class McpEvidence:
    def __init__(self, report, output):
        self.report, self.output = report, Path(output)
        self.events = report.setdefault("mcp_rpc_events", [])
        self.tool_names = set()
        report["rpc_count_scope"] = {
            "counted": "explicit public ClientSession API attempts and returned responses in this case",
            "recording_boundary": "public SDK models; JSON-RPC framing is not intercepted",
            "sdk_managed_notifications_counted": False,
            "native_internal_rpc_count": None,
            "native_internal_rpc_reason": "vendor internal RPC is not instrumented or inferred from Core tool calls",
        }

    @staticmethod
    def parameters(params):
        value = copy.deepcopy(params)
        arguments = value.get("arguments", {})
        if isinstance(arguments.get("data"), str):
            encoded = arguments["data"]
            try:
                raw = base64.b64decode(encoded, validate=True)
                arguments["data"] = {"decoded_bytes": len(raw), "decoded_sha256": hashlib.sha256(raw).hexdigest()}
            except ValueError:
                arguments["data"] = {"encoded_characters": len(encoded), "invalid_base64": True}
        return value

    def summary(self):
        discovery = [row for row in self.events if row["method"] != "tools/call"]
        tools = [row for row in self.events if row["method"] == "tools/call"]

        def counts(rows):
            return {
                "attempted": len(rows),
                "returned": sum(row["state"] == "returned" for row in rows),
                "client_exceptions": sum(row["state"] == "client_exception" for row in rows),
            }

        return {
            "discovery": {**counts(discovery), "by_method": dict(Counter(row["method"] for row in discovery))},
            "tools_call": {
                **counts(tools),
                "successful": sum(row.get("is_error") is False for row in tools),
                "mcp_errors": sum(row.get("is_error") is True for row in tools),
                "registered_attempted": sum(row["registered_tool"] for row in tools),
                "unregistered_negative_attempted": sum(not row["registered_tool"] for row in tools),
                "by_tool_attempted": dict(Counter(row["parameters"]["name"] for row in tools)),
            },
            "confirmed_child_restarts": sum(bool(row.get("confirmed_child_restart")) for row in tools),
        }

    def persist(self):
        self.report["mcp_call_summary"] = self.summary()
        (self.output / "mcp-report.json").write_text(json.dumps(self.report, indent=2), encoding="utf-8")

    async def capture(self, method, params, operation):
        """Call the existing SDK method exactly once; store raw result before assertions."""
        row = {
            "index": len(self.events) + 1,
            "method": method,
            "parameters": self.parameters(params),
            "state": "started",
        }
        if method == "tools/call":
            row["registered_tool"] = params["name"] in self.tool_names
        self.events.append(row)
        self.persist()
        try:
            result = await operation()
            raw = result.model_dump(mode="json", by_alias=True, exclude_none=True)
            row.update(state="returned", response=raw)
            if method == "tools/list":
                self.tool_names.update(tool["name"] for tool in raw["tools"])
            if method == "tools/call":
                row["is_error"] = bool(raw.get("isError", False))
                business = (raw.get("structuredContent") or {}).get("result")
                receipt = business.get("intentional_restart") if isinstance(business, dict) else None
                if not row["is_error"] and isinstance(receipt, dict) and receipt.get("completed") is True:
                    row["confirmed_child_restart"] = receipt
            self.persist()
            return result
        except BaseException as exc:
            row.update(
                state="client_exception",
                error={"type": type(exc).__name__, "message": str(exc)[:2000]},
                dispatch_known=False,
            )
            self.persist()
            raise
