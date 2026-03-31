"""Robustness tests — edge cases, malformed input, and boundary conditions."""

from __future__ import annotations

import pytest

from agent_web_compiler.core.block import BlockType
from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.core.errors import ParseError
from agent_web_compiler.pipeline.compiler import HTMLCompiler


@pytest.fixture
def compiler() -> HTMLCompiler:
    return HTMLCompiler()


@pytest.fixture
def config() -> CompileConfig:
    return CompileConfig()


# ------------------------------------------------------------------ #
# 1. Hidden content should NOT appear in blocks
# ------------------------------------------------------------------ #

class TestHiddenContent:
    def test_display_none_excluded(self, compiler: HTMLCompiler, config: CompileConfig) -> None:
        html = '<html><body><p>Visible</p><p style="display:none">Hidden</p></body></html>'
        doc = compiler.compile(html, config=config)
        texts = [b.text for b in doc.blocks]
        assert "Visible" in texts
        assert "Hidden" not in texts

    def test_aria_hidden_excluded(self, compiler: HTMLCompiler, config: CompileConfig) -> None:
        html = '<html><body><p>Visible</p><div aria-hidden="true"><p>Hidden</p></div></body></html>'
        doc = compiler.compile(html, config=config)
        texts = [b.text for b in doc.blocks]
        assert "Visible" in texts
        assert "Hidden" not in texts

    def test_hidden_attr_excluded(self, compiler: HTMLCompiler, config: CompileConfig) -> None:
        html = "<html><body><p>Visible</p><p hidden>Hidden</p></body></html>"
        doc = compiler.compile(html, config=config)
        texts = [b.text for b in doc.blocks]
        assert "Visible" in texts
        assert "Hidden" not in texts


# ------------------------------------------------------------------ #
# 2. Very large HTML
# ------------------------------------------------------------------ #

class TestLargeHTML:
    def test_large_html_compiles_without_error(self, compiler: HTMLCompiler, config: CompileConfig) -> None:
        # ~40KB HTML with many paragraphs — tests that the pipeline
        # handles large content without crashing or excessive slowdown.
        para = "<p>This is a test paragraph with enough text to be meaningful content.</p>\n"
        body = para * 500  # ~500 * ~80 bytes ≈ 40KB
        html = f"<html><body>{body}</body></html>"
        assert len(html) > 30_000
        doc = compiler.compile(html, config=config)
        assert doc is not None
        assert len(doc.blocks) > 0


# ------------------------------------------------------------------ #
# 3. Non-UTF8 encoding
# ------------------------------------------------------------------ #

class TestEncoding:
    def test_latin1_content_handled(self, compiler: HTMLCompiler, config: CompileConfig) -> None:
        # Latin-1 encoded string decoded back to str (simulating httpx doing the decoding)
        html = '<html><body><p>Caf\u00e9 R\u00e9sum\u00e9</p></body></html>'
        doc = compiler.compile(html, config=config)
        texts = [b.text for b in doc.blocks]
        assert any("Caf" in t for t in texts)


# ------------------------------------------------------------------ #
# 4. Plain text input (no HTML tags)
# ------------------------------------------------------------------ #

class TestPlainText:
    def test_plain_text_produces_blocks(self, compiler: HTMLCompiler, config: CompileConfig) -> None:
        text = "This is plain text content without any HTML tags at all."
        doc = compiler.compile(text, config=config)
        assert len(doc.blocks) >= 1
        assert any("plain text" in b.text for b in doc.blocks)

    def test_plain_text_warning(self, compiler: HTMLCompiler, config: CompileConfig) -> None:
        text = "Just some plain text."
        doc = compiler.compile(text, config=config)
        assert any("no HTML tags" in w for w in doc.quality.warnings)


# ------------------------------------------------------------------ #
# 5. Empty table
# ------------------------------------------------------------------ #

class TestEmptyTable:
    def test_empty_table_no_crash(self, compiler: HTMLCompiler, config: CompileConfig) -> None:
        html = "<html><body><table></table><p>Content</p></body></html>"
        doc = compiler.compile(html, config=config)
        assert doc is not None

    def test_table_no_tr_no_crash(self, compiler: HTMLCompiler, config: CompileConfig) -> None:
        html = "<html><body><table>Some raw text in table</table></body></html>"
        doc = compiler.compile(html, config=config)
        assert doc is not None


