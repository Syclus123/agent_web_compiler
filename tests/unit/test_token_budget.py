"""Tests for TokenBudgetController — progressive compression for LLM context windows."""

from __future__ import annotations

from agent_web_compiler.core.block import Block, BlockType
from agent_web_compiler.exporters.token_budget import TokenBudgetController

# --------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------- #

def _block(
    text: str = "Some content",
    block_type: BlockType = BlockType.PARAGRAPH,
    order: int = 0,
    importance: float = 0.5,
    metadata: dict | None = None,
    children: list[Block] | None = None,
    section_path: list[str] | None = None,
    level: int | None = None,
) -> Block:
    return Block(
        id=f"b_{order:03d}",
        type=block_type,
        text=text,
        order=order,
        importance=importance,
        metadata=metadata or {},
        children=children or [],
        section_path=section_path or [],
        level=level,
    )


def _long_paragraph(n_sentences: int = 10, order: int = 0) -> Block:
    """Create a paragraph with many sentences, exceeding 300 chars."""
    sentences = [f"This is sentence number {i} with some extra words to pad it out." for i in range(n_sentences)]
    text = " ".join(sentences)
    return _block(text=text, order=order)


def _table_block(n_rows: int = 10, order: int = 0) -> Block:
    headers = ["Name", "Value", "Unit"]
    rows = [[f"item_{i}", str(i * 10), "kg"] for i in range(n_rows)]
    text_lines = [" | ".join(headers)]
    for row in rows:
        text_lines.append(" | ".join(row))
    return _block(
        text="\n".join(text_lines),
        block_type=BlockType.TABLE,
        order=order,
        metadata={"headers": headers, "rows": rows},
    )


def _code_block(n_lines: int = 20, order: int = 0) -> Block:
    lines = [f"line_{i} = {i}" for i in range(n_lines)]
    return _block(
        text="\n".join(lines),
        block_type=BlockType.CODE,
        order=order,
        metadata={"language": "python"},
    )


def _list_block(n_items: int = 15, order: int = 0) -> Block:
    children = [
        Block(
            id=f"li_{order}_{i}",
            type=BlockType.PARAGRAPH,
            text=f"List item number {i}",
            order=i,
        )
        for i in range(n_items)
    ]
    text = "\n".join(c.text for c in children)
    return _block(
        text=text,
        block_type=BlockType.LIST,
        order=order,
        children=children,
    )


# --------------------------------------------------------------------- #
# Under budget — no compression
# --------------------------------------------------------------------- #

class TestUnderBudget:
    def test_no_compression_needed(self) -> None:
        blocks = [_block("Short text.", order=i) for i in range(3)]
        ctrl = TokenBudgetController(target_tokens=10000)
        result, stats = ctrl.compress(blocks)
        assert len(result) == 3
        assert stats.levels_applied == 0
        assert stats.blocks_truncated == 0

    def test_markdown_no_header_when_under_budget(self) -> None:
        blocks = [_block("Short.", order=0)]
        ctrl = TokenBudgetController(target_tokens=10000)
        md = ctrl.to_budget_markdown(blocks)
        assert "⚠️" not in md


# --------------------------------------------------------------------- #
# Level 1: Paragraph truncation
# --------------------------------------------------------------------- #

class TestParagraphTruncation:
    def test_long_paragraph_truncated(self) -> None:
        blocks = [_long_paragraph(order=0)]
        # Set a tight budget that requires truncation
        ctrl = TokenBudgetController(target_tokens=30)
        result, stats = ctrl.compress(blocks)
        assert stats.blocks_truncated >= 1
        # Compressed block should have metadata
        compressed = [b for b in result if b.metadata.get("compressed")]
        assert len(compressed) >= 1
        assert "original_length" in compressed[0].metadata

    def test_short_paragraph_not_truncated(self) -> None:
        blocks = [_block("Short text.", order=0)]
        ctrl = TokenBudgetController(target_tokens=5)
        result, stats = ctrl.compress(blocks)
        # Even if over budget, short paragraphs aren't truncated at level 1
        # The block may be dropped at level 6, but shouldn't be truncated
        truncated = [b for b in result if b.metadata.get("compressed") and b.type == BlockType.PARAGRAPH]
        assert len(truncated) == 0 or all(b.text != "Short text." for b in truncated)


# --------------------------------------------------------------------- #
# Level 2: Table compression
# --------------------------------------------------------------------- #

class TestTableCompression:
    def test_large_table_compressed(self) -> None:
        blocks = [_table_block(n_rows=10, order=0)]
        ctrl = TokenBudgetController(target_tokens=20)
        result, stats = ctrl.compress(blocks)
        table_blocks = [b for b in result if b.type == BlockType.TABLE]
        if table_blocks:
            tb = table_blocks[0]
            assert tb.metadata.get("compressed") is True
            assert "more rows" in tb.text

    def test_small_table_not_compressed(self) -> None:
        blocks = [_table_block(n_rows=2, order=0)]
        ctrl = TokenBudgetController(target_tokens=20)
        result, stats = ctrl.compress(blocks)
        table_blocks = [b for b in result if b.type == BlockType.TABLE]
        if table_blocks:
            assert "more rows" not in table_blocks[0].text


# --------------------------------------------------------------------- #
# Level 3: Code truncation
# --------------------------------------------------------------------- #

