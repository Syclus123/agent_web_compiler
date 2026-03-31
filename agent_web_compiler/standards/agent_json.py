"""agent.json — A proposed standard for agent-readable web content.

Similar to how robots.txt tells crawlers what to index and llms.txt tells
LLMs what a site is about, agent.json declares what an agent can DO on a site:
its content structure, available actions, and navigation paths.

This module generates agent.json from an AgentDocument, and can also
parse agent.json files back into AgentJsonSpec objects.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from agent_web_compiler.core.document import SCHEMA_VERSION, AgentDocument

# ---------------------------------------------------------------------------
# Spec data model
# ---------------------------------------------------------------------------


@dataclass
class PageSpec:
    """agent.json representation of a single page."""

    url: str = ""
    title: str = ""
    content: dict[str, Any] = field(default_factory=dict)
    actions: list[dict[str, Any]] = field(default_factory=list)
    navigation: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentJsonSpec:
    """The agent.json specification — a machine-readable site manifest."""

    version: str = "0.1.0"
    site: str = ""
    description: str = ""
    generated_by: str = f"agent-web-compiler/{SCHEMA_VERSION}"
    generated_at: str = ""
    pages: list[PageSpec] = field(default_factory=list)
    site_structure: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ENTITY_PATTERNS: list[str] = []  # reserved for future entity extraction


def _extract_block_type_counts(doc: AgentDocument) -> dict[str, int]:
    """Count occurrences of each block type."""
    counter: Counter[str] = Counter()
    for block in doc.blocks:
        counter[block.type.value] += 1
    return dict(counter.most_common())


def _extract_main_topics(doc: AgentDocument) -> list[str]:
    """Extract topic strings from heading blocks."""
    topics: list[str] = []
    for block in doc.blocks:
        if block.type.value == "heading" and block.text.strip():
            topics.append(block.text.strip())
    return topics


def _extract_key_entities(doc: AgentDocument) -> list[str]:
    """Extract notable entities (prices, dates, etc.) from block metadata."""
    entities: list[str] = []
    for block in doc.blocks:
        meta_entities = block.metadata.get("entities")
        if isinstance(meta_entities, list):
            entities.extend(str(e) for e in meta_entities)
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for e in entities:
        if e not in seen:
            seen.add(e)
            unique.append(e)
    return unique


def _action_to_dict(action: Any) -> dict[str, Any]:
    """Convert an Action model to an agent.json action dict."""
    d: dict[str, Any] = {
        "type": action.type.value if hasattr(action.type, "value") else str(action.type),
        "label": action.label,
    }
    if action.role:
        d["role"] = action.role
    if action.selector:
        d["selector"] = action.selector
    if action.required_fields:
        d["fields"] = action.required_fields
    if action.state_effect and action.state_effect.target_url:
        d["target"] = action.state_effect.target_url
    return d


def _extract_navigation(doc: AgentDocument) -> dict[str, Any]:
    """Build a navigation dict from document actions and navigation graph."""
    reachable: list[str] = []
    for action in doc.actions:
        if action.type.value == "navigate" and action.state_effect:
            url = action.state_effect.target_url
            if url and url not in reachable:
                reachable.append(url)

    nav: dict[str, Any] = {}
    if reachable:
        nav["reachable_pages"] = reachable
    if doc.navigation_graph:
        nav["graph"] = doc.navigation_graph
    return nav


def _build_page_spec(doc: AgentDocument) -> PageSpec:
    """Build a PageSpec from a single AgentDocument."""
    content: dict[str, Any] = {
        "block_types": _extract_block_type_counts(doc),
        "main_topics": _extract_main_topics(doc),
    }
    key_entities = _extract_key_entities(doc)
    if key_entities:
        content["key_entities"] = key_entities

    actions = [_action_to_dict(a) for a in doc.actions]
    navigation = _extract_navigation(doc)

    return PageSpec(
        url=doc.source_url or "",
        title=doc.title,
        content=content,
        actions=actions,
        navigation=navigation,
    )


def _build_site_structure(docs: list[AgentDocument]) -> dict[str, Any]:
    """Build site_structure from multiple documents."""
    template_elements: set[str] = set()
    common_actions: set[str] = set()

    for doc in docs:
        if doc.site_profile:
            if doc.site_profile.header_selectors:
                template_elements.add("header")
            if doc.site_profile.footer_selectors:
                template_elements.add("footer")
            if doc.site_profile.sidebar_selectors:
                template_elements.add("sidebar")

        for action in doc.actions:
            if action.role:
                common_actions.add(action.role)

    structure: dict[str, Any] = {}
    if template_elements:
        structure["template_elements"] = sorted(template_elements)
    if common_actions:
        structure["common_actions"] = sorted(common_actions)
    return structure


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_agent_json(doc: AgentDocument) -> str:
    """Generate an agent.json string from a compiled AgentDocument.

    Args:
        doc: A compiled AgentDocument.

    Returns:
        JSON string conforming to the agent.json spec.
    """
    return generate_agent_json_from_batch([doc], site_url=doc.source_url or "")


def generate_agent_json_from_batch(
    docs: list[AgentDocument], site_url: str
) -> str:
    """Generate a site-level agent.json from multiple compiled pages.

    Args:
        docs: List of AgentDocuments representing pages on the same site.
        site_url: The top-level site URL or domain.

    Returns:
        JSON string conforming to the agent.json spec.
    """
    if not docs:
        raise ValueError("At least one AgentDocument is required.")

    pages = [_build_page_spec(d) for d in docs]
    site_structure = _build_site_structure(docs)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    output: dict[str, Any] = {
        "agent_json_version": "0.1.0",
        "site": site_url,
        "generated_by": f"agent-web-compiler/{SCHEMA_VERSION}",
        "generated_at": now,
        "pages": [],
        "site_structure": site_structure,
    }

    for page in pages:
        page_dict: dict[str, Any] = {
            "url": page.url,
            "title": page.title,
            "content": page.content,
        }
        if page.actions:
            page_dict["actions"] = page.actions
        if page.navigation:
            page_dict["navigation"] = page.navigation
        output["pages"].append(page_dict)

    return json.dumps(output, indent=2, ensure_ascii=False)


def parse_agent_json(content: str) -> AgentJsonSpec:
    """Parse an agent.json file into a spec object.

    Args:
        content: Raw JSON string of an agent.json file.

    Returns:
        Parsed AgentJsonSpec.

    Raises:
        ValueError: If the JSON is invalid or missing required fields.
        json.JSONDecodeError: If the string is not valid JSON.
    """
    data = json.loads(content)

    if not isinstance(data, dict):
        raise ValueError("agent.json must be a JSON object at the top level.")

    pages_raw = data.get("pages", [])
    pages: list[PageSpec] = []
    for p in pages_raw:
        pages.append(
            PageSpec(
                url=p.get("url", ""),
                title=p.get("title", ""),
                content=p.get("content", {}),
                actions=p.get("actions", []),
                navigation=p.get("navigation", {}),
            )
        )

    return AgentJsonSpec(
        version=data.get("agent_json_version", "0.1.0"),
        site=data.get("site", ""),
        description=data.get("description", ""),
        generated_by=data.get("generated_by", ""),
        generated_at=data.get("generated_at", ""),
        pages=pages,
        site_structure=data.get("site_structure", {}),
        metadata=data.get("metadata", {}),
    )
