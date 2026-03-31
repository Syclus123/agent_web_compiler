"""LLM-optimized output formatters.

Each formatter takes an AgentDocument and produces a string optimized
for a specific LLM consumption pattern:

- AXTreeFormatter: Accessibility tree format (for OpenAI CUA, Computer Use agents)
- XMLFormatter: Structured XML (for Claude — XML is Claude's best structured format)
- FunctionCallFormatter: OpenAI function-calling schema (actions as tool definitions)
- CompactFormatter: Minimal text format for token-constrained contexts
- AgentPromptFormatter: Full system-prompt-ready format with context + actions + instructions
"""

from __future__ import annotations

import json
from typing import Any

from agent_web_compiler.core.action import Action, ActionType
from agent_web_compiler.core.block import Block, BlockType
from agent_web_compiler.core.document import AgentDocument

# ---------------------------------------------------------------------------
# AXTree Formatter — for CUA / Computer Use agents
# ---------------------------------------------------------------------------

def _axtree_role(block: Block) -> str:
    """Map block type to accessibility tree role name."""
    roles = {
        BlockType.HEADING: "heading",
        BlockType.PARAGRAPH: "paragraph",
        BlockType.LIST: "list",
        BlockType.TABLE: "table",
        BlockType.CODE: "code",
        BlockType.QUOTE: "blockquote",
        BlockType.FIGURE_CAPTION: "caption",
        BlockType.IMAGE: "image",
        BlockType.PRODUCT_SPEC: "description",
        BlockType.REVIEW: "article",
        BlockType.FAQ: "article",
        BlockType.FORM_HELP: "note",
        BlockType.METADATA: "note",
        BlockType.UNKNOWN: "generic",
    }
    return roles.get(block.type, "generic")


def _axtree_action_role(action: Action) -> str:
    """Map action type to an accessibility tree role."""
    roles = {
        ActionType.CLICK: "button",
        ActionType.INPUT: "textbox",
        ActionType.SELECT: "combobox",
        ActionType.TOGGLE: "checkbox",
        ActionType.UPLOAD: "button",
        ActionType.DOWNLOAD: "link",
        ActionType.NAVIGATE: "link",
        ActionType.SUBMIT: "button",
    }
    return roles.get(action.type, "button")


def _truncate(text: str, max_len: int = 120) -> str:
    """Truncate text with ellipsis for display labels."""
    text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _format_axtree_block(block: Block, counter: list[int]) -> list[str]:
    """Format a single block (and children) as AXTree lines.

    ``counter`` is a mutable list ``[current_id]`` that increments as nodes
    are emitted, ensuring unique sequential IDs.
    """
    lines: list[str] = []
    node_id = counter[0]
    counter[0] += 1

    role = _axtree_role(block)
    label = _truncate(block.text)
    attrs: list[str] = []

    if block.type == BlockType.HEADING and block.level:
        attrs.append(f"level={block.level}")
    if block.type == BlockType.TABLE:
        row_count = block.metadata.get("row_count", len(block.metadata.get("rows", [])))
        col_count = block.metadata.get("col_count", len(block.metadata.get("headers", [])))
        if row_count:
            attrs.append(f"rows={row_count}")
        if col_count:
            attrs.append(f"cols={col_count}")
    if block.type == BlockType.CODE:
        lang = block.metadata.get("language")
        if lang:
            attrs.append(f"lang={lang}")
    if block.importance >= 0.8:
        attrs.append("[primary]")

    # Bbox from provenance
    if block.provenance and block.provenance.page and block.provenance.page.bbox:
        bbox = block.provenance.page.bbox
        attrs.append(f"bbox={','.join(str(int(v)) for v in bbox)}")

    attr_str = " " + " ".join(attrs) if attrs else ""
    lines.append(f"[{node_id}] {role} \"{label}\"{attr_str}")

    # Table children: headers + rows as cells
    if block.type == BlockType.TABLE:
        headers = block.metadata.get("headers", [])
        rows = block.metadata.get("rows", [])
        for cell in headers:
            cell_id = f"{node_id}.{counter[0]}"
            counter[0] += 1
            lines.append(f"  [{cell_id}] cell \"{_truncate(str(cell))}\"")
        for row in rows:
            for cell in row:
                cell_id = f"{node_id}.{counter[0]}"
                counter[0] += 1
                lines.append(f"  [{cell_id}] cell \"{_truncate(str(cell))}\"")

    # List children
    if block.type == BlockType.LIST and block.children:
        for child in block.children:
            child_id = f"{node_id}.{counter[0]}"
            counter[0] += 1
            lines.append(f"  [{child_id}] listitem \"{_truncate(child.text)}\"")

    return lines


