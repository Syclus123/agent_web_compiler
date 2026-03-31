"""Streaming compilation — yields blocks as they're extracted.

For large documents, this allows the consumer (LLM, agent, API client)
to start processing content before the full compilation finishes.
Also supports early termination when a token budget is reached.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncGenerator, Generator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from agent_web_compiler.core.action import Action
from agent_web_compiler.core.block import Block
from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.core.document import AgentDocument, SourceType

logger = logging.getLogger(__name__)


@dataclass
class StreamEvent:
    """A single event in the compilation stream.

    Attributes:
        event_type: One of "block", "action", "progress", "complete", "error",
                    or "budget_reached".
        data: Event payload. Shape depends on event_type:
            - "block": serialised Block dict
            - "action": serialised Action dict
            - "progress": {"stage": str, "detail": str | None}
            - "complete": full AgentDocument dict
            - "budget_reached": {"blocks_emitted": int, "reason": str}
            - "error": {"message": str, "stage": str | None}
        sequence: Monotonically increasing event counter (0-indexed).
    """

    event_type: str
    data: dict[str, Any]
    sequence: int = 0


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English text."""
    return max(1, len(text) // 4)


class StreamCompiler:
    """Streaming compilation that yields results incrementally.

    Usage::

        compiler = StreamCompiler()
        for event in compiler.compile_stream(html):
            if event.event_type == "block":
                process_block(event.data)
            elif event.event_type == "action":
                process_action(event.data)
            elif event.event_type == "complete":
                final_doc = AgentDocument(**event.data)
    """

    def compile_stream(
        self,
        html: str,
        source_url: str | None = None,
        config: CompileConfig | None = None,
    ) -> Generator[StreamEvent, None, None]:
        """Synchronous streaming compilation.

        Yields StreamEvent objects as the pipeline progresses. The final
        event is always either "complete" (with the full AgentDocument) or
        "error".

        Args:
            html: Raw HTML string to compile.
            source_url: Optional source URL for provenance tracking.
            config: Compilation configuration. Uses defaults if not provided.

        Yields:
            StreamEvent for each pipeline milestone or extracted element.
        """
        if config is None:
            config = CompileConfig()

        seq = 0
        timings: dict[str, float] = {}
        pipeline_start = time.perf_counter()
        token_budget = config.token_budget
        tokens_used = 0

        def _event(event_type: str, data: dict[str, Any]) -> StreamEvent:
            nonlocal seq
            evt = StreamEvent(event_type=event_type, data=data, sequence=seq)
            seq += 1
            return evt

        try:
            # --- Stage 1: Normalize ---
            yield _event("progress", {"stage": "normalizing", "detail": None})
            t0 = time.perf_counter()
            from agent_web_compiler.normalizers.html_normalizer import HTMLNormalizer

            cleaned_html = HTMLNormalizer().normalize(html, config)
            timings["normalize_ms"] = (time.perf_counter() - t0) * 1000

            # --- Stage 2: Segment ---
            yield _event("progress", {"stage": "segmenting", "detail": None})
            t0 = time.perf_counter()
            from agent_web_compiler.segmenters.html_segmenter import HTMLSegmenter

            blocks: list[Block] = HTMLSegmenter().segment(cleaned_html, config)
            timings["segment_ms"] = (time.perf_counter() - t0) * 1000

            # --- Stage 2a: Entity extraction ---
            t0 = time.perf_counter()
            from agent_web_compiler.extractors.entity_extractor import EntityExtractor

            blocks = EntityExtractor().annotate_blocks(blocks)
            timings["entity_extraction_ms"] = (time.perf_counter() - t0) * 1000

            # --- Stage 2b: Salience scoring ---
            t0 = time.perf_counter()
            from agent_web_compiler.segmenters.salience import SalienceScorer

            blocks = SalienceScorer().score_blocks(blocks, cleaned_html)
            timings["salience_ms"] = (time.perf_counter() - t0) * 1000

            # --- Stage 2c: Query-aware filtering ---
            if config.query:
                t0 = time.perf_counter()
                from agent_web_compiler.segmenters.query_filter import QueryAwareFilter

                blocks = QueryAwareFilter(config.query).filter_blocks(blocks, config)
                timings["query_filter_ms"] = (time.perf_counter() - t0) * 1000

            # --- Stage 2d: Importance / max_blocks filtering ---
            if config.min_importance > 0:
                blocks = [b for b in blocks if b.importance >= config.min_importance]
            if config.max_blocks is not None and config.max_blocks > 0 and not config.query:
                blocks.sort(key=lambda b: b.importance, reverse=True)
                blocks = blocks[: config.max_blocks]

            # --- Yield blocks (with token budget check) ---
            budget_reached = False
            emitted_blocks: list[Block] = []

            for block in blocks:
                if token_budget is not None and token_budget > 0:
                    block_tokens = _estimate_tokens(block.text)
                    if tokens_used + block_tokens > token_budget:
                        yield _event(
                            "budget_reached",
                            {
                                "blocks_emitted": len(emitted_blocks),
                                "reason": (
                                    f"Token budget {token_budget} reached "
                                    f"({tokens_used} tokens used)"
                                ),
                            },
                        )
                        budget_reached = True
                        break
                    tokens_used += block_tokens

                yield _event("block", block.model_dump(mode="json"))
                emitted_blocks.append(block)

            if budget_reached:
                blocks = emitted_blocks

            # --- Stage 3: Extract actions ---
            actions: list[Action] = []
            if config.include_actions and not budget_reached:
                yield _event("progress", {"stage": "extracting_actions", "detail": None})
                t0 = time.perf_counter()
                from agent_web_compiler.extractors.action_extractor import ActionExtractor

                actions = ActionExtractor().extract(html, config)
                timings["extract_actions_ms"] = (time.perf_counter() - t0) * 1000

                for action in actions:
                    yield _event("action", action.model_dump(mode="json"))

            # --- Stage 4: Align provenance ---
            if config.include_provenance:
                yield _event("progress", {"stage": "aligning", "detail": None})
                t0 = time.perf_counter()
                from agent_web_compiler.aligners.dom_aligner import DOMAligner

                blocks, actions = DOMAligner().align(blocks, actions, html, config)
                timings["align_ms"] = (time.perf_counter() - t0) * 1000

            # --- Stage 5: Validate ---
            yield _event("progress", {"stage": "validating", "detail": None})
            t0 = time.perf_counter()
            from agent_web_compiler.pipeline.validator import DocumentValidator

            blocks, actions, quality = DocumentValidator().validate(
                blocks, actions, cleaned_html, config
            )
            timings["validate_ms"] = (time.perf_counter() - t0) * 1000

            # --- Stage 6: Build markdown ---
            t0 = time.perf_counter()
            from agent_web_compiler.exporters.markdown_exporter import to_markdown

            canonical_markdown = to_markdown(blocks)
            timings["markdown_ms"] = (time.perf_counter() - t0) * 1000

            timings["total_ms"] = (time.perf_counter() - pipeline_start) * 1000

            # --- Build provenance index ---
            provenance_index: dict[str, list[str]] = {}
            for block in blocks:
                key = " > ".join(block.section_path) if block.section_path else "(root)"
                if key not in provenance_index:
                    provenance_index[key] = []
                provenance_index[key].append(block.id)

            # --- Extract title ---
            title = self._extract_title(html, blocks)

            # --- Build debug ---
            debug: dict[str, Any] = {}
            if config.debug:
                debug["timings"] = timings
                debug["streaming"] = True
                if budget_reached:
                    debug["budget_reached"] = True
                    debug["tokens_used"] = tokens_used

            doc_id = AgentDocument.make_doc_id(html)

            doc = AgentDocument(
                doc_id=doc_id,
                source_type=SourceType.HTML,
                source_url=source_url,
                title=title,
                blocks=blocks,
                canonical_markdown=canonical_markdown,
                actions=actions,
                provenance_index=provenance_index,
                quality=quality,
                compiled_at=datetime.now(timezone.utc),
                debug=debug,
            )

            yield _event("complete", doc.model_dump(mode="json"))

        except Exception as exc:
            logger.error("Streaming compilation error: %s", exc, exc_info=True)
            yield _event(
                "error",
                {
                    "message": str(exc),
                    "stage": None,
                },
            )

    async def compile_stream_async(
        self,
        html: str,
        source_url: str | None = None,
        config: CompileConfig | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Async streaming compilation.

        Wraps the synchronous generator, yielding control back to the
        event loop between events so that other coroutines can run.

        Args:
            html: Raw HTML string to compile.
            source_url: Optional source URL for provenance tracking.
            config: Compilation configuration. Uses defaults if not provided.

        Yields:
            StreamEvent for each pipeline milestone or extracted element.
        """
        for event in self.compile_stream(html, source_url=source_url, config=config):
            yield event

    @staticmethod
    def _extract_title(html: str, blocks: list[Block]) -> str:
        """Extract document title from <title> tag or first h1 block."""
        import re

        from agent_web_compiler.core.block import BlockType

        title_match = re.search(
            r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL
        )
        if title_match:
            title = title_match.group(1).strip()
            if title:
                return title

        for block in blocks:
            if block.type == BlockType.HEADING and block.level == 1:
                return block.text

        for block in blocks:
            if block.type == BlockType.HEADING:
                return block.text

        return ""
