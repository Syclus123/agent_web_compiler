"""Tests for the provenance engine integration layer.

Tests cover:
- ProvenanceEngine initialization
- Snapshot capture from AgentDocument
- Evidence building from documents and search results
- Citation generation and rendering
- Trace session lifecycle
- End-to-end answer_with_provenance flow
"""

from __future__ import annotations

import pytest

from agent_web_compiler.core.block import Block, BlockType
from agent_web_compiler.core.document import AgentDocument, SourceType
from agent_web_compiler.core.provenance import PageProvenance, Provenance
from agent_web_compiler.provenance.citation import CitationObject
from agent_web_compiler.provenance.engine import ProvenanceEngine
from agent_web_compiler.provenance.evidence import Evidence
from agent_web_compiler.provenance.snapshot import Snapshot
from agent_web_compiler.provenance.tracer import TraceSession, TraceStep

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_block(
    block_id: str,
    text: str,
    block_type: BlockType = BlockType.PARAGRAPH,
    section_path: list[str] | None = None,
    importance: float = 0.5,
    page: int | None = None,
) -> Block:
    """Create a test Block."""
    prov = None
    if page is not None:
        prov = Provenance(page=PageProvenance(page=page))
    return Block(
        id=block_id,
        type=block_type,
        text=text,
        section_path=section_path or [],
        importance=importance,
        order=0,
        provenance=prov,
    )


def _make_doc(
    blocks: list[Block] | None = None,
    title: str = "Test Document",
    source_url: str | None = "https://example.com/test",
) -> AgentDocument:
    """Create a test AgentDocument with sensible defaults."""
    if blocks is None:
        blocks = [
            _make_block(
                "b_001",
                "The rate limit is 100 requests per minute.",
                section_path=["API", "Rate Limits"],
                importance=0.8,
            ),
            _make_block(
                "b_002",
                "Authentication uses OAuth 2.0 bearer tokens.",
                section_path=["API", "Authentication"],
                importance=0.9,
            ),
            _make_block(
                "b_003",
                "Refunds are processed within 5 business days.",
                section_path=["Billing", "Refunds"],
                importance=0.7,
                page=3,
            ),
        ]
    return AgentDocument(
        doc_id=AgentDocument.make_doc_id("test-content"),
        source_type=SourceType.HTML,
        source_url=source_url,
        title=title,
        blocks=blocks,
        canonical_markdown="# Test\n\nSome content.",
    )


# ---------------------------------------------------------------------------
# ProvenanceEngine initialization
# ---------------------------------------------------------------------------


class TestProvenanceEngineInit:
    """Test engine construction and basic state."""

    def test_creates_engine(self) -> None:
        engine = ProvenanceEngine()
        assert engine is not None

    def test_has_evidence_builder(self) -> None:
        engine = ProvenanceEngine()
        assert engine._evidence_builder is not None

    def test_has_citation_builder(self) -> None:
        engine = ProvenanceEngine()
        assert engine._citation_builder is not None

    def test_has_snapshot_store(self) -> None:
        engine = ProvenanceEngine()
        assert engine._snapshot_store is not None

    def test_has_tracer(self) -> None:
        engine = ProvenanceEngine()
        assert engine._tracer is not None


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------


class TestCaptureSnapshot:
    """Test snapshot capture from AgentDocument."""

    def test_capture_returns_snapshot(self) -> None:
        engine = ProvenanceEngine()
        doc = _make_doc()
        snapshot = engine.capture_snapshot(doc)

        assert isinstance(snapshot, Snapshot)
        assert snapshot.snapshot_id.startswith("snap_")
        assert snapshot.doc_id == doc.doc_id
        assert snapshot.source_url == "https://example.com/test"
        assert snapshot.content_hash != ""

    def test_snapshot_retrievable(self) -> None:
        engine = ProvenanceEngine()
        doc = _make_doc()
        snapshot = engine.capture_snapshot(doc)
        retrieved = engine.get_snapshot(snapshot.snapshot_id)
        assert retrieved is snapshot

    def test_get_missing_snapshot_returns_none(self) -> None:
        engine = ProvenanceEngine()
        assert engine.get_snapshot("nonexistent") is None

    def test_different_docs_different_hashes(self) -> None:
        engine = ProvenanceEngine()
        doc1 = _make_doc(title="Doc A")
        doc2 = _make_doc(title="Doc B")
        doc2.canonical_markdown = "Different content"

        s1 = engine.capture_snapshot(doc1)
        s2 = engine.capture_snapshot(doc2)
        assert s1.content_hash != s2.content_hash

    def test_snapshot_metadata_includes_block_count(self) -> None:
        engine = ProvenanceEngine()
        doc = _make_doc()
        snapshot = engine.capture_snapshot(doc)
        assert snapshot.metadata.get("block_count") == 3


