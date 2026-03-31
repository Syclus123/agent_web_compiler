"""Tests for Retriever — search pipeline, reranking, result packaging."""

from __future__ import annotations

import pytest

from agent_web_compiler.index import IndexEngine
from agent_web_compiler.index.schema import ActionRecord, BlockRecord, DocumentRecord
from agent_web_compiler.search.retriever import Retriever, SearchResponse


def _build_test_engine() -> IndexEngine:
    """Build a small IndexEngine with representative test data."""
    engine = IndexEngine()

    # Manually populate records (bypassing AgentDocument ingest)
    doc1 = DocumentRecord(
        doc_id="doc_1",
        title="Refund Policy",
        url="https://example.com/refund",
        site_id="example.com",
        source_type="html",
        summary="Full refund policy for all products.",
        block_count=3,
        action_count=1,
    )
    doc2 = DocumentRecord(
        doc_id="doc_2",
        title="API Documentation",
        url="https://example.com/api",
        site_id="example.com",
        source_type="html",
        summary="REST API reference documentation.",
        block_count=2,
        action_count=1,
    )
    engine._documents["doc_1"] = doc1
    engine._documents["doc_2"] = doc2

    blocks = [
        BlockRecord(
            block_id="b_001",
            doc_id="doc_1",
            block_type="paragraph",
            text="Full refunds are available within 30 days of purchase. Contact support for details.",
            section_path=["Products", "Refund Policy"],
            importance=0.9,
            evidence_score=0.8,
        ),
        BlockRecord(
            block_id="b_002",
            doc_id="doc_1",
            block_type="paragraph",
            text="Contact support@example.com for refund requests and order issues.",
            section_path=["Support", "Contact"],
            importance=0.6,
            evidence_score=0.7,
        ),
        BlockRecord(
            block_id="b_003",
            doc_id="doc_1",
            block_type="table",
            text="Product | Price | Refund Period\nBasic | $10 | 30 days\nPro | $50 | 60 days",
            section_path=["Products", "Pricing"],
            importance=0.8,
            evidence_score=0.6,
        ),
        BlockRecord(
            block_id="b_004",
            doc_id="doc_2",
            block_type="code",
            text="GET /api/v1/users - Returns a list of users. Authorization: Bearer token required.",
            section_path=["API", "Endpoints"],
            importance=0.9,
            evidence_score=0.5,
        ),
        BlockRecord(
            block_id="b_005",
            doc_id="doc_2",
            block_type="paragraph",
            text="The API uses REST conventions with JSON request and response bodies.",
            section_path=["API", "Overview"],
            importance=0.7,
            evidence_score=0.4,
        ),
    ]

    for b in blocks:
        engine._blocks[b.block_id] = b
        engine._index_block_bm25(b)

    actions = [
        ActionRecord(
            action_id="a_001",
            doc_id="doc_1",
            action_type="navigate",
            label="Contact Support",
            role="navigate_support",
            selector="a.support-link",
            confidence=0.9,
        ),
        ActionRecord(
            action_id="a_002",
            doc_id="doc_2",
            action_type="submit",
            label="Try API endpoint",
            role="submit_api_test",
            selector="button.try-api",
            confidence=0.8,
        ),
    ]

    for a in actions:
        engine._actions[a.action_id] = a
        engine._index_action_bm25(a)

    return engine


@pytest.fixture
def engine() -> IndexEngine:
    return _build_test_engine()


@pytest.fixture
def retriever(engine: IndexEngine) -> Retriever:
    return Retriever(engine)


# --- Basic search ---


