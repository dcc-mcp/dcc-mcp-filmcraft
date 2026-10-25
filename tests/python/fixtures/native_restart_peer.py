"""Explicit stdlib test child; models protocol state, never the FilmCraft engine."""

import json
import os
import sys
from pathlib import Path

project = {
    "name": "Untitled",
    "root": {"id": 0, "children": []},
    "path": None,
    "revision": 1,
    "dirty": False,
    "activeSequence": 8,
}
jobs = []
failed_open = False
commands = {
    "project.inspect",
    "jobs.list",
    "file.newProject",
    "file.saveAs",
    "file.open",
    "file.exportMedia",
    "jobs.cancel",
    "clip.rename",
    "sequence.inspect",
}


def tool_result(value):
    return {"content": [{"type": "text", "text": json.dumps(value)}]}


def handle(method, params):
    global project, failed_open
    if method == "initialize":
        return {
            "protocolVersion": "2025-03-26",
            "serverInfo": {"name": "filmcraft", "version": os.environ.get("FILM_FIXTURE_VERSION", "0.12.0")},
            "capabilities": {"tools": {}},
        }
    name, arguments = params["name"], params["arguments"]
    if name == "command_list":
        return tool_result([{"id": value} for value in sorted(commands)])
    if name == "media_import":
        project["root"]["children"] = [{"id": 1}]
        project["revision"] += 1
        project["dirty"] = True
        return tool_result({"items": [1], "errors": []})
    command, args = arguments["id"], arguments.get("params", {})
    value = {}
    if command == "project.inspect":
        if failed_open:
            return {
                "isError": True,
                "content": [{"type": "text", "text": "controlled secondary state readback refusal"}],
            }
        value = project
    elif command == "jobs.list":
        value = jobs
    elif command == "file.newProject":
        project.update(name=args["name"], revision=project["revision"] + 1, dirty=True)
    elif command == "clip.rename":
        project.update(revision=project["revision"] + 1, dirty=True)
    elif command == "file.saveAs":
        project.update(path=args["path"], dirty=False)
        Path(args["path"]).write_text(json.dumps(project))
    elif command == "file.open":
        if os.environ.get("FILM_FIXTURE_OPEN_AND_STATE_ERROR"):
            failed_open = True
            return {"isError": True, "content": [{"type": "text", "text": "controlled primary file.open refusal"}]}
        if os.environ.get("FILM_FIXTURE_EOF_OPEN"):
            sys.exit(0)
        if not os.environ.get("FILM_FIXTURE_NOOP_OPEN"):
            project = json.loads(Path(args["path"]).read_text())
        dirty = os.environ.get("FILM_FIXTURE_OPEN_DIRTY")
        if dirty == "missing":
            project.pop("dirty", None)
        elif dirty == "null":
            project["dirty"] = None
        elif dirty == "zero":
            project["dirty"] = 0
    elif command == "sequence.inspect":
        value = {
            "durationFrames": 24,
            "settings": {
                "width": 160,
                "height": 90,
                "frame_rate": {"num": 24, "den": 1},
                "sample_rate": 48000,
                "audio_master": "Stereo",
            },
        }
    elif command == "file.exportMedia":
        identifier = len(jobs) + 1
        jobs.append({"id": identifier, "finished": False})
        Path(args["path"]).write_bytes(b"fixture export; not rendered media")
        value = {"job": identifier}
    elif command == "jobs.cancel":
        next(row for row in jobs if row["id"] == args["job"]).update(finished=True, result={"error": "cancelled"})
    return tool_result(value)


for line in sys.stdin:
    request = json.loads(line)
    if "id" not in request:
        continue
    reply = {"jsonrpc": "2.0", "id": request["id"], "result": handle(request["method"], request.get("params", {}))}
    print(json.dumps(reply), flush=True)
