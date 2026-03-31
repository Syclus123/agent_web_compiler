"""Tests for streaming compilation pipeline."""

from __future__ import annotations

import pytest

from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.pipeline.stream_compiler import (
    StreamCompiler,
    StreamEvent,
    _estimate_tokens,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SIMPLE_HTML = """<!DOCTYPE html>
<html>
<head><title>Stream Test</title></head>
<body>
    <h1>Welcome</h1>
    <p>This is a paragraph of content for testing streaming compilation.</p>
    <button>Click me</button>
    <a href="/about">About us</a>
</body>
</html>"""

LARGE_HTML = """<!DOCTYPE html>
<html>
<head><title>Large Doc</title></head>
<body>
    <h1>Title</h1>
    <p>Paragraph one with some content that spans multiple words.</p>
    <p>Paragraph two with additional content for the document.</p>
    <p>Paragraph three with even more content to fill the page.</p>
    <p>Paragraph four with yet another block of text content.</p>
    <p>Paragraph five that should push us over a small token budget.</p>
    <p>Paragraph six with final content for the large document.</p>
</body>
</html>"""


@pytest.fixture
def compiler() -> StreamCompiler:
    return StreamCompiler()


# ---------------------------------------------------------------------------
# StreamEvent
# ---------------------------------------------------------------------------

class TestStreamEvent:
    def test_basic_construction(self):
        event = StreamEvent(event_type="block", data={"text": "hello"})
        assert event.event_type == "block"
        assert event.data == {"text": "hello"}
        assert event.sequence == 0

    def test_sequence_number(self):
        event = StreamEvent(event_type="progress", data={}, sequence=5)
        assert event.sequence == 5


# ---------------------------------------------------------------------------
# _estimate_tokens
# ---------------------------------------------------------------------------

class TestEstimateTokens:
    def test_empty_string(self):
        assert _estimate_tokens("") == 1  # Minimum 1

    def test_short_string(self):
        # "hello" = 5 chars -> 5 // 4 = 1
        assert _estimate_tokens("hello") == 1

    def test_longer_string(self):
        text = "a" * 400  # 400 chars -> 100 tokens
        assert _estimate_tokens(text) == 100


# ---------------------------------------------------------------------------
# StreamCompiler.compile_stream
# ---------------------------------------------------------------------------

class TestCompileStream:
    def test_yields_events(self, compiler):
        events = list(compiler.compile_stream(SIMPLE_HTML))
        assert len(events) > 0

    def test_first_event_is_progress(self, compiler):
        events = list(compiler.compile_stream(SIMPLE_HTML))
        assert events[0].event_type == "progress"
        assert events[0].data["stage"] == "normalizing"

    def test_last_event_is_complete(self, compiler):
        events = list(compiler.compile_stream(SIMPLE_HTML))
        last = events[-1]
        assert last.event_type == "complete"

    def test_complete_event_has_document_fields(self, compiler):
        events = list(compiler.compile_stream(SIMPLE_HTML))
        complete = events[-1]
        assert complete.event_type == "complete"
        data = complete.data
        assert "doc_id" in data
        assert "blocks" in data
        assert "title" in data
        assert data["title"] == "Stream Test"

    def test_block_events_emitted(self, compiler):
        events = list(compiler.compile_stream(SIMPLE_HTML))
        block_events = [e for e in events if e.event_type == "block"]
        assert len(block_events) > 0

    def test_block_event_has_expected_fields(self, compiler):
        events = list(compiler.compile_stream(SIMPLE_HTML))
        block_events = [e for e in events if e.event_type == "block"]
        assert len(block_events) > 0
        block = block_events[0]
        assert "id" in block.data
        assert "type" in block.data
        assert "text" in block.data

    def test_action_events_emitted(self, compiler):
        config = CompileConfig(include_actions=True)
        events = list(compiler.compile_stream(SIMPLE_HTML, config=config))
        action_events = [e for e in events if e.event_type == "action"]
        assert len(action_events) > 0

    def test_no_actions_when_disabled(self, compiler):
        config = CompileConfig(include_actions=False)
        events = list(compiler.compile_stream(SIMPLE_HTML, config=config))
        action_events = [e for e in events if e.event_type == "action"]
        assert len(action_events) == 0

    def test_progress_events_present(self, compiler):
        events = list(compiler.compile_stream(SIMPLE_HTML))
        progress_events = [e for e in events if e.event_type == "progress"]
        stages = [e.data["stage"] for e in progress_events]
        assert "normalizing" in stages
        assert "segmenting" in stages
        assert "validating" in stages

    def test_sequence_numbers_monotonic(self, compiler):
        events = list(compiler.compile_stream(SIMPLE_HTML))
        for i, event in enumerate(events):
            assert event.sequence == i

    def test_source_url_in_complete(self, compiler):
        events = list(
            compiler.compile_stream(SIMPLE_HTML, source_url="https://example.com")
        )
        complete = events[-1]
        assert complete.data.get("source_url") == "https://example.com"

    def test_default_config_used(self, compiler):
        # Should not raise when config is None
        events = list(compiler.compile_stream(SIMPLE_HTML, config=None))
        assert any(e.event_type == "complete" for e in events)


# ---------------------------------------------------------------------------
# Token budget
# ---------------------------------------------------------------------------

class TestTokenBudget:
    def test_budget_reached_event(self, compiler):
        config = CompileConfig(token_budget=10)  # Very small budget
        events = list(compiler.compile_stream(LARGE_HTML, config=config))
        budget_events = [e for e in events if e.event_type == "budget_reached"]
        assert len(budget_events) == 1

    def test_budget_stops_blocks(self, compiler):
        # Compile once without budget to count total blocks
        all_events = list(compiler.compile_stream(LARGE_HTML))
        all_blocks = [e for e in all_events if e.event_type == "block"]

        # Now compile with a small budget
        config = CompileConfig(token_budget=50)
        budget_events = list(compiler.compile_stream(LARGE_HTML, config=config))
        budget_blocks = [e for e in budget_events if e.event_type == "block"]

        # Budget should result in fewer blocks (or equal if all fit)
        assert len(budget_blocks) <= len(all_blocks)

    def test_budget_reached_has_count(self, compiler):
        config = CompileConfig(token_budget=10)
        events = list(compiler.compile_stream(LARGE_HTML, config=config))
        budget_events = [e for e in events if e.event_type == "budget_reached"]
        if budget_events:
            assert "blocks_emitted" in budget_events[0].data
            assert "reason" in budget_events[0].data

    def test_no_budget_no_budget_event(self, compiler):
        config = CompileConfig(token_budget=None)
        events = list(compiler.compile_stream(SIMPLE_HTML, config=config))
        budget_events = [e for e in events if e.event_type == "budget_reached"]
        assert len(budget_events) == 0

    def test_complete_event_after_budget(self, compiler):
        config = CompileConfig(token_budget=10)
        events = list(compiler.compile_stream(LARGE_HTML, config=config))
        # Should still get a complete event even with budget
        assert events[-1].event_type == "complete"


# ---------------------------------------------------------------------------
# Async streaming
# ---------------------------------------------------------------------------

class TestAsyncCompileStream:
    @pytest.mark.asyncio
    async def test_async_yields_events(self, compiler):
        events = []
        async for event in compiler.compile_stream_async(SIMPLE_HTML):
            events.append(event)
        assert len(events) > 0

    @pytest.mark.asyncio
    async def test_async_complete_event(self, compiler):
        events = []
        async for event in compiler.compile_stream_async(SIMPLE_HTML):
            events.append(event)
        assert events[-1].event_type == "complete"

    @pytest.mark.asyncio
    async def test_async_with_config(self, compiler):
        config = CompileConfig(include_actions=True)
        events = []
        async for event in compiler.compile_stream_async(
            SIMPLE_HTML, config=config
        ):
            events.append(event)
        action_events = [e for e in events if e.event_type == "action"]
        assert len(action_events) > 0


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestStreamErrors:
    def test_empty_html_does_not_crash(self, compiler):
        events = list(compiler.compile_stream(""))
        # Should get at least a complete or error event
        assert len(events) > 0
        last = events[-1]
        assert last.event_type in ("complete", "error")

    def test_minimal_html(self, compiler):
        events = list(compiler.compile_stream("<p>hello</p>"))
        assert any(e.event_type == "complete" for e in events)


# ---------------------------------------------------------------------------
# Public API: compile_stream
# ---------------------------------------------------------------------------

class TestPublicCompileStream:
    def test_import_from_api(self):
        from agent_web_compiler.api.compile import compile_stream
        assert callable(compile_stream)

    def test_import_from_top_level(self):
        from agent_web_compiler import compile_stream
        assert callable(compile_stream)

    def test_basic_usage(self):
        from agent_web_compiler import compile_stream

        events = list(compile_stream(SIMPLE_HTML))
        assert len(events) > 0
        assert events[-1].event_type == "complete"

    def test_with_token_budget(self):
        from agent_web_compiler.api.compile import compile_stream

        events = list(compile_stream(LARGE_HTML, token_budget=20))
        event_types = {e.event_type for e in events}
        assert "complete" in event_types


# ---------------------------------------------------------------------------
# Debug metadata
# ---------------------------------------------------------------------------

class TestStreamDebug:
    def test_debug_timings_in_complete(self, compiler):
        config = CompileConfig(debug=True)
        events = list(compiler.compile_stream(SIMPLE_HTML, config=config))
        complete = events[-1]
        assert complete.event_type == "complete"
        debug = complete.data.get("debug", {})
        assert "timings" in debug
        assert debug.get("streaming") is True

    def test_no_debug_by_default(self, compiler):
        events = list(compiler.compile_stream(SIMPLE_HTML))
        complete = events[-1]
        debug = complete.data.get("debug", {})
        assert "timings" not in debug
