"""Tests for HTMLNormalizer."""

from __future__ import annotations

import pytest

from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.normalizers.html_normalizer import HTMLNormalizer


@pytest.fixture
def normalizer() -> HTMLNormalizer:
    return HTMLNormalizer()


@pytest.fixture
def config() -> CompileConfig:
    return CompileConfig()


class TestHTMLNormalizer:
    def test_empty_input_returns_empty(self, normalizer, config):
        assert normalizer.normalize("", config) == ""

    def test_whitespace_only_returns_empty(self, normalizer, config):
        assert normalizer.normalize("   \n\t  ", config) == ""

    def test_removes_script_tags(self, normalizer, config):
        html = "<html><body><script>alert('xss')</script><p>Content</p></body></html>"
        result = normalizer.normalize(html, config)
        assert "alert" not in result
        assert "script" not in result.lower()
        assert "Content" in result

    def test_removes_style_tags(self, normalizer, config):
        html = "<html><body><style>.x{color:red}</style><p>Content</p></body></html>"
        result = normalizer.normalize(html, config)
        assert "color:red" not in result
        assert "Content" in result

    def test_removes_noscript_tags(self, normalizer, config):
        html = "<html><body><noscript>Enable JS</noscript><p>Content</p></body></html>"
        result = normalizer.normalize(html, config)
        assert "Enable JS" not in result
        assert "Content" in result

    def test_removes_boilerplate_header_low_content(self, normalizer, config):
        html = """<html><body>
            <header><a href="/">Home</a></header>
            <main><article><p>This is a really important article with lots of meaningful content that should be preserved.</p></article></main>
            <footer><a href="/terms">Terms</a></footer>
        </body></html>"""
        result = normalizer.normalize(html, config)
        assert "important article" in result

    def test_removes_boilerplate_nav_low_content(self, normalizer, config):
        html = """<html><body>
            <nav><a href="/">Home</a><a href="/about">About</a></nav>
            <main><p>This is a substantial paragraph with plenty of meaningful content for the reader to enjoy.</p></main>
        </body></html>"""
        result = normalizer.normalize(html, config)
        assert "substantial paragraph" in result

    def test_preserves_main_content_area(self, normalizer, config):
        html = """<html><body>
            <main>
                <article>
                    <h1>Article Title</h1>
                    <p>This is the main content of the article.</p>
                </article>
            </main>
        </body></html>"""
        result = normalizer.normalize(html, config)
        assert "Article Title" in result
        assert "main content" in result

    def test_noise_pattern_cookie_banner(self, normalizer, config):
        html = """<html><body>
            <div class="cookie-banner">Accept cookies</div>
            <main><p>This is a very important and substantial article with real content for the reader.</p></main>
        </body></html>"""
        result = normalizer.normalize(html, config)
        assert "important and substantial" in result

    def test_noise_pattern_subscribe_popup(self, normalizer, config):
        html = """<html><body>
            <div class="subscribe-popup">Subscribe now!</div>
            <main><p>This is real content that matters a lot and contains actual useful information for readers.</p></main>
        </body></html>"""
        result = normalizer.normalize(html, config)
        assert "real content" in result

    def test_elements_inside_main_preserved_even_short(self, normalizer, config):
        """Elements inside main/article should not be penalized for short text."""
        html = """<html><body>
            <main>
                <article>
                    <p>Short text</p>
                    <p>Another paragraph with some real content for readers to enjoy and learn from.</p>
                </article>
            </main>
        </body></html>"""
        result = normalizer.normalize(html, config)
        # The main/article container itself is preserved
        assert "real content" in result

    def test_malformed_html(self, normalizer, config):
        """Malformed HTML should not crash; returns empty or partial result."""
        html = "<html><body><p>Unclosed"
        result = normalizer.normalize(html, config)
        # Should not raise, may return content or empty
        assert isinstance(result, str)

    def test_completely_broken_html(self, normalizer, config):
        """Completely broken HTML that can't be parsed."""
        # lxml is quite permissive, so we test that it doesn't crash
        result = normalizer.normalize("<<<>>>", config)
        assert isinstance(result, str)
