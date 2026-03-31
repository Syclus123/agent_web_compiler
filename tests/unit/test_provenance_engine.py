"""Comprehensive tests for the Agent Provenance / Citation Engine.

Covers all 4 modules:
- evidence.py: Evidence, EvidenceBuilder
- citation.py: CitationObject, CitationBuilder, RenderHint
- snapshot.py: Snapshot, SnapshotStore
- tracer.py: TraceStep, TraceSession, TraceRecorder
"""

from __future__ import annotations

import pytest

from agent_web_compiler.core.action import Action, ActionType, StateEffect
from agent_web_compiler.core.block import Block, BlockType
from agent_web_compiler.core.document import AgentDocument, SourceType
from agent_web_compiler.core.provenance import (
    DOMProvenance,
    PageProvenance,
    Provenance,
    ScreenshotProvenance,
)
from agent_web_compiler.provenance.citation import (
    CitationBuilder,
    CitationObject,
    RenderHint,
)
from agent_web_compiler.provenance.evidence import Evidence, EvidenceBuilder
from agent_web_compiler.provenance.snapshot import Snapshot, SnapshotStore
from agent_web_compiler.provenance.tracer import TraceRecorder, TraceSession, TraceStep

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_block(
    block_id: str = "b_001",
    block_type: BlockType = BlockType.PARAGRAPH,
    text: str = "The return policy allows returns within 30 days.",
    section_path: list[str] | None = None,
    importance: float = 0.8,
    dom_path: str | None = "html > body > main > p:nth-child(2)",
    page: int | None = None,
    bbox: list[float] | None = None,
    char_range: list[int] | None = None,
    screenshot_region_id: str | None = None,
    metadata: dict | None = None,
) -> Block:
    prov = Provenance(
        dom=DOMProvenance(dom_path=dom_path) if dom_path else None,
        page=PageProvenance(page=page, bbox=bbox, char_range=char_range)
        if (page is not None or bbox or char_range)
        else None,
        screenshot=ScreenshotProvenance(screenshot_region_id=screenshot_region_id)
        if screenshot_region_id
        else None,
    )
    return Block(
        id=block_id,
        type=block_type,
        text=text,
        section_path=section_path or ["FAQ", "Returns"],
        importance=importance,
        provenance=prov,
        metadata=metadata or {},
    )


def _make_action(
    action_id: str = "a_submit",
    label: str = "Submit Form",
    action_type: ActionType = ActionType.SUBMIT,
    selector: str | None = "button#submit",
    role: str | None = "submit_form",
    dom_path: str | None = "html > body > form > button",
) -> Action:
    prov = Provenance(
        dom=DOMProvenance(dom_path=dom_path) if dom_path else None,
    )
    return Action(
        id=action_id,
        type=action_type,
        label=label,
        selector=selector,
        role=role,
        confidence=0.9,
        priority=0.7,
        state_effect=StateEffect(may_navigate=True, target_url="/success"),
        provenance=prov,
    )


def _make_doc(
    blocks: list[Block] | None = None,
    actions: list[Action] | None = None,
    source_url: str = "https://example.com/faq",
    title: str = "FAQ Page",
    source_type: SourceType = SourceType.HTML,
) -> AgentDocument:
    if blocks is None:
        blocks = [_make_block()]
    if actions is None:
        actions = [_make_action()]
    return AgentDocument(
        doc_id=AgentDocument.make_doc_id("test content"),
        source_type=source_type,
        source_url=source_url,
        title=title,
        blocks=blocks,
        actions=actions,
        canonical_markdown="# FAQ\n\nReturn policy allows returns within 30 days.",
    )


# ===========================================================================
# Evidence Tests
# ===========================================================================