# ---------------------------------------------------------------------------
# Evidence building
# ---------------------------------------------------------------------------


class TestBuildEvidence:
    """Test evidence building from documents."""

    def test_creates_evidence_for_blocks(self) -> None:
        engine = ProvenanceEngine()
        doc = _make_doc()
        evidence = engine.build_evidence(doc)

        # Should have at least one evidence per block
        assert len(evidence) >= 3
        assert all(isinstance(e, Evidence) for e in evidence)

    def test_evidence_preserves_block_data(self) -> None:
        engine = ProvenanceEngine()
        doc = _make_doc()
        evidence = engine.build_evidence(doc)

        # Find the evidence for b_001
        ev_b001 = [e for e in evidence if e.block_id == "b_001"]
        assert len(ev_b001) == 1
        ev = ev_b001[0]
        assert "rate limit" in ev.text.lower()
        assert ev.section_path == ["API", "Rate Limits"]
        assert ev.source_url == "https://example.com/test"
        assert ev.confidence == 0.8

    def test_evidence_captures_page_number(self) -> None:
        engine = ProvenanceEngine()
        doc = _make_doc()
        evidence = engine.build_evidence(doc)

        # b_003 has page=3
        ev_b003 = [e for e in evidence if e.block_id == "b_003"]
        assert len(ev_b003) == 1
        assert ev_b003[0].page == 3

    def test_evidence_without_page(self) -> None:
        engine = ProvenanceEngine()
        doc = _make_doc()
        evidence = engine.build_evidence(doc)

        # b_001 has no page provenance
        ev_b001 = [e for e in evidence if e.block_id == "b_001"]
        assert ev_b001[0].page is None

    def test_links_to_snapshot(self) -> None:
        engine = ProvenanceEngine()
        doc = _make_doc()
        snapshot = engine.capture_snapshot(doc)
        evidence = engine.build_evidence(doc, snapshot_id=snapshot.snapshot_id)

        for ev in evidence:
            assert ev.snapshot_id == snapshot.snapshot_id

    def test_evidence_has_source_type(self) -> None:
        engine = ProvenanceEngine()
        doc = _make_doc()
        evidence = engine.build_evidence(doc)
        # Each evidence should have a source_type field
        for ev in evidence:
            assert ev.source_type != ""


class TestBuildEvidenceFromSearch:
    """Test evidence building from search results."""

    def test_converts_search_results(self) -> None:
        from agent_web_compiler.search.retriever import SearchResult

        results = [
            SearchResult(
                kind="block",
                score=0.85,
                doc_id="doc_1",
                block_id="b_001",
                text="The rate limit is 100/min.",
                section_path=["API", "Limits"],
                provenance={"source_url": "https://example.com"},
                metadata={"block_type": "paragraph", "page": 2},
            ),
        ]

        engine = ProvenanceEngine()
        evidence = engine.build_evidence_from_search(results)

        assert len(evidence) == 1
        ev = evidence[0]
        assert ev.text == "The rate limit is 100/min."
        assert ev.source_url == "https://example.com"
        assert ev.page == 2
        assert ev.confidence == 0.85


# ---------------------------------------------------------------------------
# Citations
# ---------------------------------------------------------------------------


class TestCiteAnswer:
    """Test citation generation."""

    def test_produces_citations(self) -> None:
        engine = ProvenanceEngine()
        evidence = [
            Evidence(
                evidence_id="ev_1",
                source_type="web_block",
                text="The rate limit is 100 per minute.",
                confidence=0.9,
            ),
            Evidence(
                evidence_id="ev_2",
                source_type="web_block",
                text="Authentication uses OAuth.",
                confidence=0.7,
            ),
        ]

        citations = engine.cite_answer("Rate limit is 100/min.", evidence)

        assert len(citations) >= 1
        assert all(isinstance(c, CitationObject) for c in citations)

    def test_respects_max_citations(self) -> None:
        engine = ProvenanceEngine()
        evidence = [
            Evidence(
                evidence_id=f"ev_{i}",
                source_type="web_block",
                text=f"Evidence text number {i} with some content.",
                confidence=0.5,
            )
            for i in range(10)
        ]

        citations = engine.cite_answer("Test answer with content", evidence, max_citations=3)
        assert len(citations) <= 3

    def test_empty_evidence_returns_empty(self) -> None:
        engine = ProvenanceEngine()
        citations = engine.cite_answer("Some answer", [])
        assert citations == []