class TestSearch:
    """Test the full search pipeline."""

    def test_search_returns_response(self, retriever: Retriever) -> None:
        resp = retriever.search("refund policy")
        assert isinstance(resp, SearchResponse)
        assert resp.query == "refund policy"
        assert resp.intent == "fact"

    def test_search_finds_relevant_blocks(self, retriever: Retriever) -> None:
        resp = retriever.search("refund policy")
        assert len(resp.results) > 0
        # Top result should be about refunds
        top = resp.results[0]
        assert "refund" in top.text.lower()

    def test_search_with_top_k(self, retriever: Retriever) -> None:
        resp = retriever.search("refund", top_k=2)
        assert len(resp.results) <= 2

    def test_search_has_timing(self, retriever: Retriever) -> None:
        resp = retriever.search("api endpoint")
        assert resp.retrieval_time_ms >= 0

    def test_search_has_plan(self, retriever: Retriever) -> None:
        resp = retriever.search("refund policy")
        assert resp.plan is not None

    def test_search_total_candidates(self, retriever: Retriever) -> None:
        resp = retriever.search("refund")
        assert resp.total_candidates > 0

    def test_empty_query_returns_empty(self, retriever: Retriever) -> None:
        resp = retriever.search("")
        assert len(resp.results) == 0


# --- Block search ---


class TestSearchBlocks:
    """Test block-specific search."""

    def test_search_blocks_returns_results(self, retriever: Retriever) -> None:
        results = retriever.search_blocks("refund policy")
        assert len(results) > 0
        assert all(r.kind == "block" for r in results)

    def test_search_blocks_has_provenance(self, retriever: Retriever) -> None:
        results = retriever.search_blocks("refund policy")
        for r in results:
            assert r.provenance is not None
            assert "doc_id" in r.provenance

    def test_search_blocks_has_section_path(self, retriever: Retriever) -> None:
        results = retriever.search_blocks("refund policy")
        top = results[0]
        assert len(top.section_path) > 0

    def test_search_blocks_with_filters(self, retriever: Retriever) -> None:
        results = retriever.search_blocks(
            "refund", filters={"doc_id": "doc_1"}
        )
        assert all(r.doc_id == "doc_1" for r in results)


# --- Action search ---


class TestSearchActions:
    """Test action-specific search."""

    def test_search_actions_returns_results(self, retriever: Retriever) -> None:
        results = retriever.search_actions("support")
        assert len(results) > 0
        assert all(r.kind == "action" for r in results)

    def test_search_actions_has_metadata(self, retriever: Retriever) -> None:
        results = retriever.search_actions("support")
        top = results[0]
        assert "action_type" in top.metadata
        assert top.action_id is not None


# --- Re-ranking ---


class TestReranking:
    """Test that re-ranking adjusts scores appropriately."""

    def test_data_query_boosts_tables(self, retriever: Retriever) -> None:
        """Tables should be boosted for data/price queries."""
        resp = retriever.search("price comparison table data")
        block_types = [r.metadata.get("block_type") for r in resp.results if r.kind == "block"]
        # The table block should appear in results
        assert "table" in block_types

    def test_code_query_boosts_code(self, retriever: Retriever) -> None:
        """Code blocks should be boosted for API/code queries."""
        resp = retriever.search("api endpoint code")
        top_block = next((r for r in resp.results if r.kind == "block"), None)
        assert top_block is not None
        assert top_block.metadata.get("block_type") == "code"

    def test_high_importance_boosted(self, retriever: Retriever) -> None:
        """High-importance blocks should score higher than low-importance ones."""
        resp = retriever.search("refund")
        block_results = [r for r in resp.results if r.kind == "block"]
        if len(block_results) >= 2:
            # Top result should have high importance
            assert block_results[0].metadata.get("importance", 0) >= 0.6


# --- SearchResult data ---


class TestSearchResult:
    """Test SearchResult fields."""

    def test_block_result_fields(self, retriever: Retriever) -> None:
        results = retriever.search_blocks("refund")
        r = results[0]
        assert r.kind == "block"
        assert r.score > 0
        assert r.doc_id
        assert r.block_id
        assert r.text

    def test_action_result_fields(self, retriever: Retriever) -> None:
        results = retriever.search_actions("support")
        r = results[0]
        assert r.kind == "action"
        assert r.score > 0
        assert r.doc_id
        assert r.action_id
        assert r.text


# --- Deduplication ---


class TestDeduplication:
    """Test that duplicate results are removed."""

    def test_no_duplicate_block_ids(self, retriever: Retriever) -> None:
        resp = retriever.search("refund policy contact support")
        block_ids = [r.block_id for r in resp.results if r.block_id]
        assert len(block_ids) == len(set(block_ids))