def _format_axtree_action(action: Action, counter: list[int]) -> str:
    """Format a single action as an AXTree line."""
    node_id = counter[0]
    counter[0] += 1

    role = _axtree_action_role(action)
    label = _truncate(action.label)
    attrs: list[str] = []

    if action.type == ActionType.NAVIGATE and action.state_effect and action.state_effect.target_url:
        attrs.append(f"url=\"{action.state_effect.target_url}\"")
    if action.selector:
        attrs.append(f"selector=\"{action.selector}\"")
    if action.priority >= 0.8:
        attrs.append("[primary]")

    # Value schema fields
    if action.value_schema and "properties" in action.value_schema:
        for field_name in action.value_schema["properties"]:
            attrs.append(f"name=\"{field_name}\"")

    attr_str = " " + " ".join(attrs) if attrs else ""
    return f"[{node_id}] {role} \"{label}\"{attr_str}"


class AXTreeFormatter:
    """Format AgentDocument as an accessibility tree.

    Produces a text representation that mirrors browser accessibility tree
    output, suitable for OpenAI CUA and Anthropic Computer Use agents.
    """

    def format(self, doc: AgentDocument) -> str:
        """Render the document as an AXTree string."""
        counter = [1]
        lines: list[str] = []

        # Group blocks by section
        current_section: str | None = None
        for block in doc.blocks:
            section = " > ".join(block.section_path) if block.section_path else None
            if section != current_section:
                current_section = section
                if section:
                    lines.append(f"--- {section} ---")

            lines.extend(_format_axtree_block(block, counter))

        # Actions section
        if doc.actions:
            lines.append("--- actions ---")
            for action in doc.actions:
                lines.append(_format_axtree_action(action, counter))

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# XML Formatter — for Claude
# ---------------------------------------------------------------------------

