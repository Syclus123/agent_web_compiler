"""Pluggable pipeline — dependency injection for compilation stages.

Allows users to replace, extend, or hook into any pipeline stage
without modifying source code. This is the primary extensibility
mechanism for agent-web-compiler.

Usage:
    from agent_web_compiler.pipeline.builder import PipelineBuilder

    # Use defaults (same as HTMLCompiler)
    pipeline = PipelineBuilder().build()
    doc = pipeline.compile(html)

    # Replace a stage
    pipeline = (
        PipelineBuilder()
        .with_normalizer(MyCustomNormalizer())
        .with_segmenter(MyCustomSegmenter())
        .build()
    )
    doc = pipeline.compile(html)

    # Add hooks
    pipeline = (
        PipelineBuilder()
        .on_after_normalize(lambda html, config: log_html_size(html))
        .on_block_created(lambda block: tag_block(block))
        .build()
    )

    # Skip stages
    pipeline = (
        PipelineBuilder()
        .skip_actions()
        .skip_salience()
        .build()
    )
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from agent_web_compiler.core.action import Action
from agent_web_compiler.core.block import Block
from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.core.document import AgentDocument, SourceType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hook types — use Optional[] for Python 3.9 runtime compatibility
# ---------------------------------------------------------------------------

NormalizeHook = Callable[..., Any]  # (html: str, config: CompileConfig) -> str | None
SegmentHook = Callable[..., Any]   # (blocks: list, config: CompileConfig) -> list | None
ActionHook = Callable[..., Any]    # (actions: list, config: CompileConfig) -> list | None
BlockHook = Callable[..., Any]     # (block: Block) -> Block | None
CompileHook = Callable[..., Any]   # (doc: AgentDocument) -> AgentDocument | None


@dataclass
class PipelineHooks:
    """Collection of hooks for pipeline events."""

    before_normalize: list[NormalizeHook] = field(default_factory=list)
    after_normalize: list[NormalizeHook] = field(default_factory=list)
    after_segment: list[SegmentHook] = field(default_factory=list)
    on_block_created: list[BlockHook] = field(default_factory=list)
    after_extract_actions: list[ActionHook] = field(default_factory=list)
    after_compile: list[CompileHook] = field(default_factory=list)


class PipelineBuilder:
    """Builds a customizable compilation pipeline via fluent API.

    Every stage has a default implementation that matches the existing
    HTMLCompiler behavior. Users can replace any stage or add hooks.
    """

    def __init__(self) -> None:
        self._normalizer: Any = None
        self._segmenter: Any = None
        self._action_extractor: Any = None
        self._salience_scorer: Any = None
        self._query_filter_factory: Any = None
        self._entity_extractor: Any = None
        self._aligner: Any = None
        self._validator: Any = None
        self._hooks = PipelineHooks()

        # Skip flags
        self._skip_actions = False
        self._skip_salience = False
        self._skip_entities = False
        self._skip_provenance = False
        self._skip_validation = False

    # --- Stage replacement (fluent API) ---

    def with_normalizer(self, normalizer: Any) -> PipelineBuilder:
        """Replace the HTML normalizer. Must implement normalize(html, config) -> str."""
        self._normalizer = normalizer
        return self

    def with_segmenter(self, segmenter: Any) -> PipelineBuilder:
        """Replace the HTML segmenter. Must implement segment(html, config) -> list[Block]."""
        self._segmenter = segmenter
        return self

    def with_action_extractor(self, extractor: Any) -> PipelineBuilder:
        """Replace the action extractor. Must implement extract(html, config) -> list[Action]."""
        self._action_extractor = extractor
        return self

    def with_salience_scorer(self, scorer: Any) -> PipelineBuilder:
        """Replace the salience scorer. Must implement score_blocks(blocks, html) -> list[Block]."""
        self._salience_scorer = scorer
        return self

    def with_aligner(self, aligner: Any) -> PipelineBuilder:
        """Replace the provenance aligner. Must implement align(blocks, actions, html, config)."""
        self._aligner = aligner
        return self

    def with_validator(self, validator: Any) -> PipelineBuilder:
        """Replace the document validator."""
        self._validator = validator
        return self

    # --- Skip stages ---

    def skip_actions(self) -> PipelineBuilder:
        """Skip action extraction entirely."""
        self._skip_actions = True
        return self

    def skip_salience(self) -> PipelineBuilder:
        """Skip advanced salience scoring."""
        self._skip_salience = True
        return self

    def skip_entities(self) -> PipelineBuilder:
        """Skip entity extraction."""
        self._skip_entities = True
        return self

    def skip_provenance(self) -> PipelineBuilder:
        """Skip provenance alignment."""
        self._skip_provenance = True
        return self

    def skip_validation(self) -> PipelineBuilder:
        """Skip validation stage."""
        self._skip_validation = True
        return self

    # --- Hooks (fluent API) ---

    def on_before_normalize(self, hook: NormalizeHook) -> PipelineBuilder:
        """Add a hook called before normalization. Can modify the HTML."""
        self._hooks.before_normalize.append(hook)
        return self

    def on_after_normalize(self, hook: NormalizeHook) -> PipelineBuilder:
        """Add a hook called after normalization. Can modify the cleaned HTML."""
        self._hooks.after_normalize.append(hook)
        return self

    def on_after_segment(self, hook: SegmentHook) -> PipelineBuilder:
        """Add a hook called after segmentation. Can modify the block list."""
        self._hooks.after_segment.append(hook)
        return self

    def on_block_created(self, hook: BlockHook) -> PipelineBuilder:
        """Add a per-block hook called for each extracted block."""
        self._hooks.on_block_created.append(hook)
        return self

    def on_after_extract_actions(self, hook: ActionHook) -> PipelineBuilder:
        """Add a hook called after action extraction. Can modify actions."""
        self._hooks.after_extract_actions.append(hook)
        return self

    def on_after_compile(self, hook: CompileHook) -> PipelineBuilder:
        """Add a hook called after compilation is complete. Can modify the document."""
        self._hooks.after_compile.append(hook)
        return self

    # --- Build ---

    def build(self) -> CustomPipeline:
        """Build the configured pipeline."""
        return CustomPipeline(
            normalizer=self._normalizer,
            segmenter=self._segmenter,
            action_extractor=self._action_extractor,
            salience_scorer=self._salience_scorer,
            entity_extractor=self._entity_extractor,
            aligner=self._aligner,
            validator=self._validator,
            hooks=self._hooks,
            skip_actions=self._skip_actions,
            skip_salience=self._skip_salience,
            skip_entities=self._skip_entities,
            skip_provenance=self._skip_provenance,
            skip_validation=self._skip_validation,
        )


class CustomPipeline:
    """A compiled pipeline with customized stages and hooks.

    Created via PipelineBuilder. Implements the same compile() interface
    as HTMLCompiler but with pluggable stages.
    """

    def __init__(
        self,
        normalizer: Any = None,
        segmenter: Any = None,
        action_extractor: Any = None,
        salience_scorer: Any = None,
        entity_extractor: Any = None,
        aligner: Any = None,
        validator: Any = None,
        hooks: PipelineHooks | None = None,
        skip_actions: bool = False,
        skip_salience: bool = False,
        skip_entities: bool = False,
        skip_provenance: bool = False,
        skip_validation: bool = False,
    ) -> None:
        self._normalizer = normalizer
        self._segmenter = segmenter
        self._action_extractor = action_extractor
        self._salience_scorer = salience_scorer
        self._entity_extractor = entity_extractor
        self._aligner = aligner
        self._validator = validator
        self._hooks = hooks or PipelineHooks()
        self._skip_actions = skip_actions
        self._skip_salience = skip_salience
        self._skip_entities = skip_entities
        self._skip_provenance = skip_provenance
        self._skip_validation = skip_validation

    def compile(
        self,
        html: str,
        source_url: str | None = None,
        config: CompileConfig | None = None,
    ) -> AgentDocument:
        """Compile HTML into an AgentDocument using the configured pipeline."""
        if config is None:
            config = CompileConfig()

        timings: dict[str, float] = {}
        pipeline_start = time.perf_counter()

        # --- Hook: before normalize ---
        for hook in self._hooks.before_normalize:
            result = hook(html, config)
            if result is not None:
                html = result

        # --- Stage 1: Normalize ---
        t0 = time.perf_counter()
        normalizer = self._normalizer
        if normalizer is None:
            from agent_web_compiler.normalizers.html_normalizer import HTMLNormalizer
            normalizer = HTMLNormalizer()
        cleaned_html = normalizer.normalize(html, config)
        timings["normalize_ms"] = (time.perf_counter() - t0) * 1000

        # --- Hook: after normalize ---
        for hook in self._hooks.after_normalize:
            result = hook(cleaned_html, config)
            if result is not None:
                cleaned_html = result

        # --- Stage 2: Segment ---
        t0 = time.perf_counter()
        segmenter = self._segmenter
        if segmenter is None:
            from agent_web_compiler.segmenters.html_segmenter import HTMLSegmenter
            segmenter = HTMLSegmenter()
        blocks: list[Block] = segmenter.segment(cleaned_html, config)
        timings["segment_ms"] = (time.perf_counter() - t0) * 1000

        # --- Hook: on_block_created ---
        if self._hooks.on_block_created:
            processed: list[Block] = []
            for block in blocks:
                for hook in self._hooks.on_block_created:
                    result = hook(block)
                    if result is not None:
                        block = result
                processed.append(block)
            blocks = processed

        # --- Hook: after segment ---
        for hook in self._hooks.after_segment:
            result = hook(blocks, config)
            if result is not None:
                blocks = result

        # --- Stage 2a: Entity extraction ---
        if not self._skip_entities:
            t0 = time.perf_counter()
            entity_extractor = self._entity_extractor
            if entity_extractor is None:
                from agent_web_compiler.extractors.entity_extractor import EntityExtractor
                entity_extractor = EntityExtractor()
            blocks = entity_extractor.annotate_blocks(blocks)
            timings["entities_ms"] = (time.perf_counter() - t0) * 1000

        # --- Stage 2b: Salience scoring ---
        if not self._skip_salience:
            t0 = time.perf_counter()
            scorer = self._salience_scorer
            if scorer is None:
                from agent_web_compiler.segmenters.salience import SalienceScorer
                scorer = SalienceScorer()
            blocks = scorer.score_blocks(blocks, cleaned_html)
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

        # --- Stage 3: Extract actions ---
        actions: list[Action] = []
        if not self._skip_actions and config.include_actions:
            t0 = time.perf_counter()
            extractor = self._action_extractor
            if extractor is None:
                from agent_web_compiler.extractors.action_extractor import ActionExtractor
                extractor = ActionExtractor()
            actions = extractor.extract(html, config)
            timings["extract_actions_ms"] = (time.perf_counter() - t0) * 1000

        # --- Hook: after extract actions ---
        for hook in self._hooks.after_extract_actions:
            result = hook(actions, config)
            if result is not None:
                actions = result

        # --- Stage 4: Align provenance ---
        if not self._skip_provenance and config.include_provenance:
            t0 = time.perf_counter()
            aligner = self._aligner
            if aligner is None:
                from agent_web_compiler.aligners.dom_aligner import DOMAligner
                aligner = DOMAligner()
            blocks, actions = aligner.align(blocks, actions, html, config)
            timings["align_ms"] = (time.perf_counter() - t0) * 1000

        # --- Stage 5: Validate ---
        from agent_web_compiler.core.document import Quality
        quality = Quality(block_count=len(blocks), action_count=len(actions))
        if not self._skip_validation:
            t0 = time.perf_counter()
            validator = self._validator
            if validator is None:
                from agent_web_compiler.pipeline.validator import DocumentValidator
                validator = DocumentValidator()
            blocks, actions, quality = validator.validate(blocks, actions, cleaned_html, config)
            timings["validate_ms"] = (time.perf_counter() - t0) * 1000

        # --- Stage 6: Build markdown ---
        t0 = time.perf_counter()
        from agent_web_compiler.exporters.markdown_exporter import to_markdown
        canonical_markdown = to_markdown(blocks)
        timings["markdown_ms"] = (time.perf_counter() - t0) * 1000

        # --- Extract title ---
        title = self._extract_title(html, blocks)

        timings["total_ms"] = (time.perf_counter() - pipeline_start) * 1000

        debug: dict[str, Any] = {}
        if config.debug:
            debug["timings"] = timings

        doc = AgentDocument(
            doc_id=AgentDocument.make_doc_id(html),
            source_type=SourceType.HTML,
            source_url=source_url,
            title=title,
            blocks=blocks,
            canonical_markdown=canonical_markdown,
            actions=actions,
            quality=quality,
            compiled_at=datetime.now(timezone.utc),
            debug=debug,
        )

        # --- Hook: after compile ---
        for hook in self._hooks.after_compile:
            result = hook(doc)
            if result is not None:
                doc = result

        return doc

    @staticmethod
    def _extract_title(html: str, blocks: list[Block]) -> str:
        """Extract title from <title> tag or first heading."""
        import re

        from agent_web_compiler.core.block import BlockType

        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if match:
            title = match.group(1).strip()
            if title:
                return title
        for block in blocks:
            if block.type == BlockType.HEADING:
                return block.text
        return ""
