"""Tests for DocumentValidator."""

from __future__ import annotations

import pytest

from agent_web_compiler.core.action import Action, ActionType
from agent_web_compiler.core.block import Block, BlockType
from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.pipeline.validator import DocumentValidator


@pytest.fixture
def validator() -> DocumentValidator:
    return DocumentValidator()


@pytest.fixture
def config() -> CompileConfig:
    return CompileConfig()


def _make_block(
    text: str,
    block_type: BlockType = BlockType.PARAGRAPH,
    importance: float = 0.5,
    level: int | None = None,
    order: int = 0,
) -> Block:
    return Block(
        id=f"b_{order:03d}",
        type=block_type,
        text=text,
        importance=importance,
        level=level,
        order=order,
    )


def _make_action(action_id: str = "a_001_click") -> Action:
    return Action(
        id=action_id,
        type=ActionType.CLICK,
        label="Click me",
        selector="#btn",
    )


class TestDocumentValidator:
    # ---- Empty block removal ----

    def test_removes_empty_blocks(self, validator, config):
        blocks = [
            _make_block("Real content", order=0),
            _make_block("", order=1),
            _make_block("   ", order=2),
            _make_block("Also real", order=3),
        ]
        result_blocks, _, _ = validator.validate(blocks, [], "<html>content</html>", config)
        assert len(result_blocks) == 2
        assert all(b.text.strip() for b in result_blocks)

    # ---- Duplicate detection ----

    def test_warns_on_duplicate_blocks(self, validator, config):
        blocks = [
            _make_block("Same text", order=0),
            _make_block("Same text", order=1),
            _make_block("Different text", order=2),
        ]
        _, _, quality = validator.validate(blocks, [], "<html>content</html>", config)
        dup_warnings = [w for w in quality.warnings if w.startswith("duplicate_blocks:")]
        assert len(dup_warnings) == 1
        assert "duplicate_blocks:1" in dup_warnings[0]

    def test_no_duplicate_warning_when_unique(self, validator, config):
        blocks = [
            _make_block("Text A", order=0),
            _make_block("Text B", order=1),
            _make_block("Text C", order=2),
        ]
        _, _, quality = validator.validate(blocks, [], "<html>content</html>", config)
        dup_warnings = [w for w in quality.warnings if w.startswith("duplicate_blocks:")]
        assert len(dup_warnings) == 0

    # ---- Warning: no_headings_found ----

    def test_warns_no_headings(self, validator, config):
        blocks = [
            _make_block("Paragraph one", order=0),
            _make_block("Paragraph two", order=1),
            _make_block("Paragraph three", order=2),
        ]
        _, _, quality = validator.validate(blocks, [], "<html>content</html>", config)
        assert "no_headings_found" in quality.warnings

    def test_no_heading_warning_when_heading_present(self, validator, config):
        blocks = [
            _make_block("Title", block_type=BlockType.HEADING, level=1, order=0),
            _make_block("Body text", order=1),
            _make_block("More text", order=2),
        ]
        _, _, quality = validator.validate(blocks, [], "<html>content</html>", config)
        assert "no_headings_found" not in quality.warnings

    # ---- Warning: low_block_count ----

    def test_warns_low_block_count(self, validator, config):
        blocks = [_make_block("Only one", order=0)]
        _, _, quality = validator.validate(blocks, [], "<html>content</html>", config)
        assert "low_block_count" in quality.warnings

    def test_no_low_block_warning_when_enough(self, validator, config):
        blocks = [
            _make_block("A", order=0),
            _make_block("B", order=1),
            _make_block("C", order=2),
        ]
        _, _, quality = validator.validate(blocks, [], "<html>content</html>", config)
        assert "low_block_count" not in quality.warnings

    # ---- Warning: high_noise_ratio ----

    def test_warns_high_noise_ratio(self, validator, config):
        blocks = [_make_block("Content", order=0)]
        actions = [_make_action(f"a_{i:03d}_click") for i in range(10)]
        _, _, quality = validator.validate(blocks, actions, "<html>content</html>", config)
        assert "high_noise_ratio" in quality.warnings

    def test_no_noise_warning_when_balanced(self, validator, config):
        blocks = [_make_block(f"Block {i}", order=i) for i in range(5)]
        actions = [_make_action(f"a_{i:03d}_click") for i in range(3)]
        _, _, quality = validator.validate(blocks, actions, "<html>content</html>", config)
        assert "high_noise_ratio" not in quality.warnings

    # ---- Warning: no_main_content ----

    def test_warns_no_main_content(self, validator, config):
        blocks = [
            _make_block("Low importance", importance=0.1, order=0),
            _make_block("Also low", importance=0.2, order=1),
            _make_block("Still low", importance=0.3, order=2),
        ]
        _, _, quality = validator.validate(blocks, [], "<html>content</html>", config)
        assert "no_main_content" in quality.warnings

    def test_no_main_content_warning_when_important_blocks_exist(self, validator, config):
        blocks = [
            _make_block("Important", importance=0.8, order=0),
            _make_block("Also fine", importance=0.6, order=1),
            _make_block("Less important", importance=0.3, order=2),
        ]
        _, _, quality = validator.validate(blocks, [], "<html>content</html>", config)
        assert "no_main_content" not in quality.warnings

    # ---- Parse confidence scoring ----

    def test_confidence_zero_for_no_blocks(self, validator, config):
        _, _, quality = validator.validate([], [], "<html></html>", config)
        assert quality.parse_confidence == pytest.approx(0.0, abs=0.01)

    def test_confidence_increases_with_blocks(self, validator, config):
        blocks = [_make_block("Some text", order=0)]
        _, _, quality = validator.validate(blocks, [], "<html>Some text</html>", config)
        assert quality.parse_confidence >= 0.3

    def test_confidence_increases_with_headings(self, validator, config):
        blocks_no_heading = [
            _make_block("Text A", importance=0.8, order=0),
            _make_block("Text B", importance=0.8, order=1),
            _make_block("Text C", importance=0.8, order=2),
        ]
        blocks_with_heading = [
            _make_block("Title", block_type=BlockType.HEADING, level=1, importance=0.8, order=0),
            _make_block("Text B", importance=0.8, order=1),
            _make_block("Text C", importance=0.8, order=2),
        ]
        html = "<html>" + "x" * 100 + "</html>"
        _, _, q_no = validator.validate(blocks_no_heading, [], html, config)
        _, _, q_yes = validator.validate(blocks_with_heading, [], html, config)
        assert q_yes.parse_confidence > q_no.parse_confidence

    def test_confidence_clamped_to_one(self, validator, config):
        # Large text relative to HTML — ensure confidence doesn't exceed 1.0
        blocks = [
            _make_block("Title", block_type=BlockType.HEADING, level=1, importance=0.8, order=0),
            _make_block("A" * 500, importance=0.8, order=1),
            _make_block("B" * 500, importance=0.8, order=2),
        ]
        _, _, quality = validator.validate(blocks, [], "<html>short</html>", config)
        assert quality.parse_confidence <= 1.0

    # ---- Quality object fields ----

    def test_quality_block_and_action_counts(self, validator, config):
        blocks = [_make_block(f"B{i}", order=i) for i in range(5)]
        actions = [_make_action(f"a_{i:03d}_click") for i in range(3)]
        _, _, quality = validator.validate(blocks, actions, "<html>content</html>", config)
        assert quality.block_count == 5
        assert quality.action_count == 3

    def test_actions_passed_through(self, validator, config):
        blocks = [_make_block("Content", order=0)]
        actions = [_make_action("a_001_click")]
        _, result_actions, _ = validator.validate(blocks, actions, "<html>content</html>", config)
        assert len(result_actions) == 1
        assert result_actions[0].id == "a_001_click"

    # ---- Empty input ----

    def test_empty_blocks_list(self, validator, config):
        blocks, actions, quality = validator.validate([], [], "<html></html>", config)
        assert blocks == []
        assert actions == []
        assert quality.block_count == 0
        assert "low_block_count" in quality.warnings
