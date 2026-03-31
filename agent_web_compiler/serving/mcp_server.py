"""MCP server for agent-web-compiler.

Exposes compilation tools via the Model Context Protocol (MCP),
allowing AI assistants like Claude to compile webpages, HTML, PDFs,
and documents into agent-native structured objects.

Requires the `mcp` optional dependency: pip install agent-web-compiler[serve]
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger("agent_web_compiler.mcp")


def _check_mcp_available() -> None:
    """Raise ImportError with a helpful message if mcp is not installed."""
    try:
        import mcp  # noqa: F401
    except ImportError:
        raise ImportError(
            "The 'mcp' package is required for the MCP server. "
            "Install it with: pip install agent-web-compiler[serve]"
        ) from None


def _compile_url_sync(
    url: str,
    mode: str = "balanced",
    include_actions: bool = True,
    render: str = "off",
) -> dict[str, Any]:
    """Compile a URL and return the document as a dict."""
    from agent_web_compiler.api.compile import compile_url
    from agent_web_compiler.exporters.json_exporter import to_dict

    doc = compile_url(url, mode=mode, include_actions=include_actions, render=render)
    return to_dict(doc)


def _compile_html_sync(
    html: str,
    source_url: str | None = None,
    mode: str = "balanced",
) -> dict[str, Any]:
    """Compile raw HTML and return the document as a dict."""
    from agent_web_compiler.api.compile import compile_html
    from agent_web_compiler.exporters.json_exporter import to_dict

    doc = compile_html(html, source_url=source_url, mode=mode)
    return to_dict(doc)


def _compile_file_sync(
    path: str,
    mode: str = "balanced",
) -> dict[str, Any]:
    """Compile a local file and return the document as a dict."""
    from agent_web_compiler.api.compile import compile_file
    from agent_web_compiler.exporters.json_exporter import to_dict

    doc = compile_file(path, mode=mode)
    return to_dict(doc)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS: list[dict[str, Any]] = [
    {
        "name": "compile_url",
        "description": (
            "Compile a URL into an AgentDocument with semantic blocks, "
            "action affordances, and provenance."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch and compile.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["fast", "balanced", "high_recall"],
                    "default": "balanced",
                    "description": "Compilation mode controlling quality/speed tradeoff.",
                },
                "include_actions": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether to extract interactive action affordances.",
                },
                "render": {
                    "type": "string",
                    "enum": ["off", "auto", "always"],
                    "default": "off",
                    "description": "Browser rendering mode.",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "compile_html",
        "description": "Compile raw HTML into an AgentDocument.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "html": {
                    "type": "string",
                    "description": "Raw HTML string to compile.",
                },
                "source_url": {
                    "type": "string",
                    "description": "Optional source URL for provenance tracking.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["fast", "balanced", "high_recall"],
                    "default": "balanced",
                    "description": "Compilation mode.",
                },
            },
            "required": ["html"],
        },
    },
    {
        "name": "compile_file",
        "description": "Compile a local file (HTML or PDF) into an AgentDocument.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the file to compile.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["fast", "balanced", "high_recall"],
                    "default": "balanced",
                    "description": "Compilation mode.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "get_blocks",
        "description": (
            "Get semantic content blocks from a URL, "
            "optionally filtered by importance and type."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to compile and extract blocks from.",
                },
                "min_importance": {
                    "type": "number",
                    "default": 0.3,
                    "description": "Minimum importance threshold (0.0–1.0).",
                },
                "block_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter blocks to these types (e.g. heading, paragraph, table).",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "get_actions",
        "description": "Get interactive action affordances from a URL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to compile and extract actions from.",
                },
                "group": {
                    "type": "string",
                    "description": "Filter actions by group name.",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "get_markdown",
        "description": "Get a canonical markdown representation of a URL's content.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to compile.",
                },
                "max_blocks": {
                    "type": "integer",
                    "description": "Maximum number of blocks to include in the summary.",
                },
            },
            "required": ["url"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------


def _handle_compile_url(arguments: dict[str, Any]) -> str:
    """Handle the compile_url tool call."""
    result = _compile_url_sync(
        url=arguments["url"],
        mode=arguments.get("mode", "balanced"),
        include_actions=arguments.get("include_actions", True),
        render=arguments.get("render", "off"),
    )
    return json.dumps(result, indent=2, default=str, ensure_ascii=False)


def _handle_compile_html(arguments: dict[str, Any]) -> str:
    """Handle the compile_html tool call."""
    result = _compile_html_sync(
        html=arguments["html"],
        source_url=arguments.get("source_url"),
        mode=arguments.get("mode", "balanced"),
    )
    return json.dumps(result, indent=2, default=str, ensure_ascii=False)


def _handle_compile_file(arguments: dict[str, Any]) -> str:
    """Handle the compile_file tool call."""
    result = _compile_file_sync(
        path=arguments["path"],
        mode=arguments.get("mode", "balanced"),
    )
    return json.dumps(result, indent=2, default=str, ensure_ascii=False)


def _handle_get_blocks(arguments: dict[str, Any]) -> str:
    """Handle the get_blocks tool call."""
    from agent_web_compiler.api.compile import compile_url

    doc = compile_url(arguments["url"])
    min_importance = arguments.get("min_importance", 0.3)
    block_types = arguments.get("block_types")

    blocks = doc.get_main_content(min_importance=min_importance)
    if block_types:
        type_set = set(block_types)
        blocks = [b for b in blocks if b.type in type_set]

    blocks_data = [b.model_dump(mode="json") for b in blocks]
    return json.dumps(blocks_data, indent=2, default=str, ensure_ascii=False)


def _handle_get_actions(arguments: dict[str, Any]) -> str:
    """Handle the get_actions tool call."""
    from agent_web_compiler.api.compile import compile_url

    doc = compile_url(arguments["url"], include_actions=True)
    actions = doc.actions
    group = arguments.get("group")
    if group:
        actions = [a for a in actions if getattr(a, "group", None) == group]

    actions_data = [a.model_dump(mode="json") for a in actions]
    return json.dumps(actions_data, indent=2, default=str, ensure_ascii=False)


def _handle_get_markdown(arguments: dict[str, Any]) -> str:
    """Handle the get_markdown tool call."""
    from agent_web_compiler.api.compile import compile_url

    doc = compile_url(arguments["url"])
    max_blocks = arguments.get("max_blocks")
    if max_blocks is not None:
        return doc.summary_markdown(max_blocks=max_blocks)
    return doc.canonical_markdown


_TOOL_HANDLERS: dict[str, Any] = {
    "compile_url": _handle_compile_url,
    "compile_html": _handle_compile_html,
    "compile_file": _handle_compile_file,
    "get_blocks": _handle_get_blocks,
    "get_actions": _handle_get_actions,
    "get_markdown": _handle_get_markdown,
}


# ---------------------------------------------------------------------------
# Server creation and entry point
# ---------------------------------------------------------------------------


def create_server() -> Any:
    """Create and configure the MCP server instance.

    Returns:
        A configured mcp Server instance with all tools registered.

    Raises:
        ImportError: If the mcp package is not installed.
    """
    _check_mcp_available()

    from mcp.server import Server
    from mcp.types import TextContent, Tool

    server = Server("agent-web-compiler")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """Return the list of available tools."""
        return [
            Tool(
                name=t["name"],
                description=t["description"],
                inputSchema=t["inputSchema"],
            )
            for t in TOOLS
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Dispatch a tool call to the appropriate handler."""
        handler = _TOOL_HANDLERS.get(name)
        if handler is None:
            return [
                TextContent(
                    type="text",
                    text=json.dumps({"error": f"Unknown tool: {name}"}),
                )
            ]

        try:
            # Run synchronous compilation in a thread to avoid blocking
            result = await asyncio.to_thread(handler, arguments)
            return [TextContent(type="text", text=result)]
        except Exception as e:
            # Import here to avoid circular imports at module level
            from agent_web_compiler.core.errors import CompilerError

            if isinstance(e, CompilerError):
                error_msg = {
                    "error": str(e),
                    "stage": e.stage,
                    "context": e.context,
                }
            else:
                error_msg = {
                    "error": str(e),
                    "type": type(e).__name__,
                }
            logger.exception("Tool %s failed", name)
            return [
                TextContent(
                    type="text",
                    text=json.dumps(error_msg, default=str),
                )
            ]

    return server


async def run_stdio() -> None:
    """Run the MCP server using stdio transport.

    This is the main entry point for running the server,
    typically invoked from the CLI ``awc serve`` command.
    """
    _check_mcp_available()

    from mcp.server.stdio import stdio_server

    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    """Synchronous entry point — runs the stdio MCP server."""
    asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
