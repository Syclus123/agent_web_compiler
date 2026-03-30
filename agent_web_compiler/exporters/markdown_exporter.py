"""Markdown exporter — converts blocks to canonical markdown."""

from __future__ import annotations

from agent_web_compiler.core.block import Block, BlockType


def to_markdown(blocks: list[Block]) -> str:
    """Convert a list of blocks to canonical markdown.

    Each block type maps to a specific markdown representation:
    - HEADING: ATX headings (# level)
    - PARAGRAPH: plain text
    - LIST: "- " prefixed items
    - TABLE: pipe-separated markdown table
    - CODE: fenced code blocks
    - QUOTE: "> " prefixed lines
    - FIGURE_CAPTION: italic text
    - IMAGE: ![](image)
    - Others: plain text

    Args:
        blocks: Ordered list of semantic blocks.

    Returns:
        Canonical markdown string.
    """
    parts: list[str] = []

    for block in blocks:
        md = _block_to_markdown(block)
        if md:
            parts.append(md)

    return "\n\n".join(parts)


def _block_to_markdown(block: Block) -> str:
    """Convert a single block to its markdown representation."""
    if block.type == BlockType.HEADING:
        level = block.level if block.level and 1 <= block.level <= 6 else 1
        prefix = "#" * level
        return f"{prefix} {block.text}"

    if block.type == BlockType.PARAGRAPH:
        return block.text + "\n"

    if block.type == BlockType.LIST:
        return _render_list(block)

    if block.type == BlockType.TABLE:
        return _render_table(block)

    if block.type == BlockType.CODE:
        language = block.metadata.get("language", "")
        return f"```{language}\n{block.text}\n```"

    if block.type == BlockType.QUOTE:
        lines = block.text.splitlines()
        return "\n".join(f"> {line}" for line in lines)

    if block.type == BlockType.FIGURE_CAPTION:
        return f"*{block.text}*"

    if block.type == BlockType.IMAGE:
        src = block.metadata.get("src", "image")
        alt = block.metadata.get("alt", "")
        return f"![{alt}]({src})"

    # All other types: plain text
    return block.text


def _render_list(block: Block) -> str:
    """Render a list block as markdown bullet list."""
    if block.children:
        return "\n".join(f"- {child.text}" for child in block.children)
    # Fall back to splitting text on newlines
    lines = block.text.splitlines()
    return "\n".join(f"- {line}" for line in lines if line.strip())


def _render_table(block: Block) -> str:
    """Render a table block as a markdown table.

    Uses metadata rows/headers if available, otherwise returns text as-is.
    """
    headers: list[str] | None = block.metadata.get("headers")
    rows: list[list[str]] | None = block.metadata.get("rows")

    if headers and rows is not None:
        header_line = "| " + " | ".join(headers) + " |"
        separator = "| " + " | ".join("---" for _ in headers) + " |"
        body_lines = [
            "| " + " | ".join(str(cell) for cell in row) + " |" for row in rows
        ]
        return "\n".join([header_line, separator, *body_lines])

    # No structured data — return raw text
    return block.text
