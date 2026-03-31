"""APICompiler — compiles JSON API responses into AgentDocuments.

Walks JSON structures and maps them to semantic blocks:
- Top-level keys → heading blocks
- String values → paragraph blocks
- Nested objects → sub-sections with section_path
- Arrays of objects → table blocks (each object is a row)
- Arrays of strings → list blocks
- Numbers/booleans → metadata blocks
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from agent_web_compiler.core.action import Action, ActionType, StateEffect
from agent_web_compiler.core.block import Block, BlockType
from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.core.document import AgentDocument, Quality, SourceType
from agent_web_compiler.core.errors import ParseError
from agent_web_compiler.exporters.markdown_exporter import to_markdown

logger = logging.getLogger(__name__)

# Keys that typically indicate pagination links in API responses
_PAGINATION_KEYS = frozenset({
    "next", "previous", "prev", "next_url", "prev_url",
    "next_page", "prev_page", "previous_url", "next_page_url",
    "previous_page_url",
})


class APICompiler:
    """Compiles JSON API responses into AgentDocuments.

    Parses JSON content (string or dict) and produces semantic blocks
    that represent the API response structure in an agent-friendly way.
    """

    def compile(
        self,
        content: str | dict[str, Any],
        *,
        source_url: str | None = None,
        config: CompileConfig | None = None,
    ) -> AgentDocument:
        """Compile a JSON API response into an AgentDocument.

        Args:
            content: JSON string or already-parsed dict.
            source_url: Optional URL of the API endpoint.
            config: Compilation configuration.

        Returns:
            An AgentDocument representing the API response.

        Raises:
            ParseError: If content is a string that cannot be parsed as JSON.
        """
        if config is None:
            config = CompileConfig()

        pipeline_start = time.perf_counter()
        timings: dict[str, float] = {}

        # --- Parse ---
        t0 = time.perf_counter()
        data = self._parse_json(content)
        timings["parse_ms"] = (time.perf_counter() - t0) * 1000

        # Determine raw string for doc_id
        if isinstance(content, str):
            raw_content = content
        else:
            raw_content = json.dumps(content, sort_keys=True, default=str)

        # --- Walk and build blocks ---
        t0 = time.perf_counter()
        blocks: list[Block] = []
        self._block_counter = 0
        self._walk(data, blocks, section_path=[])
        timings["segment_ms"] = (time.perf_counter() - t0) * 1000

        # --- Extract pagination actions ---
        actions: list[Action] = []
        if config.include_actions:
            t0 = time.perf_counter()
            actions = self._extract_pagination_actions(data)
            timings["extract_actions_ms"] = (time.perf_counter() - t0) * 1000

        # --- Build markdown ---
        t0 = time.perf_counter()
        canonical_markdown = to_markdown(blocks)
        timings["markdown_ms"] = (time.perf_counter() - t0) * 1000

        timings["total_ms"] = (time.perf_counter() - pipeline_start) * 1000

        # --- Build document ---
        doc_id = AgentDocument.make_doc_id(raw_content)

        debug: dict[str, Any] = {}
        if config.debug:
            debug["timings"] = timings

        return AgentDocument(
            doc_id=doc_id,
            source_type=SourceType.API,
            source_url=source_url,
            title=self._extract_title(data),
            blocks=blocks,
            canonical_markdown=canonical_markdown,
            actions=actions,
            quality=Quality(
                block_count=len(blocks),
                action_count=len(actions),
            ),
            compiled_at=datetime.now(timezone.utc),
            debug=debug,
        )

    def _parse_json(self, content: str | dict[str, Any]) -> Any:
        """Parse JSON string into Python object, or pass through dicts.

        Raises:
            ParseError: If string content is not valid JSON.
        """
        if isinstance(content, dict):
            return content

        if isinstance(content, str):
            try:
                return json.loads(content)
            except json.JSONDecodeError as exc:
                raise ParseError(
                    f"Invalid JSON content: {exc}",
                    context={"position": exc.pos},
                ) from exc

        # Handle lists and other types passed directly
        return content

    def _next_block_id(self) -> str:
        """Generate the next sequential block ID."""
        self._block_counter += 1
        return f"b_{self._block_counter:03d}"

    def _walk(
        self,
        data: Any,
        blocks: list[Block],
        section_path: list[str],
        *,
        heading_level: int = 1,
    ) -> None:
        """Recursively walk a JSON structure and emit blocks.

        Args:
            data: Current JSON node.
            blocks: Accumulator for emitted blocks.
            section_path: Current heading hierarchy.
            heading_level: Current heading depth (1-6).
        """
        if isinstance(data, dict):
            for key, value in data.items():
                # Skip pagination keys — handled by action extraction
                if key.lower() in _PAGINATION_KEYS:
                    continue

                current_path = [*section_path, key]
                level = min(heading_level, 6)

                # Emit a heading for this key
                blocks.append(Block(
                    id=self._next_block_id(),
                    type=BlockType.HEADING,
                    text=key,
                    section_path=section_path,
                    order=len(blocks),
                    level=level,
                    importance=max(0.3, 0.8 - 0.1 * level),
                ))

                self._emit_value(value, blocks, current_path, heading_level=level + 1)

        elif isinstance(data, list):
            self._emit_value(data, blocks, section_path, heading_level=heading_level)
        else:
            # Scalar at top level
            self._emit_value(data, blocks, section_path, heading_level=heading_level)

    def _emit_value(
        self,
        value: Any,
        blocks: list[Block],
        section_path: list[str],
        *,
        heading_level: int = 2,
    ) -> None:
        """Emit blocks for a JSON value.

        Args:
            value: The JSON value to convert.
            blocks: Accumulator for emitted blocks.
            section_path: Current heading hierarchy.
            heading_level: Current heading depth.
        """
        if isinstance(value, str):
            blocks.append(Block(
                id=self._next_block_id(),
                type=BlockType.PARAGRAPH,
                text=value,
                section_path=section_path,
                order=len(blocks),
                importance=0.5,
            ))

        elif isinstance(value, bool):
            blocks.append(Block(
                id=self._next_block_id(),
                type=BlockType.METADATA,
                text=str(value).lower(),
                section_path=section_path,
                order=len(blocks),
                importance=0.3,
                metadata={"value": value, "value_type": "boolean"},
            ))

        elif isinstance(value, (int, float)):
            blocks.append(Block(
                id=self._next_block_id(),
                type=BlockType.METADATA,
                text=str(value),
                section_path=section_path,
                order=len(blocks),
                importance=0.3,
                metadata={"value": value, "value_type": "number"},
            ))

        elif isinstance(value, list):
            if len(value) == 0:
                return

            # Array of objects → table
            if all(isinstance(item, dict) for item in value):
                self._emit_table(value, blocks, section_path)

            # Array of strings → list
            elif all(isinstance(item, str) for item in value):
                self._emit_list(value, blocks, section_path)

            # Mixed array — emit each item
            else:
                for item in value:
                    self._emit_value(
                        item, blocks, section_path, heading_level=heading_level
                    )

        elif isinstance(value, dict):
            self._walk(value, blocks, section_path, heading_level=heading_level)

        elif value is None:
            # Skip null values silently
            pass

    def _emit_table(
        self,
        items: list[dict[str, Any]],
        blocks: list[Block],
        section_path: list[str],
    ) -> None:
        """Emit a table block from an array of objects.

        Uses the union of all keys as headers. Each object becomes a row.
        """
        # Collect headers preserving insertion order from all items
        headers: list[str] = []
        seen: set[str] = set()
        for item in items:
            for key in item:
                if key not in seen:
                    headers.append(key)
                    seen.add(key)

        rows: list[list[str]] = []
        for item in items:
            row = [str(item.get(h, "")) for h in headers]
            rows.append(row)

        # Build text representation
        text_parts = [" | ".join(headers)]
        for row in rows:
            text_parts.append(" | ".join(row))
        text = "\n".join(text_parts)

        blocks.append(Block(
            id=self._next_block_id(),
            type=BlockType.TABLE,
            text=text,
            section_path=section_path,
            order=len(blocks),
            importance=0.6,
            metadata={
                "headers": headers,
                "rows": rows,
                "row_count": len(rows),
                "col_count": len(headers),
            },
        ))

    def _emit_list(
        self,
        items: list[str],
        blocks: list[Block],
        section_path: list[str],
    ) -> None:
        """Emit a list block from an array of strings."""
        text = "\n".join(items)
        children = [
            Block(
                id=self._next_block_id(),
                type=BlockType.PARAGRAPH,
                text=item,
                section_path=section_path,
                order=len(blocks) + i + 1,
                importance=0.4,
            )
            for i, item in enumerate(items)
        ]

        blocks.append(Block(
            id=self._next_block_id(),
            type=BlockType.LIST,
            text=text,
            section_path=section_path,
            order=len(blocks),
            importance=0.5,
            children=children,
        ))

    def _extract_pagination_actions(self, data: Any) -> list[Action]:
        """Extract pagination navigate actions from the JSON data.

        Looks for common pagination keys like 'next', 'previous', 'next_url', etc.
        """
        if not isinstance(data, dict):
            return []

        actions: list[Action] = []
        action_counter = 0

        for key, value in data.items():
            if key.lower() not in _PAGINATION_KEYS:
                continue
            if not isinstance(value, str) or not value:
                continue

            action_counter += 1
            is_next = "next" in key.lower()
            role = "next_page" if is_next else "previous_page"
            label = "Next page" if is_next else "Previous page"

            actions.append(Action(
                id=f"a_pagination_{action_counter}",
                type=ActionType.NAVIGATE,
                label=label,
                role=role,
                selector=None,
                confidence=0.9,
                priority=0.7,
                group="pagination",
                state_effect=StateEffect(
                    may_navigate=True,
                    target_url=value,
                ),
            ))

        return actions

    @staticmethod
    def _extract_title(data: Any) -> str:
        """Extract a title from the JSON data.

        Looks for common title-like keys at the top level.
        """
        if not isinstance(data, dict):
            return ""

        for key in ("title", "name", "label", "heading"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value

        return ""
