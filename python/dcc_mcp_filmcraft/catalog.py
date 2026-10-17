"""A reviewed bounded editing surface, not a copy of the upstream command catalog."""

from copy import deepcopy

NAME = {"type": "string", "minLength": 1, "maxLength": 128}
BASENAME = {"type": "string", "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$"}
ID = {"type": "integer", "minimum": 1, "maximum": 9007199254740991}
PATH = {"type": "string", "maxLength": 256}


def tool(name, description, properties=None, required=None, read_only=False):
    return {
        "name": "filmcraft_" + name,
        "operation": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": properties or {},
            "required": list(properties or {}) if required is None else required,
            "additionalProperties": False,
        },
        "read_only": read_only,
    }


TOOLS = [
    tool("inspect", "Inspect the same owned FilmCraft browser document.", read_only=True),
    tool("inspect_sequence", "Read the current sequence and clip IDs.", {"sequence": ID}, read_only=True),
    tool("create_project", "Create only in an empty clean editor; never replaces work.", {"name": NAME}),
    tool(
        "import_media",
        "Import one authorized base64 media file, at most 16 MiB; never reads OS paths.",
        {
            "name": {"type": "string", "pattern": "^[^/\\\\]{1,128}\\.(mp4|mov|webm|png|jpg|jpeg|wav)$"},
            "data": {"type": "string", "minLength": 4, "maxLength": 22369624},
        },
    ),
    tool("create_sequence", "Create a sequence from an imported media item.", {"name": NAME, "from_item": ID}),
    tool("rename_item", "Rename a project item and read back its new name.", {"item": ID, "name": NAME}),
    tool(
        "set_playback_rate",
        "Set a clip and linked audio rate, 25–400 percent; no concurrent UI edits.",
        {
            "sequence": ID,
            "clip": ID,
            "percent": {"type": "integer", "minimum": 25, "maximum": 400},
        },
    ),
    tool("undo", "Undo the last edit in the unchanged owned document."),
    tool("redo", "Redo the last edit in the unchanged owned document."),
    tool("save_project", "Save new native .fcproj bytes; returns an immutable artifact reference.", {"name": BASENAME}),
    tool(
        "reopen_project",
        "Reopen an unchanged save owned by this session, with its imported media still present.",
        {
            "path": PATH,
        },
    ),
    tool(
        "export_media",
        "Queue a new owned native export; use list_jobs until terminal before reading.",
        {
            "name": BASENAME,
            "sequence": ID,
            "format": {"enum": ["h264", "wav"]},
        },
    ),
    tool("list_jobs", "Read actual browser export jobs and terminal results.", read_only=True),
    tool("cancel_export", "Cancel only an export owned by this session; observe terminal state.", {"job": ID}),
    tool(
        "read_export",
        "Capture bounded bytes from an owned completed export into an immutable artifact.",
        {
            "path": PATH,
        },
        read_only=True,
    ),
    tool(
        "read_artifact",
        "Read a bounded base64 chunk of a session-owned artifact; no arbitrary filesystem access.",
        {
            "artifact": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
            "offset": {"type": "integer", "minimum": 0, "maximum": 33554432},
            "size": {"type": "integer", "minimum": 1, "maximum": 262144},
        },
        read_only=True,
    ),
    tool("capture_view", "Capture pixels of the same live editor into an immutable PNG artifact.", read_only=True),
    tool(
        "reconcile",
        "Read the original uncertain operation receipt without replay or reacquiring authority.",
        read_only=True,
    ),
    tool("disconnect", "Disconnect the typed client only after exports settle; preserves the document and files."),
]


def tools_for_mode(mode):
    """A headless engine cannot truthfully advertise a live editor screenshot."""
    if mode == "browser":
        return deepcopy(TOOLS)
    if mode != "native-headless":
        raise ValueError("unsupported FilmCraft execution mode")
    tools = [deepcopy(spec) for spec in TOOLS if spec["operation"] != "capture_view"]
    descriptions = {
        "inspect": "Inspect the same owned native FilmCraft engine session and its mode capabilities.",
        "list_jobs": "Read actual native engine export jobs and terminal results.",
        "import_media": "Import authorized base64 media bytes into this native session, at most 16 MiB.",
        "disconnect": "Disconnect after owned exports settle; preserve saved native files and cached artifacts.",
    }
    for spec in tools:
        spec["description"] = descriptions.get(spec["operation"], spec["description"])
    return tools
