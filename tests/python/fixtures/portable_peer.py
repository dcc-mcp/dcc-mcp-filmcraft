"""Explicit Python-only offline MCP peer; never counts as vendor qualification."""

import json
import sys

commands = [
    "file.open",
    "file.saveAs",
    "project.inspect",
    "sequence.inspect",
    "media.findMissing",
    "media.status",
    "file.exportMedia",
    "jobs.list",
]
for line in sys.stdin:
    request = json.loads(line)
    if "id" not in request:
        continue
    method = request["method"]
    if method == "initialize":
        value = {
            "protocolVersion": "2025-03-26",
            "serverInfo": {"name": "filmcraft", "version": "0.12.0"},
            "capabilities": {"tools": {}},
        }
    elif method == "tools/list":
        value = {
            "tools": [{"name": name, "inputSchema": {"type": "object"}} for name in ("command_list", "command_run")]
        }
    elif method == "tools/call":
        params = request["params"]
        if params["name"] == "command_list":
            result = [{"id": name} for name in commands]
        else:
            if params["arguments"]["id"] == "jobs.list" and "--early-eof" in sys.argv:
                break
            result = [] if params["arguments"]["id"] == "jobs.list" else {"fixture": True}
        value = {"content": [{"type": "text", "text": json.dumps(result)}], "isError": False}
    else:
        value = {}
    print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": value}), flush=True)
