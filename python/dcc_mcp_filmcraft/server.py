"""Official MCP stdio transport. Only the reviewed Core-registered tools are visible."""

import json

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from . import __version__


def build_server(adapter):
    server = Server("dcc-mcp-filmcraft", version=__version__)
    specs = {spec["name"]: spec for spec in adapter.tool_specs}

    @server.list_tools()
    async def list_tools():
        return [
            types.Tool(
                name=row["name"],
                description=row["description"],
                inputSchema=row["input_schema"],
                outputSchema=row["output_schema"],
                annotations=types.ToolAnnotations(
                    readOnlyHint=specs[row["name"]]["read_only"],
                    destructiveHint=(
                        adapter.mode == "native-headless" and specs[row["name"]]["operation"] == "reopen_project"
                    ),
                    idempotentHint=specs[row["name"]]["read_only"],
                    openWorldHint=False,
                ),
            )
            for row in adapter.registry.list_actions_enabled()
        ]

    @server.call_tool()
    async def call_tool(name, arguments):
        result = await adapter.call_async(name, arguments)
        if not result.get("ok", False):
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=json.dumps(result))],
                structuredContent=result,
                isError=True,
            )
        return result

    @server.list_prompts()
    async def list_prompts():
        return [
            types.Prompt(
                name=adapter.skill_name, description="Mode-specific FilmCraft create/edit/save/export workflow"
            )
        ]

    @server.get_prompt()
    async def get_prompt(name, arguments):
        if name != adapter.skill_name:
            raise ValueError("unknown prompt")
        from importlib.resources import files

        text = files("dcc_mcp_filmcraft").joinpath("skills", adapter.skill_name, "SKILL.md").read_text()
        return types.GetPromptResult(
            messages=[types.PromptMessage(role="user", content=types.TextContent(type="text", text=text))]
        )

    return server


async def run_stdio(adapter):
    server = build_server(adapter)
    async with stdio_server() as (reader, writer):
        await server.run(reader, writer, server.create_initialization_options())
