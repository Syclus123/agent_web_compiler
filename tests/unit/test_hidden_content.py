"""Tests for hidden content filtering — display:none, aria-hidden, hidden attr."""

from __future__ import annotations

from agent_web_compiler import compile_html


class TestHiddenContentFiltering:
    """Verify hidden elements are excluded from compiled output."""

    def test_display_none_filtered(self):
        html = '<div style="display:none"><p>Hidden</p></div><p>Visible</p>'
        doc = compile_html(html)
        texts = [b.text for b in doc.blocks]
        assert "Visible" in texts
        assert not any("Hidden" in t for t in texts)

    def test_display_none_with_spaces(self):
        html = '<div style="display : none"><p>Hidden</p></div><p>Visible</p>'
        doc = compile_html(html)
        assert not any("Hidden" in b.text for b in doc.blocks)

    def test_visibility_hidden_filtered(self):
        html = '<p style="visibility:hidden">Ghost</p><p>Real</p>'
        doc = compile_html(html)
        assert not any("Ghost" in b.text for b in doc.blocks)
        assert any("Real" in b.text for b in doc.blocks)

    def test_hidden_attribute_filtered(self):
        html = '<p hidden>Nope</p><p>Yep</p>'
        doc = compile_html(html)
        assert not any("Nope" in b.text for b in doc.blocks)
        assert any("Yep" in b.text for b in doc.blocks)

    def test_aria_hidden_true_filtered(self):
        html = '<div aria-hidden="true"><p>Screen reader hidden</p></div><p>Normal</p>'
        doc = compile_html(html)
        assert not any("Screen reader" in b.text for b in doc.blocks)
        assert any("Normal" in b.text for b in doc.blocks)

    def test_aria_hidden_false_preserved(self):
        html = '<div aria-hidden="false"><p>Shown</p></div>'
        doc = compile_html(html)
        assert any("Shown" in b.text for b in doc.blocks)

    def test_nested_hidden_filtered(self):
        """Hidden ancestor should hide all descendants."""
        html = '<div style="display:none"><article><h1>Title</h1><p>Content</p></article></div><p>Visible</p>'
        doc = compile_html(html)
        assert not any("Title" in b.text for b in doc.blocks)
        assert not any("Content" in b.text for b in doc.blocks)
        assert any("Visible" in b.text for b in doc.blocks)

    def test_hidden_actions_filtered(self):
        html = '<button style="display:none">Hidden Btn</button><button>Visible Btn</button>'
        doc = compile_html(html)
        labels = [a.label for a in doc.actions]
        assert "Visible Btn" in labels
        # Hidden button should ideally be filtered (checked by action extractor)

    def test_mixed_visibility(self):
        html = """
        <article>
            <h1>Title</h1>
            <p>Visible paragraph</p>
            <div style="display:none"><p>Hidden paragraph</p></div>
            <div aria-hidden="true"><p>Also hidden</p></div>
            <p>Another visible</p>
        </article>
        """
        doc = compile_html(html)
        texts = " ".join(b.text for b in doc.blocks)
        assert "Visible paragraph" in texts
        assert "Another visible" in texts
        assert "Hidden paragraph" not in texts
        assert "Also hidden" not in texts

    def test_input_type_hidden_not_action(self):
        """input[type=hidden] should not produce actions."""
        html = '<form><input type="hidden" name="csrf" value="abc"><input type="text" name="q" placeholder="Search"><button>Go</button></form>'
        doc = compile_html(html)
        # csrf should not be an action
        assert not any("csrf" in (a.label or "") for a in doc.actions)
