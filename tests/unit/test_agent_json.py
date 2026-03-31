"""Tests for agent.json generation and parsing."""

from __future__ import annotations

import json

import pytest

from agent_web_compiler.core.action import Action, ActionType, StateEffect
from agent_web_compiler.core.block import Block, BlockType
from agent_web_compiler.core.document import AgentDocument, SiteProfile, SourceType
from agent_web_compiler.standards.agent_json import (
    generate_agent_json,
    generate_agent_json_from_batch,
    parse_agent_json,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc(
    title: str = "Test Page",
    source_url: str = "https://example.com/page",
    blocks: list[Block] | None = None,
    actions: list[Action] | None = None,
    site_profile: SiteProfile | None = None,
) -> AgentDocument:
    return AgentDocument(
        doc_id="sha256:abc123",
        source_type=SourceType.HTML,
        source_url=source_url,
        title=title,
        blocks=blocks or [],
        actions=actions or [],
        site_profile=site_profile,
    )


def _block(id: str, btype: BlockType, text: str) -> Block:
    return Block(id=id, type=btype, text=text)


def _action(
    id: str,
    atype: ActionType,
    label: str,
    role: str | None = None,
    selector: str | None = None,
    target_url: str | None = None,
    required_fields: list[str] | None = None,
) -> Action:
    state_effect = None
    if target_url:
        state_effect = StateEffect(may_navigate=True, target_url=target_url)
    return Action(
        id=id,
        type=atype,
        label=label,
        role=role,
        selector=selector,
        state_effect=state_effect,
        required_fields=required_fields or [],
    )


# ---------------------------------------------------------------------------
# generate_agent_json
# ---------------------------------------------------------------------------


class TestGenerateAgentJson:
    def test_basic_generation(self):
        doc = _make_doc(
            blocks=[
                _block("b1", BlockType.HEADING, "Products"),
                _block("b2", BlockType.PARAGRAPH, "We sell widgets."),
            ],
            actions=[
                _action("a1", ActionType.SUBMIT, "Search", role="search", required_fields=["q"]),
            ],
        )
        result = generate_agent_json(doc)
        data = json.loads(result)

        assert data["agent_json_version"] == "0.1.0"
        assert data["site"] == "https://example.com/page"
        assert "agent-web-compiler" in data["generated_by"]
        assert len(data["pages"]) == 1
        page = data["pages"][0]
        assert page["title"] == "Test Page"
        assert page["content"]["block_types"]["heading"] == 1
        assert page["content"]["block_types"]["paragraph"] == 1
        assert page["content"]["main_topics"] == ["Products"]

    def test_actions_included(self):
        doc = _make_doc(
            actions=[
                _action("a1", ActionType.CLICK, "Add to Cart", role="add_to_cart", selector=".btn-cart"),
                _action("a2", ActionType.NAVIGATE, "Next", target_url="/page/2"),
            ],
        )
        result = generate_agent_json(doc)
        data = json.loads(result)
        actions = data["pages"][0]["actions"]
        assert len(actions) == 2
        assert actions[0]["type"] == "click"
        assert actions[0]["role"] == "add_to_cart"
        assert actions[0]["selector"] == ".btn-cart"

    def test_navigation_extracted(self):
        doc = _make_doc(
            actions=[
                _action("a1", ActionType.NAVIGATE, "Next", target_url="/page/2"),
                _action("a2", ActionType.NAVIGATE, "Prev", target_url="/page/1"),
            ],
        )
        result = generate_agent_json(doc)
        data = json.loads(result)
        nav = data["pages"][0]["navigation"]
        assert "/page/2" in nav["reachable_pages"]
        assert "/page/1" in nav["reachable_pages"]

    def test_empty_doc(self):
        doc = _make_doc()
        result = generate_agent_json(doc)
        data = json.loads(result)
        assert len(data["pages"]) == 1
        assert data["pages"][0]["content"]["block_types"] == {}

    def test_raises_on_empty_list(self):
        with pytest.raises(ValueError, match="At least one"):
            generate_agent_json_from_batch([], site_url="https://example.com")


class TestGenerateAgentJsonBatch:
    def test_multiple_pages(self):
        doc1 = _make_doc(
            title="Page 1",
            source_url="https://example.com/1",
            blocks=[_block("b1", BlockType.HEADING, "Title 1")],
        )
        doc2 = _make_doc(
            title="Page 2",
            source_url="https://example.com/2",
            blocks=[_block("b2", BlockType.PARAGRAPH, "Content")],
        )
        result = generate_agent_json_from_batch([doc1, doc2], "https://example.com")
        data = json.loads(result)
        assert data["site"] == "https://example.com"
        assert len(data["pages"]) == 2
        assert data["pages"][0]["title"] == "Page 1"
        assert data["pages"][1]["title"] == "Page 2"

    def test_site_structure_from_profiles(self):
        profile = SiteProfile(
            site="example.com",
            header_selectors=["header"],
            footer_selectors=["footer"],
        )
        doc = _make_doc(
            site_profile=profile,
            actions=[_action("a1", ActionType.SUBMIT, "Search", role="search")],
        )
        result = generate_agent_json_from_batch([doc], "https://example.com")
        data = json.loads(result)
        structure = data["site_structure"]
        assert "header" in structure["template_elements"]
        assert "footer" in structure["template_elements"]
        assert "search" in structure["common_actions"]


# ---------------------------------------------------------------------------
# parse_agent_json
# ---------------------------------------------------------------------------


class TestParseAgentJson:
    def test_roundtrip(self):
        doc = _make_doc(
            blocks=[_block("b1", BlockType.HEADING, "Hello")],
            actions=[_action("a1", ActionType.CLICK, "Buy", selector=".buy")],
        )
        json_str = generate_agent_json(doc)
        spec = parse_agent_json(json_str)
        assert spec.version == "0.1.0"
        assert spec.site == "https://example.com/page"
        assert len(spec.pages) == 1
        assert spec.pages[0].title == "Test Page"
        assert spec.pages[0].content["block_types"]["heading"] == 1

    def test_parse_minimal(self):
        minimal = json.dumps({"agent_json_version": "0.1.0", "site": "test.com"})
        spec = parse_agent_json(minimal)
        assert spec.version == "0.1.0"
        assert spec.site == "test.com"
        assert spec.pages == []

    def test_parse_invalid_json(self):
        with pytest.raises(json.JSONDecodeError):
            parse_agent_json("not json")

    def test_parse_non_object(self):
        with pytest.raises(ValueError, match="JSON object"):
            parse_agent_json("[1, 2, 3]")

    def test_parse_with_pages(self):
        data = {
            "agent_json_version": "0.1.0",
            "site": "example.com",
            "pages": [
                {
                    "url": "/products",
                    "title": "Products",
                    "content": {"block_types": {"heading": 3}},
                    "actions": [{"type": "click", "label": "Buy"}],
                    "navigation": {"reachable_pages": ["/cart"]},
                }
            ],
            "site_structure": {"template_elements": ["header"]},
        }
        spec = parse_agent_json(json.dumps(data))
        assert len(spec.pages) == 1
        assert spec.pages[0].url == "/products"
        assert spec.pages[0].actions[0]["type"] == "click"
        assert spec.site_structure["template_elements"] == ["header"]
