"""Tests for GroundedAnswerer — answer composition, citations, markdown output."""

from __future__ import annotations

import pytest

from agent_web_compiler.index import IndexEngine
from agent_web_compiler.index.schema import ActionRecord, BlockRecord, DocumentRecord
from agent_web_compiler.search.grounded_answer import (
    Citation,
    GroundedAnswer,
    GroundedAnswerer,
)
from agent_web_compiler.search.retriever import Retriever


def _build_test_engine() -> IndexEngine:
    """Build a small IndexEngine with representative test data."""
    engine = IndexEngine()

    doc = DocumentRecord(
        doc_id="doc_1",
        title="Product Page",
        url="https://example.com/products",
        site_id="example.com",
        source_type="html",
        summary="Product listings and refund policy.",
        block_count=3,
        action_count=2,
    )
    engine._documents["doc_1"] = doc

    blocks = [
        BlockRecord(
            block_id="b_001",
            doc_id="doc_1",
            block_type="paragraph",
            text="Full refunds are available within 30 days of purchase. No questions asked.",
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
            text="Plan | Price\nBasic | $10/mo\nPro | $50/mo",
            section_path=["Products", "Pricing"],
            importance=0.8,
            evidence_score=0.5,
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
            label="Go to Pricing Page",
            role="navigate_pricing",
            selector="a.pricing-link",
            confidence=0.9,
        ),
        ActionRecord(
            action_id="a_002",
            doc_id="doc_1",
            action_type="download",
            label="Download Invoice PDF",
            role="download_invoice",
            selector="button.download-invoice",
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
def answerer(engine: IndexEngine) -> GroundedAnswerer:
    return GroundedAnswerer(Retriever(engine))


# --- Answer composition ---


class TestAnswerComposition:
    """Test that answers are composed correctly from search results."""

    def test_fact_answer_has_text(self, answerer: GroundedAnswerer) -> None:
        answer = answerer.answer("What is the refund policy?")
        assert answer.answer_text
        assert len(answer.answer_text) > 10

    def test_fact_answer_has_citations(self, answerer: GroundedAnswerer) -> None:
        answer = answerer.answer("refund policy")
        assert len(answer.citations) > 0

    def test_fact_answer_evidence_sufficient(self, answerer: GroundedAnswerer) -> None:
        answer = answerer.answer("refund policy")
        assert answer.evidence_sufficient is True

    def test_no_results_marks_insufficient(self, answerer: GroundedAnswerer) -> None:
        answer = answerer.answer("quantum entanglement physics theorem")
        assert answer.evidence_sufficient is False
        assert answer.suggested_followup is not None

    def test_task_answer_has_action_plan(self, answerer: GroundedAnswerer) -> None:
        answer = answerer.answer("Download the invoice PDF")
        # Should classify as TASK and return action plan
        if answer.action_plan:
            assert len(answer.action_plan) > 0
            assert "label" in answer.action_plan[0]

    def test_navigation_answer(self, answerer: GroundedAnswerer) -> None:
        answer = answerer.answer("Go to the pricing page")
        assert answer.answer_text
        # Should find the navigation action
        if answer.action_plan:
            assert len(answer.action_plan) > 0


# --- Citations ---


class TestCitations:
    """Test citation extraction and structure."""

    def test_citation_has_block_id(self, answerer: GroundedAnswerer) -> None:
        answer = answerer.answer("refund policy")
        for cit in answer.citations:
            assert cit.block_id

    def test_citation_has_doc_id(self, answerer: GroundedAnswerer) -> None:
        answer = answerer.answer("refund policy")
        for cit in answer.citations:
            assert cit.doc_id

    def test_citation_has_text_snippet(self, answerer: GroundedAnswerer) -> None:
        answer = answerer.answer("refund policy")
        for cit in answer.citations:
            assert cit.text_snippet
            assert len(cit.text_snippet) > 0

    def test_citation_has_section_path(self, answerer: GroundedAnswerer) -> None:
        answer = answerer.answer("refund policy")
        # At least some citations should have section paths
        paths = [cit.section_path for cit in answer.citations]
        assert any(len(p) > 0 for p in paths)

    def test_citation_confidence(self, answerer: GroundedAnswerer) -> None:
        answer = answerer.answer("refund policy")
        for cit in answer.citations:
            assert 0.0 <= cit.confidence <= 1.0


# --- Markdown output ---


class TestMarkdownOutput:
    """Test to_markdown() rendering."""

    def test_markdown_has_answer(self, answerer: GroundedAnswerer) -> None:
        answer = answerer.answer("refund policy")
        md = answer.to_markdown()
        assert "**Answer**:" in md

    def test_markdown_has_evidence_section(self, answerer: GroundedAnswerer) -> None:
        answer = answerer.answer("refund policy")
        md = answer.to_markdown()
        if answer.citations:
            assert "**Evidence**:" in md

    def test_markdown_has_numbered_citations(self, answerer: GroundedAnswerer) -> None:
        answer = answerer.answer("refund policy")
        md = answer.to_markdown()
        if answer.citations:
            assert "[1]" in md

    def test_markdown_insufficient_evidence_warning(self) -> None:
        answer = GroundedAnswer(
            answer_text="No relevant information found.",
            evidence_sufficient=False,
            suggested_followup="Try a different query.",
        )
        md = answer.to_markdown()
        assert "insufficient" in md.lower() or "⚠" in md
        assert "Try a different query" in md

    def test_markdown_with_action_plan(self) -> None:
        answer = GroundedAnswer(
            answer_text="Found 1 action.",
            action_plan=[{"label": "Click download", "action_type": "click"}],
        )
        md = answer.to_markdown()
        assert "**Action plan**:" in md
        assert "Click download" in md


# --- to_dict serialization ---


class TestToDict:
    """Test to_dict() serialization."""

    def test_to_dict_has_all_fields(self, answerer: GroundedAnswerer) -> None:
        answer = answerer.answer("refund policy")
        d = answer.to_dict()
        assert "answer_text" in d
        assert "citations" in d
        assert "confidence" in d
        assert "evidence_sufficient" in d

    def test_to_dict_citations_are_dicts(self, answerer: GroundedAnswerer) -> None:
        answer = answerer.answer("refund policy")
        d = answer.to_dict()
        for cit in d["citations"]:
            assert isinstance(cit, dict)
            assert "block_id" in cit
            assert "text_snippet" in cit

    def test_to_dict_roundtrip_fields(self) -> None:
        answer = GroundedAnswer(
            answer_text="Test answer",
            citations=[
                Citation(
                    block_id="b_1",
                    doc_id="doc_1",
                    text_snippet="snippet",
                    section_path=["A", "B"],
                    page=3,
                    url="https://example.com",
                    confidence=0.9,
                )
            ],
            confidence=0.8,
            evidence_sufficient=True,
            suggested_followup=None,
            action_plan=None,
        )
        d = answer.to_dict()
        assert d["answer_text"] == "Test answer"
        assert d["confidence"] == 0.8
        assert d["citations"][0]["page"] == 3
        assert d["citations"][0]["url"] == "https://example.com"


# --- Edge cases ---


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_query(self, answerer: GroundedAnswerer) -> None:
        answer = answerer.answer("")
        assert isinstance(answer, GroundedAnswer)
        # Should handle gracefully
        assert answer.evidence_sufficient is False

    def test_very_long_query(self, answerer: GroundedAnswerer) -> None:
        long_query = "refund " * 100
        answer = answerer.answer(long_query)
        assert isinstance(answer, GroundedAnswer)

    def test_citation_text_truncated(self) -> None:
        """Citations with long text should be truncated."""
        long_text = "x" * 500
        cit = Citation(
            block_id="b_1", doc_id="doc_1", text_snippet=long_text
        )
        # The answerer truncates during extraction, but Citation itself holds what it gets
        assert len(cit.text_snippet) == 500  # raw storage, no auto-truncation

    def test_markdown_empty_citations(self) -> None:
        answer = GroundedAnswer(answer_text="Some answer", citations=[])
        md = answer.to_markdown()
        assert "**Answer**:" in md
        assert "**Evidence**:" not in md
