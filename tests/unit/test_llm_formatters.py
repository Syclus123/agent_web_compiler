"""Tests for LLM-optimized output formatters."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from agent_web_compiler.core.action import Action, ActionType, StateEffect
from agent_web_compiler.core.block import Block, BlockType
from agent_web_compiler.core.document import AgentDocument, Quality, SourceType
from agent_web_compiler.core.provenance import PageProvenance, Provenance
from agent_web_compiler.exporters.llm_formatters import (
    AgentPromptFormatter,
    AXTreeFormatter,
    CompactFormatter,
    FunctionCallFormatter,
    XMLFormatter,
    format_for_llm,
    to_agent_prompt,
    to_axtree,
    to_compact,
    to_function_calls,
    to_xml,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_blocks() -> list[Block]:
    """A representative set of blocks for testing."""
    return [
        Block(
            id="b_001",
            type=BlockType.HEADING,
            text="Search Results",
            section_path=["Search Results"],
            order=0,
            importance=0.9,
            level=1,
        ),
        Block(
            id="b_002",
            type=BlockType.PARAGRAPH,
            text="Found 42 results for your query.",
            section_path=["Search Results"],
            order=1,
            importance=0.7,
        ),
        Block(
            id="b_003",
            type=BlockType.TABLE,
            text="Name | Price\nWidget A | $9.99\nWidget B | $19.99",
            section_path=["Search Results", "Product Table"],
            order=2,
            importance=0.8,
            metadata={
                "headers": ["Name", "Price"],
                "rows": [["Widget A", "$9.99"], ["Widget B", "$19.99"]],
                "row_count": 2,
                "col_count": 2,
            },
        ),
        Block(
            id="b_004",
            type=BlockType.CODE,
            text='print("hello")',
            section_path=["Examples"],
            order=3,
            importance=0.6,
            metadata={"language": "python"},
        ),
        Block(
            id="b_005",
            type=BlockType.LIST,
            text="Item one\nItem two",
            section_path=["Examples"],
            order=4,
            importance=0.5,
            children=[
                Block(id="b_005_1", type=BlockType.PARAGRAPH, text="Item one", order=0),
                Block(id="b_005_2", type=BlockType.PARAGRAPH, text="Item two", order=1),
            ],
        ),
    ]


@pytest.fixture()
def sample_actions() -> list[Action]:
    """A representative set of actions for testing."""
    return [
        Action(
            id="a_search",
            type=ActionType.SUBMIT,
            label="Search",
            selector="#search-btn",
            role="submit_search",
            priority=0.9,
            confidence=0.95,
            value_schema={
                "type": "object",
                "properties": {
                    "q": {"type": "string", "description": "Search query"},
                },
            },
            required_fields=["q"],
        ),
        Action(
            id="a_next",
            type=ActionType.NAVIGATE,
            label="Next Page",
            role="next_page",
            priority=0.7,
            confidence=0.9,
            state_effect=StateEffect(
                may_navigate=True,
                target_url="/page/2",
            ),
        ),
        Action(
            id="a_download",
            type=ActionType.DOWNLOAD,
            label="Download PDF",
            role="download_pdf",
            priority=0.5,
            confidence=0.85,
            state_effect=StateEffect(may_download=True),
        ),
    ]


@pytest.fixture()
def sample_doc(sample_blocks: list[Block], sample_actions: list[Action]) -> AgentDocument:
    """A representative AgentDocument for testing."""
    return AgentDocument(
        doc_id="sha256:abc123",
        source_type=SourceType.HTML,
        source_url="https://example.com/search?q=widgets",
        title="Widget Search - Example.com",
        fetched_at=datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc),
        compiled_at=datetime(2026, 3, 15, 12, 0, 1, tzinfo=timezone.utc),
        blocks=sample_blocks,
        actions=sample_actions,
        canonical_markdown="# Search Results\n\nFound 42 results.",
        quality=Quality(parse_confidence=0.95, block_count=5, action_count=3),
    )


@pytest.fixture()
def empty_doc() -> AgentDocument:
    """An empty AgentDocument with no blocks or actions."""
    return AgentDocument(
        doc_id="sha256:empty",
        source_type=SourceType.HTML,
        title="",
        compiled_at=datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# AXTree Formatter
# ---------------------------------------------------------------------------

class TestAXTreeFormatter:
    def test_basic_output(self, sample_doc: AgentDocument) -> None:
        result = to_axtree(sample_doc)
        assert "[1] heading" in result
        assert '"Search Results"' in result
        assert "level=1" in result

    def test_table_cells(self, sample_doc: AgentDocument) -> None:
        result = to_axtree(sample_doc)
        assert "cell" in result
        assert '"Widget A"' in result

    def test_list_items(self, sample_doc: AgentDocument) -> None:
        result = to_axtree(sample_doc)
        assert "listitem" in result
        assert '"Item one"' in result

    def test_actions_section(self, sample_doc: AgentDocument) -> None:
        result = to_axtree(sample_doc)
        assert "--- actions ---" in result
        assert 'button "Search"' in result
        assert 'link "Next Page"' in result

    def test_primary_marker(self, sample_doc: AgentDocument) -> None:
        result = to_axtree(sample_doc)
        # Heading has importance 0.9 >= 0.8
        assert "[primary]" in result

    def test_code_block_with_language(self, sample_doc: AgentDocument) -> None:
        result = to_axtree(sample_doc)
        assert "lang=python" in result

    def test_section_grouping(self, sample_doc: AgentDocument) -> None:
        result = to_axtree(sample_doc)
        assert "--- Search Results ---" in result
        assert "--- Examples ---" in result

    def test_empty_doc(self, empty_doc: AgentDocument) -> None:
        result = to_axtree(empty_doc)
        assert result == ""

    def test_bbox_included(self) -> None:
        block = Block(
            id="b_1",
            type=BlockType.PARAGRAPH,
            text="Located text",
            order=0,
            provenance=Provenance(
                page=PageProvenance(bbox=[10.0, 20.0, 300.0, 40.0])
            ),
        )
        doc = AgentDocument(
            doc_id="sha256:bbox",
            source_type=SourceType.HTML,
            blocks=[block],
        )
        result = to_axtree(doc)
        assert "bbox=10,20,300,40" in result

    def test_formatter_class_api(self, sample_doc: AgentDocument) -> None:
        formatter = AXTreeFormatter()
        result = formatter.format(sample_doc)
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# XML Formatter
# ---------------------------------------------------------------------------

class TestXMLFormatter:
    def test_document_wrapper(self, sample_doc: AgentDocument) -> None:
        result = to_xml(sample_doc)
        assert result.startswith("<document")
        assert result.endswith("</document>")
        assert 'title="Widget Search - Example.com"' in result
        assert 'blocks="5"' in result
        assert 'actions="3"' in result

    def test_sections(self, sample_doc: AgentDocument) -> None:
        result = to_xml(sample_doc)
        assert '<section name="Search Results">' in result
        assert '<section name="Examples">' in result
        assert "</section>" in result

    def test_heading(self, sample_doc: AgentDocument) -> None:
        result = to_xml(sample_doc)
        assert '<heading level="1"' in result
        assert "Search Results</heading>" in result

    def test_table_structure(self, sample_doc: AgentDocument) -> None:
        result = to_xml(sample_doc)
        assert "<headers>" in result
        assert "Name | Price" in result
        assert "<row>" in result

    def test_code_language(self, sample_doc: AgentDocument) -> None:
        result = to_xml(sample_doc)
        assert 'language="python"' in result

    def test_list_items(self, sample_doc: AgentDocument) -> None:
        result = to_xml(sample_doc)
        assert "<item>" in result
        assert "Item one</item>" in result

    def test_actions_section(self, sample_doc: AgentDocument) -> None:
        result = to_xml(sample_doc)
        assert "<actions>" in result
        assert 'type="submit"' in result
        assert 'label="Search"' in result
        assert 'role="submit_search"' in result

    def test_action_fields(self, sample_doc: AgentDocument) -> None:
        result = to_xml(sample_doc)
        assert "<fields>" in result
        assert 'name="q"' in result
        assert 'required="true"' in result

    def test_navigate_action_url(self, sample_doc: AgentDocument) -> None:
        result = to_xml(sample_doc)
        assert "<url>/page/2</url>" in result

    def test_xml_escaping(self) -> None:
        block = Block(
            id="b_1",
            type=BlockType.PARAGRAPH,
            text='Price < $10 & "free" shipping',
            order=0,
        )
        doc = AgentDocument(
            doc_id="sha256:esc",
            source_type=SourceType.HTML,
            blocks=[block],
        )
        result = to_xml(doc)
        assert "&lt;" in result
        assert "&amp;" in result
        assert "&quot;" in result

    def test_empty_doc(self, empty_doc: AgentDocument) -> None:
        result = to_xml(empty_doc)
        assert "<document" in result
        assert "</document>" in result

    def test_formatter_class_api(self, sample_doc: AgentDocument) -> None:
        formatter = XMLFormatter()
        result = formatter.format(sample_doc)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Function Call Formatter
# ---------------------------------------------------------------------------

class TestFunctionCallFormatter:
    def test_valid_json(self, sample_doc: AgentDocument) -> None:
        result = to_function_calls(sample_doc)
        parsed = json.loads(result)
        assert "content" in parsed
        assert "available_tools" in parsed

    def test_tool_count(self, sample_doc: AgentDocument) -> None:
        parsed = json.loads(to_function_calls(sample_doc))
        assert len(parsed["available_tools"]) == 3

    def test_search_tool_structure(self, sample_doc: AgentDocument) -> None:
        parsed = json.loads(to_function_calls(sample_doc))
        search_tool = parsed["available_tools"][0]
        assert search_tool["type"] == "function"
        func = search_tool["function"]
        assert func["name"] == "submit_search"
        assert "Search" in func["description"]
        assert "q" in func["parameters"]["properties"]
        assert func["parameters"]["required"] == ["q"]

    def test_navigate_tool(self, sample_doc: AgentDocument) -> None:
        parsed = json.loads(to_function_calls(sample_doc))
        nav_tool = parsed["available_tools"][1]
        func = nav_tool["function"]
        assert func["name"] == "next_page"
        assert "/page/2" in func["description"]

    def test_content_field(self, sample_doc: AgentDocument) -> None:
        parsed = json.loads(to_function_calls(sample_doc))
        assert "Search Results" in parsed["content"]

    def test_no_actions(self, empty_doc: AgentDocument) -> None:
        parsed = json.loads(to_function_calls(empty_doc))
        assert parsed["available_tools"] == []

    def test_function_name_sanitization(self) -> None:
        action = Action(
            id="a_1",
            type=ActionType.CLICK,
            label="Go!",
            role="some-weird.role/name",
        )
        doc = AgentDocument(
            doc_id="sha256:san",
            source_type=SourceType.HTML,
            actions=[action],
        )
        parsed = json.loads(to_function_calls(doc))
        name = parsed["available_tools"][0]["function"]["name"]
        # Should only contain alnum and underscores
        assert all(c.isalnum() or c == "_" for c in name)

    def test_formatter_class_api(self, sample_doc: AgentDocument) -> None:
        formatter = FunctionCallFormatter()
        result = formatter.format(sample_doc)
        assert isinstance(result, str)
        json.loads(result)  # Must be valid JSON


# ---------------------------------------------------------------------------
# Compact Formatter
# ---------------------------------------------------------------------------

class TestCompactFormatter:
    def test_title(self, sample_doc: AgentDocument) -> None:
        result = to_compact(sample_doc)
        assert "TITLE: Widget Search - Example.com" in result

    def test_sections(self, sample_doc: AgentDocument) -> None:
        result = to_compact(sample_doc)
        assert "SECTIONS:" in result
        assert "Search Results" in result
        assert "Examples" in result

    def test_key_content(self, sample_doc: AgentDocument) -> None:
        result = to_compact(sample_doc)
        assert "KEY_CONTENT:" in result
        assert "Table:" in result

    def test_code_summary(self, sample_doc: AgentDocument) -> None:
        result = to_compact(sample_doc)
        assert "Code:" in result
        assert "python" in result

    def test_actions(self, sample_doc: AgentDocument) -> None:
        result = to_compact(sample_doc)
        assert "ACTIONS:" in result
        assert "[submit_search(q)]" in result
        assert "[next_page]" in result

    def test_empty_doc(self, empty_doc: AgentDocument) -> None:
        result = to_compact(empty_doc)
        # Should not crash, may be empty or near-empty
        assert isinstance(result, str)

    def test_entities(self) -> None:
        block = Block(
            id="b_1",
            type=BlockType.PARAGRAPH,
            text="Price is $99.99",
            order=0,
            metadata={"entities": ["$99.99", "2026-03-15"]},
        )
        doc = AgentDocument(
            doc_id="sha256:ent",
            source_type=SourceType.HTML,
            blocks=[block],
        )
        result = to_compact(doc)
        assert "ENTITIES:" in result
        assert "$99.99" in result

    def test_formatter_class_api(self, sample_doc: AgentDocument) -> None:
        formatter = CompactFormatter()
        result = formatter.format(sample_doc)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Agent Prompt Formatter
# ---------------------------------------------------------------------------

class TestAgentPromptFormatter:
    def test_page_header(self, sample_doc: AgentDocument) -> None:
        result = to_agent_prompt(sample_doc)
        assert "## Current Page: Widget Search - Example.com" in result
        assert "Source: https://example.com/search?q=widgets" in result
        assert "Confidence" in result or "confidence" in result.lower()

    def test_content_section(self, sample_doc: AgentDocument) -> None:
        result = to_agent_prompt(sample_doc)
        assert "### Content (5 blocks)" in result
        assert "Search Results" in result

    def test_actions_section(self, sample_doc: AgentDocument) -> None:
        result = to_agent_prompt(sample_doc)
        assert "### Available Actions (3)" in result
        assert "**Search** [submit]" in result
        assert "Required: q" in result

    def test_page_structure(self, sample_doc: AgentDocument) -> None:
        result = to_agent_prompt(sample_doc)
        assert "### Page Structure" in result
        assert "Sections:" in result
        assert "Tables:" in result
        assert "Code blocks:" in result

    def test_entities_in_prompt(self) -> None:
        block = Block(
            id="b_1",
            type=BlockType.PARAGRAPH,
            text="Contact: user@example.com",
            order=0,
            metadata={"entities": ["user@example.com"]},
        )
        doc = AgentDocument(
            doc_id="sha256:ent2",
            source_type=SourceType.HTML,
            blocks=[block],
        )
        result = to_agent_prompt(doc)
        assert "### Entities Found" in result
        assert "user@example.com" in result

    def test_empty_doc(self, empty_doc: AgentDocument) -> None:
        result = to_agent_prompt(empty_doc)
        assert "## Current Page:" in result

    def test_formatter_class_api(self, sample_doc: AgentDocument) -> None:
        formatter = AgentPromptFormatter()
        result = formatter.format(sample_doc)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# format_for_llm dispatch
# ---------------------------------------------------------------------------

class TestFormatForLLM:
    def test_markdown_format(self, sample_doc: AgentDocument) -> None:
        result = format_for_llm(sample_doc, "markdown")
        assert "Search Results" in result

    def test_axtree_format(self, sample_doc: AgentDocument) -> None:
        result = format_for_llm(sample_doc, "axtree")
        assert "[1]" in result

    def test_xml_format(self, sample_doc: AgentDocument) -> None:
        result = format_for_llm(sample_doc, "xml")
        assert "<document" in result

    def test_function_call_format(self, sample_doc: AgentDocument) -> None:
        result = format_for_llm(sample_doc, "function_call")
        json.loads(result)

    def test_compact_format(self, sample_doc: AgentDocument) -> None:
        result = format_for_llm(sample_doc, "compact")
        assert "TITLE:" in result

    def test_agent_prompt_format(self, sample_doc: AgentDocument) -> None:
        result = format_for_llm(sample_doc, "agent_prompt")
        assert "## Current Page:" in result

    def test_unknown_format_raises(self, sample_doc: AgentDocument) -> None:
        with pytest.raises(ValueError, match="Unknown LLM format"):
            format_for_llm(sample_doc, "nonexistent")

    def test_default_is_markdown(self, sample_doc: AgentDocument) -> None:
        result = format_for_llm(sample_doc)
        assert result == format_for_llm(sample_doc, "markdown")
