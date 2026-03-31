"""Generate /content.json — structured block-level content feed.

Unlike agent.json which is a manifest, content.json provides the actual
block-level content for direct agent consumption. Agents can fetch this
instead of scraping HTML.

Schema:
{
    "version": "0.1.0",
    "site": "example.com",
    "generated_at": "...",
    "pages": [{
        "url": "/api",
        "title": "API Reference",
        "blocks": [{
            "id": "b_001",
            "type": "heading",
            "text": "Authentication",
            "section_path": ["API Reference", "Authentication"],
            "importance": 0.9,
            "entities": [...]
        }]
    }]
}
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from agent_web_compiler.core.block import Block
from agent_web_compiler.core.document import AgentDocument

# Blocks below this importance are considered noise and skipped
_MIN_IMPORTANCE = 0.2

# Max characters per block text
_MAX_TEXT_LENGTH = 500


def _serialize_block(block: Block) -> dict[str, Any]:
    """Serialize a single block to a content.json block dict."""
    text = block.text
    if len(text) > _MAX_TEXT_LENGTH:
        text = text[:_MAX_TEXT_LENGTH - 3] + "..."

    d: dict[str, Any] = {
        "id": block.id,
        "type": block.type.value,
        "text": text,
    }

    if block.section_path:
        d["section_path"] = block.section_path

    d["importance"] = round(block.importance, 2)

    entities = block.metadata.get("entities")
    if isinstance(entities, list) and entities:
        d["entities"] = entities

    return d


def _serialize_page(doc: AgentDocument) -> dict[str, Any]:
    """Serialize a single document to a content.json page dict."""
    blocks = [
        _serialize_block(b) for b in doc.blocks if b.importance >= _MIN_IMPORTANCE
    ]

    page: dict[str, Any] = {
        "url": doc.source_url or "",
        "title": doc.title,
        "block_count": len(blocks),
    }

    if doc.lang:
        page["language"] = doc.lang

    page["blocks"] = blocks
    return page


def generate_content_json(
    docs: list[AgentDocument],
    site_name: str = "",
    site_url: str = "",
    site_description: str = "",
) -> str:
    """Generate /content.json from compiled pages.

    Args:
        docs: Compiled AgentDocuments representing site pages.
        site_name: Site name (included in output metadata).
        site_url: The top-level site URL or domain.
        site_description: Brief site description (reserved for future use).

    Returns:
        JSON string conforming to the content.json schema.

    Raises:
        ValueError: If docs is empty.
    """
    if not docs:
        raise ValueError("At least one AgentDocument is required.")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    output: dict[str, Any] = {
        "version": "0.1.0",
        "site": site_url,
        "generated_at": now,
        "pages": [_serialize_page(doc) for doc in docs],
    }

    return json.dumps(output, indent=2, ensure_ascii=False)


def generate_agent_json(
    docs: list[AgentDocument],
    site_name: str = "",
    site_url: str = "",
    site_description: str = "",
) -> str:
    """Generate /agent.json from compiled pages.

    Delegates to the canonical agent.json generator in the standards module,
    providing a consistent interface for the publisher toolkit.

    Args:
        docs: Compiled AgentDocuments representing site pages.
        site_name: Site name (unused, kept for interface consistency).
        site_url: The top-level site URL or domain.
        site_description: Brief site description (unused, kept for interface consistency).

    Returns:
        JSON string conforming to the agent.json spec.
    """
    from agent_web_compiler.standards.agent_json import generate_agent_json_from_batch

    return generate_agent_json_from_batch(docs, site_url=site_url)