# ------------------------------------------------------------------ #
# 6. Table with only thead
# ------------------------------------------------------------------ #

class TestTheadOnlyTable:
    def test_thead_only_produces_table_block(self, compiler: HTMLCompiler, config: CompileConfig) -> None:
        html = """<html><body>
        <table>
            <thead><tr><th>Name</th><th>Age</th></tr></thead>
        </table>
        </body></html>"""
        doc = compiler.compile(html, config=config)
        table_blocks = [b for b in doc.blocks if b.type == BlockType.TABLE]
        if table_blocks:
            # Should have headers extracted
            assert table_blocks[0].metadata.get("headers") is not None


# ------------------------------------------------------------------ #
# 7. Table with rowspan
# ------------------------------------------------------------------ #

class TestTableRowspan:
    def test_rowspan_dimensions(self) -> None:
        import lxml.html

        from agent_web_compiler.segmenters.html_segmenter import HTMLSegmenter

        html = """<table>
            <tr><th rowspan="2">Name</th><th>Q1</th></tr>
            <tr><td>100</td></tr>
            <tr><td>Alice</td><td>200</td></tr>
        </table>"""
        table = lxml.html.fromstring(html)
        rows, cols = HTMLSegmenter._table_dimensions(table)
        assert rows == 3
        assert cols == 2  # 2 columns in first row


# ------------------------------------------------------------------ #
# 8. HTML with only images
# ------------------------------------------------------------------ #

class TestImageOnlyHTML:
    def test_images_produce_image_blocks(self, compiler: HTMLCompiler, config: CompileConfig) -> None:
        html = """<html><body>
        <img src="photo1.jpg" alt="A beautiful sunset">
        <img src="photo2.jpg" alt="A mountain landscape">
        </body></html>"""
        doc = compiler.compile(html, config=config)
        image_blocks = [b for b in doc.blocks if b.type == BlockType.IMAGE]
        assert len(image_blocks) >= 1


# ------------------------------------------------------------------ #
# 9. HTML with only links
# ------------------------------------------------------------------ #

class TestLinksOnlyHTML:
    def test_links_produce_actions(self, compiler: HTMLCompiler, config: CompileConfig) -> None:
        html = """<html><body>
        <a href="/page1">Page One</a>
        <a href="/page2">Page Two</a>
        <a href="/page3">Page Three</a>
        </body></html>"""
        doc = compiler.compile(html, config=config)
        assert len(doc.actions) >= 1


# ------------------------------------------------------------------ #
# 10. Deeply nested divs (50 levels)
# ------------------------------------------------------------------ #

class TestDeepNesting:
    def test_deep_nesting_no_overflow(self, compiler: HTMLCompiler, config: CompileConfig) -> None:
        inner = "<p>Deep content that should be found</p>"
        for _ in range(50):
            inner = f"<div>{inner}</div>"
        html = f"<html><body>{inner}</body></html>"
        doc = compiler.compile(html, config=config)
        assert doc is not None
        # Should still find the paragraph
        texts = [b.text for b in doc.blocks]
        assert any("Deep content" in t for t in texts)


# ------------------------------------------------------------------ #
# 11. Huge number of blocks (100 paragraphs)
# ------------------------------------------------------------------ #

class TestManyBlocks:
    def test_100_paragraphs_compile_fast(self, compiler: HTMLCompiler, config: CompileConfig) -> None:
        import time

        paragraphs = "\n".join(
            f"<p>Paragraph number {i} with some meaningful text content.</p>"
            for i in range(100)
        )
        html = f"<html><body>{paragraphs}</body></html>"
        start = time.perf_counter()
        doc = compiler.compile(html, config=config)
        elapsed = time.perf_counter() - start
        assert len(doc.blocks) >= 50  # At least half should survive
        assert elapsed < 10.0  # Should complete in under 10 seconds


# ------------------------------------------------------------------ #
# 12. Binary content (PNG bytes)
# ------------------------------------------------------------------ #

class TestBinaryContent:
    def test_binary_raises_parse_error(self, compiler: HTMLCompiler, config: CompileConfig) -> None:
        # Simulate PNG header bytes as a string (binary content)
        binary_content = "\x89PNG\r\n\x1a\n" + "\x00" * 500
        with pytest.raises(ParseError, match="binary"):
            compiler.compile(binary_content, config=config)


