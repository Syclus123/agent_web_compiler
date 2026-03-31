"""Tests for AgentSearch integration with action graph analysis."""

from __future__ import annotations

from agent_web_compiler.core.action import Action, ActionType
from agent_web_compiler.core.block import Block, BlockType
from agent_web_compiler.core.document import AgentDocument, SourceType
from agent_web_compiler.search.agent_search import AgentSearch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc(
    doc_id: str = "test_doc_001",
    title: str = "Test Document",
    source_url: str = "https://example.com",
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
            Block(id="b_001", type=BlockType.HEADING, text="API Docs", importance=0.9, order=0),
            Block(id="b_002", type=BlockType.PARAGRAPH, text="Use the API to access data.", importance=0.7, order=1),
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
                confidence=0.9,
                priority=0.7,
            ),
            Action(
                id="a_003",
                type=ActionType.SUBMIT,
                label="Submit search",
                selector="button#go",
                role="submit_search",
                confidence=0.8,
                priority=0.6,
            ),
        ],
    )


# ---------------------------------------------------------------------------
# analyze_actions tests
# ---------------------------------------------------------------------------


class TestAnalyzeActions:
    """Tests for AgentSearch.analyze_actions()."""

    def test_analyze_with_doc(self) -> None:
        """analyze_actions should return stats for a single document."""
        search = AgentSearch()
        doc = _make_doc()
        result = search.analyze_actions(doc)

        assert result["action_count"] == 3
        assert "navigate" in result["action_types"]
        assert "input" in result["action_types"]
        assert "submit" in result["action_types"]
        assert "navigation" in result["action_roles"]
        assert "search" in result["action_roles"]
        assert isinstance(result["api_candidates"], list)

    def test_analyze_without_doc_uses_index(self) -> None:
        """analyze_actions with no doc should use index actions."""
        search = AgentSearch()
        doc = _make_doc()
        search.ingest(doc)

        result = search.analyze_actions()
        assert result["action_count"] == 3
        assert "navigate" in result["action_types"]

    def test_analyze_empty_index(self) -> None:
        """analyze_actions on empty index should return zeros."""
        search = AgentSearch()
        result = search.analyze_actions()
        assert result["action_count"] == 0
        assert result["action_types"] == {}
        assert result["action_roles"] == {}

    def test_analyze_has_graph_builder_key(self) -> None:
        """Result should indicate whether actiongraph package is available."""
        search = AgentSearch()
        result = search.analyze_actions()
        assert "has_graph_builder" in result
        assert isinstance(result["has_graph_builder"], bool)

    def test_analyze_doc_no_actions(self) -> None:
        """Document with no actions should produce minimal stats."""
        search = AgentSearch()
        doc = _make_doc(actions=[])
        result = search.analyze_actions(doc)
        # May have 0 or few actions depending on analysis
        assert isinstance(result["action_count"], int)
        assert isinstance(result["api_candidates"], list)


# ---------------------------------------------------------------------------
# get_api_candidates tests
# ---------------------------------------------------------------------------


class TestGetAPICandidates:
    """Tests for AgentSearch.get_api_candidates()."""

    def test_heuristic_finds_submit(self) -> None:
        """Submit actions should be identified as API candidates."""
        search = AgentSearch()
        doc = _make_doc()
        candidates = search.get_api_candidates(doc)

        assert len(candidates) >= 1
        labels = [c["label"] for c in candidates]
        # Submit search and Search documentation should both appear
        assert any("search" in label.lower() or "submit" in label.lower() for label in labels)

    def test_heuristic_submit_uses_post(self) -> None:
        """Submit actions should get POST method."""
        search = AgentSearch()
        doc = _make_doc(
            actions=[
                Action(
                    id="a_sub",
                    type=ActionType.SUBMIT,
                    label="Submit form",
                    selector="button#submit",
                    role="submit",
                    confidence=0.9,
                    priority=0.8,
                ),
            ]
        )
        candidates = search.get_api_candidates(doc)
        assert len(candidates) == 1
        assert candidates[0]["method"] == "POST"
        assert candidates[0]["source"] == "heuristic"

    def test_heuristic_search_uses_get(self) -> None:
        """Input actions with search role should get GET method."""
        search = AgentSearch()
        doc = _make_doc(
            actions=[
                Action(
                    id="a_search",
                    type=ActionType.INPUT,
                    label="Search",
                    selector="input#q",
                    role="search",
                    confidence=0.9,
                    priority=0.8,
                ),
            ]
        )
        candidates = search.get_api_candidates(doc)
        assert len(candidates) == 1
        assert candidates[0]["method"] == "GET"

    def test_navigate_not_api_candidate(self) -> None:
        """Plain navigate actions should not be API candidates."""
        search = AgentSearch()
        doc = _make_doc(
            actions=[
                Action(
                    id="a_nav",
                    type=ActionType.NAVIGATE,
                    label="About us",
                    selector="a.about",
                    role="navigation",
                    confidence=0.9,
                    priority=0.5,
                ),
            ]
        )
        candidates = search.get_api_candidates(doc)
        assert len(candidates) == 0

    def test_no_doc_returns_empty(self) -> None:
        """get_api_candidates without a doc and no actiongraph should return empty."""
        search = AgentSearch()
        candidates = search.get_api_candidates()
        assert candidates == []

    def test_candidates_have_required_keys(self) -> None:
        """Each candidate dict should have method, label, role, selector, source."""
        search = AgentSearch()
        doc = _make_doc()
        candidates = search.get_api_candidates(doc)
        for c in candidates:
            assert "method" in c
            assert "label" in c
            assert "role" in c
            assert "selector" in c
            assert "source" in c


# ---------------------------------------------------------------------------
# Integration: ingest + analyze round-trip
# ---------------------------------------------------------------------------


class TestIngestAnalyzeRoundTrip:
    """Tests combining ingest and analyze_actions."""

    def test_ingest_then_analyze(self) -> None:
        """Ingesting a doc and then analyzing should return consistent stats."""
        search = AgentSearch()
        doc = _make_doc()
        search.ingest(doc)

        # analyze from index (no doc arg)
        result = search.analyze_actions()
        assert result["action_count"] == 3

        # analyze from doc directly
        result_direct = search.analyze_actions(doc)
        assert result_direct["action_count"] == 3

    def test_multiple_docs_aggregate(self) -> None:
        """Actions from multiple ingested docs should aggregate."""
        search = AgentSearch()
        doc1 = _make_doc(
            doc_id="doc_001",
            source_url="https://example.com/page1",
            actions=[
                Action(id="a1", type=ActionType.NAVIGATE, label="Nav 1",
                       selector="a.nav1", role="nav", confidence=0.9, priority=0.5),
            ],
        )
        doc2 = _make_doc(
            doc_id="doc_002",
            source_url="https://example.com/page2",
            actions=[
                Action(id="a2", type=ActionType.SUBMIT, label="Submit form",
                       selector="button.go", role="submit", confidence=0.9, priority=0.8),
            ],
        )
        search.ingest(doc1)
        search.ingest(doc2)

        result = search.analyze_actions()
        assert result["action_count"] == 2
        assert "navigate" in result["action_types"]
        assert "submit" in result["action_types"]
