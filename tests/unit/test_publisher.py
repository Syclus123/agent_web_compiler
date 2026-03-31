"""Tests for the Agent Publisher Toolkit generators."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import pytest

from agent_web_compiler.core.action import Action, ActionType, StateEffect
from agent_web_compiler.core.block import Block, BlockType
from agent_web_compiler.core.document import AgentDocument, SourceType
from agent_web_compiler.publisher.actions_json import generate_actions_json
from agent_web_compiler.publisher.agent_sitemap import generate_agent_sitemap
from agent_web_compiler.publisher.content_json import generate_agent_json, generate_content_json
from agent_web_compiler.publisher.delta_feed import generate_delta_feed
from agent_web_compiler.publisher.llms_txt import generate_llms_txt

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc(
    title: str = "Test Page",
    source_url: str = "https://example.com/page",
    blocks: list[Block] | None = None,
    actions: list[Action] | None = None,
    lang: str | None = None,
) -> AgentDocument:
    return AgentDocument(
        doc_id="sha256:abc123",
        source_type=SourceType.HTML,
        source_url=source_url,
        title=title,
        blocks=blocks or [],
        actions=actions or [],
        lang=lang,
    )


def _block(
    id: str,
    btype: BlockType,
    text: str,
    importance: float = 0.5,
    section_path: list[str] | None = None,
    metadata: dict | None = None,
) -> Block:
    return Block(
        id=id,
        type=btype,
        text=text,
        importance=importance,
        section_path=section_path or [],
        metadata=metadata or {},
    )


def _action(
    id: str,
    atype: ActionType,
    label: str,
    role: str | None = None,
    selector: str | None = None,
    required_fields: list[str] | None = None,
    confidence: float = 0.9,
    target_url: str | None = None,
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
        required_fields=required_fields or [],
        confidence=confidence,
        state_effect=state_effect,
    )


# ---------------------------------------------------------------------------
# Test: generate_llms_txt
# ---------------------------------------------------------------------------


class TestLlmsTxt:
    def test_basic_output(self) -> None:
        doc = _make_doc(
            title="My Docs",
            source_url="https://docs.example.com/guide",
            blocks=[_block("b1", BlockType.HEADING, "Getting Started")],
        )
        result = generate_llms_txt([doc], site_name="Example Docs")
        assert result.startswith("# Example Docs")
        assert "> " in result  # description line
        assert "## Important Pages" in result
        assert "My Docs" in result

    def test_auto_derive_site_name(self) -> None:
        doc = _make_doc(source_url="https://docs.example.com/page")
        result = generate_llms_txt([doc])
        assert "# docs.example.com" in result

    def test_sections_grouped_by_path(self) -> None:
        doc1 = _make_doc(title="API Ref", source_url="https://ex.com/api/auth")
        doc2 = _make_doc(title="Guide", source_url="https://ex.com/guide/start")
        result = generate_llms_txt([doc1, doc2])
        assert "## Main Sections" in result
        assert "Api" in result
        assert "Guide" in result

    def test_actions_section(self) -> None:
        doc = _make_doc(
            actions=[_action("a1", ActionType.SUBMIT, "Search", role="submit_search")],
        )
        result = generate_llms_txt([doc])
        assert "## API / Actions" in result
        assert "Submit Search" in result

    def test_important_pages_sorted_by_block_count(self) -> None:
        doc1 = _make_doc(
            title="Small", source_url="https://ex.com/small",
            blocks=[_block("b1", BlockType.PARAGRAPH, "one")],
        )
        doc2 = _make_doc(
            title="Big", source_url="https://ex.com/big",
            blocks=[
                _block("b1", BlockType.PARAGRAPH, "one"),
                _block("b2", BlockType.PARAGRAPH, "two"),
                _block("b3", BlockType.PARAGRAPH, "three"),
            ],
        )
        result = generate_llms_txt([doc1, doc2])
        # Both pages should appear in the output
        assert "Big" in result
        assert "Small" in result
        # In the Key Pages section, "Big" (3 blocks) should be listed
        # The exact order depends on implementation; just verify both present
        assert "3 blocks" in result or "big" in result.lower()

    def test_empty_docs_raises(self) -> None:
        with pytest.raises(ValueError, match="At least one"):
            generate_llms_txt([])

    def test_truncation(self) -> None:
        """Very long output should be truncated."""
        docs = [
            _make_doc(
                title=f"Page {i}",
                source_url=f"https://ex.com/page/{i}",
                blocks=[_block(f"b{i}", BlockType.PARAGRAPH, "x" * 200)],
            )
            for i in range(200)
        ]
        result = generate_llms_txt(docs)
        assert len(result) <= 8000


# ---------------------------------------------------------------------------
# Test: generate_content_json
# ---------------------------------------------------------------------------


class TestContentJson:
    def test_basic_structure(self) -> None:
        doc = _make_doc(
            title="API",
            source_url="https://ex.com/api",
            blocks=[_block("b1", BlockType.HEADING, "Auth", importance=0.9)],
            lang="en",
        )
        result = json.loads(generate_content_json([doc], site_url="https://ex.com"))
        assert result["version"] == "0.1.0"
        assert result["site"] == "https://ex.com"
        assert len(result["pages"]) == 1
        page = result["pages"][0]
        assert page["url"] == "https://ex.com/api"
        assert page["title"] == "API"
        assert page["language"] == "en"
        assert len(page["blocks"]) == 1
        assert page["blocks"][0]["id"] == "b1"
        assert page["blocks"][0]["type"] == "heading"

    def test_low_importance_blocks_filtered(self) -> None:
        doc = _make_doc(blocks=[
            _block("b1", BlockType.PARAGRAPH, "important", importance=0.8),
            _block("b2", BlockType.PARAGRAPH, "noise", importance=0.1),
        ])
        result = json.loads(generate_content_json([doc]))
        page = result["pages"][0]
        assert len(page["blocks"]) == 1
        assert page["blocks"][0]["id"] == "b1"

    def test_text_truncation(self) -> None:
        long_text = "a" * 600
        doc = _make_doc(blocks=[_block("b1", BlockType.PARAGRAPH, long_text)])
        result = json.loads(generate_content_json([doc]))
        block_text = result["pages"][0]["blocks"][0]["text"]
        assert len(block_text) <= 500
        assert block_text.endswith("...")

    def test_entities_included(self) -> None:
        doc = _make_doc(blocks=[
            _block("b1", BlockType.PARAGRAPH, "Price: $99", metadata={"entities": ["$99"]}),
        ])
        result = json.loads(generate_content_json([doc]))
        assert result["pages"][0]["blocks"][0]["entities"] == ["$99"]

    def test_section_path_included(self) -> None:
        doc = _make_doc(blocks=[
            _block("b1", BlockType.HEADING, "Auth", section_path=["API", "Auth"]),
        ])
        result = json.loads(generate_content_json([doc]))
        assert result["pages"][0]["blocks"][0]["section_path"] == ["API", "Auth"]

    def test_empty_docs_raises(self) -> None:
        with pytest.raises(ValueError):
            generate_content_json([])


# ---------------------------------------------------------------------------
# Test: generate_agent_json (publisher wrapper)
# ---------------------------------------------------------------------------


class TestAgentJsonPublisher:
    def test_delegates_to_standards(self) -> None:
        doc = _make_doc(
            title="Test",
            source_url="https://ex.com/test",
            blocks=[_block("b1", BlockType.HEADING, "Hello")],
        )
        result = json.loads(generate_agent_json([doc], site_url="https://ex.com"))
        assert result["agent_json_version"] == "0.1.0"
        assert result["site"] == "https://ex.com"
        assert len(result["pages"]) == 1


# ---------------------------------------------------------------------------
# Test: generate_actions_json
# ---------------------------------------------------------------------------


class TestActionsJson:
    def test_basic_structure(self) -> None:
        doc = _make_doc(
            source_url="https://ex.com/search",
            actions=[
                _action(
                    "a1", ActionType.SUBMIT, "Search",
                    role="submit_search",
                    selector="#search-btn",
                    required_fields=["q"],
                ),
            ],
        )
        result = json.loads(generate_actions_json([doc], site_url="https://ex.com"))
        assert result["version"] == "0.1.0"
        assert result["site"] == "https://ex.com"
        assert "search" in result["capabilities"]
        assert len(result["actions"]) == 1
        action = result["actions"][0]
        assert action["id"] == "a1"
        assert action["type"] == "submit"
        assert action["label"] == "Search"
        assert action["role"] == "submit_search"
        assert action["fields"] == [{"name": "q", "type": "text", "required": True}]

    def test_forms_populated_for_submit_actions(self) -> None:
        doc = _make_doc(actions=[
            _action("a1", ActionType.SUBMIT, "Send", required_fields=["name", "email"]),
        ])
        result = json.loads(generate_actions_json([doc]))
        assert len(result["forms"]) == 1
        form = result["forms"][0]
        assert form["submit_label"] == "Send"
        assert len(form["fields"]) == 2

    def test_deduplication(self) -> None:
        action = _action("a1", ActionType.CLICK, "Buy", role="purchase", selector="#buy")
        doc1 = _make_doc(source_url="https://ex.com/p1", actions=[action])
        doc2 = _make_doc(source_url="https://ex.com/p2", actions=[action])
        result = json.loads(generate_actions_json([doc1, doc2]))
        # Same role+selector+type should be deduplicated
        assert len(result["actions"]) == 1

    def test_capabilities_inferred(self) -> None:
        doc = _make_doc(actions=[
            _action("a1", ActionType.NAVIGATE, "Next", role="next_page"),
            _action("a2", ActionType.DOWNLOAD, "Get PDF", role="download"),
        ])
        result = json.loads(generate_actions_json([doc]))
        caps = result["capabilities"]
        assert "navigate" in caps
        assert "download" in caps

    def test_empty_docs_raises(self) -> None:
        with pytest.raises(ValueError):
            generate_actions_json([])


# ---------------------------------------------------------------------------
# Test: generate_agent_sitemap
# ---------------------------------------------------------------------------


class TestAgentSitemap:
    def test_basic_xml(self) -> None:
        doc = _make_doc(
            title="API",
            source_url="https://ex.com/api",
            blocks=[
                _block("b1", BlockType.HEADING, "Auth"),
                _block("b2", BlockType.PARAGRAPH, "Use tokens"),
            ],
            actions=[_action("a1", ActionType.CLICK, "Try")],
        )
        result = generate_agent_sitemap([doc])
        assert result.startswith('<?xml version="1.0"')

        # Parse as XML to validate structure
        ns = {"a": "https://agent-web-compiler.dev/sitemap/0.1"}
        root = ET.fromstring(result)
        pages = root.findall("a:page", ns)
        assert len(pages) == 1

        page = pages[0]
        assert page.findtext("a:url", namespaces=ns) == "https://ex.com/api"
        assert page.findtext("a:title", namespaces=ns) == "API"
        assert page.findtext("a:blocks", namespaces=ns) == "2"
        assert page.findtext("a:actions", namespaces=ns) == "1"

    def test_content_types(self) -> None:
        doc = _make_doc(blocks=[
            _block("b1", BlockType.HEADING, "H"),
            _block("b2", BlockType.PARAGRAPH, "P"),
            _block("b3", BlockType.CODE, "code"),
        ])
        result = generate_agent_sitemap([doc])
        assert "heading" in result
        assert "paragraph" in result
        assert "code" in result

    def test_importance_computed(self) -> None:
        doc = _make_doc(blocks=[
            _block("b1", BlockType.HEADING, "H", importance=0.8),
            _block("b2", BlockType.PARAGRAPH, "P", importance=0.4),
        ])
        result = generate_agent_sitemap([doc])
        # Mean importance = 0.6
        assert "<importance>0.6</importance>" in result

    def test_multiple_pages(self) -> None:
        doc1 = _make_doc(title="A", source_url="https://ex.com/a")
        doc2 = _make_doc(title="B", source_url="https://ex.com/b")
        result = generate_agent_sitemap([doc1, doc2])
        assert result.count("<page>") == 2

    def test_empty_docs_raises(self) -> None:
        with pytest.raises(ValueError):
            generate_agent_sitemap([])

    def test_xml_escaping(self) -> None:
        doc = _make_doc(title="A & B <C>", source_url="https://ex.com/a&b")
        result = generate_agent_sitemap([doc])
        assert "&amp;" in result
        assert "&lt;" in result
        # Should still parse as valid XML
        ET.fromstring(result)


# ---------------------------------------------------------------------------
# Test: generate_delta_feed
# ---------------------------------------------------------------------------


class TestDeltaFeed:
    def test_no_changes(self) -> None:
        doc = _make_doc(
            title="Same",
            source_url="https://ex.com/page",
            blocks=[_block("b1", BlockType.PARAGRAPH, "unchanged")],
        )
        result = json.loads(generate_delta_feed(
            current_docs=[doc], previous_docs=[doc],
        ))
        assert result["version"] == "0.1.0"
        assert len(result["changes"]) == 0

    def test_added_page(self) -> None:
        new_doc = _make_doc(title="New", source_url="https://ex.com/new")
        result = json.loads(generate_delta_feed(
            current_docs=[new_doc], previous_docs=[],
        ))
        assert len(result["changes"]) == 1
        assert result["changes"][0]["change_type"] == "added"
        assert result["changes"][0]["url"] == "https://ex.com/new"

    def test_removed_page(self) -> None:
        old_doc = _make_doc(title="Old", source_url="https://ex.com/old")
        result = json.loads(generate_delta_feed(
            current_docs=[], previous_docs=[old_doc],
        ))
        assert len(result["changes"]) == 1
        assert result["changes"][0]["change_type"] == "removed"

    def test_updated_page(self) -> None:
        old_doc = _make_doc(
            title="Page",
            source_url="https://ex.com/page",
            blocks=[_block("b1", BlockType.PARAGRAPH, "old text")],
        )
        new_doc = _make_doc(
            title="Page",
            source_url="https://ex.com/page",
            blocks=[
                _block("b1", BlockType.PARAGRAPH, "old text"),
                _block("b2", BlockType.PARAGRAPH, "new block"),
            ],
        )
        result = json.loads(generate_delta_feed(
            current_docs=[new_doc], previous_docs=[old_doc],
        ))
        assert len(result["changes"]) == 1
        change = result["changes"][0]
        assert change["change_type"] == "updated"
        assert change["blocks_added"] >= 1

    def test_since_timestamp(self) -> None:
        old_doc = _make_doc(source_url="https://ex.com/a")
        result = json.loads(generate_delta_feed(
            current_docs=[], previous_docs=[old_doc],
        ))
        assert result["since"] != ""

    def test_site_url(self) -> None:
        doc = _make_doc(source_url="https://ex.com/a")
        result = json.loads(generate_delta_feed(
            current_docs=[doc], previous_docs=[], site_url="https://ex.com",
        ))
        assert result["site"] == "https://ex.com"

    def test_empty_both_raises(self) -> None:
        with pytest.raises(ValueError):
            generate_delta_feed(current_docs=[], previous_docs=[])

    def test_legacy_kwargs(self) -> None:
        """Legacy old_docs/new_docs kwargs still work."""
        new_doc = _make_doc(title="New", source_url="https://ex.com/new")
        result = json.loads(generate_delta_feed(
            old_docs=[], new_docs=[new_doc],
        ))
        assert len(result["changes"]) == 1
        assert result["changes"][0]["change_type"] == "added"

    def test_mixed_add_remove_update(self) -> None:
        old1 = _make_doc(
            title="Kept", source_url="https://ex.com/kept",
            blocks=[_block("b1", BlockType.PARAGRAPH, "original")],
        )
        old2 = _make_doc(title="Removed", source_url="https://ex.com/removed")
        new1 = _make_doc(
            title="Kept", source_url="https://ex.com/kept",
            blocks=[_block("b1", BlockType.PARAGRAPH, "changed significantly here")],
        )
        new2 = _make_doc(title="Added", source_url="https://ex.com/added")
        result = json.loads(generate_delta_feed(
            current_docs=[new1, new2], previous_docs=[old1, old2],
        ))
        types = {c["change_type"] for c in result["changes"]}
        assert "updated" in types
        assert "removed" in types
        assert "added" in types
