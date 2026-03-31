"""ProvenanceEngine — unified API for evidence, citations, snapshots, and traces.

This is the high-level entry point for the provenance system.
Integrates with AgentSearch to provide evidence-backed answers.

Usage:
    from agent_web_compiler.provenance import ProvenanceEngine

    engine = ProvenanceEngine()

    # Capture a page snapshot
    snapshot = engine.capture_snapshot(compiled_doc)

    # Build evidence from a document
    evidence_list = engine.build_evidence(compiled_doc)

    # Generate citations for an answer
    citations = engine.cite_answer(answer_text, evidence_list)

    # Record a decision trace
    session = engine.start_trace("What is the refund policy?")
    engine.record_step(session.session_id, "retrieve", results=search_results)
    engine.record_step(session.session_id, "answer", answer=answer_text)
    trace = engine.end_trace(session.session_id)

    # Render everything
    print(engine.render_cited_answer(answer_text, citations))
    print(trace.to_markdown())
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_web_compiler.provenance.citation import (
    CitationBuilder,
    CitationObject,
)
from agent_web_compiler.provenance.evidence import (
    Evidence,
    EvidenceBuilder,
)
from agent_web_compiler.provenance.snapshot import (
    Snapshot,
    SnapshotStore,
)
from agent_web_compiler.provenance.tracer import (
    TraceRecorder,
    TraceSession,
    TraceStep,
)

if TYPE_CHECKING:
    from agent_web_compiler.core.document import AgentDocument
    from agent_web_compiler.search.agent_search import AgentSearch
    from agent_web_compiler.search.retriever import SearchResult

# Re-export core types for convenience
__all__ = [
    "ProvenanceEngine",
    "Evidence",
    "CitationObject",
    "Snapshot",
    "TraceSession",
    "TraceStep",
]


class ProvenanceEngine:
    """Unified provenance, citation, and trace management.

    Provides a single facade over evidence building, citation generation,
    document snapshotting, and decision tracing. Designed to integrate with
    :class:`AgentSearch` for end-to-end evidence-backed answers.

    Delegates to the core provenance modules:
    - :class:`EvidenceBuilder` for evidence extraction
    - :class:`CitationBuilder` for citation generation and rendering
    - :class:`SnapshotStore` for document snapshots
    - :class:`TraceRecorder` for decision traces
    """

    def __init__(self) -> None:
        self._evidence_builder = EvidenceBuilder()
        self._citation_builder = CitationBuilder()
        self._snapshot_store = SnapshotStore()
        self._tracer = TraceRecorder()

    # --- Snapshots ---

    def capture_snapshot(self, doc: AgentDocument) -> Snapshot:
        """Capture an immutable snapshot of a compiled document.

        Args:
            doc: The AgentDocument to snapshot.

        Returns:
            A Snapshot with a unique ID and content hash.
        """
        return self._snapshot_store.capture(doc)

    def get_snapshot(self, snapshot_id: str) -> Snapshot | None:
        """Retrieve a previously captured snapshot by ID.

        Args:
            snapshot_id: The snapshot identifier.

        Returns:
            The Snapshot, or None if not found.
        """
        return self._snapshot_store.get(snapshot_id)

    # --- Evidence ---

    def build_evidence(
        self,
        doc: AgentDocument,
        snapshot_id: str | None = None,
    ) -> list[Evidence]:
        """Build evidence items from all blocks in a compiled document.

        Each block becomes an Evidence item with full provenance
        (section path, source URL, DOM path, page number, bbox).

        Args:
            doc: The AgentDocument to extract evidence from.
            snapshot_id: Optional snapshot ID to link evidence to.

        Returns:
            A list of Evidence objects, one per block and action.
        """
        return self._evidence_builder.build_from_document(doc, snapshot_id)

    def build_evidence_from_search(
        self, results: list[SearchResult]
    ) -> list[Evidence]:
        """Build evidence items from search results.

        Converts retriever SearchResult objects into Evidence objects
        with provenance information preserved.

        Args:
            results: Search results from the retriever.

        Returns:
            A list of Evidence objects.
        """
        evidence_list: list[Evidence] = []
        for result in results:
            ev = self._evidence_builder.build_from_search_result(result)
            evidence_list.append(ev)
        return evidence_list

    # --- Citations ---

    def cite_answer(
        self,
        answer_text: str,
        evidence: list[Evidence],
        max_citations: int = 5,
    ) -> list[CitationObject]:
        """Generate citations linking an answer to supporting evidence.

        Selects the top evidence items by relevance and creates numbered
        citation objects.

        Args:
            answer_text: The answer text to cite.
            evidence: Available evidence items.
            max_citations: Maximum number of citations to produce.

        Returns:
            A list of CitationObjects, sorted by relevance.
        """
        return self._citation_builder.cite_answer(
            answer_text, evidence, max_citations=max_citations
        )

    def cite_action(
        self, action_description: str, action_evidence: Evidence
    ) -> CitationObject:
        """Create a citation for a specific action.

        Args:
            action_description: Description of the action being cited.
            action_evidence: The evidence backing the action.

        Returns:
            A single CitationObject.
        """
        return self._citation_builder.cite_action(
            action_description, action_evidence
        )

    def render_cited_answer(
        self,
        answer_text: str,
        citations: list[CitationObject],
    ) -> str:
        """Render an answer with inline citation markers and a footnote section.

        Produces text with [N] markers after the answer and a numbered
        evidence list with provenance details.

        Args:
            answer_text: The answer text.
            citations: Citation objects to render.

        Returns:
            Formatted string with citations and evidence section.
        """
        return self._citation_builder.render_answer_with_citations(
            answer_text, citations
        )

    # --- Traces ---

    def start_trace(self, query: str = "") -> TraceSession:
        """Start a new decision trace session.

        Args:
            query: The query being traced.

        Returns:
            A new active TraceSession.
        """
        return self._tracer.start_session(query)

    def record_step(
        self, session_id: str, step_type: str, **kwargs: Any
    ) -> TraceStep:
        """Record a step in an active trace session.

        Args:
            session_id: The session to record the step in.
            step_type: Type of step (e.g. "retrieve", "answer", "cite").
            **kwargs: Additional data stored in the step's input_data dict.

        Returns:
            The recorded TraceStep.

        Raises:
            KeyError: If the session_id is not found.
        """
        return self._tracer.record_step(
            session_id,
            step_type,
            input_data=_serialize_kwargs(kwargs),
        )

    def end_trace(
        self, session_id: str, answer: str | None = None
    ) -> TraceSession:
        """End a trace session and mark it completed.

        Args:
            session_id: The session to end.
            answer: Optional final answer text.

        Returns:
            The completed TraceSession.

        Raises:
            KeyError: If the session_id is not found.
        """
        return self._tracer.end_session(session_id, answer=answer)

    def get_trace(self, session_id: str) -> TraceSession | None:
        """Retrieve a trace session by ID.

        Args:
            session_id: The session identifier.

        Returns:
            The TraceSession, or None if not found.
        """
        return self._tracer.get_session(session_id)

    # --- Convenience ---

    def answer_with_provenance(
        self, search: AgentSearch, query: str
    ) -> dict[str, Any]:
        """Full pipeline: search -> evidence -> citations -> traced answer.

        Executes the complete provenance-backed answer flow:
        1. Start trace session
        2. Search for relevant content
        3. Build evidence from search results
        4. Generate citations
        5. Compose and render the cited answer
        6. End trace

        Args:
            search: An AgentSearch instance with indexed content.
            query: The natural-language query.

        Returns:
            Dict with keys: answer, cited_answer, citations, evidence,
            trace, snapshot_ids.
        """
        # 1. Start trace
        session = self.start_trace(query)

        # 2. Search
        self.record_step(session.session_id, "search", query=query)
        response = search.search(query)
        self.record_step(
            session.session_id,
            "retrieve",
            result_count=len(response.results),
            intent=response.intent,
        )

        # 3. Get grounded answer
        grounded = search.answer(query)
        answer_text = grounded.answer_text

        # 4. Build evidence from search results
        evidence = self.build_evidence_from_search(response.results)
        self.record_step(
            session.session_id,
            "evidence",
            evidence_count=len(evidence),
        )

        # 5. Generate citations
        citations = self.cite_answer(answer_text, evidence)
        self.record_step(
            session.session_id,
            "cite",
            citation_count=len(citations),
        )

        # 6. Render
        cited_answer = self.render_cited_answer(answer_text, citations)

        # 7. End trace
        self.end_trace(session.session_id, answer=answer_text)

        return {
            "answer": answer_text,
            "cited_answer": cited_answer,
            "citations": [c.to_dict() for c in citations],
            "evidence": [e.to_dict() for e in evidence],
            "trace": session.to_dict(),
            "snapshot_ids": [],
        }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _serialize_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Serialize kwargs to JSON-safe types for trace storage."""
    result: dict[str, Any] = {}
    for k, v in kwargs.items():
        if isinstance(v, (str, int, float, bool, type(None))):
            result[k] = v
        elif isinstance(v, list):
            result[k] = f"[{len(v)} items]"
        elif isinstance(v, dict):
            result[k] = f"{{{len(v)} keys}}"
        elif hasattr(v, "to_dict"):
            result[k] = str(type(v).__name__)
        else:
            result[k] = str(v)
    return result