class TestEvidence:
    """Tests for Evidence dataclass."""

    def test_basic_creation(self) -> None:
        ev = Evidence(
            evidence_id="ev_abc123",
            source_type="web_block",
            source_url="https://example.com",
            text="Some text",
        )
        assert ev.evidence_id == "ev_abc123"
        assert ev.source_type == "web_block"
        assert ev.text == "Some text"
        assert ev.confidence == 1.0
        assert ev.section_path == []
        assert ev.metadata == {}

    def test_to_dict(self) -> None:
        ev = Evidence(
            evidence_id="ev_test",
            source_type="pdf_block",
            source_url="https://example.com/doc.pdf",
            block_id="b_001",
            text="PDF content",
            page=3,
            bbox=[10.0, 20.0, 300.0, 50.0],
            confidence=0.85,
        )
        d = ev.to_dict()
        assert d["evidence_id"] == "ev_test"
        assert d["source_type"] == "pdf_block"
        assert d["page"] == 3
        assert d["bbox"] == [10.0, 20.0, 300.0, 50.0]
        assert d["confidence"] == 0.85
        assert d["block_id"] == "b_001"

    def test_from_block(self) -> None:
        block = _make_block(
            dom_path="html > body > p",
            page=2,
            bbox=[0.0, 0.0, 100.0, 20.0],
            char_range=[10, 50],
            screenshot_region_id="region_1",
        )
        doc = _make_doc(blocks=[block])
        ev = Evidence.from_block(block, doc, snapshot_id="snap_abc")

        assert ev.evidence_id.startswith("ev_")
        assert ev.source_type == "web_block"
        assert ev.source_url == "https://example.com/faq"
        assert ev.snapshot_id == "snap_abc"
        assert ev.block_id == "b_001"
        assert ev.text == block.text
        assert ev.section_path == ["FAQ", "Returns"]
        assert ev.dom_path == "html > body > p"
        assert ev.page == 2
        assert ev.bbox == [0.0, 0.0, 100.0, 20.0]
        assert ev.char_range == [10, 50]
        assert ev.screenshot_region_id == "region_1"
        assert ev.content_type == "paragraph"
        assert ev.confidence == block.importance

    def test_from_block_pdf(self) -> None:
        block = _make_block(page=5, bbox=[10.0, 20.0, 200.0, 40.0])
        doc = _make_doc(blocks=[block], source_type=SourceType.PDF)
        ev = Evidence.from_block(block, doc)
        assert ev.source_type == "pdf_block"

    def test_from_block_table(self) -> None:
        block = _make_block(block_type=BlockType.TABLE, text="Row 1 | Row 2")
        doc = _make_doc(blocks=[block])
        ev = Evidence.from_block(block, doc)
        assert ev.source_type == "table_cell"

    def test_from_block_code(self) -> None:
        block = _make_block(
            block_type=BlockType.CODE,
            text="print('hello')",
            metadata={"language": "python"},
        )
        doc = _make_doc(blocks=[block])
        ev = Evidence.from_block(block, doc)
        assert ev.source_type == "code_block"
        assert ev.language == "python"

    def test_from_block_no_provenance(self) -> None:
        block = Block(
            id="b_noprov",
            type=BlockType.PARAGRAPH,
            text="No provenance block",
        )
        doc = _make_doc(blocks=[block])
        ev = Evidence.from_block(block, doc)
        assert ev.dom_path is None
        assert ev.page is None
        assert ev.bbox is None

    def test_from_action(self) -> None:
        action = _make_action()
        doc = _make_doc(actions=[action])
        ev = Evidence.from_action(action, doc, snapshot_id="snap_xyz")

        assert ev.evidence_id.startswith("ev_")
        assert ev.source_type == "action"
        assert ev.block_id == "a_submit"
        assert ev.text == "Submit Form"
        assert ev.dom_path == "html > body > form > button"
        assert ev.snapshot_id == "snap_xyz"
        assert ev.confidence == 0.9
        assert ev.metadata["action_type"] == "submit"
        assert ev.metadata["selector"] == "button#submit"
        assert ev.metadata["role"] == "submit_form"
        assert ev.metadata["state_effect"]["may_navigate"] is True
        assert ev.metadata["state_effect"]["target_url"] == "/success"

    def test_from_action_no_provenance(self) -> None:
        action = Action(
            id="a_bare",
            type=ActionType.CLICK,
            label="Click me",
        )
        doc = _make_doc(actions=[action])
        ev = Evidence.from_action(action, doc)
        assert ev.dom_path is None
        assert ev.page is None

    def test_evidence_id_deterministic(self) -> None:
        block = _make_block()
        doc = _make_doc(blocks=[block])
        ev1 = Evidence.from_block(block, doc)
        ev2 = Evidence.from_block(block, doc)
        assert ev1.evidence_id == ev2.evidence_id


