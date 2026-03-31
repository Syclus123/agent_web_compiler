"""Tests for the unified AgentSearch SDK."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from agent_web_compiler.core.action import Action, ActionType
from agent_web_compiler.core.block import Block, BlockType
from agent_web_compiler.core.document import AgentDocument, SourceType
from agent_web_compiler.search.agent_search import AgentSearch

# --- Fixtures ---


def _make_doc(
    doc_id: str = "test_doc_001",
    title: str = "Test Document",
    source_url: str | None = "https://example.com",
    blocks: list[Block] | None = None,
    actions: list[Action] | None = None,
) -> AgentDocument:
    """Create a minimal AgentDocument for testing."""
    return AgentDocument(
        doc_id=doc_id,
        source_type=SourceType.HTML,
        source_url=source_url,
        title=title,
        blocks=blocks or [
            Block(
                id="b_001",
                type=BlockType.HEADING,
                text="Getting Started",
                importance=0.9,
                order=0,
                section_path=["Getting Started"],
            ),
            Block(
                id="b_002",
                type=BlockType.PARAGRAPH,
                text="The API rate limit is 100 requests per minute for free tier users.",
                importance=0.7,
                order=1,
                section_path=["Getting Started", "Rate Limits"],
            ),
            Block(
                id="b_003",
                type=BlockType.PARAGRAPH,
                text="Authentication uses OAuth 2.0 with bearer tokens.",
                importance=0.8,
                order=2,
                section_path=["Authentication"],
            ),
            Block(
                id="b_004",
                type=BlockType.CODE,
                text='curl -H "Authorization: Bearer TOKEN" https://api.example.com/v1/data',
                importance=0.6,
                order=3,
                section_path=["Authentication", "Examples"],
            ),
        ],
        actions=actions or [
            Action(
                id="a_001",
                type=ActionType.NAVIGATE,
                label="Go to API Reference",
                selector="a.api-ref",
                role="navigation",
                confidence=0.9,
                priority=0.8,
            ),
            Action(
                id="a_002",
                type=ActionType.INPUT,
                label="Search documentation",
                selector="input#search",
                role="search",
                confidence=0.85,
                priority=0.7,
            ),
            Action(
                id="a_003",
                type=ActionType.SUBMIT,
                label="Submit search",
                selector="button#search-submit",
                role="submit_search",
                confidence=0.85,
                priority=0.6,
            ),
        ],
    )


def _make_second_doc() -> AgentDocument:
    """Create a second document for multi-doc tests."""
    return AgentDocument(
        doc_id="test_doc_002",
        source_type=SourceType.HTML,
        source_url="https://example.com/pricing",
        title="Pricing",
        blocks=[
            Block(
                id="b_p001",
                type=BlockType.HEADING,
                text="Pricing Plans",
                importance=0.9,
                order=0,
                section_path=["Pricing"],
            ),
            Block(
                id="b_p002",
                type=BlockType.PARAGRAPH,
                text="The free tier includes 1000 API calls per day.",
                importance=0.8,
                order=1,
                section_path=["Pricing", "Free Tier"],
            ),
            Block(
                id="b_p003",
                type=BlockType.PARAGRAPH,
                text="Enterprise pricing starts at $99/month with unlimited API calls.",
                importance=0.7,
                order=2,
                section_path=["Pricing", "Enterprise"],
            ),
        ],
        actions=[
            Action(
                id="a_p001",
                type=ActionType.CLICK,
                label="Download pricing PDF",
                selector="a.download-pdf",
                role="download",
                confidence=0.9,
                priority=0.8,
            ),
        ],
    )


# --- Ingestion tests ---


class TestIngestion:
    def test_ingest_document(self) -> None:
        search = AgentSearch()
        doc = _make_doc()
        search.ingest(doc)
        stats = search.stats
        assert stats["documents"] == 1
        assert stats["blocks"] == 4
        assert stats["actions"] == 3

    def test_ingest_multiple_documents(self) -> None:
        search = AgentSearch()
        search.ingest(_make_doc())
        search.ingest(_make_second_doc())
        stats = search.stats
        assert stats["documents"] == 2
        assert stats["blocks"] == 7
        assert stats["actions"] == 4

    def test_ingest_idempotent(self) -> None:
        """Re-ingesting the same doc should replace, not duplicate."""
        search = AgentSearch()
        doc = _make_doc()
        search.ingest(doc)
        search.ingest(doc)
        assert search.stats["documents"] == 1
        assert search.stats["blocks"] == 4


# --- Search tests ---


class TestSearch:
    def _setup_search(self) -> AgentSearch:
        search = AgentSearch()
        search.ingest(_make_doc())
        search.ingest(_make_second_doc())
        return search

    def test_search_returns_results(self) -> None:
        search = self._setup_search()
        response = search.search("rate limit")
        assert len(response.results) > 0
        assert response.query == "rate limit"

    def test_search_relevance(self) -> None:
        search = self._setup_search()
        response = search.search("rate limit")
        # The block about rate limits should be in results
        texts = [r.text for r in response.results]
        assert any("rate limit" in t.lower() for t in texts)

    def test_search_top_k(self) -> None:
        search = self._setup_search()
        response = search.search("API", top_k=2)
        assert len(response.results) <= 2

    def test_search_blocks_only(self) -> None:
        search = self._setup_search()
        results = search.search_blocks("authentication")
        assert all(r.kind == "block" for r in results)

    def test_search_actions_only(self) -> None:
        search = self._setup_search()
        results = search.search_actions("search")
        assert all(r.kind == "action" for r in results)

    def test_search_empty_index(self) -> None:
        search = AgentSearch()
        response = search.search("anything")
        assert len(response.results) == 0


# --- Answer tests ---


class TestAnswer:
    def _setup_search(self) -> AgentSearch:
        search = AgentSearch()
        search.ingest(_make_doc())
        search.ingest(_make_second_doc())
        return search

    def test_answer_returns_grounded_answer(self) -> None:
        search = self._setup_search()
        answer = search.answer("What is the rate limit?")
        assert answer.answer_text
        assert isinstance(answer.confidence, float)

    def test_answer_has_citations(self) -> None:
        search = self._setup_search()
        answer = search.answer("What is the rate limit?")
        # Should have at least one citation
        if answer.evidence_sufficient:
            assert len(answer.citations) > 0

    def test_answer_to_markdown(self) -> None:
        search = self._setup_search()
        answer = search.answer("What is the rate limit?")
        md = answer.to_markdown()
        assert "Answer" in md

    def test_answer_empty_index(self) -> None:
        search = AgentSearch()
        answer = search.answer("anything")
        assert answer.confidence == 0.0
        assert not answer.evidence_sufficient


# --- Plan tests ---


class TestPlan:
    def _setup_search(self) -> AgentSearch:
        search = AgentSearch()
        search.ingest(_make_doc())
        search.ingest(_make_second_doc())
        return search

    def test_plan_navigation(self) -> None:
        search = self._setup_search()
        plan = search.plan("go to the pricing page")
        assert plan.task == "go to the pricing page"
        assert len(plan.steps) >= 1

    def test_plan_download(self) -> None:
        search = self._setup_search()
        plan = search.plan("download the pricing PDF")
        assert any(s.action_type == "click" for s in plan.steps)

    def test_plan_search(self) -> None:
        search = self._setup_search()
        plan = search.plan("search for authentication")
        assert any(s.action_type == "fill" for s in plan.steps)

    def test_plan_to_markdown(self) -> None:
        search = self._setup_search()
        plan = search.plan("download the pricing PDF")
        md = plan.to_markdown()
        assert "Execution Plan" in md

    def test_plan_to_browser_commands(self) -> None:
        search = self._setup_search()
        plan = search.plan("go to https://example.com")
        cmds = plan.to_browser_commands()
        assert len(cmds) >= 1
        assert all("type" in cmd for cmd in cmds)

    def test_plan_to_dict(self) -> None:
        search = self._setup_search()
        plan = search.plan("download the pricing PDF")
        d = plan.to_dict()
        assert "task" in d
        assert "steps" in d
        assert "confidence" in d

    def test_plan_empty_index(self) -> None:
        search = AgentSearch()
        plan = search.plan("download something")
        # Should still produce steps from pattern matching
        assert isinstance(plan.steps, list)


# --- Save/Load tests ---


class TestSaveLoad:
    def test_save_and_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "test_index.json")

            # Save
            search1 = AgentSearch()
            search1.ingest(_make_doc())
            search1.ingest(_make_second_doc())
            search1.save(path)

            # Verify file was created
            assert Path(path).exists()

            # Load
            search2 = AgentSearch()
            search2.load(path)
            assert search2.stats == search1.stats

    def test_load_nonexistent_raises(self) -> None:
        search = AgentSearch()
        with pytest.raises(FileNotFoundError):
            search.load("/nonexistent/path/index.json")

    def test_save_load_search_works(self) -> None:
        """End-to-end: save, load, and search produces results."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "test_index.json")

            search1 = AgentSearch()
            search1.ingest(_make_doc())
            search1.save(path)

            search2 = AgentSearch()
            search2.load(path)
            response = search2.search("rate limit")
            assert len(response.results) > 0

    def test_save_load_preserves_content(self) -> None:
        """Verify that loaded index has the same data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "test_index.json")

            search1 = AgentSearch()
            search1.ingest(_make_doc())
            search1.save(path)

            search2 = AgentSearch()
            search2.load(path)

            # Both should return similar search results
            r1 = search1.search("authentication")
            r2 = search2.search("authentication")
            assert len(r1.results) == len(r2.results)


# --- Stats tests ---


class TestStats:
    def test_empty_stats(self) -> None:
        search = AgentSearch()
        stats = search.stats
        assert stats["documents"] == 0
        assert stats["blocks"] == 0
        assert stats["actions"] == 0
        assert stats["sites"] == 0

    def test_stats_after_ingest(self) -> None:
        search = AgentSearch()
        search.ingest(_make_doc())
        stats = search.stats
        assert stats["documents"] == 1
        assert stats["blocks"] > 0
        assert stats["actions"] > 0
