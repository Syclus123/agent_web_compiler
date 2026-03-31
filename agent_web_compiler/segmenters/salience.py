"""Advanced salience scoring — computes block importance using multiple features."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from agent_web_compiler.core.block import Block, BlockType


@dataclass(frozen=True)
class SalienceFeatures:
    """Features extracted from a block for importance scoring."""

    block_type_weight: float = 0.5
    in_main_content: bool = False
    heading_coverage: float = 0.0
    entity_density: float = 0.0
    position_score: float = 0.5
    text_length_score: float = 0.5
    link_density: float = 0.0
    has_data_content: bool = False
    dom_depth_penalty: float = 1.0
    semantic_tag_bonus: float = 0.0


@dataclass
class ScoringContext:
    """Context passed to the scorer for position-relative and structural features."""

    total_blocks: int = 1
    block_index: int = 0
    html: str = ""


# Default base weights by block type.
BLOCK_TYPE_WEIGHTS: dict[BlockType, float] = {
    BlockType.HEADING: 0.9,
    BlockType.PARAGRAPH: 0.7,
    BlockType.TABLE: 0.85,
    BlockType.CODE: 0.75,
    BlockType.LIST: 0.65,
    BlockType.QUOTE: 0.5,
    BlockType.FIGURE_CAPTION: 0.6,
    BlockType.IMAGE: 0.5,
    BlockType.PRODUCT_SPEC: 0.8,
    BlockType.REVIEW: 0.6,
    BlockType.FAQ: 0.7,
    BlockType.FORM_HELP: 0.4,
    BlockType.METADATA: 0.3,
    BlockType.UNKNOWN: 0.3,
}

# Default feature-group weights for the final weighted combination.
DEFAULT_WEIGHTS: dict[str, float] = {
    "block_type": 0.25,
    "position": 0.15,
    "content_richness": 0.20,
    "structural": 0.20,
    "context": 0.20,
}

# Regex patterns for entity detection.
_NUMBER_RE = re.compile(r"\d+")
_DATE_RE = re.compile(
    r"\b(?:20\d{2}|19\d{2}|January|February|March|April|May|June"
    r"|July|August|September|October|November|December)\b",
    re.IGNORECASE,
)
_CAPITALIZED_RE = re.compile(r"\b[A-Z][a-z]{2,}\b")
_URL_RE = re.compile(r"https?://\S+")
_SEMANTIC_TAGS = {"main", "article", "section"}
_DATA_BLOCK_TYPES = {BlockType.TABLE, BlockType.CODE, BlockType.PRODUCT_SPEC}


class SalienceScorer:
    """Computes block importance using multi-feature scoring.

    All weights are configurable at construction time; the defaults produce
    reasonable results for general web pages.
    """

    def __init__(
        self,
        *,
        weights: dict[str, float] | None = None,
        block_type_weights: dict[BlockType, float] | None = None,
    ) -> None:
        self.weights = weights or dict(DEFAULT_WEIGHTS)
        self.block_type_weights = block_type_weights or dict(BLOCK_TYPE_WEIGHTS)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score(self, block: Block, context: ScoringContext) -> float:
        """Compute importance score for a single block.

        Returns a float clipped to [0.0, 1.0].
        """
        features = self.extract_features(block, context)
        return self._combine(features)

    def score_blocks(self, blocks: list[Block], html: str) -> list[Block]:
        """Re-score all *blocks* with advanced features.

        Returns a **new** list of blocks with updated ``importance`` values.
        The input list is not mutated.
        """
        if not blocks:
            return []

        total = len(blocks)
        scored: list[Block] = []
        for idx, block in enumerate(blocks):
            ctx = ScoringContext(total_blocks=total, block_index=idx, html=html)
            new_importance = self.score(block, ctx)
            scored.append(block.model_copy(update={"importance": new_importance}))
        return scored

    # ------------------------------------------------------------------
    # Feature extraction
    # ------------------------------------------------------------------

    def extract_features(self, block: Block, context: ScoringContext) -> SalienceFeatures:
        """Extract all salience features for *block*."""
        return SalienceFeatures(
            block_type_weight=self.block_type_weights.get(block.type, 0.5),
            in_main_content=self._in_main_content(block),
            heading_coverage=self._heading_coverage(block),
            entity_density=self._entity_density(block.text),
            position_score=self._position_score(context.block_index, context.total_blocks),
            text_length_score=self._text_length_score(block.text),
            link_density=self._link_density(block.text),
            has_data_content=block.type in _DATA_BLOCK_TYPES,
            dom_depth_penalty=self._dom_depth_penalty(block),
            semantic_tag_bonus=self._semantic_tag_bonus(block),
        )

    # ------------------------------------------------------------------
    # Individual feature computations
    # ------------------------------------------------------------------

    @staticmethod
    def _position_score(index: int, total: int) -> float:
        """1.0 for the first block, linear decay to 0.3 for the last."""
        if total <= 1:
            return 1.0
        return 1.0 - 0.7 * (index / (total - 1))

    @staticmethod
    def _entity_density(text: str) -> float:
        """Count numbers, dates, and capitalized words per character.

        Returns a value in roughly [0, 1] via a sigmoid squash so that
        very dense text does not blow up.
        """
        if not text:
            return 0.0
        count = (
            len(_NUMBER_RE.findall(text))
            + len(_DATE_RE.findall(text))
            + len(_CAPITALIZED_RE.findall(text))
        )
        raw = count / max(len(text), 1)
        # Sigmoid squash: maps raw density [0, inf) -> [0, 1)
        return 2.0 / (1.0 + math.exp(-raw * 100)) - 1.0

    @staticmethod
    def _text_length_score(text: str) -> float:
        """Sigmoid around 200 chars — medium paragraphs score highest."""
        length = len(text)
        return 1.0 / (1.0 + math.exp(-(length - 100) / 50))

    @staticmethod
    def _link_density(text: str) -> float:
        """Fraction of words that are URLs. High = likely navigation."""
        words = text.split()
        if not words:
            return 0.0
        url_count = len(_URL_RE.findall(text))
        return min(url_count / len(words), 1.0)

    @staticmethod
    def _heading_coverage(block: Block) -> float:
        """1.0 if block has a heading ancestor (section_path), 0.0 otherwise."""
        if block.type == BlockType.HEADING:
            return 1.0
        if block.section_path:
            return 1.0
        return 0.0

    @staticmethod
    def _in_main_content(block: Block) -> bool:
        """Heuristic: check provenance DOM path for main/article tags."""
        if block.provenance and block.provenance.dom:
            path = block.provenance.dom.dom_path.lower()
            if "main" in path or "article" in path:
                return True
        return False

    @staticmethod
    def _dom_depth_penalty(block: Block) -> float:
        """max(0, 1 - depth/20). Depth estimated from DOM path segments."""
        if block.provenance and block.provenance.dom:
            depth = block.provenance.dom.dom_path.count(">")
            return max(0.0, 1.0 - depth / 20.0)
        return 1.0  # No provenance -> no penalty

    @staticmethod
    def _semantic_tag_bonus(block: Block) -> float:
        """Bonus for blocks inside semantic elements (main, article, section)."""
        if block.provenance and block.provenance.dom:
            path = block.provenance.dom.dom_path.lower()
            bonus = 0.0
            for tag in _SEMANTIC_TAGS:
                if tag in path:
                    bonus += 0.3
            return min(bonus, 1.0)
        return 0.0

    # ------------------------------------------------------------------
    # Combination
    # ------------------------------------------------------------------

    def _combine(self, f: SalienceFeatures) -> float:
        """Weighted combination of feature groups, clipped to [0, 1]."""
        w = self.weights

        block_type = f.block_type_weight
        position = f.position_score
        content_richness = (
            f.text_length_score * 0.4
            + f.entity_density * 0.3
            + (1.0 - f.link_density) * 0.3
        )
        structural = (
            f.heading_coverage * 0.4
            + f.dom_depth_penalty * 0.3
            + (1.0 if f.has_data_content else 0.0) * 0.3
        )
        context = (
            (1.0 if f.in_main_content else 0.0) * 0.5
            + f.semantic_tag_bonus * 0.5
        )

        raw = (
            w.get("block_type", 0.25) * block_type
            + w.get("position", 0.15) * position
            + w.get("content_richness", 0.20) * content_richness
            + w.get("structural", 0.20) * structural
            + w.get("context", 0.20) * context
        )
        return max(0.0, min(1.0, raw))