def _escape_xml(text: str) -> str:
    """Escape XML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _xml_block(block: Block, indent: int = 4) -> list[str]:
    """Convert a block to XML lines."""
    pad = " " * indent
    lines: list[str] = []

    tag = block.type.value
    attrs: dict[str, str] = {}

    if block.type == BlockType.HEADING and block.level:
        attrs["level"] = str(block.level)
    if block.importance != 0.5:
        attrs["importance"] = f"{block.importance:.1f}"
    if block.type == BlockType.CODE:
        lang = block.metadata.get("language")
        if lang:
            attrs["language"] = lang
    if block.type == BlockType.TABLE:
        row_count = block.metadata.get("row_count", len(block.metadata.get("rows", [])))
        col_count = block.metadata.get("col_count", len(block.metadata.get("headers", [])))
        if row_count:
            attrs["rows"] = str(row_count)
        if col_count:
            attrs["cols"] = str(col_count)

    attr_str = "".join(f' {k}="{_escape_xml(v)}"' for k, v in attrs.items())

    # Table with structured data
    if block.type == BlockType.TABLE:
        headers = block.metadata.get("headers")
        rows = block.metadata.get("rows")
        if headers or rows:
            lines.append(f"{pad}<{tag}{attr_str}>")
            if headers:
                lines.append(f"{pad}  <headers>{_escape_xml(' | '.join(str(h) for h in headers))}</headers>")
            if rows:
                for row in rows:
                    lines.append(f"{pad}  <row>{_escape_xml(' | '.join(str(c) for c in row))}</row>")
            lines.append(f"{pad}</{tag}>")
            return lines

    # List with children
    if block.type == BlockType.LIST and block.children:
        lines.append(f"{pad}<{tag}{attr_str}>")
        for child in block.children:
            lines.append(f"{pad}  <item>{_escape_xml(child.text)}</item>")
        lines.append(f"{pad}</{tag}>")
        return lines

    # Simple block
    text = _escape_xml(block.text)
    lines.append(f"{pad}<{tag}{attr_str}>{text}</{tag}>")
    return lines


def _xml_action(action: Action, indent: int = 4) -> list[str]:
    """Convert an action to XML lines."""
    pad = " " * indent
    lines: list[str] = []

    attrs: dict[str, str] = {
        "type": action.type.value,
        "label": action.label,
    }
    if action.selector:
        attrs["selector"] = action.selector
    if action.role:
        attrs["role"] = action.role
    if action.priority != 0.5:
        attrs["priority"] = f"{action.priority:.1f}"

    attr_str = "".join(f' {k}="{_escape_xml(v)}"' for k, v in attrs.items())

    has_children = False

    # Navigate actions with target URL
    target_url = None
    if action.state_effect and action.state_effect.target_url:
        target_url = action.state_effect.target_url

    # Fields from value schema
    fields: list[dict[str, str]] = []
    if action.value_schema and "properties" in action.value_schema:
        for name, schema in action.value_schema["properties"].items():
            field: dict[str, str] = {"name": name}
            if "type" in schema:
                field["type"] = schema["type"]
            if name in action.required_fields:
                field["required"] = "true"
            fields.append(field)

    has_children = bool(target_url or fields)

    if has_children:
        lines.append(f"{pad}<action{attr_str}>")
        if target_url:
            lines.append(f"{pad}  <url>{_escape_xml(target_url)}</url>")
        if fields:
            lines.append(f"{pad}  <fields>")
            for f in fields:
                f_attrs = "".join(f' {k}="{_escape_xml(v)}"' for k, v in f.items())
                lines.append(f"{pad}    <field{f_attrs}/>")
            lines.append(f"{pad}  </fields>")
        lines.append(f"{pad}</action>")
    else:
        lines.append(f"{pad}<action{attr_str}/>")

    return lines


class XMLFormatter:
    """Format AgentDocument as structured XML.

    Claude processes XML structure exceptionally well, making this the
    preferred format for Claude-based agents.
    """

    def format(self, doc: AgentDocument) -> str:
        """Render the document as an XML string."""
        attrs: dict[str, str] = {}
        if doc.title:
            attrs["title"] = doc.title
        if doc.source_url:
            attrs["url"] = doc.source_url
        attrs["blocks"] = str(doc.block_count)
        attrs["actions"] = str(doc.action_count)

        attr_str = "".join(f' {k}="{_escape_xml(v)}"' for k, v in attrs.items())
        lines: list[str] = [f"<document{attr_str}>"]

        # Group blocks by top-level section
        current_section: str | None = None
        section_open = False
        for block in doc.blocks:
            section = block.section_path[0] if block.section_path else None
            if section != current_section:
                if section_open:
                    lines.append("  </section>")
                current_section = section
                if section:
                    lines.append(f'  <section name="{_escape_xml(section)}">')
                    section_open = True
                else:
                    section_open = False
            lines.extend(_xml_block(block, indent=4 if section_open else 2))

        if section_open:
            lines.append("  </section>")

        # Actions
        if doc.actions:
            lines.append("  <actions>")
            for action in doc.actions:
                lines.extend(_xml_action(action, indent=4))
            lines.append("  </actions>")

        lines.append("</document>")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Function Call Formatter — for OpenAI function calling
# ---------------------------------------------------------------------------

def _action_to_function(action: Action) -> dict[str, Any]:
    """Convert an Action to an OpenAI function tool definition."""
    # Build a stable function name from role or id
    func_name = action.role or action.id
    # Sanitize: only alphanumeric and underscores
    func_name = "".join(c if c.isalnum() or c == "_" else "_" for c in func_name)

    description_parts: list[str] = [action.label]
    if action.state_effect and action.state_effect.target_url:
        description_parts.append(f"(url: {action.state_effect.target_url})")
    if action.selector:
        description_parts.append(f"(selector: {action.selector})")
    description = " ".join(description_parts)

    properties: dict[str, Any] = {}
    required: list[str] = []

    if action.value_schema and "properties" in action.value_schema:
        for name, schema in action.value_schema["properties"].items():
            prop: dict[str, str] = {}
            prop["type"] = schema.get("type", "string")
            if "description" in schema:
                prop["description"] = schema["description"]
            properties[name] = prop
            if name in action.required_fields:
                required.append(name)

    parameters: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        parameters["required"] = required

    return {
        "type": "function",
        "function": {
            "name": func_name,
            "description": description,
            "parameters": parameters,
        },
    }


class FunctionCallFormatter:
    """Format AgentDocument actions as OpenAI function-calling tool definitions.

    Produces a JSON object with page content and a list of available tools
    suitable for the OpenAI Chat Completions ``tools`` parameter.
    """

    def format(self, doc: AgentDocument) -> str:
        """Render the document as a JSON string with content and tools."""
        tools = [_action_to_function(action) for action in doc.actions]

        result: dict[str, Any] = {
            "content": doc.canonical_markdown or doc.summary_markdown(),
            "available_tools": tools,
        }

        return json.dumps(result, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Compact Formatter — for token-constrained contexts
# ---------------------------------------------------------------------------

class CompactFormatter:
    """Ultra-compact format for token-constrained contexts.

    Designed to convey maximum information in minimal tokens. Useful when
    the LLM context budget is severely limited (< 500 tokens).
    """

    def format(self, doc: AgentDocument) -> str:
        """Render the document in compact format."""
        parts: list[str] = []

        # Title
        if doc.title:
            parts.append(f"TITLE: {doc.title}")

        # Sections
        sections: list[str] = []
        seen: set[str] = set()
        for block in doc.blocks:
            if block.section_path:
                top = block.section_path[0]
                if top not in seen:
                    seen.add(top)
                    sections.append(top)
        if sections:
            parts.append(f"SECTIONS: {' | '.join(sections)}")

        # Key content — pick top blocks by importance
        key_blocks = sorted(doc.blocks, key=lambda b: b.importance, reverse=True)[:8]
        key_blocks.sort(key=lambda b: b.order)
        key_lines: list[str] = []
        for block in key_blocks:
            if block.type == BlockType.TABLE:
                row_count = block.metadata.get("row_count", len(block.metadata.get("rows", [])))
                key_lines.append(f"- Table: {row_count} rows")
            elif block.type == BlockType.CODE:
                lang = block.metadata.get("language", "")
                line_count = block.text.count("\n") + 1
                lang_str = f" {lang}" if lang else ""
                key_lines.append(f"- Code:{lang_str} ({line_count} lines)")
            elif block.type == BlockType.HEADING:
                continue  # sections already captured above
            else:
                key_lines.append(f"- {_truncate(block.text, 80)}")
        if key_lines:
            parts.append("KEY_CONTENT:\n" + "\n".join(key_lines))

        # Actions
        if doc.actions:
            action_strs: list[str] = []
            for action in doc.actions:
                name = action.role or action.id
                if action.required_fields:
                    fields = ",".join(action.required_fields)
                    action_strs.append(f"[{name}({fields})]")
                else:
                    action_strs.append(f"[{name}]")
            parts.append(f"ACTIONS: {' '.join(action_strs)}")

        # Entities from metadata
        entities: list[str] = []
        for block in doc.blocks:
            for entity in block.metadata.get("entities", []):
                if isinstance(entity, str) and entity not in entities:
                    entities.append(entity)
        if entities:
            parts.append(f"ENTITIES: {' | '.join(entities[:10])}")

        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Agent Prompt Formatter — full system prompt section
# ---------------------------------------------------------------------------

class AgentPromptFormatter:
    """Generate a complete system-prompt-ready section for an agent.

    Includes page content, available actions with details, page structure
    summary, and extracted entities — everything an LLM agent needs to
    decide its next action.
    """

    def format(self, doc: AgentDocument) -> str:
        """Render the document as a full agent prompt section."""
        parts: list[str] = []

        # Header
        title = doc.title or "Untitled"
        parts.append(f"## Current Page: {title}")
        header_lines: list[str] = []
        if doc.source_url:
            header_lines.append(f"Source: {doc.source_url}")
        header_lines.append(
            f"Compiled: {doc.compiled_at.strftime('%Y-%m-%dT%H:%M:%SZ')}"
            f" | Confidence: {doc.quality.parse_confidence:.1f}"
        )
        parts.append("\n".join(header_lines))

        # Content
        content = doc.canonical_markdown or doc.summary_markdown()
        parts.append(f"### Content ({doc.block_count} blocks)\n{content}")

        # Actions
        if doc.actions:
            action_lines: list[str] = []
            for i, action in enumerate(doc.actions, 1):
                type_label = action.type.value
                desc_parts: list[str] = [f"**{action.label}** [{type_label}]"]

                detail_parts: list[str] = []
                if action.role:
                    detail_parts.append(action.role)
                if action.selector:
                    detail_parts.append(f"selector: {action.selector}")
                if action.state_effect and action.state_effect.target_url:
                    detail_parts.append(f"url: {action.state_effect.target_url}")
                if detail_parts:
                    desc_parts.append(f"— {', '.join(detail_parts)}")

                line = f"{i}. {' '.join(desc_parts)}"

                if action.required_fields:
                    line += f"\n   Required: {', '.join(action.required_fields)}"

                action_lines.append(line)

            parts.append(
                f"### Available Actions ({doc.action_count})\n"
                + "\n".join(action_lines)
            )

        # Page structure summary
        structure_parts: list[str] = []
        sections: list[str] = []
        seen: set[str] = set()
        for block in doc.blocks:
            if block.section_path:
                top = block.section_path[0]
                if top not in seen:
                    seen.add(top)
                    sections.append(top)
        if sections:
            structure_parts.append(f"Sections: {' > '.join(sections)}")

        tables = doc.get_blocks_by_type("table")
        if tables:
            table_descs: list[str] = []
            for t in tables:
                rows = t.metadata.get("row_count", len(t.metadata.get("rows", [])))
                cols = t.metadata.get("col_count", len(t.metadata.get("headers", [])))
                table_descs.append(f"{rows}x{cols}" if rows and cols else "?")
            structure_parts.append(f"Tables: {', '.join(table_descs)}")

        code_blocks = doc.get_blocks_by_type("code")
        if code_blocks:
            langs = [b.metadata.get("language", "?") for b in code_blocks]
            structure_parts.append(f"Code blocks: {len(code_blocks)} ({', '.join(langs)})")

        if structure_parts:
            parts.append("### Page Structure\n" + "\n".join(structure_parts))

        # Entities
        entities: list[str] = []
        for block in doc.blocks:
            for entity in block.metadata.get("entities", []):
                if isinstance(entity, str) and entity not in entities:
                    entities.append(entity)
        if entities:
            parts.append("### Entities Found\n" + "\n".join(f"- {e}" for e in entities[:15]))

        return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Registry and public API
# ---------------------------------------------------------------------------

_FORMATTERS: dict[str, AXTreeFormatter | XMLFormatter | FunctionCallFormatter | CompactFormatter | AgentPromptFormatter] = {
    "axtree": AXTreeFormatter(),
    "xml": XMLFormatter(),
    "function_call": FunctionCallFormatter(),
    "compact": CompactFormatter(),
    "agent_prompt": AgentPromptFormatter(),
}


def format_for_llm(doc: AgentDocument, format: str = "markdown") -> str:
    """Format an AgentDocument for LLM consumption.

    Args:
        doc: The compiled document to format.
        format: One of ``"markdown"``, ``"axtree"``, ``"xml"``,
                ``"function_call"``, ``"compact"``, ``"agent_prompt"``.

    Returns:
        Formatted string optimized for the chosen LLM consumption pattern.

    Raises:
        ValueError: If *format* is not a recognized format name.
    """
    if format == "markdown":
        return doc.canonical_markdown or doc.summary_markdown()

    formatter = _FORMATTERS.get(format)
    if formatter is None:
        valid = ", ".join(sorted(["markdown", *_FORMATTERS.keys()]))
        raise ValueError(f"Unknown LLM format {format!r}. Valid formats: {valid}")

    return formatter.format(doc)


# Convenience functions -------------------------------------------------------

def to_axtree(doc: AgentDocument) -> str:
    """Format an AgentDocument as an accessibility tree string."""
    return AXTreeFormatter().format(doc)


def to_xml(doc: AgentDocument) -> str:
    """Format an AgentDocument as structured XML."""
    return XMLFormatter().format(doc)


def to_function_calls(doc: AgentDocument) -> str:
    """Format an AgentDocument's actions as OpenAI function-calling JSON."""
    return FunctionCallFormatter().format(doc)


def to_compact(doc: AgentDocument) -> str:
    """Format an AgentDocument in ultra-compact token-saving format."""
    return CompactFormatter().format(doc)


def to_agent_prompt(doc: AgentDocument) -> str:
    """Format an AgentDocument as a full agent system-prompt section."""
    return AgentPromptFormatter().format(doc)
