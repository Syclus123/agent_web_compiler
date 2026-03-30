"""Integration tests for full HTML compilation pipeline.

These tests compile real HTML fixtures end-to-end and verify
that the output AgentDocument is well-formed and semantically correct.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_web_compiler.core.block import BlockType
from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.core.document import SourceType
from agent_web_compiler.pipeline.compiler import HTMLCompiler

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
SAMPLE_ARTICLE = FIXTURES_DIR / "sample_article.html"


@pytest.fixture
def compiler() -> HTMLCompiler:
    return HTMLCompiler()


@pytest.fixture
def article_html() -> str:
    return SAMPLE_ARTICLE.read_text(encoding="utf-8")


@pytest.fixture
def compiled_doc(compiler, article_html):
    config = CompileConfig(include_actions=True, include_provenance=True, debug=True)
    return compiler.compile(article_html, source_url="https://techblog.example.com/neural-networks", config=config)


@pytest.mark.integration
class TestFullCompilation:
    def test_produces_agent_document(self, compiled_doc):
        assert compiled_doc is not None
        assert compiled_doc.source_type == SourceType.HTML
        assert compiled_doc.doc_id.startswith("sha256:")

    def test_title_extracted(self, compiled_doc):
        assert compiled_doc.title == "Understanding Neural Networks: A Practical Guide"

    def test_has_blocks(self, compiled_doc):
        assert len(compiled_doc.blocks) > 0

    def test_has_headings(self, compiled_doc):
        headings = compiled_doc.get_blocks_by_type(BlockType.HEADING)
        assert len(headings) >= 1
        heading_texts = [h.text for h in headings]
        # Should find the main headings from the article
        assert any("Introduction" in t for t in heading_texts)
        assert any("Key Concepts" in t for t in heading_texts)

    def test_has_paragraphs(self, compiled_doc):
        paragraphs = compiled_doc.get_blocks_by_type(BlockType.PARAGRAPH)
        assert len(paragraphs) >= 1
        # Should contain article content
        all_text = " ".join(p.text for p in paragraphs)
        assert "neural network" in all_text.lower()

    def test_has_list(self, compiled_doc):
        lists = compiled_doc.get_blocks_by_type(BlockType.LIST)
        assert len(lists) >= 1
        list_text = " ".join(item.text for item in lists)
        assert "Input Layer" in list_text

    def test_has_table(self, compiled_doc):
        tables = compiled_doc.get_blocks_by_type(BlockType.TABLE)
        assert len(tables) >= 1
        table = tables[0]
        assert "headers" in table.metadata
        assert "rows" in table.metadata
        assert "Hyperparameter" in table.metadata["headers"]

    def test_has_code_block(self, compiled_doc):
        codes = compiled_doc.get_blocks_by_type(BlockType.CODE)
        assert len(codes) >= 1
        code_text = " ".join(c.text for c in codes)
        assert "SimpleNet" in code_text
        # Should detect python language
        assert any(c.metadata.get("language") == "python" for c in codes)

    def test_has_blockquote(self, compiled_doc):
        quotes = compiled_doc.get_blocks_by_type(BlockType.QUOTE)
        assert len(quotes) >= 1
        assert any("Dijkstra" in q.text for q in quotes)

    def test_all_expected_block_types_present(self, compiled_doc):
        types = {b.type for b in compiled_doc.blocks}
        expected = {
            BlockType.HEADING,
            BlockType.PARAGRAPH,
            BlockType.LIST,
            BlockType.TABLE,
            BlockType.CODE,
            BlockType.QUOTE,
        }
        assert expected.issubset(types), f"Missing types: {expected - types}"


@pytest.mark.integration
class TestBoilerplateRemoval:
    def test_script_content_removed(self, compiled_doc):
        all_text = " ".join(b.text for b in compiled_doc.blocks)
        assert "analytics" not in all_text.lower()

    def test_article_content_preserved(self, compiled_doc):
        all_text = " ".join(b.text for b in compiled_doc.blocks)
        assert "neural network" in all_text.lower()
        assert "backpropagation" in all_text.lower()


@pytest.mark.integration
class TestActionExtraction:
    def test_has_actions(self, compiled_doc):
        assert len(compiled_doc.actions) > 0

    def test_actions_have_types(self, compiled_doc):
        for action in compiled_doc.actions:
            assert action.type is not None

    def test_actions_have_labels(self, compiled_doc):
        for action in compiled_doc.actions:
            assert action.label  # Non-empty


@pytest.mark.integration
class TestMarkdownOutput:
    def test_canonical_markdown_populated(self, compiled_doc):
        md = compiled_doc.canonical_markdown
        assert len(md) > 0

    def test_markdown_contains_headings(self, compiled_doc):
        md = compiled_doc.canonical_markdown
        assert "# " in md or "## " in md

    def test_markdown_contains_content(self, compiled_doc):
        md = compiled_doc.canonical_markdown
        assert "neural network" in md.lower() or "Neural" in md

    def test_markdown_has_code_fences(self, compiled_doc):
        md = compiled_doc.canonical_markdown
        assert "```" in md


@pytest.mark.integration
class TestDebugMetadata:
    def test_debug_timings_present(self, compiled_doc):
        assert "timings" in compiled_doc.debug
        timings = compiled_doc.debug["timings"]
        assert "normalize_ms" in timings
        assert "segment_ms" in timings
        assert "total_ms" in timings
        # All timings should be non-negative
        for key, val in timings.items():
            assert val >= 0, f"Timing {key} is negative: {val}"

    def test_quality_metadata(self, compiled_doc):
        assert compiled_doc.quality.block_count > 0
        assert compiled_doc.quality.block_count == len(compiled_doc.blocks)
