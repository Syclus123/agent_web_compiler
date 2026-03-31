"""Query-aware filtering — re-ranks and filters blocks by query relevance."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from agent_web_compiler.core.block import Block
from agent_web_compiler.core.config import CompileConfig

# Tokenisation: split on whitespace and punctuation, lowercase.
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    """Split *text* into lowercase alphanumeric tokens."""
    return _TOKEN_RE.findall(text.lower())


@dataclass(frozen=True)
class RelevanceBreakdown:
    """Transparent breakdown of how a block's relevance was computed."""

    tf_idf: float = 0.0
    section_match: float = 0.0
    heading_proximity: float = 0.0
    combined: float = 0.0


class QueryAwareFilter:
    """Filters and re-ranks blocks based on query relevance.

    Pure-function style: calling :meth:`filter_blocks` does **not** mutate the
    input list.  All intermediate scores are deterministic given the same input.
    """

    def __init__(
        self,
        query: str,
        *,
        relevance_threshold: float = 0.1,
        tf_idf_weight: float = 0.6,
        section_weight: float = 0.2,
        heading_weight: float = 0.2,
        importance_blend: float = 0.5,
    ) -> None:
        if not query or not query.strip():
            raise ValueError("query must be a non-empty string")
        self.query = query
        self.query_terms = _tokenize(query)
        self.relevance_threshold = relevance_threshold
        self.tf_idf_weight = tf_idf_weight
        self.section_weight = section_weight
        self.heading_weight = heading_weight
        self.importance_blend = importance_blend

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def filter_blocks(
        self,
        blocks: list[Block],
        config: CompileConfig,
    ) -> list[Block]:
        """Filter blocks by query relevance and return re-scored copies.

        Steps:
        1. Compute IDF across all blocks.
        2. Compute per-block relevance (TF-IDF + section + heading proximity).
        3. Drop blocks below ``relevance_threshold``.
        4. Blend relevance into ``importance``.
        5. If ``config.max_blocks`` is set, keep only the top-N.

        Returns a new list; *blocks* is not mutated.
        """
        if not blocks or not self.query_terms:
            return list(blocks)

        idf = self._compute_idf(blocks)
        scored: list[tuple[Block, float]] = []

        for block in blocks:
            breakdown = self._relevance_breakdown(block, blocks, idf)
            if breakdown.combined < self.relevance_threshold:
                continue
            new_importance = (
                block.importance * (1.0 - self.importance_blend)
                + breakdown.combined * self.importance_blend
            )
            new_importance = max(0.0, min(1.0, new_importance))
            updated = block.model_copy(update={"importance": new_importance})
            scored.append((updated, new_importance))

        # Sort by new importance descending.
        scored.sort(key=lambda pair: pair[1], reverse=True)

        # Token budget: honour max_blocks.
        if config.max_blocks is not None and config.max_blocks > 0:
            scored = scored[: config.max_blocks]

        return [block for block, _ in scored]

    def compute_relevance(self, block: Block, all_blocks: list[Block] | None = None) -> float:
        """Compute combined relevance of *block* to the query.

        When *all_blocks* is provided the IDF is computed across the corpus;
        otherwise a single-document IDF is used (every term has IDF 1.0).
        """
        if all_blocks is not None:
            idf = self._compute_idf(all_blocks)
        else:
            idf = {term: 1.0 for term in self.query_terms}
        return self._relevance_breakdown(block, all_blocks or [block], idf).combined

    # ------------------------------------------------------------------
    # IDF computation
    # ------------------------------------------------------------------

    def _compute_idf(self, blocks: list[Block]) -> dict[str, float]:
        """Compute inverse document frequency for each query term.

        Uses smoothed IDF: log(1 + N / (1 + df(t))) to avoid zero scores
        when a term appears in many blocks.
        """
        n = len(blocks)
        doc_freq: dict[str, int] = {term: 0 for term in self.query_terms}
        for block in blocks:
            block_tokens = set(_tokenize(block.text))
            for term in self.query_terms:
                if term in block_tokens:
                    doc_freq[term] += 1

        return {
            term: math.log(1.0 + n / (1.0 + df)) if n > 0 else 0.0
            for term, df in doc_freq.items()
        }

    # ------------------------------------------------------------------
    # Per-block relevance
    # ------------------------------------------------------------------

    def _relevance_breakdown(
        self,
        block: Block,
        all_blocks: list[Block],
        idf: dict[str, float],
    ) -> RelevanceBreakdown:
        """Full relevance breakdown for a single block."""
        tf_idf = self._tf_idf_score(block.text, idf)
        section_match = self._section_match_score(block)
        heading_proximity = self._heading_proximity_score(block, all_blocks)
        combined = (
            self.tf_idf_weight * tf_idf
            + self.section_weight * section_match
            + self.heading_weight * heading_proximity
        )
        combined = max(0.0, min(1.0, combined))
        return RelevanceBreakdown(
            tf_idf=tf_idf,
            section_match=section_match,
            heading_proximity=heading_proximity,
            combined=combined,
        )

    # ------------------------------------------------------------------
    # Feature helpers
    # ------------------------------------------------------------------

    def _tf_idf_score(self, text: str, idf: dict[str, float]) -> float:
        """TF-IDF score of query terms in *text*, normalised to [0, 1]."""
        tokens = _tokenize(text)
        if not tokens:
            return 0.0
        token_count = len(tokens)
        score = 0.0
        for term in self.query_terms:
            tf = tokens.count(term) / token_count
            score += tf * idf.get(term, 0.0)
        # Normalise: divide by number of query terms so result ∈ ~[0, 1].
        if self.query_terms:
            score /= len(self.query_terms)
        # Squash via sigmoid to keep in [0, 1] range.
        return min(1.0, 2.0 / (1.0 + math.exp(-score * 5)) - 1.0)

    def _section_match_score(self, block: Block) -> float:
        """Fraction of query terms that appear in the block's section_path."""
        if not block.section_path or not self.query_terms:
            return 0.0
        path_text = " ".join(block.section_path).lower()
        path_tokens = set(_tokenize(path_text))
        matches = sum(1 for t in self.query_terms if t in path_tokens)
        return matches / len(self.query_terms)

    def _heading_proximity_score(self, block: Block, all_blocks: list[Block]) -> float:
        """Boost blocks near headings that contain query terms.

        Finds the closest heading (by order) whose text contains at least
        one query term.  Proximity decays with distance.
        """
        from agent_web_compiler.core.block import BlockType

        if not all_blocks or not self.query_terms:
            return 0.0

        # Collect headings that contain at least one query term.
        matching_headings: list[int] = []
        for b in all_blocks:
            if b.type == BlockType.HEADING:
                heading_tokens = set(_tokenize(b.text))
                if any(t in heading_tokens for t in self.query_terms):
                    matching_headings.append(b.order)

        if not matching_headings:
            return 0.0

        # Find minimum distance to any matching heading.
        min_dist = min(abs(block.order - h) for h in matching_headings)
        # Decay: score = 1 / (1 + dist).  Distance 0 -> 1.0, distance 5 -> ~0.17
        return 1.0 / (1.0 + min_dist)
