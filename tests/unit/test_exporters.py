"""Tests for markdown and JSON exporters."""

from __future__ import annotations

import json

from agent_web_compiler.core.block import Block, BlockType
from agent_web_compiler.core.document import AgentDocument, SourceType
from agent_web_compiler.exporters.json_exporter import to_dict, to_json
from agent_web_compiler.exporters.markdown_exporter import to_markdown

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _block(type: BlockType, text: str, **kwargs) -> Block:
    return Block(id="b_000", type=type, text=text, order=0, **kwargs)


def _make_doc(blocks=None) -> AgentDocument:
    return AgentDocument(
        doc_id="sha256:test1234567890ab",
        source_type=SourceType.HTML,
        title="Test Doc",
        blocks=blocks or [],
    )


# ---------------------------------------------------------------------------
# Markdown exporter
# ---------------------------------------------------------------------------


class TestToMarkdown:
    def test_empty_blocks(self):
        assert to_markdown([]) == ""

    def test_heading_formatting(self):
        blocks = [
            _block(BlockType.HEADING, "Title", level=1),
            _block(BlockType.HEADING, "Subtitle", level=2),
            _block(BlockType.HEADING, "Deep", level=4),
        ]
        md = to_markdown(blocks)
        assert "# Title" in md
        assert "## Subtitle" in md
        assert "#### Deep" in md

    def test_heading_default_level(self):
        block = _block(BlockType.HEADING, "No Level", level=None)
        md = to_markdown([block])
        assert md.startswith("# No Level")

    def test_paragraph(self):
        md = to_markdown([_block(BlockType.PARAGRAPH, "Hello world")])
        assert "Hello world" in md

    def test_list_formatting(self):
        block = _block(BlockType.LIST, "Apple\nBanana\nCherry")
        md = to_markdown([block])
        assert "- Apple" in md
        assert "- Banana" in md
        assert "- Cherry" in md

    def test_table_formatting_with_metadata(self):
        block = _block(
            BlockType.TABLE,
            "Name Age Alice 30",
            metadata={
                "headers": ["Name", "Age"],
                "rows": [["Alice", "30"], ["Bob", "25"]],
            },
        )
        md = to_markdown([block])
        assert "| Name | Age |" in md
        assert "| --- | --- |" in md
        assert "| Alice | 30 |" in md
        assert "| Bob | 25 |" in md

    def test_table_formatting_without_metadata(self):
        block = _block(BlockType.TABLE, "Name Age Alice 30")
        md = to_markdown([block])
        # Without headers/rows metadata, should fall back to plain text
        assert "Name Age Alice 30" in md

    def test_code_block_with_language(self):
        block = _block(BlockType.CODE, 'print("hello")', metadata={"language": "python"})
        md = to_markdown([block])
        assert "```python" in md
        assert 'print("hello")' in md
        assert "```" in md

    def test_code_block_no_language(self):
        block = _block(BlockType.CODE, "some code")
        md = to_markdown([block])
        assert "```\nsome code\n```" in md

    def test_blockquote(self):
        block = _block(BlockType.QUOTE, "Famous words")
        md = to_markdown([block])
        assert "> Famous words" in md

    def test_blockquote_multiline(self):
        block = _block(BlockType.QUOTE, "Line 1\nLine 2")
        md = to_markdown([block])
        assert "> Line 1" in md
        assert "> Line 2" in md

    def test_figure_caption(self):
        block = _block(BlockType.FIGURE_CAPTION, "A photo of sunset")
        md = to_markdown([block])
        assert "*A photo of sunset*" in md

    def test_multiple_block_types(self):
        blocks = [
            _block(BlockType.HEADING, "Title", level=1),
            _block(BlockType.PARAGRAPH, "Content here"),
            _block(BlockType.CODE, "x = 1", metadata={"language": "python"}),
        ]
        md = to_markdown(blocks)
        assert "# Title" in md
        assert "Content here" in md
        assert "```python" in md


# ---------------------------------------------------------------------------
# JSON exporter
# ---------------------------------------------------------------------------


class TestToJson:
    def test_valid_json(self):
        doc = _make_doc([_block(BlockType.PARAGRAPH, "Hello")])
        result = to_json(doc)
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_contains_expected_keys(self):
        doc = _make_doc()
        result = to_json(doc)
        parsed = json.loads(result)
        assert "doc_id" in parsed
        assert "source_type" in parsed
        assert "title" in parsed
        assert "blocks" in parsed
        assert "schema_version" in parsed

    def test_to_dict_returns_dict(self):
        doc = _make_doc()
        result = to_dict(doc)
        assert isinstance(result, dict)
        assert result["doc_id"] == "sha256:test1234567890ab"
        assert result["source_type"] == "html"

    def test_blocks_serialized(self):
        doc = _make_doc([_block(BlockType.HEADING, "Title", level=1)])
        result = to_dict(doc)
        assert len(result["blocks"]) == 1
        assert result["blocks"][0]["type"] == "heading"
        assert result["blocks"][0]["text"] == "Title"
