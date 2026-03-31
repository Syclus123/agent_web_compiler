"""Adapter for OpenAI-compatible agents.

Translates AgentDocument into formats that work with OpenAI's API:
- Accessibility tree format for CUA (Computer Use Agent)
- Tool definitions for function calling
- Structured content for chat completions
"""

from __future__ import annotations

from typing import Any

from agent_web_compiler.core.action import Action, ActionType
from agent_web_compiler.core.block import Block
from agent_web_compiler.core.document import AgentDocument


class OpenAIAdapter:
    """Produces OpenAI-compatible output from AgentDocument.

    All methods are pure transforms — no network calls, no framework dependency.
    """

    # ── CUA observation ──────────────────────────────────────────────

    def to_cua_observation(self, doc: AgentDocument) -> dict[str, Any]:
        """Format as a CUA observation with accessibility tree + screenshot.

        Returns a dict compatible with the OpenAI CUA API observation shape:
        ``{"type": "observation", "accessibility_tree": ..., "url": ..., "title": ...}``
        """
        tree = self._build_accessibility_tree(doc)
        return {
            "type": "observation",
            "url": doc.source_url or "",
            "title": doc.title,
            "accessibility_tree": tree,
            "action_count": doc.action_count,
        }

    # ── Chat messages ────────────────────────────────────────────────

    def to_chat_messages(
        self, doc: AgentDocument, role: str = "user"
    ) -> list[dict[str, Any]]:
        """Format as chat completion messages.

        Returns a list with a single message dict whose ``content`` is the
        compiled page represented as structured text (title, blocks, actions).
        """
        parts: list[str] = []

        if doc.title:
            parts.append(f"# {doc.title}")
        if doc.source_url:
            parts.append(f"URL: {doc.source_url}")

        parts.append("")  # blank line separator

        for block in doc.blocks:
            parts.append(self._block_to_text(block))

        if doc.actions:
            parts.append("\n## Available Actions")
            for action in doc.actions:
                parts.append(self._action_summary(action))

        return [{"role": role, "content": "\n".join(parts)}]

    # ── Tool / function definitions ──────────────────────────────────

    def to_tool_definitions(self, doc: AgentDocument) -> list[dict[str, Any]]:
        """Convert actions to OpenAI tool/function definitions.

        Each action becomes a tool definition suitable for the ``tools``
        parameter of the chat completions API.
        """
        tools: list[dict[str, Any]] = []
        for action in doc.actions:
            tool = self._action_to_tool(action)
            if tool is not None:
                tools.append(tool)
        return tools

    # ── Private helpers ──────────────────────────────────────────────

    @staticmethod
    def _build_accessibility_tree(doc: AgentDocument) -> str:
        """Build a text accessibility tree from blocks and actions."""
        lines: list[str] = []
        for block in doc.blocks:
            indent = "  " * len(block.section_path)
            type_tag = block.type.value.upper()
            lines.append(f"{indent}[{type_tag}] {block.text}")

        if doc.actions:
            lines.append("")
            lines.append("[ACTIONS]")
            for action in doc.actions:
                lines.append(f"  [{action.type.value.upper()}] {action.label} (id={action.id})")

        return "\n".join(lines)

    @staticmethod
    def _block_to_text(block: Block) -> str:
        """Render a block as plain text for chat messages."""
        if block.type.value == "heading":
            level = block.level or 2
            return f"{'#' * level} {block.text}"
        if block.type.value == "code":
            return f"```\n{block.text}\n```"
        return block.text

    @staticmethod
    def _action_summary(action: Action) -> str:
        """One-line summary of an action."""
        parts = [f"- **{action.label}**"]
        parts.append(f"(type={action.type.value}, id={action.id})")
        if action.selector:
            parts.append(f"[selector={action.selector}]")
        return " ".join(parts)

    @staticmethod
    def _action_to_tool(action: Action) -> dict[str, Any] | None:
        """Convert a single Action to an OpenAI tool definition."""
        parameters: dict[str, Any] = {
            "type": "object",
            "properties": {
                "action_id": {
                    "type": "string",
                    "description": f"Action identifier: {action.id}",
                    "const": action.id,
                },
            },
            "required": ["action_id"],
        }

        # Add value parameter for input-like actions
        if action.type in (ActionType.INPUT, ActionType.SELECT, ActionType.UPLOAD):
            parameters["properties"]["value"] = {
                "type": "string",
                "description": f"Value to enter for '{action.label}'",
            }
            parameters["required"].append("value")

        if action.value_schema:
            parameters["properties"]["value"] = action.value_schema

        return {
            "type": "function",
            "function": {
                "name": f"action_{action.id}",
                "description": action.label,
                "parameters": parameters,
            },
        }