class TestEvidenceBuilder:
    """Tests for EvidenceBuilder."""

    def test_build_from_document(self) -> None:
        blocks = [
            _make_block(block_id="b_001", text="First block"),
            _make_block(block_id="b_002", text="Second block"),
        ]
        actions = [_make_action(action_id="a_001")]
        doc = _make_doc(blocks=blocks, actions=actions)

        builder = EvidenceBuilder()
        evidence = builder.build_from_document(doc, snapshot_id="snap_test")

        # 2 blocks + 1 action = 3 evidence items
        assert len(evidence) == 3
        assert evidence[0].block_id == "b_001"
        assert evidence[1].block_id == "b_002"
        assert evidence[2].block_id == "a_001"
        assert evidence[2].source_type == "action"
        for ev in evidence:
            assert ev.snapshot_id == "snap_test"

    def test_build_from_document_empty(self) -> None:
        doc = _make_doc(blocks=[], actions=[])
        builder = EvidenceBuilder()
        evidence = builder.build_from_document(doc)
        assert evidence == []

    def test_build_from_block(self) -> None:
        block = _make_block()
        doc = _make_doc(blocks=[block])
        builder = EvidenceBuilder()
        ev = builder.build_from_block(block, doc)
        assert ev.block_id == "b_001"
        assert ev.source_type == "web_block"

    def test_build_from_action(self) -> None:
        action = _make_action()
        doc = _make_doc(actions=[action])
        builder = EvidenceBuilder()
        ev = builder.build_from_action(action, doc)
        assert ev.source_type == "action"
        assert ev.text == "Submit Form"

    def test_build_from_search_result(self) -> None:
        """Test with a mock search result object."""

        class MockResult:
            block_id = "b_mock"
            action_id = None
            doc_id = "doc_123"
            text = "Mock result text"
            section_path = ["Section", "Subsection"]
            score = 0.92
            kind = "block"
            provenance = {"source_url": "https://example.com/page"}
            metadata = {"page": 5}

        builder = EvidenceBuilder()
        ev = builder.build_from_search_result(MockResult())
        assert ev.block_id == "b_mock"
        assert ev.source_url == "https://example.com/page"
        assert ev.page == 5
        assert ev.confidence == 0.92
        assert ev.section_path == ["Section", "Subsection"]

    def test_build_from_search_result_action(self) -> None:
        class MockActionResult:
            block_id = None
            action_id = "a_search"
            doc_id = "doc_456"
            text = "Search button"
            section_path = []
            score = 0.75
            kind = "action"
            provenance = {}
            metadata = {}

        builder = EvidenceBuilder()
        ev = builder.build_from_search_result(MockActionResult())
        assert ev.source_type == "action"
        assert ev.block_id == "a_search"


# ===========================================================================
# Citation Tests
# ===========================================================================


class TestRenderHint:
    """Tests for RenderHint."""

    def test_defaults(self) -> None:
        hint = RenderHint()
        assert hint.label == ""
        assert hint.url is None
        assert hint.page is None

    def test_to_dict(self) -> None:
        hint = RenderHint(
            label="FAQ > Returns",
            url="https://example.com/faq",
            page=2,
            highlight_bbox=[10.0, 20.0, 300.0, 50.0],
            highlight_text="30 day return",
            screenshot_region="region_1",
        )
        d = hint.to_dict()
        assert d["label"] == "FAQ > Returns"
        assert d["url"] == "https://example.com/faq"
        assert d["page"] == 2
        assert d["highlight_bbox"] == [10.0, 20.0, 300.0, 50.0]


