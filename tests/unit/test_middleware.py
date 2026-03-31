"""Tests for browser agent middleware."""

from __future__ import annotations

import pytest

from agent_web_compiler.core.action import Action, ActionType, StateEffect
from agent_web_compiler.core.block import Block, BlockType
from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.core.document import AgentDocument, Quality, SourceType
from agent_web_compiler.middleware.browser_middleware import (
    BrowserMiddleware,
    PageContext,
    PageVisit,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SIMPLE_HTML = """
<html>
<head><title>Test Page</title></head>
<body>
  <h1>Welcome</h1>
  <p>Hello world.</p>
  <form>
    <input id="search" type="text" placeholder="Search..." />
    <button type="submit">Go</button>
  </form>
  <a href="/about">About</a>
</body>
</html>
"""


def _make_doc(
    *,
    title: str = "Test Page",
    url: str = "https://example.com",
    confidence: float = 0.9,
    blocks: list[Block] | None = None,
    actions: list[Action] | None = None,
) -> AgentDocument:
    if blocks is None:
        blocks = [
            Block(id="b_001", type=BlockType.HEADING, text="Welcome", order=0, level=1, importance=0.9),
            Block(id="b_002", type=BlockType.PARAGRAPH, text="Hello world.", order=1, importance=0.7),
        ]
    if actions is None:
        actions = [
            Action(id="a_click", type=ActionType.CLICK, label="Click Me", selector="#btn", confidence=0.8),
            Action(
                id="a_input", type=ActionType.INPUT, label="Search", selector="#search", confidence=0.9
            ),
            Action(
                id="a_nav",
                type=ActionType.NAVIGATE,
                label="About",
                selector="a.about",
                state_effect=StateEffect(may_navigate=True, target_url="https://example.com/about"),
                confidence=0.95,
            ),
            Action(id="a_submit", type=ActionType.SUBMIT, label="Go", selector="#go", confidence=0.9),
        ]
    return AgentDocument(
        doc_id="sha256:test1234",
        source_type=SourceType.HTML,
        source_url=url,
        title=title,
        blocks=blocks,
        actions=actions,
        quality=Quality(parse_confidence=confidence, block_count=len(blocks), action_count=len(actions)),
    )


# ===========================================================================
# PageContext
# ===========================================================================


class TestPageContext:
    def test_to_llm_prompt_contains_title(self):
        doc = _make_doc()
        ctx = PageContext(doc=doc, confidence=0.9, needs_fallback=False)
        prompt = ctx.to_llm_prompt()

        assert "Test Page" in prompt
        assert "https://example.com" in prompt

    def test_to_llm_prompt_contains_actions(self):
        doc = _make_doc()
        ctx = PageContext(doc=doc, confidence=0.9, needs_fallback=False)
        prompt = ctx.to_llm_prompt()

        assert "Available actions:" in prompt
        assert "a_click" in prompt
        assert "a_input" in prompt

    def test_to_llm_prompt_fallback_warning(self):
        doc = _make_doc(confidence=0.3)
        ctx = PageContext(doc=doc, confidence=0.3, needs_fallback=True)
        prompt = ctx.to_llm_prompt()

        assert "Warning" in prompt
        assert "screenshot" in prompt.lower()

    def test_to_llm_prompt_summary_format(self):
        doc = _make_doc()
        ctx = PageContext(doc=doc, confidence=0.9, needs_fallback=False)
        prompt = ctx.to_llm_prompt(format="summary")

        # summary_markdown is used instead of action listing
        assert "Welcome" in prompt

    def test_to_action_list(self):
        doc = _make_doc()
        ctx = PageContext(doc=doc, confidence=0.9, needs_fallback=False)
        actions = ctx.to_action_list()

        assert len(actions) == 4
        for a in actions:
            assert "action_id" in a
            assert "type" in a
            assert "label" in a
            assert "selector" in a


# ===========================================================================
# BrowserMiddleware
# ===========================================================================


class TestBrowserMiddleware:
    def test_on_page_load_returns_page_context(self):
        mw = BrowserMiddleware()
        ctx = mw.on_page_load("https://example.com", SIMPLE_HTML)

        assert isinstance(ctx, PageContext)
        assert isinstance(ctx.doc, AgentDocument)
        assert isinstance(ctx.confidence, float)
        assert isinstance(ctx.needs_fallback, bool)

    def test_on_page_load_stores_history(self):
        mw = BrowserMiddleware()
        mw.on_page_load("https://example.com/1", SIMPLE_HTML)
        mw.on_page_load("https://example.com/2", SIMPLE_HTML)

        assert len(mw.history) == 2
        assert mw.history[0].url == "https://example.com/1"
        assert mw.history[1].url == "https://example.com/2"

    def test_history_trimming(self):
        mw = BrowserMiddleware(history_size=3)
        for i in range(5):
            mw.on_page_load(f"https://example.com/{i}", SIMPLE_HTML)

        assert len(mw.history) == 3
        assert mw.history[0].url == "https://example.com/2"

    def test_on_page_load_with_screenshot(self):
        mw = BrowserMiddleware()
        screenshot = b"\x89PNG\r\n\x1a\nfakedata"
        mw.on_page_load("https://example.com", SIMPLE_HTML, screenshot=screenshot)

        assert mw.history[-1].screenshot == screenshot

    def test_translate_action_click(self):
        mw = BrowserMiddleware()
        # Manually set a doc with known actions
        doc = _make_doc()
        mw._current_doc = doc

        cmd = mw.translate_action("a_click")
        assert cmd["type"] == "click"
        assert cmd["selector"] == "#btn"

    def test_translate_action_input(self):
        mw = BrowserMiddleware()
        mw._current_doc = _make_doc()

        cmd = mw.translate_action("a_input")
        assert cmd["type"] == "fill"
        assert cmd["selector"] == "#search"

    def test_translate_action_navigate(self):
        mw = BrowserMiddleware()
        mw._current_doc = _make_doc()

        cmd = mw.translate_action("a_nav")
        assert cmd["type"] == "navigate"
        assert cmd["url"] == "https://example.com/about"

    def test_translate_action_submit(self):
        mw = BrowserMiddleware()
        mw._current_doc = _make_doc()

        cmd = mw.translate_action("a_submit")
        assert cmd["type"] == "click"

    def test_translate_action_not_found(self):
        mw = BrowserMiddleware()
        mw._current_doc = _make_doc()

        with pytest.raises(ValueError, match="not found"):
            mw.translate_action("nonexistent")

    def test_translate_action_no_page(self):
        mw = BrowserMiddleware()

        with pytest.raises(ValueError, match="No page loaded"):
            mw.translate_action("a_click")

    def test_get_history_summary_empty(self):
        mw = BrowserMiddleware()
        summary = mw.get_history_summary()
        assert "No pages visited" in summary

    def test_get_history_summary_with_visits(self):
        mw = BrowserMiddleware()
        mw.on_page_load("https://example.com", SIMPLE_HTML)

        summary = mw.get_history_summary()
        assert "example.com" in summary
        assert "Recent page visits:" in summary

    def test_needs_screenshot_fallback_no_page(self):
        mw = BrowserMiddleware()
        assert mw.needs_screenshot_fallback() is True

    def test_needs_screenshot_fallback_high_confidence(self):
        mw = BrowserMiddleware()
        mw._current_doc = _make_doc(confidence=0.9)
        assert mw.needs_screenshot_fallback() is False

    def test_needs_screenshot_fallback_low_confidence(self):
        mw = BrowserMiddleware(fallback_threshold=0.8)
        mw._current_doc = _make_doc(confidence=0.3)
        assert mw.needs_screenshot_fallback() is True

    def test_custom_config(self):
        cfg = CompileConfig(debug=True)
        mw = BrowserMiddleware(config=cfg)
        assert mw.config.debug is True

    def test_custom_fallback_threshold(self):
        mw = BrowserMiddleware(fallback_threshold=0.9)
        assert mw.fallback_threshold == 0.9


# ===========================================================================
# PageVisit dataclass
# ===========================================================================


class TestPageVisit:
    def test_creation(self):
        doc = _make_doc()
        visit = PageVisit(url="https://example.com", doc=doc, timestamp=1000.0)

        assert visit.url == "https://example.com"
        assert visit.doc is doc
        assert visit.timestamp == 1000.0
        assert visit.screenshot is None

    def test_with_screenshot(self):
        doc = _make_doc()
        data = b"screenshot_bytes"
        visit = PageVisit(url="https://example.com", doc=doc, timestamp=1000.0, screenshot=data)
        assert visit.screenshot == data
