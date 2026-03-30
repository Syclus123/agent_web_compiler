"""DOM aligner — enriches blocks and actions with provenance data."""

from __future__ import annotations

import logging

from agent_web_compiler.core.action import Action
from agent_web_compiler.core.block import Block
from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.core.provenance import PageProvenance, Provenance

logger = logging.getLogger(__name__)


class DOMAligner:
    """Aligns blocks and actions with DOM provenance data.

    Enriches existing provenance (set by segmenter/extractor) with source_url
    and character offset information. For blocks lacking provenance, attempts
    to match text content back to positions in the source HTML.
    """

    def align(
        self,
        blocks: list[Block],
        actions: list[Action],
        html: str,
        config: CompileConfig,
    ) -> tuple[list[Block], list[Action]]:
        """Enrich blocks and actions with provenance information.

        Args:
            blocks: Semantic blocks from the segmenter.
            actions: Actions from the extractor.
            html: The source HTML string for offset matching.
            config: Compilation configuration (used for source_url context).

        Returns:
            Tuple of (enriched_blocks, enriched_actions).
        """
        if not config.include_provenance:
            return blocks, actions

        source_url = self._resolve_source_url(config)

        enriched_blocks = [
            self._align_block(block, html, source_url) for block in blocks
        ]
        enriched_actions = [
            self._align_action(action, source_url) for action in actions
        ]

        return enriched_blocks, enriched_actions

    def _resolve_source_url(self, config: CompileConfig) -> str | None:
        """Extract source URL from config context if available."""
        # The config doesn't have a source_url field directly, but the query
        # or debug context may carry it. For now, return None; the pipeline
        # caller sets source_url on the document directly.
        return None

    def _align_block(
        self, block: Block, html: str, source_url: str | None
    ) -> Block:
        """Enrich a single block with provenance."""
        if block.provenance is not None:
            # Already has provenance from segmenter — fill in source_url
            if source_url and not block.provenance.source_url:
                block.provenance.source_url = source_url
            # Try to fill in char_range if missing and we have DOM provenance
            if (
                block.provenance.dom is not None
                and (
                    block.provenance.page is None
                    or block.provenance.page.char_range is None
                )
            ):
                char_range = self._find_char_range(block.text, html)
                if char_range is not None:
                    if block.provenance.page is None:
                        block.provenance.page = PageProvenance(char_range=char_range)
                    else:
                        block.provenance.page.char_range = char_range
        else:
            # No provenance at all — try substring matching
            provenance = self._build_provenance_from_text(
                block.text, html, source_url
            )
            if provenance is not None:
                block.provenance = provenance

        return block

    def _align_action(
        self, action: Action, source_url: str | None
    ) -> Action:
        """Enrich a single action with provenance."""
        if action.provenance is not None and source_url and not action.provenance.source_url:
            action.provenance.source_url = source_url
        return action

    def _find_char_range(
        self, text: str, html: str
    ) -> list[int] | None:
        """Find character offset range of text in the HTML source.

        Uses simple substring search. Returns [start, end] or None.
        """
        if not text or not html:
            return None

        # Try exact match first
        idx = html.find(text)
        if idx >= 0:
            return [idx, idx + len(text)]

        # Try matching a meaningful prefix (first 80 chars) for longer blocks
        prefix = text[:80].strip()
        if len(prefix) >= 10:
            idx = html.find(prefix)
            if idx >= 0:
                return [idx, idx + len(prefix)]

        return None

    def _build_provenance_from_text(
        self, text: str, html: str, source_url: str | None
    ) -> Provenance | None:
        """Build provenance for a block by matching its text in the HTML."""
        char_range = self._find_char_range(text, html)
        if char_range is None:
            return None

        return Provenance(
            page=PageProvenance(char_range=char_range),
            source_url=source_url,
        )