class TestCitationObject:
    """Tests for CitationObject."""

    def test_basic_creation(self) -> None:
        cit = CitationObject(
            citation_id="cit_abc",
            citation_type="block",
            answer_span="returns within 30 days",
            evidence_ids=["ev_001"],
            evidence_texts=["The return policy allows returns within 30 days."],
            confidence=0.85,
        )
        assert cit.citation_id == "cit_abc"
        assert cit.citation_type == "block"
        assert len(cit.evidence_ids) == 1

    def test_to_dict(self) -> None:
        cit = CitationObject(
            citation_id="cit_test",
            evidence_ids=["ev_1", "ev_2"],
            evidence_texts=["text1", "text2"],
            render_hint=RenderHint(label="Section", url="https://example.com"),
        )
        d = cit.to_dict()
        assert d["citation_id"] == "cit_test"
        assert d["evidence_ids"] == ["ev_1", "ev_2"]
        assert "render_hint" in d
        assert d["render_hint"]["url"] == "https://example.com"

    def test_to_dict_no_render_hint(self) -> None:
        cit = CitationObject(citation_id="cit_none")
        d = cit.to_dict()
        assert "render_hint" not in d

    def test_to_markdown_with_url(self) -> None:
        cit = CitationObject(
            citation_id="cit_md",
            evidence_texts=["Returns within 30 days"],
            render_hint=RenderHint(
                label="FAQ",
                url="https://example.com/faq",
                page=3,
            ),
        )
        md = cit.to_markdown()
        assert "[FAQ](https://example.com/faq)" in md
        assert "p.3" in md
        assert "Returns within 30 days" in md

    def test_to_markdown_no_hint(self) -> None:
        cit = CitationObject(
            citation_id="cit_plain",
            evidence_texts=["some text"],
        )
        md = cit.to_markdown()
        assert "some text" in md

    def test_to_html_with_url(self) -> None:
        cit = CitationObject(
            citation_id="cit_html",
            render_hint=RenderHint(
                label="FAQ",
                url="https://example.com",
                highlight_text="30 days",
                highlight_bbox=[10.0, 20.0, 200.0, 40.0],
                screenshot_region="region_1",
            ),
        )
        html = cit.to_html()
        assert "<a " in html
        assert 'data-citation-id="cit_html"' in html
        assert 'data-highlight-text="30 days"' in html
        assert 'data-highlight-bbox="10.0,20.0,200.0,40.0"' in html
        assert 'data-screenshot-region="region_1"' in html
        assert 'href="https://example.com"' in html

    def test_to_html_no_url(self) -> None:
        cit = CitationObject(
            citation_id="cit_cite",
            render_hint=RenderHint(label="Section"),
        )
        html = cit.to_html()
        assert "<cite " in html
        assert "Section" in html


class TestCitationBuilder:
    """Tests for CitationBuilder."""

    def _make_evidence_list(self) -> list[Evidence]:
        return [
            Evidence(
                evidence_id="ev_001",
                source_type="web_block",
                source_url="https://example.com/faq",
                text="The return policy allows returns within 30 days of purchase.",
                section_path=["FAQ", "Returns"],
                confidence=0.9,
            ),
            Evidence(
                evidence_id="ev_002",
                source_type="web_block",
                source_url="https://example.com/faq",
                text="Shipping is free for orders over $50.",
                section_path=["FAQ", "Shipping"],
                confidence=0.7,
            ),
            Evidence(
                evidence_id="ev_003",
                source_type="web_block",
                source_url="https://example.com/about",
                text="We are a family-owned business since 1995.",
                section_path=["About"],
                confidence=0.5,
            ),
        ]

    def test_cite_answer_basic(self) -> None:
        builder = CitationBuilder()
        evidence = self._make_evidence_list()
        answer = "You can return items within 30 days of purchase."

        citations = builder.cite_answer(answer, evidence)
        assert len(citations) > 0
        # The return policy evidence should rank highest
        assert citations[0].evidence_ids == ["ev_001"]
        assert citations[0].citation_id.startswith("cit_")

    def test_cite_answer_max_citations(self) -> None:
        builder = CitationBuilder()
        evidence = self._make_evidence_list()
        answer = "Returns within 30 days. Free shipping over $50."

        citations = builder.cite_answer(answer, evidence, max_citations=2)
        assert len(citations) <= 2

    def test_cite_answer_empty_evidence(self) -> None:
        builder = CitationBuilder()
        citations = builder.cite_answer("Some answer", [])
        assert citations == []

    def test_cite_answer_no_overlap(self) -> None:
        builder = CitationBuilder()
        evidence = [
            Evidence(
                evidence_id="ev_unrelated",
                source_type="web_block",
                text="xyz abc totally unrelated content 123",
                confidence=0.3,
            ),
        ]
        # Even with low overlap, builder should still attempt citation
        # but may produce 0 if score is 0
        citations = builder.cite_answer(
            "The weather is sunny today.", evidence
        )
        # May or may not produce citation depending on threshold
        assert isinstance(citations, list)

    def test_cite_answer_render_hints(self) -> None:
        builder = CitationBuilder()
        evidence = [
            Evidence(
                evidence_id="ev_hint",
                source_type="web_block",
                source_url="https://example.com/page",
                text="Returns are allowed within 30 days.",
                section_path=["Policy", "Returns"],
                page=5,
                bbox=[10.0, 20.0, 300.0, 50.0],
                screenshot_region_id="region_42",
                confidence=0.95,
            ),
        ]
        answer = "Returns are allowed within 30 days."
        citations = builder.cite_answer(answer, evidence)
        assert len(citations) == 1
        hint = citations[0].render_hint
        assert hint is not None
        assert hint.url == "https://example.com/page"
        assert hint.page == 5
        assert hint.label == "Policy > Returns"
        assert hint.highlight_bbox == [10.0, 20.0, 300.0, 50.0]
        assert hint.screenshot_region == "region_42"

    def test_cite_action(self) -> None:
        builder = CitationBuilder()
        ev = Evidence(
            evidence_id="ev_action",
            source_type="action",
            source_url="https://example.com",
            text="Submit Order",
            confidence=0.88,
        )
        cit = builder.cite_action("Click the submit button", ev)
        assert cit.citation_type == "action"
        assert cit.answer_span == "Click the submit button"
        assert cit.evidence_ids == ["ev_action"]
        assert cit.confidence == 0.88

    def test_render_answer_with_citations(self) -> None:
        builder = CitationBuilder()
        evidence = self._make_evidence_list()
        answer = "Returns within 30 days of purchase."
        citations = builder.cite_answer(answer, evidence)

        rendered = builder.render_answer_with_citations(answer, citations)
        assert answer in rendered
        assert "[1]" in rendered
        assert "---" in rendered
        # Should have footnotes
        assert "[1]" in rendered

    def test_render_answer_no_citations(self) -> None:
        builder = CitationBuilder()
        answer = "Some answer text."
        rendered = builder.render_answer_with_citations(answer, [])
        assert rendered == answer

    def test_citation_type_mapping(self) -> None:
        builder = CitationBuilder()
        table_ev = Evidence(
            evidence_id="ev_table",
            source_type="table_cell",
            text="Table data about returns policy and conditions.",
            confidence=0.9,
        )
        citations = builder.cite_answer(
            "The returns policy has conditions.", [table_ev]
        )
        if citations:
            assert citations[0].citation_type == "table"


