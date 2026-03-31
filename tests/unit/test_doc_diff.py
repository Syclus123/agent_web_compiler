"""Tests for document diff — semantic change detection between AgentDocuments."""

from __future__ import annotations

from agent_web_compiler.core.action import Action, ActionType
from agent_web_compiler.core.block import Block, BlockType
from agent_web_compiler.core.document import AgentDocument, SourceType
from agent_web_compiler.utils.doc_diff import (
    ActionChange,
    BlockChange,
    DocumentDiff,
    diff_documents,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc(
    title: str = "Test Page",
    blocks: list[Block] | None = None,
    actions: list[Action] | None = None,
) -> AgentDocument:
    return AgentDocument(
        doc_id="sha256:test",
        source_type=SourceType.HTML,
        title=title,
        blocks=blocks or [],
        actions=actions or [],
    )


def _block(id: str, btype: BlockType, text: str, section_path: list[str] | None = None) -> Block:
    return Block(id=id, type=btype, text=text, section_path=section_path or [])


def _action(id: str, atype: ActionType, label: str, selector: str | None = None) -> Action:
    return Action(id=id, type=atype, label=label, selector=selector)


# ---------------------------------------------------------------------------
# No changes
# ---------------------------------------------------------------------------


class TestDiffNoChanges:
    def test_identical_documents(self):
        blocks = [_block("b1", BlockType.PARAGRAPH, "Hello world")]
        old = _make_doc(blocks=blocks)
        new = _make_doc(blocks=blocks)
        diff = diff_documents(old, new)
        assert not diff.has_changes

    def test_empty_documents(self):
        diff = diff_documents(_make_doc(), _make_doc())
        assert not diff.has_changes


# ---------------------------------------------------------------------------
# Title changes
# ---------------------------------------------------------------------------


class TestDiffTitleChange:
    def test_title_changed(self):
        old = _make_doc(title="Old Title")
        new = _make_doc(title="New Title")
        diff = diff_documents(old, new)
        assert diff.title_changed
        assert diff.old_title == "Old Title"
        assert diff.new_title == "New Title"
        assert diff.has_changes


# ---------------------------------------------------------------------------
# Block changes
# ---------------------------------------------------------------------------


class TestDiffBlockChanges:
    def test_block_added(self):
        old = _make_doc(blocks=[_block("b1", BlockType.PARAGRAPH, "First")])
        new = _make_doc(
            blocks=[
                _block("b1", BlockType.PARAGRAPH, "First"),
                _block("b2", BlockType.PARAGRAPH, "Second"),
            ]
        )
        diff = diff_documents(old, new)
        assert len(diff.blocks_added) == 1
        assert diff.blocks_added[0].new_text == "Second"
        assert diff.blocks_added[0].change_type == "added"

    def test_block_removed(self):
        old = _make_doc(
            blocks=[
                _block("b1", BlockType.PARAGRAPH, "First"),
                _block("b2", BlockType.PARAGRAPH, "Second"),
            ]
        )
        new = _make_doc(blocks=[_block("b1", BlockType.PARAGRAPH, "First")])
        diff = diff_documents(old, new)
        assert len(diff.blocks_removed) == 1
        assert diff.blocks_removed[0].old_text == "Second"
        assert diff.blocks_removed[0].change_type == "removed"

    def test_block_modified(self):
        old = _make_doc(
            blocks=[_block("b1", BlockType.PARAGRAPH, "The price is $299.99 for this item")]
        )
        new = _make_doc(
            blocks=[_block("b1", BlockType.PARAGRAPH, "The price is $249.99 for this item")]
        )
        diff = diff_documents(old, new)
        assert len(diff.blocks_modified) == 1
        assert diff.blocks_modified[0].old_text == "The price is $299.99 for this item"
        assert diff.blocks_modified[0].new_text == "The price is $249.99 for this item"

    def test_completely_different_blocks(self):
        old = _make_doc(blocks=[_block("b1", BlockType.PARAGRAPH, "Alpha")])
        new = _make_doc(blocks=[_block("b2", BlockType.PARAGRAPH, "Zeta")])
        diff = diff_documents(old, new)
        # "Alpha" and "Zeta" are too dissimilar to match
        assert len(diff.blocks_removed) == 1
        assert len(diff.blocks_added) == 1
        assert len(diff.blocks_modified) == 0

    def test_section_path_preserved_on_changes(self):
        old = _make_doc(
            blocks=[_block("b1", BlockType.HEADING, "Summer Collection", section_path=["Shop"])]
        )
        new = _make_doc(blocks=[])
        diff = diff_documents(old, new)
        assert diff.blocks_removed[0].section_path == ["Shop"]


# ---------------------------------------------------------------------------
# Action changes
# ---------------------------------------------------------------------------


class TestDiffActionChanges:
    def test_action_added(self):
        old = _make_doc()
        new = _make_doc(
            actions=[_action("a1", ActionType.CLICK, "Checkout", selector=".btn-checkout")]
        )
        diff = diff_documents(old, new)
        assert len(diff.actions_added) == 1
        assert diff.actions_added[0].label == "Checkout"

    def test_action_removed(self):
        old = _make_doc(
            actions=[_action("a1", ActionType.CLICK, "Delete", selector=".btn-delete")]
        )
        new = _make_doc()
        diff = diff_documents(old, new)
        assert len(diff.actions_removed) == 1
        assert diff.actions_removed[0].label == "Delete"

    def test_action_modified(self):
        old = _make_doc(
            actions=[_action("a1", ActionType.CLICK, "Add to Cart", selector=".btn-cart")]
        )
        new = _make_doc(
            actions=[_action("a2", ActionType.CLICK, "Add to Bag", selector=".btn-cart")]
        )
        diff = diff_documents(old, new)
        assert len(diff.actions_modified) == 1
        assert diff.actions_modified[0].old_state["label"] == "Add to Cart"
        assert diff.actions_modified[0].new_state["label"] == "Add to Bag"

    def test_matching_actions_no_change(self):
        actions = [_action("a1", ActionType.CLICK, "Buy", selector=".buy")]
        old = _make_doc(actions=actions)
        new = _make_doc(actions=actions)
        diff = diff_documents(old, new)
        assert len(diff.actions_added) == 0
        assert len(diff.actions_removed) == 0
        assert len(diff.actions_modified) == 0


# ---------------------------------------------------------------------------
# DocumentDiff methods
# ---------------------------------------------------------------------------


class TestDocumentDiffMethods:
    def test_summary_no_changes(self):
        diff = DocumentDiff()
        assert diff.summary() == "No changes detected."

    def test_summary_with_changes(self):
        diff = DocumentDiff(
            title_changed=True,
            old_title="Product Page",
            new_title="Product Page (Updated)",
            blocks_added=[
                BlockChange(
                    change_type="added",
                    block_id="b3",
                    new_text="Holiday Sale section",
                    section_path=["Holiday Sale"],
                )
            ],
            blocks_removed=[
                BlockChange(
                    change_type="removed",
                    block_id="b2",
                    old_text="Summer Collection items",
                    section_path=["Summer Collection"],
                )
            ],
            blocks_modified=[
                BlockChange(
                    change_type="modified",
                    block_id="b1",
                    old_text="$299.99",
                    new_text="$249.99",
                )
            ],
            actions_added=[
                ActionChange(
                    change_type="added",
                    action_id="a2",
                    label="checkout",
                )
            ],
        )
        summary = diff.summary()
        assert "Product Page" in summary
        assert "Updated" in summary
        assert "+1 blocks added" in summary
        assert "-1 removed" in summary
        assert "1 modified" in summary
        assert "checkout" in summary
        assert "[added]" in summary
        assert "[removed]" in summary
        assert "[modified]" in summary

    def test_to_dict(self):
        diff = DocumentDiff(
            title_changed=True,
            old_title="A",
            new_title="B",
            blocks_added=[
                BlockChange(change_type="added", block_id="b1", new_text="new")
            ],
        )
        d = diff.to_dict()
        assert d["title_changed"] is True
        assert d["old_title"] == "A"
        assert d["new_title"] == "B"
        assert d["has_changes"] is True
        assert len(d["blocks_added"]) == 1
        assert d["blocks_added"][0]["block_id"] == "b1"

    def test_has_changes_false(self):
        assert not DocumentDiff().has_changes

    def test_has_changes_true_title(self):
        assert DocumentDiff(title_changed=True, old_title="A", new_title="B").has_changes

    def test_has_changes_true_blocks(self):
        diff = DocumentDiff(
            blocks_added=[BlockChange(change_type="added", block_id="b1")]
        )
        assert diff.has_changes


# ---------------------------------------------------------------------------
# Complex scenarios
# ---------------------------------------------------------------------------


class TestDiffComplexScenarios:
    def test_full_page_update(self):
        """Simulate a page that changes price, adds a block, removes a block."""
        old = _make_doc(
            title="Product Page",
            blocks=[
                _block("b1", BlockType.HEADING, "ErgoDesk Pro"),
                _block("b2", BlockType.PARAGRAPH, "Price: $299.99"),
                _block("b3", BlockType.PARAGRAPH, "Summer sale ends soon!"),
            ],
            actions=[
                _action("a1", ActionType.CLICK, "Add to Cart", selector=".add-cart"),
            ],
        )
        new = _make_doc(
            title="Product Page (Updated)",
            blocks=[
                _block("b1", BlockType.HEADING, "ErgoDesk Pro"),
                _block("b2", BlockType.PARAGRAPH, "Price: $249.99"),
                _block("b4", BlockType.PARAGRAPH, "Holiday special!"),
            ],
            actions=[
                _action("a1", ActionType.CLICK, "Add to Cart", selector=".add-cart"),
                _action("a2", ActionType.CLICK, "Express Checkout", selector=".express"),
            ],
        )
        diff = diff_documents(old, new)
        assert diff.title_changed
        assert len(diff.blocks_modified) == 1  # price changed
        assert len(diff.blocks_removed) == 1  # summer sale removed
        assert len(diff.blocks_added) == 1  # holiday special added
        assert len(diff.actions_added) == 1  # express checkout added
        assert diff.actions_added[0].label == "Express Checkout"
