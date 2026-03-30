"""Tests for text utilities."""

from __future__ import annotations

from agent_web_compiler.utils.text import (
    clean_whitespace,
    count_tokens_approx,
    extract_text_from_html,
    truncate,
)


class TestCleanWhitespace:
    def test_collapses_spaces(self):
        assert clean_whitespace("hello   world") == "hello world"

    def test_collapses_tabs_and_newlines(self):
        assert clean_whitespace("hello\n\t  world") == "hello world"

    def test_strips_leading_trailing(self):
        assert clean_whitespace("  hello  ") == "hello"

    def test_empty_string(self):
        assert clean_whitespace("") == ""

    def test_only_whitespace(self):
        assert clean_whitespace("   \t\n  ") == ""

    def test_single_word(self):
        assert clean_whitespace("hello") == "hello"


class TestTruncate:
    def test_short_text_unchanged(self):
        assert truncate("hello", max_length=10) == "hello"

    def test_exact_length_unchanged(self):
        assert truncate("hello", max_length=5) == "hello"

    def test_truncated_with_suffix(self):
        result = truncate("hello world", max_length=8)
        assert result == "hello..."
        assert len(result) <= 8

    def test_custom_suffix(self):
        result = truncate("hello world", max_length=9, suffix="~~")
        assert result.endswith("~~")
        assert len(result) <= 9

    def test_very_short_max_length(self):
        result = truncate("hello world", max_length=3)
        assert len(result) <= 3

    def test_max_length_equals_suffix_length(self):
        result = truncate("hello world", max_length=3, suffix="...")
        assert len(result) <= 3

    def test_empty_string(self):
        assert truncate("", max_length=10) == ""

    def test_large_max_length(self):
        text = "hello"
        assert truncate(text, max_length=1000) == "hello"


class TestCountTokensApprox:
    def test_empty_string(self):
        assert count_tokens_approx("") == 0

    def test_whitespace_only(self):
        assert count_tokens_approx("   ") == 0

    def test_single_word(self):
        result = count_tokens_approx("hello")
        assert result >= 1

    def test_multiple_words(self):
        result = count_tokens_approx("hello world foo bar")
        # 4 words * 1.3 = 5.2 -> 5
        assert result >= 4

    def test_returns_int(self):
        result = count_tokens_approx("some text here")
        assert isinstance(result, int)

    def test_always_positive_for_nonempty(self):
        assert count_tokens_approx("a") >= 1


class TestExtractTextFromHtml:
    def test_simple_html(self):
        result = extract_text_from_html("<p>Hello <b>world</b></p>")
        assert "Hello" in result
        assert "world" in result

    def test_strips_tags(self):
        result = extract_text_from_html("<div><span>text</span></div>")
        assert "<" not in result
        assert "text" in result

    def test_empty_html(self):
        assert extract_text_from_html("") == ""

    def test_whitespace_only(self):
        assert extract_text_from_html("   ") == ""

    def test_normalizes_whitespace(self):
        result = extract_text_from_html("<p>hello    \n\n   world</p>")
        assert result == "hello world"

    def test_script_tag_text_included(self):
        # extract_text_from_html just strips tags; it does NOT remove script content
        # (that's the normalizer's job). It just extracts text_content.
        result = extract_text_from_html("<div><script>var x=1;</script>text</div>")
        # lxml text_content includes text of all descendants
        assert "text" in result