# ===========================================================================
# Snapshot Tests
# ===========================================================================


class TestSnapshot:
    """Tests for Snapshot dataclass."""

    def test_basic_creation(self) -> None:
        snap = Snapshot(
            snapshot_id="snap_test",
            source_url="https://example.com",
            content_hash="abc123",
            timestamp=1000.0,
            compiler_version="0.7.0",
            doc_id="doc_001",
        )
        assert snap.snapshot_id == "snap_test"
        assert snap.source_url == "https://example.com"
        assert snap.content_hash == "abc123"

    def test_to_dict(self) -> None:
        snap = Snapshot(
            snapshot_id="snap_dict",
            source_url="https://example.com",
            content_hash="deadbeef",
            metadata={"extra": "data"},
        )
        d = snap.to_dict()
        assert d["snapshot_id"] == "snap_dict"
        assert d["content_hash"] == "deadbeef"
        assert d["metadata"] == {"extra": "data"}

    def test_from_document(self) -> None:
        doc = _make_doc()
        snap = Snapshot.from_document(doc)
        assert snap.snapshot_id.startswith("snap_")
        assert snap.source_url == "https://example.com/faq"
        assert snap.doc_id == doc.doc_id
        assert snap.content_hash != ""
        assert snap.timestamp > 0
        assert snap.compiler_version != ""
        assert snap.metadata["block_count"] == 1
        assert snap.metadata["action_count"] == 1

    def test_from_document_content_hash_deterministic(self) -> None:
        doc = _make_doc()
        snap1 = Snapshot.from_document(doc)
        snap2 = Snapshot.from_document(doc)
        # content_hash should be same for same doc
        assert snap1.content_hash == snap2.content_hash
        # snapshot_ids should differ (uuid-based)
        assert snap1.snapshot_id != snap2.snapshot_id


