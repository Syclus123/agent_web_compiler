"""Adapter for Anthropic Claude agents.

Translates AgentDocument into Claude-optimal formats:
- XML structured content (Claude excels at XML parsing)
- Computer Use tool results
- Tool definitions for tool_use
"""

from __future__ import annotations

from typing import Any
from xml.sax.saxutils import escape as xml_escape

from agent_web_compiler.core.action import Action, ActionType
from agent_web_compiler.core.block import Block
from agent_web_compiler.core.document import AgentDocument


class AnthropicAdapter:
    """Produces Claude-compatible output from AgentDocument.

    All methods are pure transforms — no network calls, no framework dependency.
    """

    # ── Computer Use tool result ─────────────────────────────────────

    def to_computer_use_result(self, doc: AgentDocument) -> dict[str, Any]:
        """Format as a computer_use tool result with structured content.

        Returns a dict compatible with the Anthropic computer_use API shape.
        The ``content`` field contains XML-structured page data so that
        Claude can reason over it without a raw screenshot.
        """
        xml = self.to_xml_content(doc)
        return {
            "type": "tool_result",
            "tool_use_id": "",  # caller fills in the actual tool_use_id
            "content": xml,
            "metadata": {
                "url": doc.source_url or "",
                "title": doc.title,
                "block_count": doc.block_count,
                "action_count": doc.action_count,
                "confidence": doc.quality.parse_confidence,
            },
        }

    # ── XML content ──────────────────────────────────────────────────

    def to_xml_content(self, doc: AgentDocument) -> str:
        """Format as XML for optimal Claude consumption.

        Claude processes XML structure exceptionally well. The output wraps
        blocks, actions, and metadata in descriptive tags.
        """
        parts: list[str] = ['<page>']

        # Metadata
        parts.append("  <metadata>")
        if doc.title:
            parts.append(f"    <title>{xml_escape(doc.title)}</title>")
        if doc.source_url:
            parts.append(f"    <url>{xml_escape(doc.source_url)}</url>")
        if doc.lang:
            parts.append(f"    <lang>{xml_escape(doc.lang)}</lang>")
        parts.append(f"    <confidence>{doc.quality.parse_confidence}</confidence>")
        parts.append("  </metadata>")

        # Blocks
        parts.append("  <content>")
        for block in doc.blocks:
            parts.append(self._block_to_xml(block, indent=4))
        parts.append("  </content>")

        # Actions
        if doc.actions:
            parts.append("  <actions>")
            for action in doc.actions:
                parts.append(self._action_to_xml(action, indent=4))
            parts.append("  </actions>")

        parts.append("</page>")
        return "\n".join(parts)

    # ── Tool definitions ─────────────────────────────────────────────

    def to_tool_definitions(self, doc: AgentDocument) -> list[dict[str, Any]]:
        """Convert actions to Anthropic tool definitions.

        Returns a list of tool dicts suitable for the ``tools`` parameter
        of the Anthropic Messages API.
        """
        tools: list[dict[str, Any]] = []
        for action in doc.actions:
            tool = self._action_to_tool(action)
            if tool is not None:
                tools.append(tool)
        return tools

    # ── Private helpers ──────────────────────────────────────────────

    @staticmethod
    def _block_to_xml(block: Block, indent: int = 0) -> str:
        """Render a block as an XML element."""
        pad = " " * indent
        attrs = f' id="{xml_escape(block.id)}" type="{block.type.value}"'
        if block.importance != 0.5:
            attrs += f' importance="{block.importance}"'
        if block.section_path:
            path_str = xml_escape(" > ".join(block.section_path))
            attrs += f' section="{path_str}"'
        if block.level is not None:
            attrs += f' level="{block.level}"'

        text = xml_escape(block.text)
        return f"{pad}<block{attrs}>{text}</block>"

    @staticmethod
    def _action_to_xml(action: Action, indent: int = 0) -> str:
        """Render an action as an XML element."""
        pad = " " * indent
        attrs = f' id="{xml_escape(action.id)}" type="{action.type.value}"'
        if action.selector:
            attrs += f' selector="{xml_escape(action.selector)}"'
        if action.role:
            attrs += f' role="{xml_escape(action.role)}"'
        if action.group:
            attrs += f' group="{xml_escape(action.group)}"'
        label = xml_escape(action.label)
        return f"{pad}<action{attrs}>{label}</action>"

    @staticmethod
    def _action_to_tool(action: Action) -> dict[str, Any] | None:
        """Convert a single Action to an Anthropic tool definition."""
        input_schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "action_id": {
                    "type": "string",
                    "description": f"Action identifier: {action.id}",
                },
            },
            "required": ["action_id"],
        }

        if action.type in (ActionType.INPUT, ActionType.SELECT, ActionType.UPLOAD):
            input_schema["properties"]["value"] = {
                "type": "string",
                "description": f"Value to provide for '{action.label}'",
            }
            input_schema["required"].append("value")

        if action.value_schema:
            input_schema["properties"]["value"] = action.value_schema

        return {
            "name": f"action_{action.id}",
            "description": action.label,
            "input_schema": input_schema,
        }
