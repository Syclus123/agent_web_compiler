"""Tests for P0 bug fixes — table colspan, nested lists, form grouping, validation."""

from __future__ import annotations

from agent_web_compiler import compile_html
from agent_web_compiler.core.config import CompileConfig

# ---------------------------------------------------------------------------
# Table colspan/rowspan fixes
# ---------------------------------------------------------------------------


class TestTableColspan:
    def test_colspan_counted_correctly(self):
        html = '<table><tr><th colspan="2">Wide</th><th>Normal</th></tr><tr><td>A</td><td>B</td><td>C</td></tr></table>'
        doc = compile_html(html)
        tables = doc.get_blocks_by_type("table")
        assert len(tables) == 1
        assert tables[0].metadata["col_count"] == 3

    def test_no_colspan_counted_correctly(self):
        html = "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>"
        doc = compile_html(html)
        tables = doc.get_blocks_by_type("table")
        assert tables[0].metadata["col_count"] == 2

    def test_mixed_colspan(self):
        html = '<table><tr><th colspan="3">Full</th></tr><tr><td>A</td><td>B</td><td>C</td></tr></table>'
        doc = compile_html(html)
        tables = doc.get_blocks_by_type("table")
        assert tables[0].metadata["col_count"] == 3

    def test_invalid_colspan_handled(self):
        html = '<table><tr><th colspan="abc">Bad</th><th>OK</th></tr></table>'
        doc = compile_html(html)
        tables = doc.get_blocks_by_type("table")
        assert tables[0].metadata["col_count"] == 2  # bad one counts as 1


# ---------------------------------------------------------------------------
# Nested list deduplication
# ---------------------------------------------------------------------------


class TestNestedLists:
    def test_nested_list_single_block(self):
        html = "<ul><li>A<ul><li>A.1</li><li>A.2</li></ul></li><li>B</li></ul>"
        doc = compile_html(html)
        lists = doc.get_blocks_by_type("list")
        assert len(lists) == 1, f"Expected 1 list block, got {len(lists)}"

    def test_nested_ol_in_ul(self):
        html = "<ul><li>Parent<ol><li>Child 1</li></ol></li></ul>"
        doc = compile_html(html)
        lists = doc.get_blocks_by_type("list")
        assert len(lists) == 1

    def test_standalone_lists_are_separate(self):
        html = "<ul><li>A</li></ul><ol><li>B</li></ol>"
        doc = compile_html(html)
        lists = doc.get_blocks_by_type("list")
        assert len(lists) == 2


# ---------------------------------------------------------------------------
# Definition list handling
# ---------------------------------------------------------------------------


class TestDefinitionLists:
    def test_dl_pairs_merged(self):
        html = "<dl><dt>Key</dt><dd>Value</dd></dl>"
        doc = compile_html(html)
        lists = doc.get_blocks_by_type("list")
        assert len(lists) == 1
        assert "Key: Value" in lists[0].text

    def test_dl_multiple_pairs(self):
        html = "<dl><dt>A</dt><dd>1</dd><dt>B</dt><dd>2</dd></dl>"
        doc = compile_html(html)
        lists = doc.get_blocks_by_type("list")
        assert "A: 1" in lists[0].text
        assert "B: 2" in lists[0].text

    def test_dl_orphan_dt(self):
        """dt without dd should still appear."""
        html = "<dl><dt>Orphan</dt></dl>"
        doc = compile_html(html)
        lists = doc.get_blocks_by_type("list")
        assert len(lists) == 1
        assert "Orphan" in lists[0].text


# ---------------------------------------------------------------------------
# FAQ/details element
# ---------------------------------------------------------------------------


class TestFAQBlocks:
    def test_details_as_faq(self):
        html = "<details><summary>What is X?</summary><p>X is Y.</p></details>"
        doc = compile_html(html)
        faqs = doc.get_blocks_by_type("faq")
        assert len(faqs) == 1
        assert "What is X?" in faqs[0].text


# ---------------------------------------------------------------------------
# Form grouping in actions
# ---------------------------------------------------------------------------