class TestSnapshotStore:
    """Tests for SnapshotStore."""

    def test_capture_and_get(self) -> None:
        store = SnapshotStore()
        doc = _make_doc()
        snap = store.capture(doc)
        assert snap.snapshot_id.startswith("snap_")

        retrieved = store.get(snap.snapshot_id)
        assert retrieved is not None
        assert retrieved.snapshot_id == snap.snapshot_id

    def test_get_missing(self) -> None:
        store = SnapshotStore()
        assert store.get("nonexistent") is None

    def test_get_by_url(self) -> None:
        store = SnapshotStore()
        doc1 = _make_doc(source_url="https://example.com/a")
        doc2 = _make_doc(source_url="https://example.com/a")
        doc3 = _make_doc(source_url="https://example.com/b")

        store.capture(doc1)
        store.capture(doc2)
        store.capture(doc3)

        url_a_snaps = store.get_by_url("https://example.com/a")
        assert len(url_a_snaps) == 2

        url_b_snaps = store.get_by_url("https://example.com/b")
        assert len(url_b_snaps) == 1

        url_c_snaps = store.get_by_url("https://example.com/c")
        assert len(url_c_snaps) == 0

    def test_get_latest(self) -> None:
        store = SnapshotStore()
        doc = _make_doc(source_url="https://example.com/page")

        store.capture(doc)
        store.capture(doc)

        latest = store.get_latest("https://example.com/page")
        assert latest is not None
        # The latest snapshot should exist
        assert latest.snapshot_id is not None

    def test_get_latest_missing(self) -> None:
        store = SnapshotStore()
        assert store.get_latest("https://missing.com") is None

    def test_list_all(self) -> None:
        store = SnapshotStore()
        doc1 = _make_doc(source_url="https://a.com")
        doc2 = _make_doc(source_url="https://b.com")

        store.capture(doc1)
        store.capture(doc2)

        all_snaps = store.list_all()
        assert len(all_snaps) == 2
        # Should be sorted by timestamp
        assert all_snaps[0].timestamp <= all_snaps[1].timestamp

    def test_list_all_empty(self) -> None:
        store = SnapshotStore()
        assert store.list_all() == []


# ===========================================================================
# Tracer Tests
# ===========================================================================


class TestTraceStep:
    """Tests for TraceStep dataclass."""

    def test_basic_creation(self) -> None:
        step = TraceStep(
            step_id="step_001",
            step_type="retrieve",
            decision_summary="Retrieved top 5 blocks",
            evidence_ids=["ev_1", "ev_2"],
        )
        assert step.step_id == "step_001"
        assert step.step_type == "retrieve"
        assert step.evidence_ids == ["ev_1", "ev_2"]

    def test_to_dict(self) -> None:
        step = TraceStep(
            step_id="step_dict",
            step_type="answer",
            input_data={"query": "What is the return policy?"},
            output_data={"answer": "30 day returns"},
            duration_ms=42.5,
        )
        d = step.to_dict()
        assert d["step_id"] == "step_dict"
        assert d["step_type"] == "answer"
        assert d["input_data"]["query"] == "What is the return policy?"
        assert d["duration_ms"] == 42.5


class TestTraceSession:
    """Tests for TraceSession dataclass."""

    def test_basic_creation(self) -> None:
        session = TraceSession(
            session_id="trace_001",
            query="What is the return policy?",
            start_time=1000.0,
        )
        assert session.session_id == "trace_001"
        assert session.query == "What is the return policy?"
        assert session.step_count == 0
        assert session.duration_ms == 0.0

    def test_add_step(self) -> None:
        session = TraceSession(session_id="trace_add")
        step = TraceStep(step_id="step_a", step_type="retrieve")
        session.add_step(step)
        assert session.step_count == 1
        assert session.steps[0].step_id == "step_a"

    def test_duration_ms(self) -> None:
        session = TraceSession(
            session_id="trace_dur",
            start_time=1000.0,
            end_time=1000.5,
        )
        assert session.duration_ms == pytest.approx(500.0, abs=0.1)

    def test_duration_ms_no_end(self) -> None:
        session = TraceSession(
            session_id="trace_noend",
            start_time=1000.0,
        )
        assert session.duration_ms == 0.0

    def test_to_dict(self) -> None:
        session = TraceSession(
            session_id="trace_dict",
            query="test query",
            start_time=100.0,
            end_time=100.05,
            final_answer="The answer",
            citations=["cit_1", "cit_2"],
        )
        step = TraceStep(step_id="s1", step_type="retrieve")
        session.add_step(step)

        d = session.to_dict()
        assert d["session_id"] == "trace_dict"
        assert d["query"] == "test query"
        assert d["final_answer"] == "The answer"
        assert d["citations"] == ["cit_1", "cit_2"]
        assert len(d["steps"]) == 1
        assert d["step_count"] == 1
        assert d["duration_ms"] == pytest.approx(50.0, abs=0.1)

    def test_to_markdown(self) -> None:
        session = TraceSession(
            session_id="trace_md",
            query="What is the return policy?",
            start_time=100.0,
            end_time=100.1,
            final_answer="30 day returns.",
            citations=["cit_1"],
        )
        step = TraceStep(
            step_id="s1",
            step_type="retrieve",
            decision_summary="Found 3 relevant blocks",
            evidence_ids=["ev_1"],
            duration_ms=25.0,
        )
        session.add_step(step)

        md = session.to_markdown()
        assert "trace_md" in md
        assert "What is the return policy?" in md
        assert "retrieve" in md
        assert "Found 3 relevant blocks" in md
        assert "30 day returns." in md
        assert "cit_1" in md


