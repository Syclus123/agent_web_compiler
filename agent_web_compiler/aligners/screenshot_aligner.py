"""Screenshot and accessibility tree alignment for visual provenance.

Provides bbox provenance and screenshot region mapping for blocks/actions
when browser rendering is used.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from agent_web_compiler.core.action import Action
from agent_web_compiler.core.block import Block
from agent_web_compiler.core.provenance import ScreenshotProvenance


@dataclass
class BBoxRegion:
    """A bounding box region on a screenshot."""

    region_id: str
    x: float
    y: float
    width: float
    height: float
    label: str = ""

    @property
    def bbox(self) -> list[float]:
        """Return [x1, y1, x2, y2] format."""
        return [self.x, self.y, self.x + self.width, self.y + self.height]


@dataclass
class AccessibilityNode:
    """A node from the accessibility tree."""

    role: str
    name: str = ""
    value: str = ""
    description: str = ""
    children: list[AccessibilityNode] = field(default_factory=list)
    bbox: list[float] | None = None  # [x, y, width, height]

    def flatten(self) -> list[AccessibilityNode]:
        """Flatten the tree into a list of nodes."""
        result = [self]
        for child in self.children:
            result.extend(child.flatten())
        return result


def parse_ax_tree(raw_tree: dict | None) -> AccessibilityNode | None:
    """Parse a raw accessibility tree dict (from Playwright) into AccessibilityNode.

    Args:
        raw_tree: Raw dict from page.accessibility.snapshot()

    Returns:
        Root AccessibilityNode, or None if input is None/empty.
    """
    if not raw_tree:
        return None

    children = []
    for child_data in raw_tree.get("children", []):
        child = parse_ax_tree(child_data)
        if child is not None:
            children.append(child)

    return AccessibilityNode(
        role=raw_tree.get("role", "unknown"),
        name=raw_tree.get("name", ""),
        value=raw_tree.get("value", ""),
        description=raw_tree.get("description", ""),
        children=children,
        bbox=raw_tree.get("bbox"),
    )


class ScreenshotAligner:
    """Aligns blocks and actions with screenshot regions using bounding boxes.

    Requires element position data from browser rendering (Playwright).
    Uses the accessibility tree to match blocks to visual regions.
    """

    def align_with_screenshot(
        self,
        blocks: list[Block],
        actions: list[Action],
        element_positions: dict[str, list[float]],
        screenshot_size: tuple[int, int] | None = None,
    ) -> tuple[list[Block], list[Action]]:
        """Align blocks and actions with screenshot bounding boxes.

        Args:
            blocks: Semantic blocks to align.
            actions: Actions to align.
            element_positions: Mapping of CSS selector -> [x, y, width, height].
            screenshot_size: (width, height) of the screenshot in pixels.

        Returns:
            Tuple of (aligned_blocks, aligned_actions).
        """
        for block in blocks:
            if block.provenance and block.provenance.dom:
                dom_path = block.provenance.dom.dom_path
                bbox = element_positions.get(dom_path)
                if bbox and len(bbox) == 4:
                    region_id = self._make_region_id(f"block_{block.id}")
                    block.provenance.screenshot = ScreenshotProvenance(
                        screenshot_region_id=region_id,
                        screenshot_bbox=[bbox[0], bbox[1], bbox[0] + bbox[2], bbox[1] + bbox[3]],
                    )

        for action in actions:
            if action.provenance and action.provenance.dom:
                selector = action.selector or action.provenance.dom.dom_path
                bbox = element_positions.get(selector)
                if bbox and len(bbox) == 4:
                    region_id = self._make_region_id(f"action_{action.id}")
                    action.provenance.screenshot = ScreenshotProvenance(
                        screenshot_region_id=region_id,
                        screenshot_bbox=[bbox[0], bbox[1], bbox[0] + bbox[2], bbox[1] + bbox[3]],
                    )

        return blocks, actions

    def align_with_ax_tree(
        self,
        blocks: list[Block],
        ax_tree: AccessibilityNode,
    ) -> list[Block]:
        """Enrich blocks with accessibility tree information.

        Matches blocks to AX tree nodes by text content similarity.

        Args:
            blocks: Blocks to enrich.
            ax_tree: Parsed accessibility tree.

        Returns:
            Blocks with enriched metadata.
        """
        flat_nodes = ax_tree.flatten()
        node_texts = {node.name.lower().strip(): node for node in flat_nodes if node.name}

        for block in blocks:
            block_text_lower = block.text[:100].lower().strip()
            # Try exact prefix match
            matched_node = node_texts.get(block_text_lower)

            if matched_node is None:
                # Try partial match
                for name, node in node_texts.items():
                    if name and block_text_lower.startswith(name[:50]):
                        matched_node = node
                        break

            if matched_node:
                block.metadata["ax_role"] = matched_node.role
                if matched_node.bbox:
                    block.metadata["ax_bbox"] = matched_node.bbox

        return blocks

    @staticmethod
    def _make_region_id(prefix: str) -> str:
        """Generate a short region ID."""
        return f"r_{hashlib.md5(prefix.encode()).hexdigest()[:8]}"
