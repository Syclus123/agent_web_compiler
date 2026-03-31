"""Token budget controller — compresses AgentDocument output to fit LLM context windows.

Strategies (applied progressively until budget is met):
1. Detail pruning: collapse long paragraphs to first 2 sentences
2. Table compression: show only headers + first 3 rows + "... N more rows"
3. Code truncation: keep first 5 lines of code blocks + "... N more lines"
4. List compression: keep first 5 items + "... N more items"
5. Section collapsing: merge low-importance sections into "[Collapsed: ...]"
6. Block dropping: remove lowest-importance blocks one at a time
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agent_web_compiler.core.block import Block, BlockType
from agent_web_compiler.exporters.markdown_exporter import to_markdown


@dataclass
class CompressionStats:
    """Tracks what compression did."""

    original_tokens: int = 0
    final_tokens: int = 0
    blocks_collapsed: int = 0
    blocks_truncated: int = 0
    blocks_dropped: int = 0
    levels_applied: int = 0


# Sentence boundary — period/question/exclamation followed by space or end.
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

_MAX_PARAGRAPH_CHARS = 300
_MAX_TABLE_ROWS = 3
_MAX_CODE_LINES = 5
_MAX_LIST_ITEMS = 5
_LOW_IMPORTANCE_THRESHOLD = 0.3


class TokenBudgetController:
    """Compresses document output to fit within a token budget.

    Unlike simple truncation, this preserves document structure and
    key information by applying graduated compression strategies.
    """

    def __init__(
        self,
        target_tokens: int,
        approx_chars_per_token: float = 4.0,
    ) -> None:
        self.target_tokens = target_tokens
        self.chars_per_token = approx_chars_per_token

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def compress(self, blocks: list[Block]) -> tuple[list[Block], CompressionStats]:
        """Apply progressive compression to fit within token budget.

        Returns (new_blocks, stats). Input list is not mutated.
        """
        stats = CompressionStats()
        stats.original_tokens = self._estimate_tokens(blocks)

        if stats.original_tokens <= self.target_tokens:
            stats.final_tokens = stats.original_tokens
            return list(blocks), stats

        # Deep copy so we never mutate the original
        working = [self._copy_block(b) for b in blocks]

        # Level 1: Truncate long paragraphs
        working, n = self._level_truncate_paragraphs(working)
        stats.blocks_truncated += n
        stats.levels_applied = 1
        if self._estimate_tokens(working) <= self.target_tokens:
            stats.final_tokens = self._estimate_tokens(working)
            return working, stats

        # Level 2: Compress tables
        working, n = self._level_compress_tables(working)
        stats.blocks_truncated += n
        stats.levels_applied = 2
        if self._estimate_tokens(working) <= self.target_tokens:
            stats.final_tokens = self._estimate_tokens(working)
            return working, stats

        # Level 3: Truncate code blocks
        working, n = self._level_truncate_code(working)
        stats.blocks_truncated += n
        stats.levels_applied = 3
        if self._estimate_tokens(working) <= self.target_tokens:
            stats.final_tokens = self._estimate_tokens(working)
            return working, stats

        # Level 4: Compress lists
        working, n = self._level_compress_lists(working)
        stats.blocks_truncated += n
        stats.levels_applied = 4
        if self._estimate_tokens(working) <= self.target_tokens:
            stats.final_tokens = self._estimate_tokens(working)
            return working, stats

        # Level 5: Collapse low-importance sections
        working, n = self._level_collapse_sections(working)
        stats.blocks_collapsed += n
        stats.levels_applied = 5
        if self._estimate_tokens(working) <= self.target_tokens:
            stats.final_tokens = self._estimate_tokens(working)
            return working, stats

        # Level 6: Drop lowest-importance blocks one at a time
        stats.levels_applied = 6
        while (
            self._estimate_tokens(working) > self.target_tokens
            and len(working) > 1
        ):
            # Find lowest-importance non-heading block
            min_idx = -1
            min_imp = 2.0
            for i, b in enumerate(working):
                if b.type != BlockType.HEADING and b.importance < min_imp:
                    min_imp = b.importance
                    min_idx = i
            if min_idx == -1:
                break
            working.pop(min_idx)
            stats.blocks_dropped += 1

        stats.final_tokens = self._estimate_tokens(working)
        return working, stats

    def to_budget_markdown(self, blocks: list[Block]) -> str:
        """Generate markdown that fits within the token budget.

        Includes a compression summary header when compression was applied.
        """
        compressed, stats = self.compress(blocks)
        md = to_markdown(compressed)

        if stats.levels_applied > 0:
            ratio = round(
                stats.final_tokens / max(stats.original_tokens, 1) * 100
            )
            header = (
                f"> \u26a0\ufe0f Compressed to ~{stats.final_tokens} tokens "
                f"({ratio}% of original). "
                f"{stats.blocks_collapsed} blocks collapsed, "
                f"{stats.blocks_truncated} truncated."
            )
            md = header + "\n\n" + md

        return md

    # ------------------------------------------------------------------ #
    # Token estimation
    # ------------------------------------------------------------------ #

    def _estimate_tokens(self, blocks: list[Block]) -> int:
        """Rough token count from block text lengths."""
        total_chars = sum(len(b.text) for b in blocks)
        return max(1, int(total_chars / self.chars_per_token))

    # ------------------------------------------------------------------ #
    # Compression levels
    # ------------------------------------------------------------------ #

    def _level_truncate_paragraphs(
        self, blocks: list[Block],
    ) -> tuple[list[Block], int]:
        """Level 1: Truncate long paragraphs to first 2 sentences."""
        result: list[Block] = []
        count = 0
        for b in blocks:
            if b.type == BlockType.PARAGRAPH and len(b.text) > _MAX_PARAGRAPH_CHARS:
                sentences = _SENTENCE_RE.split(b.text)
                truncated = ". ".join(sentences[:2]).rstrip()
                if not truncated.endswith("."):
                    truncated += "."
                if len(truncated) < len(b.text):
                    new_meta = dict(b.metadata)
                    new_meta["compressed"] = True
                    new_meta["original_length"] = len(b.text)
                    result.append(b.model_copy(update={
                        "text": truncated,
                        "metadata": new_meta,
                    }))
                    count += 1
                    continue
            result.append(b)
        return result, count

    def _level_compress_tables(
        self, blocks: list[Block],
    ) -> tuple[list[Block], int]:
        """Level 2: Compress tables to headers + 3 rows + count."""
        result: list[Block] = []
        count = 0
        for b in blocks:
            if b.type == BlockType.TABLE:
                rows = b.metadata.get("rows")
                if rows and len(rows) > _MAX_TABLE_ROWS:
                    kept = rows[:_MAX_TABLE_ROWS]
                    omitted = len(rows) - _MAX_TABLE_ROWS
                    new_meta = dict(b.metadata)
                    new_meta["rows"] = kept
                    new_meta["compressed"] = True
                    new_meta["original_length"] = len(b.text)
                    # Rebuild text to reflect compression
                    headers = b.metadata.get("headers", [])
                    text_parts = []
                    if headers:
                        text_parts.append(" | ".join(str(h) for h in headers))
                    for row in kept:
                        text_parts.append(" | ".join(str(c) for c in row))
                    text_parts.append(f"... {omitted} more rows")
                    result.append(b.model_copy(update={
                        "text": "\n".join(text_parts),
                        "metadata": new_meta,
                    }))
                    count += 1
                    continue
            result.append(b)
        return result, count

    def _level_truncate_code(
        self, blocks: list[Block],
    ) -> tuple[list[Block], int]:
        """Level 3: Truncate code blocks to 5 lines + count."""
        result: list[Block] = []
        count = 0
        for b in blocks:
            if b.type == BlockType.CODE:
                lines = b.text.splitlines()
                if len(lines) > _MAX_CODE_LINES:
                    omitted = len(lines) - _MAX_CODE_LINES
                    truncated = "\n".join(lines[:_MAX_CODE_LINES])
                    truncated += f"\n... {omitted} more lines"
                    new_meta = dict(b.metadata)
                    new_meta["compressed"] = True
                    new_meta["original_length"] = len(b.text)
                    result.append(b.model_copy(update={
                        "text": truncated,
                        "metadata": new_meta,
                    }))
                    count += 1
                    continue
            result.append(b)
        return result, count

    def _level_compress_lists(
        self, blocks: list[Block],
    ) -> tuple[list[Block], int]:
        """Level 4: Compress lists to 5 items + count."""
        result: list[Block] = []
        count = 0
        for b in blocks:
            if b.type == BlockType.LIST:
                text_lines = b.text.splitlines() if not b.children else []

                if b.children and len(b.children) > _MAX_LIST_ITEMS:
                    omitted = len(b.children) - _MAX_LIST_ITEMS
                    kept_children = list(b.children[:_MAX_LIST_ITEMS])
                    kept_text = "\n".join(c.text for c in kept_children)
                    kept_text += f"\n... {omitted} more items"
                    new_meta = dict(b.metadata)
                    new_meta["compressed"] = True
                    new_meta["original_length"] = len(b.text)
                    result.append(b.model_copy(update={
                        "text": kept_text,
                        "children": kept_children,
                        "metadata": new_meta,
                    }))
                    count += 1
                    continue
                elif not b.children and len(text_lines) > _MAX_LIST_ITEMS:
                    omitted = len(text_lines) - _MAX_LIST_ITEMS
                    kept_text = "\n".join(text_lines[:_MAX_LIST_ITEMS])
                    kept_text += f"\n... {omitted} more items"
                    new_meta = dict(b.metadata)
                    new_meta["compressed"] = True
                    new_meta["original_length"] = len(b.text)
                    result.append(b.model_copy(update={
                        "text": kept_text,
                        "metadata": new_meta,
                    }))
                    count += 1
                    continue
            result.append(b)
        return result, count

    def _level_collapse_sections(
        self, blocks: list[Block],
    ) -> tuple[list[Block], int]:
        """Level 5: Collapse sections where all blocks are low-importance."""
        # Group blocks by their first section_path element
        sections: list[tuple[str, list[int]]] = []  # (section_name, [indices])
        current_section: str | None = None
        current_indices: list[int] = []

        for i, b in enumerate(blocks):
            section = b.section_path[0] if b.section_path else "(root)"
            if section != current_section:
                if current_section is not None:
                    sections.append((current_section, current_indices))
                current_section = section
                current_indices = [i]
            else:
                current_indices.append(i)
        if current_section is not None:
            sections.append((current_section, current_indices))

        collapse_indices: set[int] = set()
        replacements: dict[int, Block] = {}  # first index -> placeholder block
        count = 0

        for section_name, indices in sections:
            if len(indices) <= 1:
                continue
            section_blocks = [blocks[i] for i in indices]
            # Skip if any block is a heading or high importance
            non_heading = [
                b for b in section_blocks if b.type != BlockType.HEADING
            ]
            if not non_heading:
                continue
            if all(b.importance < _LOW_IMPORTANCE_THRESHOLD for b in non_heading):
                # Collapse: keep first heading if present, replace rest with placeholder
                first_idx = indices[0]
                first_block = blocks[first_idx]
                if first_block.type == BlockType.HEADING:
                    # Keep heading, collapse the rest
                    for idx in indices[1:]:
                        collapse_indices.add(idx)
                    placeholder = Block(
                        id=f"collapsed_{section_name}",
                        type=BlockType.METADATA,
                        text=f"[Collapsed: {section_name} - {len(non_heading)} blocks]",
                        section_path=blocks[first_idx].section_path,
                        order=blocks[indices[1]].order if len(indices) > 1 else 0,
                        importance=0.1,
                        metadata={"compressed": True, "collapsed_count": len(non_heading)},
                    )
                    replacements[indices[1]] = placeholder
                else:
                    for idx in indices:
                        collapse_indices.add(idx)
                    placeholder = Block(
                        id=f"collapsed_{section_name}",
                        type=BlockType.METADATA,
                        text=f"[Collapsed: {section_name} - {len(section_blocks)} blocks]",
                        section_path=section_blocks[0].section_path,
                        order=section_blocks[0].order,
                        importance=0.1,
                        metadata={"compressed": True, "collapsed_count": len(section_blocks)},
                    )
                    replacements[first_idx] = placeholder
                count += len(non_heading)

        result: list[Block] = []
        for i, b in enumerate(blocks):
            if i in replacements:
                result.append(replacements[i])
            elif i not in collapse_indices:
                result.append(b)

        return result, count

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _copy_block(block: Block) -> Block:
        """Create a shallow copy of a block."""
        return block.model_copy(deep=True)