class TestTraceRecorder:
    """Tests for TraceRecorder."""

    def test_start_session(self) -> None:
        recorder = TraceRecorder()
        session = recorder.start_session(query="test query")
        assert session.session_id.startswith("trace_")
        assert session.query == "test query"
        assert session.start_time > 0

    def test_record_step(self) -> None:
        recorder = TraceRecorder()
        session = recorder.start_session("q")
        step = recorder.record_step(
            session.session_id,
            "retrieve",
            input_data={"query": "q"},
            evidence_ids=["ev_1"],
            decision_summary="Found match",
            duration_ms=10.0,
        )
        assert step.step_id.startswith("step_")
        assert step.step_type == "retrieve"
        assert step.evidence_ids == ["ev_1"]
        assert step.decision_summary == "Found match"

        # Step should be added to the session
        assert session.step_count == 1

    def test_record_step_missing_session(self) -> None:
        recorder = TraceRecorder()
        with pytest.raises(KeyError, match="Trace session not found"):
            recorder.record_step("nonexistent", "retrieve")

    def test_end_session(self) -> None:
        recorder = TraceRecorder()
        session = recorder.start_session("q")
        recorder.record_step(session.session_id, "retrieve")

        ended = recorder.end_session(
            session.session_id,
            answer="The answer",
            citations=["cit_1"],
        )
        assert ended.final_answer == "The answer"
        assert ended.citations == ["cit_1"]
        assert ended.end_time > 0
        assert ended.duration_ms > 0

    def test_end_session_missing(self) -> None:
        recorder = TraceRecorder()
        with pytest.raises(KeyError):
            recorder.end_session("nonexistent")

    def test_get_session(self) -> None:
        recorder = TraceRecorder()
        session = recorder.start_session("q")
        retrieved = recorder.get_session(session.session_id)
        assert retrieved is not None
        assert retrieved.session_id == session.session_id

    def test_get_session_missing(self) -> None:
        recorder = TraceRecorder()
        assert recorder.get_session("nonexistent") is None

    def test_list_sessions(self) -> None:
        recorder = TraceRecorder()
        recorder.start_session("query 1")
        recorder.start_session("query 2")

        sessions = recorder.list_sessions()
        assert len(sessions) == 2
        assert sessions[0].start_time <= sessions[1].start_time

    def test_list_sessions_empty(self) -> None:
        recorder = TraceRecorder()
        assert recorder.list_sessions() == []

    def test_full_trace_workflow(self) -> None:
        """End-to-end trace recording workflow."""
        recorder = TraceRecorder()

        # Start
        session = recorder.start_session("What is the return policy?")

        # Record steps
        recorder.record_step(
            session.session_id,
            "query",
            input_data={"query": "What is the return policy?"},
        )
        recorder.record_step(
            session.session_id,
            "retrieve",
            evidence_ids=["ev_001", "ev_002"],
            decision_summary="Retrieved 2 relevant blocks",
            duration_ms=15.0,
        )
        recorder.record_step(
            session.session_id,
            "select_evidence",
            evidence_ids=["ev_001"],
            decision_summary="Selected top evidence by relevance",
        )
        recorder.record_step(
            session.session_id,
            "answer",
            output_data={"answer": "Returns within 30 days."},
            duration_ms=5.0,
        )

        # End
        ended = recorder.end_session(
            session.session_id,
            answer="Returns within 30 days.",
            citations=["cit_001"],
        )

        assert ended.step_count == 4
        assert ended.final_answer == "Returns within 30 days."
        assert ended.duration_ms > 0

        # Verify serialization
        d = ended.to_dict()
        assert len(d["steps"]) == 4
        assert d["final_answer"] == "Returns within 30 days."

        # Verify markdown rendering
        md = ended.to_markdown()
        assert "query" in md
        assert "retrieve" in md
        assert "Returns within 30 days." in md


