"""Tests for HTMLCompiler end-to-end pipeline."""

from __future__ import annotations

import pytest

from agent_web_compiler.core.block import BlockType
from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.core.document import SourceType
from agent_web_compiler.pipeline.compiler import HTMLCompiler


@pytest.fixture
def compiler() -> HTMLCompiler:
    return HTMLCompiler()


SIMPLE_HTML = """<!DOCTYPE html>
<html>
<head><title>Test Page</title></head>
<body>
    <h1>Welcome</h1>
    <p>This is a paragraph of content.</p>
    <button>Click me</button>
    <a href="/about">About us</a>
</body>
</html>"""


class TestHTMLCompiler:
    def test_compiles_to_agent_document(self, compiler):
        doc = compiler.compile(SIMPLE_HTML)
        assert doc is not None
        assert doc.source_type == SourceType.HTML

    def test_title_from_title_tag(self, compiler):
        doc = compiler.compile(SIMPLE_HTML)
        assert doc.title == "Test Page"

    def test_title_from_h1_when_no_title_tag(self, compiler):
        html = "<html><body><h1>Heading Title</h1><p>Content</p></body></html>"
        doc = compiler.compile(html)
        assert doc.title == "Heading Title"

    def test_blocks_populated(self, compiler):
        doc = compiler.compile(SIMPLE_HTML)
        assert len(doc.blocks) > 0
        types = {b.type for b in doc.blocks}
        assert BlockType.HEADING in types or BlockType.PARAGRAPH in types

    def test_actions_included_by_default(self, compiler):
        doc = compiler.compile(SIMPLE_HTML)
        # Default config has include_actions=True
        assert len(doc.actions) > 0

    def test_actions_when_include_actions_true(self, compiler):
        config = CompileConfig(include_actions=True)
        doc = compiler.compile(SIMPLE_HTML, config=config)
        assert len(doc.actions) > 0

    def test_actions_empty_when_include_actions_false(self, compiler):
        config = CompileConfig(include_actions=False)
        doc = compiler.compile(SIMPLE_HTML, config=config)
        assert len(doc.actions) == 0

    def test_provenance_when_enabled(self, compiler):
        config = CompileConfig(include_provenance=True)
        doc = compiler.compile(SIMPLE_HTML, config=config)
        # At least some blocks should have provenance
        blocks_with_prov = [b for b in doc.blocks if b.provenance is not None]
        assert len(blocks_with_prov) > 0

    def test_debug_timings_when_debug_true(self, compiler):
        config = CompileConfig(debug=True)
        doc = compiler.compile(SIMPLE_HTML, config=config)
        assert "timings" in doc.debug
        timings = doc.debug["timings"]
        assert "normalize_ms" in timings
        assert "segment_ms" in timings
        assert "total_ms" in timings

    def test_debug_empty_when_debug_false(self, compiler):
        config = CompileConfig(debug=False)
        doc = compiler.compile(SIMPLE_HTML, config=config)
        assert doc.debug == {}

    def test_canonical_markdown_populated(self, compiler):
        doc = compiler.compile(SIMPLE_HTML)
        assert doc.canonical_markdown != ""
        assert "Welcome" in doc.canonical_markdown

    def test_doc_id_deterministic(self, compiler):
        doc1 = compiler.compile(SIMPLE_HTML)
        doc2 = compiler.compile(SIMPLE_HTML)
        assert doc1.doc_id == doc2.doc_id

    def test_doc_id_differs_for_different_input(self, compiler):
        doc1 = compiler.compile("<html><body><p>A</p></body></html>")
        doc2 = compiler.compile("<html><body><p>B</p></body></html>")
        assert doc1.doc_id != doc2.doc_id

    def test_source_url_preserved(self, compiler):
        doc = compiler.compile(SIMPLE_HTML, source_url="https://example.com")
        assert doc.source_url == "https://example.com"

    def test_quality_metadata(self, compiler):
        doc = compiler.compile(SIMPLE_HTML)
        assert doc.quality.block_count == len(doc.blocks)
        assert doc.quality.action_count == len(doc.actions)
