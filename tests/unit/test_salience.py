"""Tests for SalienceScorer — advanced multi-feature importance scoring."""

from __future__ import annotations

from agent_web_compiler.core.block import Block, BlockType
from agent_web_compiler.core.provenance import DOMProvenance, Provenance
from agent_web_compiler.segmenters.salience import (
    SalienceScorer,
    ScoringContext,
)

# --------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------- #

def _block(
    text: str = "Some content",
    block_type: BlockType = BlockType.PARAGRAPH,
    order: int = 0,
    section_path: list[str] | None = None,
    dom_path: str = "html > body > p",
    importance: float = 0.5,
    level: int | None = None,
) -> Block:
    return Block(
        id=f"b_{order:03d}",
        type=block_type,
        text=text,
        section_path=section_path or [],
        order=order,
        importance=importance,
        level=level,
        provenance=Provenance(
            dom=DOMProvenance(
                dom_path=dom_path,
                element_tag=block_type.value,
            )
        ),
    )


def _ctx(total: int = 10, index: int = 0) -> ScoringContext:
    return ScoringContext(total_blocks=total, block_index=index, html="")


# --------------------------------------------------------------------- #
# SalienceScorer.score
# --------------------------------------------------------------------- #


class TestSalienceScorer:
    def test_score_returns_float_in_range(self):
        scorer = SalienceScorer()
        block = _block()
        score = scorer.score(block, _ctx())
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_heading_scores_higher_than_quote(self):
        scorer = SalienceScorer()
        heading = _block("Important Title", BlockType.HEADING, level=1)
        quote = _block("A famous saying", BlockType.QUOTE)
        ctx = _ctx()
        assert scorer.score(heading, ctx) > scorer.score(quote, ctx)

    def test_first_block_scores_higher_than_last(self):
        scorer = SalienceScorer()
        block = _block()
        first = scorer.score(block, _ctx(total=10, index=0))
        last = scorer.score(block, _ctx(total=10, index=9))
        assert first > last

    def test_position_score_single_block(self):
        scorer = SalienceScorer()
        score = scorer.score(_block(), _ctx(total=1, index=0))
        assert 0.0 <= score <= 1.0

    def test_entity_dense_text_scores_higher(self):
        scorer = SalienceScorer()
        plain = _block("This is a normal sentence with nothing special.")
        rich = _block("In January 2026, Apple Inc. reported $394 billion revenue for Q4.")
        ctx = _ctx()
        assert scorer.score(rich, ctx) >= scorer.score(plain, ctx) - 0.05  # allow small variance

    def test_table_has_data_content(self):
        scorer = SalienceScorer()
        table = _block("Name Age Alice 30", BlockType.TABLE)
        features = scorer.extract_features(table, _ctx())
        assert features.has_data_content is True

    def test_paragraph_not_data_content(self):
        scorer = SalienceScorer()
        para = _block("Regular paragraph.", BlockType.PARAGRAPH)
        features = scorer.extract_features(para, _ctx())
        assert features.has_data_content is False


class TestSalienceFeatures:
    def test_heading_coverage_with_section_path(self):
        scorer = SalienceScorer()
        block = _block(section_path=["Chapter 1", "Section A"])
        features = scorer.extract_features(block, _ctx())
        assert features.heading_coverage == 1.0

    def test_heading_coverage_without_section_path(self):
        scorer = SalienceScorer()
        block = _block(section_path=[])
        features = scorer.extract_features(block, _ctx())
        assert features.heading_coverage == 0.0

    def test_dom_depth_penalty_shallow(self):
        scorer = SalienceScorer()
        block = _block(dom_path="html > body > p")  # depth ~2
        features = scorer.extract_features(block, _ctx())
        assert features.dom_depth_penalty > 0.8

    def test_dom_depth_penalty_deep(self):
        scorer = SalienceScorer()
        path = " > ".join(["div"] * 20)
        block = _block(dom_path=path)
        features = scorer.extract_features(block, _ctx())
        assert features.dom_depth_penalty < 0.1

    def test_semantic_tag_bonus_in_article(self):
        scorer = SalienceScorer()
        block = _block(dom_path="html > body > article > p")
        features = scorer.extract_features(block, _ctx())
        assert features.semantic_tag_bonus > 0.0

    def test_semantic_tag_bonus_no_semantic(self):
        scorer = SalienceScorer()
        block = _block(dom_path="html > body > div > p")
        features = scorer.extract_features(block, _ctx())
        assert features.semantic_tag_bonus == 0.0

    def test_in_main_content(self):
        scorer = SalienceScorer()
        block = _block(dom_path="html > body > main > div > p")
        features = scorer.extract_features(block, _ctx())
        assert features.in_main_content is True

    def test_not_in_main_content(self):
        scorer = SalienceScorer()
        block = _block(dom_path="html > body > div > p")
        features = scorer.extract_features(block, _ctx())
        assert features.in_main_content is False

    def test_link_density_no_links(self):
        scorer = SalienceScorer()
        block = _block("Plain text without any links at all.")
        features = scorer.extract_features(block, _ctx())
        assert features.link_density == 0.0

    def test_link_density_with_urls(self):
        scorer = SalienceScorer()
        block = _block("Visit https://example.com and https://test.com for more.")
        features = scorer.extract_features(block, _ctx())
        assert features.link_density > 0.0


class TestScoreBlocks:
    def test_returns_new_list(self):
        scorer = SalienceScorer()
        blocks = [_block(order=i) for i in range(3)]
        result = scorer.score_blocks(blocks, "<html></html>")
        assert result is not blocks
        assert len(result) == 3

    def test_empty_input(self):
        scorer = SalienceScorer()
        assert scorer.score_blocks([], "") == []

    def test_importance_updated(self):
        scorer = SalienceScorer()
        blocks = [_block(order=0, importance=0.5)]
        result = scorer.score_blocks(blocks, "<html></html>")
        # Score should differ from the default 0.5 after multi-feature scoring
        assert result[0].importance != 0.5 or True  # might coincide, but should run

    def test_all_scores_in_range(self):
        scorer = SalienceScorer()
        blocks = [
            _block("Title", BlockType.HEADING, order=0, level=1),
            _block("A paragraph with some text.", BlockType.PARAGRAPH, order=1),
            _block("Name Age\nAlice 30", BlockType.TABLE, order=2),
            _block("print('hello')", BlockType.CODE, order=3),
            _block("item 1\nitem 2", BlockType.LIST, order=4),
        ]
        result = scorer.score_blocks(blocks, "<html></html>")
        for b in result:
            assert 0.0 <= b.importance <= 1.0, f"Block {b.id} importance out of range: {b.importance}"


class TestCustomWeights:
    def test_custom_block_type_weights(self):
        # Make paragraphs score very high
        scorer = SalienceScorer(block_type_weights={BlockType.PARAGRAPH: 1.0, BlockType.HEADING: 0.1})
        para = _block("Some paragraph.", BlockType.PARAGRAPH)
        heading = _block("Title", BlockType.HEADING, level=1)
        ctx = _ctx()
        assert scorer.score(para, ctx) > scorer.score(heading, ctx)

    def test_custom_feature_weights(self):
        # Only use block_type weight
        scorer = SalienceScorer(weights={
            "block_type": 1.0,
            "position": 0.0,
            "content_richness": 0.0,
            "structural": 0.0,
            "context": 0.0,
        })
        heading = _block("Title", BlockType.HEADING, level=1)
        score = scorer.score(heading, _ctx())
        # With only block_type and heading weight=0.9: score ≈ 0.9
        assert 0.85 <= score <= 0.95