class TestFormGrouping:
    def test_form_inputs_grouped(self):
        html = """
        <form action="/search" method="get">
            <input type="text" name="q" placeholder="Search...">
            <button type="submit">Go</button>
        </form>
        """
        doc = compile_html(html)
        # Should have a submit action for the form, not separate input + button
        submit_actions = [a for a in doc.actions if a.type.value == "submit"]
        assert len(submit_actions) >= 1
        form_action = submit_actions[0]
        assert form_action.required_fields  # Should have required fields

    def test_standalone_input_preserved(self):
        """Inputs NOT in a form should remain as standalone actions."""
        html = '<input type="text" placeholder="Standalone">'
        doc = compile_html(html)
        input_actions = [a for a in doc.actions if a.type.value == "input"]
        assert len(input_actions) >= 1

    def test_login_form_grouped(self):
        html = """
        <form action="/login">
            <input type="text" name="username" placeholder="Username">
            <input type="password" name="password" placeholder="Password">
            <button type="submit">Login</button>
        </form>
        """
        doc = compile_html(html)
        submit_actions = [a for a in doc.actions if a.type.value == "submit"]
        assert len(submit_actions) >= 1


# ---------------------------------------------------------------------------
# Validation stage
# ---------------------------------------------------------------------------


class TestValidationStage:
    def test_quality_populated(self):
        html = "<html><body><h1>Title</h1><p>Content here.</p></body></html>"
        doc = compile_html(html)
        assert doc.quality.parse_confidence > 0
        assert doc.quality.block_count > 0

    def test_empty_html_warns(self):
        doc = compile_html("<html><body></body></html>")
        # Should have a warning about low block count or no content
        assert doc.quality.parse_confidence < 1.0

    def test_heading_present_improves_confidence(self):
        with_heading = compile_html("<h1>Title</h1><p>Content</p>")
        without_heading = compile_html("<p>Content only</p>")
        assert with_heading.quality.parse_confidence >= without_heading.quality.parse_confidence


# ---------------------------------------------------------------------------
# Min importance and max blocks
# ---------------------------------------------------------------------------


class TestMinImportanceMaxBlocks:
    MULTI_BLOCK_HTML = """
    <article>
        <h1>Title</h1>
        <p>Para 1</p>
        <p>Para 2</p>
        <p>Para 3</p>
        <p>Para 4</p>
        <p>Para 5</p>
        <h2>Section</h2>
        <p>Para 6</p>
    </article>
    """

    def test_max_blocks_limits(self):
        config = CompileConfig(max_blocks=3)
        doc = compile_html(self.MULTI_BLOCK_HTML, config=config)
        assert doc.block_count <= 3

    def test_min_importance_filters(self):
        config = CompileConfig(min_importance=0.8)
        doc = compile_html(self.MULTI_BLOCK_HTML, config=config)
        for block in doc.blocks:
            assert block.importance >= 0.8


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_unicode_preserved(self):
        html = "<h1>日本語</h1><p>中文内容</p><p>Ñoño</p>"
        doc = compile_html(html)
        assert "日本語" in doc.canonical_markdown
        assert "中文内容" in doc.canonical_markdown

    def test_deeply_nested_content(self):
        html = "<html><body>" + "<div>" * 20 + "<p>Deep</p>" + "</div>" * 20 + "</body></html>"
        doc = compile_html(html)
        assert any("Deep" in b.text for b in doc.blocks)

    def test_malformed_html_doesnt_crash(self):
        doc = compile_html("<p>Unclosed<div>Mixed</p></div>")
        assert doc.block_count >= 1

    def test_completely_empty(self):
        doc = compile_html("")
        assert doc.block_count == 0

    def test_whitespace_only(self):
        doc = compile_html("   \n\t  ")
        assert doc.block_count == 0

    def test_very_large_table(self):
        rows = "".join(f"<tr><td>{i}</td><td>data</td></tr>" for i in range(100))
        html = f"<table><tr><th>ID</th><th>Value</th></tr>{rows}</table>"
        doc = compile_html(html)
        tables = doc.get_blocks_by_type("table")
        assert len(tables) == 1
        assert tables[0].metadata["row_count"] == 101