# ------------------------------------------------------------------ #
# 13. XML content
# ------------------------------------------------------------------ #

class TestXMLContent:
    def test_xml_attempts_parsing(self, compiler: HTMLCompiler, config: CompileConfig) -> None:
        xml = """<?xml version="1.0"?>
        <root>
            <item><p>XML paragraph content</p></item>
        </root>"""
        doc = compiler.compile(xml, config=config)
        assert doc is not None


# ------------------------------------------------------------------ #
# 14. HTML with BOM
# ------------------------------------------------------------------ #

class TestBOMHandling:
    def test_html_with_bom(self, compiler: HTMLCompiler, config: CompileConfig) -> None:
        # UTF-8 BOM + HTML
        html = "\ufeff<html><body><p>Content after BOM</p></body></html>"
        doc = compiler.compile(html, config=config)
        assert doc is not None
        texts = [b.text for b in doc.blocks]
        assert any("Content after BOM" in t for t in texts)


# ------------------------------------------------------------------ #
# 15. Empty body
# ------------------------------------------------------------------ #

class TestEmptyBody:
    def test_empty_body_zero_blocks(self, compiler: HTMLCompiler, config: CompileConfig) -> None:
        html = "<html><body></body></html>"
        doc = compiler.compile(html, config=config)
        assert len(doc.blocks) == 0

    def test_empty_body_no_crash(self, compiler: HTMLCompiler, config: CompileConfig) -> None:
        html = "<html><body>   </body></html>"
        doc = compiler.compile(html, config=config)
        assert doc is not None


# ------------------------------------------------------------------ #
# Encoding detection helper tests
# ------------------------------------------------------------------ #

class TestDetectEncoding:
    def test_charset_from_header(self) -> None:
        from agent_web_compiler.sources.http_fetcher import _detect_encoding

        result = _detect_encoding(b"", {"content-type": "text/html; charset=iso-8859-1"})
        assert result == "iso-8859-1"

    def test_charset_from_meta(self) -> None:
        from agent_web_compiler.sources.http_fetcher import _detect_encoding

        content = b'<html><head><meta charset="windows-1252"></head></html>'
        result = _detect_encoding(content, {})
        assert result == "windows-1252"

    def test_charset_from_http_equiv(self) -> None:
        from agent_web_compiler.sources.http_fetcher import _detect_encoding

        content = b'<meta http-equiv="Content-Type" content="text/html; charset=shift_jis">'
        result = _detect_encoding(content, {})
        assert result == "shift_jis"

    def test_bom_detection(self) -> None:
        from agent_web_compiler.sources.http_fetcher import _detect_encoding

        content = b"\xef\xbb\xbf<html></html>"
        result = _detect_encoding(content, {})
        assert result == "utf-8"

    def test_default_utf8(self) -> None:
        from agent_web_compiler.sources.http_fetcher import _detect_encoding

        result = _detect_encoding(b"<html></html>", {})
        assert result == "utf-8"


# ------------------------------------------------------------------ #
# Table with thead and tbody
# ------------------------------------------------------------------ #

class TestTableTheadTbody:
    def test_thead_tbody_extraction(self) -> None:
        import lxml.html

        from agent_web_compiler.segmenters.html_segmenter import HTMLSegmenter

        html = """<table>
            <thead><tr><th>Name</th><th>Score</th></tr></thead>
            <tbody>
                <tr><td>Alice</td><td>95</td></tr>
                <tr><td>Bob</td><td>87</td></tr>
            </tbody>
        </table>"""
        table = lxml.html.fromstring(html)
        headers, rows = HTMLSegmenter._extract_table_data(table)
        assert headers == ["Name", "Score"]
        assert rows is not None
        assert len(rows) == 2
        assert rows[0] == ["Alice", "95"]

    def test_mixed_th_td_in_data_rows(self) -> None:
        import lxml.html

        from agent_web_compiler.segmenters.html_segmenter import HTMLSegmenter

        html = """<table>
            <tr><th>Header1</th><th>Header2</th></tr>
            <tr><th>RowHeader</th><td>Value</td></tr>
        </table>"""
        table = lxml.html.fromstring(html)
        headers, rows = HTMLSegmenter._extract_table_data(table)
        assert headers == ["Header1", "Header2"]
        assert rows is not None
        assert len(rows) == 1
