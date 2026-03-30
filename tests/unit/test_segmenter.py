"""Tests for HTMLSegmenter."""

from __future__ import annotations

import pytest

from agent_web_compiler.core.block import BlockType
from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.segmenters.html_segmenter import HTMLSegmenter


@pytest.fixture
def segmenter() -> HTMLSegmenter:
    return HTMLSegmenter()


@pytest.fixture
def config() -> CompileConfig:
    return CompileConfig()


class TestHTMLSegmenter:
    def test_empty_input(self, segmenter, config):
        assert segmenter.segment("", config) == []

    def test_whitespace_only(self, segmenter, config):
        assert segmenter.segment("   \n  ", config) == []

    # ---- Headings ----

    def test_heading_h1(self, segmenter, config):
        html = "<h1>Main Title</h1>"
        blocks = segmenter.segment(html, config)
        headings = [b for b in blocks if b.type == BlockType.HEADING]
        assert len(headings) >= 1
        assert headings[0].text == "Main Title"
        assert headings[0].level == 1

    def test_heading_h2_to_h6(self, segmenter, config):
        html = "<h2>Two</h2><h3>Three</h3><h4>Four</h4><h5>Five</h5><h6>Six</h6>"
        blocks = segmenter.segment(html, config)
        headings = [b for b in blocks if b.type == BlockType.HEADING]
        levels = [h.level for h in headings]
        assert levels == [2, 3, 4, 5, 6]

    def test_heading_importance(self, segmenter, config):
        html = "<h1>Title</h1>"
        blocks = segmenter.segment(html, config)
        heading = [b for b in blocks if b.type == BlockType.HEADING][0]
        assert heading.importance == 0.9

    # ---- Paragraphs ----

    def test_paragraph(self, segmenter, config):
        html = "<p>Hello world</p>"
        blocks = segmenter.segment(html, config)
        paragraphs = [b for b in blocks if b.type == BlockType.PARAGRAPH]
        assert len(paragraphs) == 1
        assert paragraphs[0].text == "Hello world"

    def test_paragraph_importance(self, segmenter, config):
        html = "<p>Content</p>"
        blocks = segmenter.segment(html, config)
        p = [b for b in blocks if b.type == BlockType.PARAGRAPH][0]
        assert p.importance == 0.7

    # ---- Lists ----

    def test_list_extraction(self, segmenter, config):
        html = "<ul><li>Apple</li><li>Banana</li><li>Cherry</li></ul>"
        blocks = segmenter.segment(html, config)
        lists = [b for b in blocks if b.type == BlockType.LIST]
        assert len(lists) == 1
        # Items should be newline-separated
        assert "Apple" in lists[0].text
        assert "Banana" in lists[0].text
        assert "Cherry" in lists[0].text

    def test_ordered_list(self, segmenter, config):
        html = "<ol><li>First</li><li>Second</li></ol>"
        blocks = segmenter.segment(html, config)
        lists = [b for b in blocks if b.type == BlockType.LIST]
        assert len(lists) == 1
        assert "First" in lists[0].text

    # ---- Tables ----

    def test_table_extraction(self, segmenter, config):
        html = """<table>
            <tr><th>Name</th><th>Age</th></tr>
            <tr><td>Alice</td><td>30</td></tr>
            <tr><td>Bob</td><td>25</td></tr>
        </table>"""
        blocks = segmenter.segment(html, config)
        tables = [b for b in blocks if b.type == BlockType.TABLE]
        assert len(tables) == 1
        assert tables[0].metadata.get("headers") == ["Name", "Age"]
        rows = tables[0].metadata.get("rows")
        assert rows is not None
        assert len(rows) == 2
        assert rows[0] == ["Alice", "30"]

    def test_table_dimensions(self, segmenter, config):
        html = """<table>
            <tr><th>A</th><th>B</th><th>C</th></tr>
            <tr><td>1</td><td>2</td><td>3</td></tr>
        </table>"""
        blocks = segmenter.segment(html, config)
        table = [b for b in blocks if b.type == BlockType.TABLE][0]
        assert table.metadata["row_count"] == 2
        assert table.metadata["col_count"] == 3

    def test_table_importance(self, segmenter, config):
        html = "<table><tr><td>Data</td></tr></table>"
        blocks = segmenter.segment(html, config)
        table = [b for b in blocks if b.type == BlockType.TABLE][0]
        assert table.importance == 0.8

    # ---- Code blocks ----

    def test_code_block(self, segmenter, config):
        html = '<pre><code class="language-python">print("hello")</code></pre>'
        blocks = segmenter.segment(html, config)
        code_blocks = [b for b in blocks if b.type == BlockType.CODE]
        assert len(code_blocks) == 1
        assert 'print("hello")' in code_blocks[0].text
        assert code_blocks[0].metadata.get("language") == "python"

    def test_code_block_no_language(self, segmenter, config):
        html = "<pre>some code</pre>"
        blocks = segmenter.segment(html, config)
        code_blocks = [b for b in blocks if b.type == BlockType.CODE]
        assert len(code_blocks) == 1
        assert "language" not in code_blocks[0].metadata

    def test_nested_code_in_pre_no_duplicate(self, segmenter, config):
        """<code> inside <pre> should not produce a duplicate block."""
        html = "<pre><code>x = 1</code></pre>"
        blocks = segmenter.segment(html, config)
        code_blocks = [b for b in blocks if b.type == BlockType.CODE]
        # Should only have one block (the <pre>), not two
        assert len(code_blocks) == 1

    # ---- Blockquote ----

    def test_blockquote(self, segmenter, config):
        html = "<blockquote>Famous quote here</blockquote>"
        blocks = segmenter.segment(html, config)
        quotes = [b for b in blocks if b.type == BlockType.QUOTE]
        assert len(quotes) == 1
        assert "Famous quote" in quotes[0].text

    def test_blockquote_importance(self, segmenter, config):
        html = "<blockquote>Quote</blockquote>"
        blocks = segmenter.segment(html, config)
        q = [b for b in blocks if b.type == BlockType.QUOTE][0]
        assert q.importance == 0.5

    # ---- Figure / figcaption ----

    def test_figure_extraction(self, segmenter, config):
        html = "<figure><img src='img.png'/><figcaption>A caption</figcaption></figure>"
        blocks = segmenter.segment(html, config)
        fig_blocks = [b for b in blocks if b.type == BlockType.FIGURE_CAPTION]
        assert len(fig_blocks) >= 1
        # The figure block should contain the caption text
        texts = [b.text for b in fig_blocks]
        assert any("caption" in t.lower() for t in texts)

    # ---- Section path tracking ----

    def test_section_path(self, segmenter, config):
        html = """
        <h1>Chapter 1</h1>
        <h2>Section A</h2>
        <p>Content in section A.</p>
        <h2>Section B</h2>
        <p>Content in section B.</p>
        """
        blocks = segmenter.segment(html, config)
        paragraphs = [b for b in blocks if b.type == BlockType.PARAGRAPH]
        # First paragraph under "Chapter 1" > "Section A"
        assert paragraphs[0].section_path == ["Chapter 1", "Section A", "Content in section A."][:2]
        # Verify correct path
        assert "Chapter 1" in paragraphs[0].section_path
        assert "Section A" in paragraphs[0].section_path

    def test_section_path_heading_pops(self, segmenter, config):
        html = """
        <h1>Top</h1>
        <h2>Sub A</h2>
        <h2>Sub B</h2>
        <p>Under Sub B</p>
        """
        blocks = segmenter.segment(html, config)
        paragraphs = [b for b in blocks if b.type == BlockType.PARAGRAPH]
        # "Sub A" should have been popped when "Sub B" was encountered
        assert "Sub A" not in paragraphs[0].section_path
        assert "Sub B" in paragraphs[0].section_path

    # ---- Block ordering ----

    def test_block_ordering(self, segmenter, config):
        html = "<h1>Title</h1><p>First</p><p>Second</p>"
        blocks = segmenter.segment(html, config)
        orders = [b.order for b in blocks]
        assert orders == sorted(orders)
        # Orders should be sequential starting from 0
        assert orders == list(range(len(blocks)))

    # ---- Provenance ----

    def test_provenance_included_by_default(self, segmenter, config):
        html = "<p>Test content</p>"
        blocks = segmenter.segment(html, config)
        p = [b for b in blocks if b.type == BlockType.PARAGRAPH][0]
        assert p.provenance is not None
        assert p.provenance.dom is not None
        assert p.provenance.dom.element_tag == "p"

    def test_provenance_excluded_when_disabled(self, segmenter):
        config = CompileConfig(include_provenance=False)
        html = "<p>Test content</p>"
        blocks = segmenter.segment(html, config)
        p = [b for b in blocks if b.type == BlockType.PARAGRAPH][0]
        assert p.provenance is None
