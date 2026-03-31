"""Grounded answering — composes answers with citations from search results.

Instead of generating unconstrained text, builds answers that are:
1. Backed by specific block evidence
2. Traceable via provenance (section, page, DOM path)
3. Explicit about uncertainty when evidence is insufficient
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent_web_compiler.search.query_planner import QueryIntent
from agent_web_compiler.search.retriever import Retriever, SearchResponse, SearchResult

# Minimum score threshold below which evidence is considered insufficient
_MIN_EVIDENCE_SCORE = 0.3


@dataclass
class Citation:
    """A provenance-backed citation."""

    block_id: str
    doc_id: str
    text_snippet: str  # The specific text being cited
    section_path: list[str] = field(default_factory=list)
    page: int | None = None
    url: str | None = None
    confidence: float = 0.5


@dataclass
class GroundedAnswer:
    """An answer backed by grounded evidence.

    Contains the composed answer text, a list of citations with provenance,
    confidence scoring, and optional follow-up suggestions when evidence
    is insufficient.
    """

    answer_text: str
    citations: list[Citation] = field(default_factory=list)
    confidence: float = 0.5
    evidence_sufficient: bool = True
    suggested_followup: str | None = None  # If evidence insufficient
    action_plan: list[dict] | None = None  # If task query

    def to_markdown(self) -> str:
        """Render answer with inline citations as markdown.

        Format:
            **Answer**: <text> [1][2]

            **Evidence**:
            [1] "snippet..." — Section > Path (url)
            [2] "snippet..." — Section > Path (url)
        """
        parts: list[str] = []

        # Answer line with citation references
        if self.citations:
            refs = "".join(f"[{i + 1}]" for i in range(len(self.citations)))
            parts.append(f"**Answer**: {self.answer_text} {refs}")
        else:
            parts.append(f"**Answer**: {self.answer_text}")

        # Evidence section
        if self.citations:
            parts.append("")
            parts.append("**Evidence**:")
            for i, cit in enumerate(self.citations):
                section_str = " > ".join(cit.section_path) if cit.section_path else ""
                location = section_str
                if cit.url:
                    location = f"{location} ({cit.url})" if location else f"({cit.url})"
                if cit.page is not None:
                    location = f"{location}, p.{cit.page}" if location else f"p.{cit.page}"

                snippet = _truncate(cit.text_snippet, 200)
                line = f'[{i + 1}] "{snippet}"'
                if location:
                    line += f"\n    — {location}"
                parts.append(line)

        # Insufficient evidence warning
        if not self.evidence_sufficient:
            parts.append("")
            parts.append(
                "⚠ Evidence may be insufficient for a complete answer."
            )
            if self.suggested_followup:
                parts.append(f"**Suggested follow-up**: {self.suggested_followup}")

        # Action plan
        if self.action_plan:
            parts.append("")
            parts.append("**Action plan**:")
            for i, step in enumerate(self.action_plan):
                label = step.get("label", step.get("action_type", "action"))
                parts.append(f"{i + 1}. {label}")

        return "\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "answer_text": self.answer_text,
            "citations": [
                {
                    "block_id": c.block_id,
                    "doc_id": c.doc_id,
                    "text_snippet": c.text_snippet,
                    "section_path": c.section_path,
                    "page": c.page,
                    "url": c.url,
                    "confidence": c.confidence,
                }
                for c in self.citations
            ],
            "confidence": self.confidence,
            "evidence_sufficient": self.evidence_sufficient,
            "suggested_followup": self.suggested_followup,
            "action_plan": self.action_plan,
        }


class GroundedAnswerer:
    """Composes grounded answers from search results.

    Uses the Retriever to find relevant blocks/actions, then composes
    an answer purely from extraction (no LLM required).
    """

    def __init__(self, retriever: Retriever) -> None:
        self.retriever = retriever

    def answer(self, query: str, top_k: int = 5, **kwargs: Any) -> GroundedAnswer:
        """Search and compose a grounded answer with citations.

        Args:
            query: Natural-language question.
            top_k: Maximum number of evidence results to use.
            **kwargs: Passed through to retriever.search().

        Returns:
            A GroundedAnswer with citations and confidence.
        """
        response = self.retriever.search(query, top_k=top_k, **kwargs)
        return self._compose_answer(query, response.results, response)

    def _compose_answer(
        self,
        query: str,
        results: list[SearchResult],
        response: SearchResponse | None = None,
    ) -> GroundedAnswer:
        """Compose answer text from search results (no LLM required).

        Strategy by intent:
        - FACT: Extract the most relevant paragraph as answer text.
        - EVIDENCE: Extract all high-score blocks as evidence list.
        - TASK: Extract action candidates as action_plan.
        - NAVIGATION: Extract navigation action details.
        - HYBRID: Combine block content with action info.
        """
        intent = QueryIntent.FACT
        if response and response.intent:
            try:
                intent = QueryIntent(response.intent)
            except ValueError:
                intent = QueryIntent.FACT

        # Filter to results above minimum score
        strong_results = [r for r in results if r.score > _MIN_EVIDENCE_SCORE]
        block_results = [r for r in strong_results if r.kind == "block"]
        action_results = [r for r in strong_results if r.kind == "action"]

        citations = self._extract_citations(block_results)
        evidence_sufficient = len(strong_results) > 0

        # Compose answer text based on intent
        if intent == QueryIntent.TASK:
            return self._compose_task_answer(
                query, block_results, action_results, citations, evidence_sufficient
            )

        if intent == QueryIntent.NAVIGATION:
            return self._compose_navigation_answer(
                query, action_results, citations, evidence_sufficient
            )

        if intent == QueryIntent.EVIDENCE:
            return self._compose_evidence_answer(
                query, block_results, citations, evidence_sufficient
            )

        # FACT or HYBRID
        return self._compose_fact_answer(
            query, block_results, action_results, citations, evidence_sufficient
        )

    def _compose_fact_answer(
        self,
        query: str,
        block_results: list[SearchResult],
        action_results: list[SearchResult],
        citations: list[Citation],
        evidence_sufficient: bool,
    ) -> GroundedAnswer:
        """Compose a factual answer from the top block result."""
        if block_results:
            # Use the top result's text as the answer
            answer_text = _first_meaningful_sentence(block_results[0].text)
            confidence = min(block_results[0].score, 1.0)
        else:
            answer_text = "No relevant information found."
            confidence = 0.0
            evidence_sufficient = False

        followup = None
        if not evidence_sufficient:
            followup = f"Try rephrasing: \"{query}\" or compile additional pages."

        return GroundedAnswer(
            answer_text=answer_text,
            citations=citations,
            confidence=round(confidence, 2),
            evidence_sufficient=evidence_sufficient,
            suggested_followup=followup,
        )

    def _compose_evidence_answer(
        self,
        query: str,
        block_results: list[SearchResult],
        citations: list[Citation],
        evidence_sufficient: bool,
    ) -> GroundedAnswer:
        """Compose an evidence-oriented answer with all supporting blocks."""
        if block_results:
            # Combine top results into evidence summary
            snippets = [
                _truncate(r.text, 150) for r in block_results[:5]
            ]
            answer_text = " ".join(snippets)
            confidence = min(block_results[0].score, 1.0)
        else:
            answer_text = "No supporting evidence found."
            confidence = 0.0
            evidence_sufficient = False

        followup = None
        if not evidence_sufficient:
            followup = f"Try searching for specific terms related to: \"{query}\""

        return GroundedAnswer(
            answer_text=answer_text,
            citations=citations,
            confidence=round(confidence, 2),
            evidence_sufficient=evidence_sufficient,
            suggested_followup=followup,
        )

    def _compose_task_answer(
        self,
        query: str,
        block_results: list[SearchResult],
        action_results: list[SearchResult],
        citations: list[Citation],
        evidence_sufficient: bool,
    ) -> GroundedAnswer:
        """Compose a task-oriented answer with an action plan."""
        action_plan: list[dict] = []
        for r in action_results:
            action_plan.append({
                "action_id": r.action_id,
                "action_type": r.metadata.get("action_type", ""),
                "label": r.text,
                "selector": r.metadata.get("selector"),
                "confidence": r.metadata.get("confidence", 0.5),
            })

        if action_plan:
            answer_text = f"Found {len(action_plan)} relevant action(s) to complete the task."
            confidence = min(action_results[0].score, 1.0)
        elif block_results:
            answer_text = _first_meaningful_sentence(block_results[0].text)
            confidence = min(block_results[0].score, 1.0)
        else:
            answer_text = "No actions or relevant content found for this task."
            confidence = 0.0
            evidence_sufficient = False

        followup = None
        if not evidence_sufficient:
            followup = "Compile the target page first, then retry."

        return GroundedAnswer(
            answer_text=answer_text,
            citations=citations,
            confidence=round(confidence, 2),
            evidence_sufficient=evidence_sufficient,
            suggested_followup=followup,
            action_plan=action_plan if action_plan else None,
        )

    def _compose_navigation_answer(
        self,
        query: str,
        action_results: list[SearchResult],
        citations: list[Citation],
        evidence_sufficient: bool,
    ) -> GroundedAnswer:
        """Compose a navigation-oriented answer."""
        if action_results:
            top = action_results[0]
            answer_text = f"Navigate: {top.text}"
            confidence = min(top.score, 1.0)
            action_plan = [
                {
                    "action_id": top.action_id,
                    "action_type": top.metadata.get("action_type", "navigate"),
                    "label": top.text,
                    "selector": top.metadata.get("selector"),
                }
            ]
        else:
            answer_text = "No matching navigation action found."
            confidence = 0.0
            evidence_sufficient = False
            action_plan = None

        followup = None
        if not evidence_sufficient:
            followup = "The target page may not be indexed yet."

        return GroundedAnswer(
            answer_text=answer_text,
            citations=citations,
            confidence=round(confidence, 2),
            evidence_sufficient=evidence_sufficient,
            suggested_followup=followup,
            action_plan=action_plan,
        )

    def _extract_citations(self, results: list[SearchResult]) -> list[Citation]:
        """Extract citation objects from search results."""
        citations: list[Citation] = []
        for r in results:
            prov = r.provenance or {}
            url = prov.get("source_url") or prov.get("url")
            page = r.metadata.get("page") if r.metadata else None

            citations.append(
                Citation(
                    block_id=r.block_id or "",
                    doc_id=r.doc_id,
                    text_snippet=_truncate(r.text, 200),
                    section_path=list(r.section_path),
                    page=page,
                    url=url,
                    confidence=min(r.score, 1.0),
                )
            )
        return citations


# --- Pure helpers ---


def _truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len, adding ellipsis if needed."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _first_meaningful_sentence(text: str) -> str:
    """Extract the first meaningful sentence from text.

    Splits on common sentence boundaries and returns the first
    non-trivial sentence (at least 10 chars).
    """
    # Split on sentence-ending punctuation followed by space or end
    import re

    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    for s in sentences:
        s = s.strip()
        if len(s) >= 10:
            return s
    # Fallback: return entire text truncated
    return _truncate(text.strip(), 300)
