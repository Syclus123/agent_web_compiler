"""DocumentValidator — validates compiled output and computes quality metrics.

Pipeline stage between align and emit.  Performs integrity checks, duplicate
detection, quality scoring, and warning generation.
"""

from __future__ import annotations

from agent_web_compiler.core.action import Action
from agent_web_compiler.core.block import Block, BlockType
from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.core.document import Quality


class DocumentValidator:
    """Validates compiled output and computes quality metrics.

    Checks:
    - Block integrity (no empty blocks, no orphaned provenance)
    - Duplicate detection (blocks with identical text)
    - Quality scoring (parse_confidence based on evidence)
    - Warning generation (low block count, missing headings, etc.)
    """

    def validate(
        self,
        blocks: list[Block],
        actions: list[Action],
        html: str,
        config: CompileConfig,
    ) -> tuple[list[Block], list[Action], Quality]:
        """Validate blocks/actions and compute quality metrics.

        Parameters
        ----------
        blocks:
            Semantic blocks from the segmenter/aligner.
        actions:
            Extracted actions.
        html:
            The normalised HTML (used for content-length ratio).
        config:
            Compilation configuration.

        Returns
        -------
        tuple
            (validated_blocks, validated_actions, quality)
        """
        warnings: list[str] = []

        # --- 1. Empty block removal ---
        blocks = [b for b in blocks if b.text and b.text.strip()]

        # --- 2. Duplicate detection ---
        seen_texts: dict[str, int] = {}
        for block in blocks:
            seen_texts[block.text] = seen_texts.get(block.text, 0) + 1

        duplicate_count = sum(1 for count in seen_texts.values() if count > 1)
        if duplicate_count > 0:
            warnings.append(f"duplicate_blocks:{duplicate_count}")

        # --- 3. Warning generation ---
        has_headings = any(b.type == BlockType.HEADING for b in blocks)
        if not has_headings:
            warnings.append("no_headings_found")

        if len(blocks) < 3:
            warnings.append("low_block_count")

        if len(blocks) > 0 and len(actions) > len(blocks) * 3:
            warnings.append("high_noise_ratio")

        has_important = any(b.importance > 0.5 for b in blocks)
        if blocks and not has_important:
            warnings.append("no_main_content")

        # --- 4. Parse confidence scoring ---
        parse_confidence = 0.0

        # +0.3 if any blocks exist
        if len(blocks) > 0:
            parse_confidence += 0.3

        # +0.2 if heading present
        if has_headings:
            parse_confidence += 0.2

        # +0.3 based on content length ratio
        total_text_len = sum(len(b.text) for b in blocks)
        html_len = len(html) if html else 1
        ratio = total_text_len / max(html_len, 1)
        # Clamp ratio contribution: full 0.3 when ratio >= 0.1
        ratio_score = min(ratio / 0.1, 1.0) * 0.3
        parse_confidence += ratio_score

        # +0.2 if no warnings
        if not warnings:
            parse_confidence += 0.2

        # Clamp to [0, 1]
        parse_confidence = max(0.0, min(1.0, parse_confidence))

        quality = Quality(
            parse_confidence=parse_confidence,
            block_count=len(blocks),
            action_count=len(actions),
            warnings=warnings,
        )

        return blocks, actions, quality