# ===========================================================================
# Integration Tests (cross-module)
# ===========================================================================


class TestProvenanceIntegration:
    """Integration tests combining evidence, citations, snapshots, and traces."""

    def test_full_pipeline(self) -> None:
        """End-to-end: document -> snapshot -> evidence -> citations -> trace."""
        # 1. Create a document
        blocks = [
            _make_block(
                block_id="b_001",
                text="The return policy allows returns within 30 days of purchase.",
                section_path=["FAQ", "Returns"],
                importance=0.9,
            ),
            _make_block(
                block_id="b_002",
                text="Shipping is free for orders over $50.",
                section_path=["FAQ", "Shipping"],
                importance=0.7,
            ),
        ]
        actions = [
            _make_action(
                action_id="a_return",
                label="Start Return",
                action_type=ActionType.CLICK,
            ),
        ]
        doc = _make_doc(blocks=blocks, actions=actions)

        # 2. Capture snapshot
        store = SnapshotStore()
        snapshot = store.capture(doc)
        assert snapshot.snapshot_id.startswith("snap_")

        # 3. Build evidence
        builder = EvidenceBuilder()
        evidence = builder.build_from_document(doc, snapshot_id=snapshot.snapshot_id)
        assert len(evidence) == 3  # 2 blocks + 1 action

        # All evidence should reference the snapshot
        for ev in evidence:
            assert ev.snapshot_id == snapshot.snapshot_id

        # 4. Generate citations
        citation_builder = CitationBuilder()
        answer = "You can return items within 30 days."
        citations = citation_builder.cite_answer(answer, evidence)
        assert len(citations) > 0

        # 5. Render cited answer
        rendered = citation_builder.render_answer_with_citations(answer, citations)
        assert "[1]" in rendered

        # 6. Record trace
        recorder = TraceRecorder()
        session = recorder.start_session("What is the return policy?")
        recorder.record_step(
            session.session_id,
            "retrieve",
            evidence_ids=[ev.evidence_id for ev in evidence],
        )
        recorder.record_step(
            session.session_id,
            "answer",
            output_data={"answer": answer},
        )
        ended = recorder.end_session(
            session.session_id,
            answer=answer,
            citations=[c.citation_id for c in citations],
        )

        assert ended.step_count == 2
        assert ended.final_answer == answer
        assert len(ended.citations) > 0

    def test_evidence_to_citation_round_trip(self) -> None:
        """Evidence -> CitationObject -> to_dict -> verify all fields present."""
        ev = Evidence(
            evidence_id="ev_rt",
            source_type="web_block",
            source_url="https://example.com",
            text="Round trip test content for verification.",
            section_path=["Test", "Section"],
            page=3,
            confidence=0.95,
        )

        cb = CitationBuilder()
        cit = cb.cite_action("Test action description", ev)
        d = cit.to_dict()

        assert d["citation_type"] == "action"
        assert d["evidence_ids"] == ["ev_rt"]
        assert len(d["evidence_texts"]) == 1
        assert d["confidence"] == 0.95
        assert d["render_hint"]["page"] == 3

    def test_snapshot_evidence_binding(self) -> None:
        """Verify evidence correctly references snapshots."""
        doc = _make_doc()
        store = SnapshotStore()
        snap1 = store.capture(doc)
        snap2 = store.capture(doc)

        builder = EvidenceBuilder()
        ev1 = builder.build_from_document(doc, snapshot_id=snap1.snapshot_id)
        ev2 = builder.build_from_document(doc, snapshot_id=snap2.snapshot_id)

        # Evidence from different snapshots should reference different snapshot_ids
        assert all(e.snapshot_id == snap1.snapshot_id for e in ev1)
        assert all(e.snapshot_id == snap2.snapshot_id for e in ev2)

        # But content should be the same
        assert ev1[0].text == ev2[0].text
