"""Retriever — orchestrates multi-stage hybrid retrieval.

Implements the 4-stage retrieval pipeline:
1. Query understanding (via QueryPlanner)
2. Candidate retrieval (BM25 + dense + filters)
3. Structured re-ranking (importance, evidence, freshness, type prior)
4. Result packaging (with provenance)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from agent_web_compiler.index import IndexEngine
from agent_web_compiler.index.schema import BlockRecord
from agent_web_compiler.search.query_planner import QueryIntent, QueryPlan, QueryPlanner


@dataclass
class SearchResult:
    """A single search result with provenance."""

    kind: str  # "block", "action", "document"
    score: float
    doc_id: str
    block_id: str | None = None
    action_id: str | None = None
    text: str = ""
    section_path: list[str] = field(default_factory=list)
    provenance: dict | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class SearchResponse:
    """Complete search response with results and metadata."""

    query: str
    intent: str
    results: list[SearchResult] = field(default_factory=list)
    total_candidates: int = 0
    retrieval_time_ms: float = 0.0
    plan: QueryPlan | None = None


# --- Re-ranking weights ---

_IMPORTANCE_BOOST = 0.15
_EVIDENCE_BOOST = 0.2
_SECTION_PENALTY = 0.05

# Block types that get a boost for data-oriented queries
_DATA_TYPES = frozenset({"table", "product_spec", "faq"})
# Block types that get a boost for code/API queries
_CODE_TYPES = frozenset({"code"})

_DATA_KEYWORDS = frozenset(
    {"data", "table", "price", "cost", "spec", "comparison", "feature", "plan"}
)
_CODE_KEYWORDS = frozenset(
    {"api", "code", "endpoint", "function", "method", "sdk", "example", "snippet"}
)


class Retriever:
    """Multi-stage hybrid retriever over indexed Agent Web objects.

    Orchestrates query planning, candidate retrieval via the IndexEngine,
    structured re-ranking, and result packaging with provenance.
    """

    def __init__(self, engine: IndexEngine) -> None:
        self.engine = engine
        self.planner = QueryPlanner()

    def search(
        self,
        query: str,
        top_k: int = 10,
        query_embedding: list[float] | None = None,
        filters: dict | None = None,
    ) -> SearchResponse:
        """Execute a full search pipeline: plan → retrieve → rerank → package.

        Args:
            query: Natural-language search query.
            top_k: Maximum number of results to return.
            query_embedding: Optional dense vector for hybrid retrieval.
            filters: Optional metadata filters (block_type, min_importance, doc_id).

        Returns:
            A SearchResponse with ranked results and retrieval metadata.
        """
        start = time.monotonic()

        plan = self.planner.plan(query)
        results: list[SearchResult] = []
        total_candidates = 0

        for step in plan.search_steps:
            if step.tool == "search_blocks":
                step_filters = dict(filters) if filters else {}
                # Merge step-level filter hints
                if "min_evidence_score" in step.args:
                    step_filters["min_importance"] = step.args["min_evidence_score"]
                block_results = self._retrieve_blocks(
                    query,
                    top_k=top_k * 3,
                    query_embedding=query_embedding,
                    filters=step_filters if step_filters else None,
                )
                total_candidates += len(block_results)
                results.extend(block_results)

            elif step.tool == "search_actions":
                action_results = self._retrieve_actions(
                    query,
                    top_k=top_k * 3,
                    query_embedding=query_embedding,
                )
                total_candidates += len(action_results)
                results.extend(action_results)

            # "execute_action" and "compile_url" are plan-only hints;
            # actual execution is the caller's responsibility.

        # Re-rank all collected results
        results = self._rerank(results, query, plan.intent)

        # Deduplicate by (kind, block_id/action_id)
        results = self._deduplicate(results)

        elapsed_ms = (time.monotonic() - start) * 1000

        return SearchResponse(
            query=query,
            intent=plan.intent.value,
            results=results[:top_k],
            total_candidates=total_candidates,
            retrieval_time_ms=round(elapsed_ms, 2),
            plan=plan,
        )

    def search_blocks(
        self,
        query: str,
        top_k: int = 10,
        query_embedding: list[float] | None = None,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        """Search for content blocks (convenience method).

        Returns a flat list of SearchResult objects for block matches.
        """
        raw = self._retrieve_blocks(query, top_k, query_embedding, filters)
        return raw[:top_k]

    def search_actions(
        self,
        query: str,
        top_k: int = 10,
        query_embedding: list[float] | None = None,
    ) -> list[SearchResult]:
        """Search for executable actions (convenience method).

        Returns a flat list of SearchResult objects for action matches.
        """
        raw = self._retrieve_actions(query, top_k, query_embedding)
        return raw[:top_k]

    # --- Internal retrieval ---

    def _retrieve_blocks(
        self,
        query: str,
        top_k: int = 30,
        query_embedding: list[float] | None = None,
        filters: dict | None = None,
    ) -> list[SearchResult]:
        """Retrieve block candidates from the index engine."""
        raw = self.engine.search_blocks(
            query,
            query_embedding=query_embedding,
            top_k=top_k,
            filters=filters,
        )
        results: list[SearchResult] = []
        for record, score in raw:
            provenance = _block_provenance(record)
            results.append(
                SearchResult(
                    kind="block",
                    score=score,
                    doc_id=record.doc_id,
                    block_id=record.block_id,
                    text=record.text,
                    section_path=list(record.section_path),
                    provenance=provenance,
                    metadata={
                        "block_type": record.block_type,
                        "importance": record.importance,
                        "evidence_score": record.evidence_score,
                        "page": record.page,
                    },
                )
            )
        return results

    def _retrieve_actions(
        self,
        query: str,
        top_k: int = 30,
        query_embedding: list[float] | None = None,
    ) -> list[SearchResult]:
        """Retrieve action candidates from the index engine."""
        raw = self.engine.search_actions(
            query,
            query_embedding=query_embedding,
            top_k=top_k,
        )
        results: list[SearchResult] = []
        for record, score in raw:
            results.append(
                SearchResult(
                    kind="action",
                    score=score,
                    doc_id=record.doc_id,
                    action_id=record.action_id,
                    text=record.label,
                    provenance={"action_type": record.action_type, "role": record.role},
                    metadata={
                        "action_type": record.action_type,
                        "role": record.role,
                        "selector": record.selector,
                        "confidence": record.confidence,
                    },
                )
            )
        return results

    # --- Re-ranking ---

    def _rerank(
        self,
        results: list[SearchResult],
        query: str,
        intent: QueryIntent,
    ) -> list[SearchResult]:
        """Re-rank results using structured signals.

        Adjustments:
        - Boost blocks whose type matches the query topic (data/code)
        - Boost blocks with high importance
        - Boost blocks with high evidence_score (for evidence queries)
        - Penalize blocks without section_path context
        """
        query_lower = query.lower()
        query_words = set(query_lower.split())

        is_data_query = bool(query_words & _DATA_KEYWORDS)
        is_code_query = bool(query_words & _CODE_KEYWORDS)

        reranked: list[SearchResult] = []
        for result in results:
            adjusted = result.score

            if result.kind == "block":
                block_type = result.metadata.get("block_type", "")
                importance = result.metadata.get("importance", 0.5)
                evidence_score = result.metadata.get("evidence_score", 0.5)

                # Type-topic boost
                if is_data_query and block_type in _DATA_TYPES:
                    adjusted += _IMPORTANCE_BOOST
                if is_code_query and block_type in _CODE_TYPES:
                    adjusted += _IMPORTANCE_BOOST

                # Section path relevance boost — if query terms appear in the
                # block's section path, the block is likely more relevant
                if result.section_path:
                    section_text = " ".join(result.section_path).lower()
                    section_overlap = sum(1 for w in query_words if w in section_text)
                    if section_overlap > 0:
                        adjusted += _IMPORTANCE_BOOST * min(section_overlap, 3)

                # Importance boost
                if importance > 0.7:
                    adjusted += _IMPORTANCE_BOOST * (importance - 0.5)

                # Evidence boost (especially for evidence queries)
                if intent == QueryIntent.EVIDENCE and evidence_score > 0.7:
                    adjusted += _EVIDENCE_BOOST * (evidence_score - 0.5)

                # Section path penalty
                if not result.section_path:
                    adjusted -= _SECTION_PENALTY

            # Update score
            result.score = max(adjusted, 0.0)
            reranked.append(result)

        reranked.sort(key=lambda r: r.score, reverse=True)
        return reranked

    def _deduplicate(self, results: list[SearchResult]) -> list[SearchResult]:
        """Remove duplicate results, keeping the highest-scored entry."""
        seen: set[str] = set()
        deduped: list[SearchResult] = []
        for r in results:
            key = f"{r.kind}:{r.block_id or r.action_id}"
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        return deduped


# --- Helpers ---


def _block_provenance(record: BlockRecord) -> dict:
    """Build a provenance dict from a BlockRecord."""
    prov: dict = {
        "doc_id": record.doc_id,
        "block_id": record.block_id,
        "section_path": list(record.section_path),
    }
    if record.page is not None:
        prov["page"] = record.page
    if record.bbox is not None:
        prov["bbox"] = list(record.bbox)
    return prov
