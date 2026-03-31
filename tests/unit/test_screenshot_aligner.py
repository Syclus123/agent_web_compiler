"""Tests for screenshot alignment and accessibility tree."""

from __future__ import annotations

from agent_web_compiler.aligners.screenshot_aligner import (
    AccessibilityNode,
    BBoxRegion,
    ScreenshotAligner,
    parse_ax_tree,
)
from agent_web_compiler.core.action import Action, ActionType
from agent_web_compiler.core.block import Block, BlockType
from agent_web_compiler.core.provenance import DOMProvenance, Provenance


class TestBBoxRegion:
    def test_bbox_property(self):
        region = BBoxRegion(region_id="r_001", x=10, y=20, width=100, height=50)
        assert region.bbox == [10, 20, 110, 70]

    def test_label(self):
        region = BBoxRegion(region_id="r_002", x=0, y=0, width=50, height=50, label="button")
        assert region.label == "button"


class TestAccessibilityNode:
    def test_flatten_single_node(self):
        node = AccessibilityNode(role="heading", name="Title")
        assert len(node.flatten()) == 1

    def test_flatten_nested(self):
        child1 = AccessibilityNode(role="text", name="Hello")
        child2 = AccessibilityNode(role="link", name="Click")
        parent = AccessibilityNode(role="main", name="", children=[child1, child2])
        flat = parent.flatten()
        assert len(flat) == 3

    def test_flatten_deep_nesting(self):
        deep = AccessibilityNode(role="text", name="deep")
        mid = AccessibilityNode(role="div", name="", children=[deep])
        root = AccessibilityNode(role="main", name="", children=[mid])
        flat = root.flatten()
        assert len(flat) == 3
        assert flat[-1].name == "deep"


class TestParseAxTree:
    def test_none_input(self):
        assert parse_ax_tree(None) is None

    def test_empty_dict(self):
        result = parse_ax_tree({})
        # Empty dict has no 'role' key, so depends on implementation
        # It may return a node with role="unknown" or None
        # Just verify it doesn't crash
        assert result is None or result.role == "unknown"

    def test_simple_tree(self):
        raw = {
            "role": "WebArea",
            "name": "Test Page",
            "children": [
                {"role": "heading", "name": "Title", "children": []},
                {"role": "text", "name": "Hello world"},
            ],
        }
        node = parse_ax_tree(raw)
        assert node is not None
        assert node.role == "WebArea"
        assert node.name == "Test Page"
        assert len(node.children) == 2

    def test_with_bbox(self):
        raw = {"role": "button", "name": "Click", "bbox": [10, 20, 100, 40]}
        node = parse_ax_tree(raw)
        assert node is not None
        assert node.bbox == [10, 20, 100, 40]


class TestScreenshotAligner:
    def _make_block(self, block_id: str, text: str, dom_path: str) -> Block:
        return Block(
            id=block_id,
            type=BlockType.PARAGRAPH,
            text=text,
            order=0,
            provenance=Provenance(
                dom=DOMProvenance(dom_path=dom_path, element_tag="p")
            ),
        )

    def _make_action(self, action_id: str, label: str, selector: str) -> Action:
        return Action(
            id=action_id,
            type=ActionType.CLICK,
            label=label,
            selector=selector,
            provenance=Provenance(
                dom=DOMProvenance(dom_path=selector, element_tag="button")
            ),
        )

    def test_align_blocks_with_positions(self):
        aligner = ScreenshotAligner()
        block = self._make_block("b_001", "Hello", "body > p")
        positions = {"body > p": [10, 20, 200, 50]}

        aligned, _ = aligner.align_with_screenshot([block], [], positions)
        assert len(aligned) == 1
        assert aligned[0].provenance.screenshot is not None
        assert aligned[0].provenance.screenshot.screenshot_region_id.startswith("r_")

    def test_align_actions_with_positions(self):
        aligner = ScreenshotAligner()
        action = self._make_action("a_001", "Click", "#btn")
        positions = {"#btn": [50, 100, 80, 30]}

        _, aligned = aligner.align_with_screenshot([], [action], positions)
        assert len(aligned) == 1
        assert aligned[0].provenance.screenshot is not None

    def test_missing_position_skipped(self):
        aligner = ScreenshotAligner()
        block = self._make_block("b_001", "Hello", "body > p")
        positions = {}  # No positions

        aligned, _ = aligner.align_with_screenshot([block], [], positions)
        assert aligned[0].provenance.screenshot is None

    def test_align_with_ax_tree(self):
        aligner = ScreenshotAligner()
        block = self._make_block("b_001", "Introduction to ML", "body > p")
        ax_tree = AccessibilityNode(
            role="main",
            name="",
            children=[
                AccessibilityNode(role="heading", name="Introduction to ML", bbox=[0, 0, 500, 30]),
            ],
        )

        aligned = aligner.align_with_ax_tree([block], ax_tree)
        assert aligned[0].metadata.get("ax_role") == "heading"
