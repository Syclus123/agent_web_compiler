"""Citation objects — renderable references linking answers to evidence.

A Citation is the user-facing representation of an evidence chain.
It's what gets displayed as [1], [2] in grounded answers.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from agent_web_compiler.provenance.evidence import Evidence


def _make_citation_id(index: int, evidence_ids: list[str]) -> str:
    """Generate a deterministic citation ID."""
    raw = f"{index}{''.join(evidence_ids)}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]
    return f"cit_{digest}"


def _truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len, adding ellipsis if needed."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _tokenize(text: str) -> set[str]:
    """Simple word tokenizer for keyword overlap."""
    return {w.lower().strip(".,;:!?\"'()[]{}") for w in text.split() if len(w) > 2}


@dataclass
class RenderHint:
    """How to visually render this citation."""

    label: str = ""  # e.g. "FAQ > Returns"
    url: str | None = None
    page: int | None = None
    highlight_bbox: list[float] | None = None
    highlight_text: str = ""  # text to highlight
    screenshot_region: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "label": self.label,
            "url": self.url,
            "page": self.page,
            "highlight_bbox": self.highlight_bbox,
            "highlight_text": self.highlight_text,
            "screenshot_region": self.screenshot_region,
        }


@dataclass
class CitationObject:
    """A structured citation linking answer content to evidence.

    More than a URL — contains rendering hints, confidence,
    and references to specific Evidence objects.
    """

    citation_id: str
    citation_type: str = "block"  # "block", "action", "table", "code", "page"
    answer_span: str = ""  # The text in the answer this cites
    evidence_ids: list[str] = field(default_factory=list)
    evidence_texts: list[str] = field(default_factory=list)  # snippets for display
    render_hint: RenderHint | None = None
    confidence: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        d: dict[str, Any] = {
            "citation_id": self.citation_id,
            "citation_type": self.citation_type,
            "answer_span": self.answer_span,
            "evidence_ids": self.evidence_ids,
            "evidence_texts": self.evidence_texts,
            "confidence": self.confidence,
        }
        if self.render_hint is not None:
            d["render_hint"] = self.render_hint.to_dict()
        return d

    def to_markdown(self) -> str:
        """Render as markdown citation."""
        parts: list[str] = []
        snippets = [_truncate(t, 120) for t in self.evidence_texts]

        if self.render_hint and self.render_hint.url:
            label = self.render_hint.label or self.render_hint.url
            parts.append(f"[{label}]({self.render_hint.url})")
        elif self.render_hint and self.render_hint.label:
            parts.append(self.render_hint.label)

        if snippets:
            joined = "; ".join(f'"{s}"' for s in snippets)
            parts.append(joined)

        if self.render_hint and self.render_hint.page is not None:
            parts.append(f"p.{self.render_hint.page}")

        return " — ".join(parts) if parts else self.citation_id

    def to_html(self) -> str:
        """Render as HTML citation with highlight data attributes."""
        attrs: list[str] = [f'data-citation-id="{self.citation_id}"']
        if self.render_hint:
            if self.render_hint.highlight_text:
                safe_text = self.render_hint.highlight_text.replace('"', "&quot;")
                attrs.append(f'data-highlight-text="{safe_text}"')
            if self.render_hint.highlight_bbox:
                bbox_str = ",".join(str(v) for v in self.render_hint.highlight_bbox)
                attrs.append(f'data-highlight-bbox="{bbox_str}"')
            if self.render_hint.url:
                attrs.append(f'href="{self.render_hint.url}"')
            if self.render_hint.screenshot_region:
                attrs.append(f'data-screenshot-region="{self.render_hint.screenshot_region}"')

        attr_str = " ".join(attrs)
        label = self.citation_id
        if self.render_hint and self.render_hint.label:
            label = self.render_hint.label

        if self.render_hint and self.render_hint.url:
            return f"<a {attr_str}>{label}</a>"
        return f"<cite {attr_str}>{label}</cite>"


class CitationBuilder:
    """Builds citations from evidence and answer text."""

    def cite_answer(
        self,
        answer_text: str,
        evidence_list: list[Evidence],
        max_citations: int = 5,
    ) -> list[CitationObject]:
        """Generate citations for an answer based on evidence.

        Aligns answer text spans to evidence texts using
        substring matching and keyword overlap. Returns up to
        max_citations citations, ranked by relevance.
        """
        if not evidence_list:
            return []

        answer_tokens = _tokenize(answer_text)
        scored: list[tuple[float, int, Evidence]] = []

        for idx, ev in enumerate(evidence_list):
            score = self._compute_relevance(answer_text, answer_tokens, ev)
            scored.append((score, idx, ev))

        # Sort by score descending, take top max_citations
        scored.sort(key=lambda x: (-x[0], x[1]))
        top = scored[:max_citations]

        citations: list[CitationObject] = []
        for rank, (score, _idx, ev) in enumerate(top):
            if score <= 0.0:
                continue

            # Find the best matching span in the answer
            answer_span = self._find_answer_span(answer_text, ev)

            # Build render hint
            section_label = " > ".join(ev.section_path) if ev.section_path else ""
            render_hint = RenderHint(
                label=section_label,
                url=ev.source_url,
                page=ev.page,
                highlight_bbox=ev.bbox,
                highlight_text=_truncate(ev.text, 100),
                screenshot_region=ev.screenshot_region_id,
            )

            # Map evidence source_type to citation_type
            type_map = {
                "table_cell": "table",
                "code_block": "code",
                "action": "action",
            }
            citation_type = type_map.get(ev.source_type, "block")

            cit = CitationObject(
                citation_id=_make_citation_id(rank, [ev.evidence_id]),
                citation_type=citation_type,
                answer_span=answer_span,
                evidence_ids=[ev.evidence_id],
                evidence_texts=[_truncate(ev.text, 200)],
                render_hint=render_hint,
                confidence=ev.confidence * min(score, 1.0),
            )
            citations.append(cit)

        return citations

    def cite_action(
        self,
        action_description: str,
        action_evidence: Evidence,
    ) -> CitationObject:
        """Generate a citation for an action decision."""
        section_label = " > ".join(action_evidence.section_path) if action_evidence.section_path else ""
        render_hint = RenderHint(
            label=section_label or action_evidence.text,
            url=action_evidence.source_url,
            page=action_evidence.page,
            highlight_bbox=action_evidence.bbox,
            highlight_text=action_evidence.text,
            screenshot_region=action_evidence.screenshot_region_id,
        )

        return CitationObject(
            citation_id=_make_citation_id(0, [action_evidence.evidence_id]),
            citation_type="action",
            answer_span=action_description,
            evidence_ids=[action_evidence.evidence_id],
            evidence_texts=[_truncate(action_evidence.text, 200)],
            render_hint=render_hint,
            confidence=action_evidence.confidence,
        )

    def render_answer_with_citations(
        self,
        answer_text: str,
        citations: list[CitationObject],
    ) -> str:
        """Render answer text with inline [N] citation markers and footnotes.

        Appends citation markers at the end of the answer text,
        then adds a footnote section with evidence details.
        """
        if not citations:
            return answer_text

        # Build marker string
        markers = "".join(f"[{i + 1}]" for i in range(len(citations)))
        rendered = f"{answer_text} {markers}"

        # Build footnote section
        rendered += "\n\n---\n"
        for i, cit in enumerate(citations):
            snippets = "; ".join(f'"{t}"' for t in cit.evidence_texts)
            line = f"[{i + 1}] {snippets}"
            if cit.render_hint:
                location_parts: list[str] = []
                if cit.render_hint.label:
                    location_parts.append(cit.render_hint.label)
                if cit.render_hint.url:
                    location_parts.append(f"({cit.render_hint.url})")
                if cit.render_hint.page is not None:
                    location_parts.append(f"p.{cit.render_hint.page}")
                if location_parts:
                    line += f"\n    -- {' '.join(location_parts)}"
            rendered += f"\n{line}"

        return rendered

    def _compute_relevance(
        self,
        answer_text: str,
        answer_tokens: set[str],
        ev: Evidence,
    ) -> float:
        """Compute relevance score between answer text and evidence.

        Uses a combination of:
        1. Keyword overlap (Jaccard-like)
        2. Substring presence
        """
        if not ev.text:
            return 0.0

        ev_tokens = _tokenize(ev.text)
        if not ev_tokens:
            return 0.0

        # Keyword overlap
        overlap = answer_tokens & ev_tokens
        union = answer_tokens | ev_tokens
        jaccard = len(overlap) / len(union) if union else 0.0

        # Substring bonus: check if meaningful evidence words appear in answer
        answer_lower = answer_text.lower()
        substring_hits = sum(
            1 for token in ev_tokens
            if len(token) > 3 and token in answer_lower
        )
        substring_score = min(substring_hits / max(len(ev_tokens), 1), 1.0)

        return 0.6 * jaccard + 0.4 * substring_score

    def _find_answer_span(self, answer_text: str, ev: Evidence) -> str:
        """Find the best matching span in answer_text for this evidence.

        Returns the sentence in the answer that best overlaps with the evidence.
        Falls back to the first sentence if no good match.
        """
        if not answer_text:
            return ""

        # Split answer into sentences
        sentences = _split_sentences(answer_text)
        if not sentences:
            return _truncate(answer_text, 150)

        ev_tokens = _tokenize(ev.text)
        best_sentence = sentences[0]
        best_overlap = 0.0

        for sentence in sentences:
            s_tokens = _tokenize(sentence)
            if not s_tokens or not ev_tokens:
                continue
            overlap = len(s_tokens & ev_tokens) / len(s_tokens | ev_tokens)
            if overlap > best_overlap:
                best_overlap = overlap
                best_sentence = sentence

        return _truncate(best_sentence, 150)


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences using simple heuristics."""
    import re

    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in sentences if s.strip()]
