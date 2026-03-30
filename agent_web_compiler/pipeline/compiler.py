"""HTMLCompiler — orchestrates the full compilation pipeline.

Pipeline stages: normalize -> segment -> extract_actions -> align -> build_document
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from agent_web_compiler.core.action import Action
from agent_web_compiler.core.block import Block
from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.core.document import AgentDocument, Quality, SourceType


class HTMLCompiler:
    """Compiles raw HTML into an AgentDocument through a staged pipeline.

    Each stage is explicit and independently testable. The pipeline shape is:
    normalize -> segment -> extract_actions -> align -> build_document
    """

    def compile(
        self,
        html: str,
        source_url: str | None = None,
        config: CompileConfig | None = None,
    ) -> AgentDocument:
        """Compile raw HTML into a canonical AgentDocument.

        Args:
            html: Raw HTML string to compile.
            source_url: Optional source URL for provenance tracking.
            config: Compilation configuration. Uses defaults if not provided.

        Returns:
            A fully populated AgentDocument.
        """
        if config is None:
            config = CompileConfig()

        timings: dict[str, float] = {}
        pipeline_start = time.perf_counter()

        # --- Stage 1: Normalize ---
        t0 = time.perf_counter()
        from agent_web_compiler.normalizers.html_normalizer import HTMLNormalizer

        cleaned_html = HTMLNormalizer().normalize(html, config)
        timings["normalize_ms"] = (time.perf_counter() - t0) * 1000

        # --- Stage 2: Segment ---
        t0 = time.perf_counter()
        from agent_web_compiler.segmenters.html_segmenter import HTMLSegmenter

        blocks: list[Block] = HTMLSegmenter().segment(cleaned_html, config)
        timings["segment_ms"] = (time.perf_counter() - t0) * 1000

        # --- Stage 3: Extract actions (from original HTML) ---
        actions: list[Action] = []
        if config.include_actions:
            t0 = time.perf_counter()
            from agent_web_compiler.extractors.action_extractor import ActionExtractor

            actions = ActionExtractor().extract(html, config)
            timings["extract_actions_ms"] = (time.perf_counter() - t0) * 1000

        # --- Stage 4: Align provenance ---
        if config.include_provenance:
            t0 = time.perf_counter()
            from agent_web_compiler.aligners.dom_aligner import DOMAligner

            blocks, actions = DOMAligner().align(blocks, actions, html, config)
            timings["align_ms"] = (time.perf_counter() - t0) * 1000

        # --- Stage 5: Build canonical markdown ---
        t0 = time.perf_counter()
        from agent_web_compiler.exporters.markdown_exporter import to_markdown

        canonical_markdown = to_markdown(blocks)
        timings["markdown_ms"] = (time.perf_counter() - t0) * 1000

        timings["total_ms"] = (time.perf_counter() - pipeline_start) * 1000

        # --- Extract title ---
        title = self._extract_title(html, blocks)

        # --- Build document ---
        debug: dict[str, Any] = {}
        if config.debug:
            debug["timings"] = timings

        doc_id = AgentDocument.make_doc_id(html)

        return AgentDocument(
            doc_id=doc_id,
            source_type=SourceType.HTML,
            source_url=source_url,
            title=title,
            blocks=blocks,
            canonical_markdown=canonical_markdown,
            actions=actions,
            quality=Quality(
                block_count=len(blocks),
                action_count=len(actions),
            ),
            compiled_at=datetime.now(timezone.utc),
            debug=debug,
        )

    @staticmethod
    def _extract_title(html: str, blocks: list[Block]) -> str:
        """Extract document title from <title> tag or first h1 block."""
        # Try <title> tag first
        import re

        from agent_web_compiler.core.block import BlockType

        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if title_match:
            title = title_match.group(1).strip()
            if title:
                return title

        # Fall back to first h1 block
        for block in blocks:
            if block.type == BlockType.HEADING and block.level == 1:
                return block.text

        # Fall back to any heading
        for block in blocks:
            if block.type == BlockType.HEADING:
                return block.text

        return ""