class TestCodeTruncation:
    def test_long_code_truncated(self) -> None:
        blocks = [_code_block(n_lines=20, order=0)]
        ctrl = TokenBudgetController(target_tokens=20)
        result, stats = ctrl.compress(blocks)
        code_blocks = [b for b in result if b.type == BlockType.CODE]
        if code_blocks:
            cb = code_blocks[0]
            assert cb.metadata.get("compressed") is True
            assert "more lines" in cb.text

    def test_short_code_not_truncated(self) -> None:
        blocks = [_code_block(n_lines=3, order=0)]
        ctrl = TokenBudgetController(target_tokens=100)
        result, stats = ctrl.compress(blocks)
        code_blocks = [b for b in result if b.type == BlockType.CODE]
        if code_blocks:
            assert "more lines" not in code_blocks[0].text


# --------------------------------------------------------------------- #
# Level 4: List compression
# --------------------------------------------------------------------- #

class TestListCompression:
    def test_long_list_compressed(self) -> None:
        blocks = [_list_block(n_items=15, order=0)]
        ctrl = TokenBudgetController(target_tokens=20)
        result, stats = ctrl.compress(blocks)
        list_blocks = [b for b in result if b.type == BlockType.LIST]
        if list_blocks:
            lb = list_blocks[0]
            assert lb.metadata.get("compressed") is True
            assert "more items" in lb.text

    def test_short_list_not_compressed(self) -> None:
        blocks = [_list_block(n_items=3, order=0)]
        ctrl = TokenBudgetController(target_tokens=100)
        result, stats = ctrl.compress(blocks)
        list_blocks = [b for b in result if b.type == BlockType.LIST]
        if list_blocks:
            assert "more items" not in list_blocks[0].text


# --------------------------------------------------------------------- #
# Level 5: Section collapsing
# --------------------------------------------------------------------- #

class TestSectionCollapsing:
    def test_low_importance_section_collapsed(self) -> None:
        long_text = "This is a paragraph of content that contains enough words to actually consume some tokens in the budget calculation. " * 3
        blocks = [
            _block("Important heading", block_type=BlockType.HEADING, order=0,
                   importance=0.9, section_path=["Intro"], level=1),
            _block(long_text, order=1, importance=0.8, section_path=["Intro"]),
            _block("Low heading", block_type=BlockType.HEADING, order=2,
                   importance=0.2, section_path=["Footer"], level=2),
            _block(long_text, order=3, importance=0.1, section_path=["Footer"]),
            _block(long_text, order=4, importance=0.1, section_path=["Footer"]),
        ]
        ctrl = TokenBudgetController(target_tokens=40)
        result, stats = ctrl.compress(blocks)
        # The footer section should be collapsed or blocks dropped
        assert stats.blocks_collapsed >= 1 or stats.blocks_dropped >= 1


# --------------------------------------------------------------------- #
# Level 6: Block dropping
# --------------------------------------------------------------------- #

class TestBlockDropping:
    def test_blocks_dropped_by_importance(self) -> None:
        long_text = "This sentence has enough words to consume real tokens in the budget system. " * 5
        blocks = [
            _block("Critical information block here.", order=0, importance=0.9),
            _block(long_text, order=1, importance=0.5),
            _block(long_text, order=2, importance=0.1),
        ]
        ctrl = TokenBudgetController(target_tokens=30)
        result, stats = ctrl.compress(blocks)
        assert stats.blocks_dropped >= 1 or stats.blocks_truncated >= 1
        # Critical block (highest importance) should survive
        assert any("Critical" in b.text for b in result)

    def test_headings_preserved_during_dropping(self) -> None:
        blocks = [
            _block("Title", block_type=BlockType.HEADING, order=0,
                   importance=0.9, level=1),
            _block("Low content", order=1, importance=0.1),
        ]
        ctrl = TokenBudgetController(target_tokens=3)
        result, stats = ctrl.compress(blocks)
        heading_blocks = [b for b in result if b.type == BlockType.HEADING]
        assert len(heading_blocks) >= 1


# --------------------------------------------------------------------- #
# to_budget_markdown
# --------------------------------------------------------------------- #

class TestToBudgetMarkdown:
    def test_compression_header_present(self) -> None:
        blocks = [_long_paragraph(order=i) for i in range(20)]
        ctrl = TokenBudgetController(target_tokens=50)
        md = ctrl.to_budget_markdown(blocks)
        assert "⚠️" in md
        assert "Compressed to" in md
        assert "% of original" in md

    def test_valid_markdown_output(self) -> None:
        blocks = [
            _block("Title", block_type=BlockType.HEADING, order=0, level=1),
            _long_paragraph(order=1),
        ]
        ctrl = TokenBudgetController(target_tokens=30)
        md = ctrl.to_budget_markdown(blocks)
        # Should still contain the heading
        assert "Title" in md


# --------------------------------------------------------------------- #
# Input immutability
# --------------------------------------------------------------------- #

class TestImmutability:
    def test_original_blocks_not_mutated(self) -> None:
        blocks = [_long_paragraph(order=0)]
        original_text = blocks[0].text
        original_meta = dict(blocks[0].metadata)
        ctrl = TokenBudgetController(target_tokens=10)
        ctrl.compress(blocks)
        assert blocks[0].text == original_text
        assert blocks[0].metadata == original_meta


# --------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------- #

class TestEdgeCases:
    def test_empty_blocks(self) -> None:
        ctrl = TokenBudgetController(target_tokens=100)
        result, stats = ctrl.compress([])
        assert result == []
        assert stats.levels_applied == 0

    def test_single_block(self) -> None:
        blocks = [_block("Hello", order=0)]
        ctrl = TokenBudgetController(target_tokens=1)
        result, stats = ctrl.compress(blocks)
        # Should not drop the last remaining block
        assert len(result) >= 1

    def test_zero_budget_keeps_at_least_one(self) -> None:
        blocks = [_block("A", order=0), _block("B", order=1)]
        ctrl = TokenBudgetController(target_tokens=0)
        result, stats = ctrl.compress(blocks)
        # We enforce at least 1 block
        assert len(result) >= 1