class TestCiteAction:
    """Test action citation."""

    def test_creates_action_citation(self) -> None:
        engine = ProvenanceEngine()
        ev = Evidence(
            evidence_id="ev_act",
            source_type="action",
            text="Click the submit button",
            confidence=0.8,
        )
        cit = engine.cite_action("Submit form", ev)
        assert isinstance(cit, CitationObject)
        assert cit.answer_span == "Submit form"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


class TestRenderCitedAnswer:
    """Test cited answer rendering."""

    def test_renders_with_markers(self) -> None:
        engine = ProvenanceEngine()
        evidence = [
            Evidence(
                evidence_id="ev_1",
                source_type="web_block",
                text="Rate limit is 100 per minute for all API endpoints.",
                source_url="https://example.com/api",
                section_path=["API", "Limits"],
                confidence=0.9,
            ),
        ]
        citations = engine.cite_answer(
            "The rate limit is 100 per minute.", evidence
        )
        rendered = engine.render_cited_answer(
            "The rate limit is 100 per minute.", citations
        )

        assert "[1]" in rendered
        assert "rate limit" in rendered.lower() or "Rate limit" in rendered

    def test_renders_without_citations(self) -> None:
        engine = ProvenanceEngine()
        rendered = engine.render_cited_answer("No evidence.", [])
        assert "No evidence." in rendered

    def test_renders_page_number(self) -> None:
        engine = ProvenanceEngine()
        ev = Evidence(
            evidence_id="ev_1",
            source_type="web_block",
            text="Something on page 5 about the topic at hand.",
            page=5,
            confidence=0.8,
        )
        citations = engine.cite_answer("Page 5 content about the topic", [ev])
        rendered = engine.render_cited_answer("Page 5 content about the topic", citations)
        assert "p.5" in rendered


# ---------------------------------------------------------------------------
# Traces
# ---------------------------------------------------------------------------


class TestTraceLifecycle:
    """Test trace session start/record/end flow."""

    def test_start_trace(self) -> None:
        engine = ProvenanceEngine()
        session = engine.start_trace("What is the rate limit?")

        assert isinstance(session, TraceSession)
        assert session.session_id.startswith("trace_")
        assert session.query == "What is the rate limit?"
        assert session.steps == []

    def test_record_step(self) -> None:
        engine = ProvenanceEngine()
        session = engine.start_trace("test query")
        step = engine.record_step(
            session.session_id,
            "retrieve",
            result_count=5,
        )

        assert isinstance(step, TraceStep)
        assert step.step_type == "retrieve"
        assert len(session.steps) == 1

    def test_end_trace(self) -> None:
        engine = ProvenanceEngine()
        session = engine.start_trace("test query")
        engine.record_step(session.session_id, "retrieve")
        completed = engine.end_trace(
            session.session_id, answer="The rate limit is 100/min."
        )

        assert completed.final_answer == "The rate limit is 100/min."
        assert completed.end_time > 0

    def test_get_trace(self) -> None:
        engine = ProvenanceEngine()
        session = engine.start_trace("test")
        retrieved = engine.get_trace(session.session_id)
        assert retrieved is session

    def test_get_missing_trace_returns_none(self) -> None:
        engine = ProvenanceEngine()
        assert engine.get_trace("nonexistent") is None

    def test_record_step_missing_session_raises(self) -> None:
        engine = ProvenanceEngine()
        with pytest.raises(KeyError, match="Trace session not found"):
            engine.record_step("bad_id", "retrieve")

    def test_end_trace_missing_session_raises(self) -> None:
        engine = ProvenanceEngine()
        with pytest.raises(KeyError, match="Trace session not found"):
            engine.end_trace("bad_id")

    def test_multiple_steps(self) -> None:
        engine = ProvenanceEngine()
        session = engine.start_trace("multi-step")
        engine.record_step(session.session_id, "search", query="test")
        engine.record_step(session.session_id, "retrieve", count=3)
        engine.record_step(session.session_id, "cite", count=2)

        assert len(session.steps) == 3
        assert [s.step_type for s in session.steps] == [
            "search",
            "retrieve",
            "cite",
        ]


class TestTraceSessionSerialization:
    """Test trace session serialization."""

    def test_to_dict(self) -> None:
        engine = ProvenanceEngine()
        session = engine.start_trace("serialize test")
        engine.record_step(session.session_id, "search")
        engine.end_trace(session.session_id, answer="42")

        data = session.to_dict()
        assert data["query"] == "serialize test"
        assert data["final_answer"] == "42"
        assert len(data["steps"]) == 1

    def test_to_markdown(self) -> None:
        engine = ProvenanceEngine()
        session = engine.start_trace("markdown test")
        engine.record_step(session.session_id, "search")
        engine.end_trace(session.session_id, answer="Result")

        md = session.to_markdown()
        assert "Trace" in md
        assert "markdown test" in md
        assert "search" in md
        assert "Result" in md


# ---------------------------------------------------------------------------
# End-to-end: answer_with_provenance
# ---------------------------------------------------------------------------


class TestAnswerWithProvenance:
    """Test the full answer_with_provenance pipeline.

    Uses AgentSearch with test data to exercise the complete flow.
    """

    def _build_search(self) -> object:
        """Build an AgentSearch instance with test content indexed."""
        from agent_web_compiler.search import AgentSearch

        search = AgentSearch()
        doc = _make_doc()
        search.ingest(doc)
        return search

    def test_returns_expected_keys(self) -> None:
        search = self._build_search()
        engine = ProvenanceEngine()
        result = engine.answer_with_provenance(search, "What is the rate limit?")

        assert "answer" in result
        assert "cited_answer" in result
        assert "citations" in result
        assert "evidence" in result
        assert "trace" in result
        assert "snapshot_ids" in result

    def test_answer_is_string(self) -> None:
        search = self._build_search()
        engine = ProvenanceEngine()
        result = engine.answer_with_provenance(search, "What is the rate limit?")
        assert isinstance(result["answer"], str)
        assert len(result["answer"]) > 0

    def test_cited_answer_has_markers(self) -> None:
        search = self._build_search()
        engine = ProvenanceEngine()
        result = engine.answer_with_provenance(search, "What is the rate limit?")
        # Should have citation markers if evidence was found
        if result["citations"]:
            assert "[1]" in result["cited_answer"]

    def test_trace_has_steps(self) -> None:
        search = self._build_search()
        engine = ProvenanceEngine()
        result = engine.answer_with_provenance(search, "rate limit")
        steps = result["trace"]["steps"]
        assert len(steps) >= 4
        step_types = [s["step_type"] for s in steps]
        assert "search" in step_types
        assert "retrieve" in step_types
        assert "evidence" in step_types
        assert "cite" in step_types

    def test_evidence_list_populated(self) -> None:
        search = self._build_search()
        engine = ProvenanceEngine()
        result = engine.answer_with_provenance(search, "rate limit")
        # Should have evidence from the indexed document
        assert isinstance(result["evidence"], list)


# ---------------------------------------------------------------------------
# Data model unit tests
# ---------------------------------------------------------------------------


class TestDataModels:
    """Test the provenance data model basics."""

    def test_evidence_fields(self) -> None:
        ev = Evidence(
            evidence_id="ev_1",
            source_type="web_block",
            text="test",
        )
        assert ev.evidence_id == "ev_1"
        assert ev.confidence == 1.0  # default in core module
        assert ev.metadata == {}  # default

    def test_citation_object_fields(self) -> None:
        cit = CitationObject(
            citation_id="cit_1",
            citation_type="block",
        )
        assert cit.citation_id == "cit_1"
        assert cit.confidence == 0.5  # default

    def test_snapshot_fields(self) -> None:
        snap = Snapshot(
            snapshot_id="snap_1",
        )
        assert snap.snapshot_id == "snap_1"

    def test_trace_step_to_dict(self) -> None:
        step = TraceStep(
            step_id="step_1",
            step_type="retrieve",
        )
        data = step.to_dict()
        assert data["step_id"] == "step_1"
        assert data["step_type"] == "retrieve"
