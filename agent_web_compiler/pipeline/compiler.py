"""HTMLCompiler — orchestrates the full compilation pipeline.

Pipeline stages:
    fetch/render -> normalize -> segment -> score_salience -> filter_query
    -> extract_actions -> align -> validate -> build_document
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

from agent_web_compiler.core.action import Action
from agent_web_compiler.core.block import Block
from agent_web_compiler.core.config import CompileConfig, RenderMode
from agent_web_compiler.core.document import AgentDocument, SourceType
from agent_web_compiler.core.errors import ParseError

logger = logging.getLogger(__name__)

# Heuristic: bytes that are extremely unlikely in text/HTML
_BINARY_PROBE_SIZE = 512
_BINARY_THRESHOLD = 0.30  # if >30% of first bytes are non-text, treat as binary


def _looks_binary(content: str) -> bool:
    """Return True if *content* appears to be binary (not text/HTML)."""
    probe = content[:_BINARY_PROBE_SIZE]
    if not probe:
        return False
    non_text = sum(1 for ch in probe if ord(ch) < 9 or (13 < ord(ch) < 32))
    return (non_text / len(probe)) > _BINARY_THRESHOLD


def _looks_like_html(content: str) -> bool:
    """Return True if *content* has at least one HTML tag."""
    return bool(re.search(r"<[a-zA-Z][^>]*>", content))


def _wrap_plain_text(content: str) -> str:
    """Wrap plain text content in minimal HTML structure."""
    lines = content.strip().splitlines()
    paragraphs = []
    for line in lines:
        stripped = line.strip()
        if stripped:
            from html import escape
            paragraphs.append(f"<p>{escape(stripped)}</p>")
    body = "\n".join(paragraphs) if paragraphs else "<p></p>"
    return f"<html><body>{body}</body></html>"


class HTMLCompiler:
    """Compiles raw HTML into an AgentDocument through a staged pipeline.

    Each stage is explicit and independently testable. The pipeline shape is:
    fetch/render -> normalize -> segment -> score_salience -> filter_query
    -> extract_actions -> align -> validate -> build_document
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

        Raises:
            ParseError: If the content is binary and cannot be parsed.
        """
        if config is None:
            config = CompileConfig()

        warnings: list[str] = []

        # --- Content type detection ---
        if _looks_binary(html):
            raise ParseError(
                "Content appears to be binary (not text/HTML). "
                "Binary content cannot be compiled.",
                context={"content_length": len(html)},
            )

        if not _looks_like_html(html) and html.strip():
                # Plain text — wrap in HTML
                warnings.append("Input has no HTML tags; wrapped plain text in <p> elements")
                html = _wrap_plain_text(html)
            # else: empty input, will produce empty doc

        # --- Cache check ---
        from agent_web_compiler.pipeline.cache import CompilationCache

        cache: CompilationCache | None = None
        content_hash: str | None = None
        if config.cache_dir is not None:
            cache = CompilationCache(
                cache_dir=config.cache_dir,
                default_ttl=config.cache_ttl,
            )
            content_hash = CompilationCache.hash_content(html)
            cached_doc = cache.get(content_hash)
            if cached_doc is not None:
                logger.debug("Cache hit for %s", content_hash)
                return cached_doc

        timings: dict[str, float] = {}
        pipeline_start = time.perf_counter()
        deadline = pipeline_start + config.timeout_seconds
        dynamic_rendered = False
        render_metadata: dict[str, Any] = {}
        partial = False

        def _check_timeout(stage_name: str) -> bool:
            """Return True if we have exceeded the deadline."""
            if time.perf_counter() > deadline:
                warnings.append(f"Pipeline timeout after {config.timeout_seconds}s at stage '{stage_name}'")
                return True
            return False

        # --- Stage 0: Dynamic rendering (when applicable) ---
        if source_url and config.render in (RenderMode.AUTO, RenderMode.ALWAYS):
            rendered_html, dynamic_rendered, render_metadata, render_time = (
                self._maybe_render(html, source_url, config)
            )
            if dynamic_rendered:
                html = rendered_html
                timings["render_ms"] = render_time

        # --- Stage 1: Normalize ---
        t0 = time.perf_counter()
        from agent_web_compiler.normalizers.html_normalizer import HTMLNormalizer

        cleaned_html = HTMLNormalizer().normalize(html, config)
        timings["normalize_ms"] = (time.perf_counter() - t0) * 1000

        if _check_timeout("normalize"):
            partial = True

        # --- Stage 2: Segment ---
        blocks: list[Block] = []
        if not partial:
            t0 = time.perf_counter()
            from agent_web_compiler.segmenters.html_segmenter import HTMLSegmenter

            blocks = HTMLSegmenter().segment(cleaned_html, config)
            timings["segment_ms"] = (time.perf_counter() - t0) * 1000

            if _check_timeout("segment"):
                partial = True

        # --- Stage 2a+: Entity extraction ---
        if not partial and blocks:
            t0 = time.perf_counter()
            from agent_web_compiler.extractors.entity_extractor import EntityExtractor

            blocks = EntityExtractor().annotate_blocks(blocks)
            timings["entity_extraction_ms"] = (time.perf_counter() - t0) * 1000

            if _check_timeout("entity_extraction"):
                partial = True

        # --- Stage 2b: Advanced salience scoring ---
        if not partial and blocks:
            t0 = time.perf_counter()
            from agent_web_compiler.segmenters.salience import SalienceScorer

            blocks = SalienceScorer().score_blocks(blocks, cleaned_html)
            timings["salience_ms"] = (time.perf_counter() - t0) * 1000

            if _check_timeout("salience"):
                partial = True

        # --- Stage 2c: Query-aware filtering ---
        if not partial and config.query:
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

        # --- Stage 3: Extract actions (from original HTML) ---
        actions: list[Action] = []
        if not partial and config.include_actions:
            t0 = time.perf_counter()
            from agent_web_compiler.extractors.action_extractor import ActionExtractor

            actions = ActionExtractor().extract(html, config)
            timings["extract_actions_ms"] = (time.perf_counter() - t0) * 1000

            if _check_timeout("extract_actions"):
                partial = True

        # --- Stage 3b: Extract assets ---
        from agent_web_compiler.core.document import Asset

        assets: list[Asset] = []
        if not partial:
            t0 = time.perf_counter()
            from agent_web_compiler.extractors.asset_extractor import AssetExtractor

            assets = AssetExtractor().extract(html)
            timings["extract_assets_ms"] = (time.perf_counter() - t0) * 1000

        # --- Stage 3c: Build navigation graph ---
        nav_graph_dict: dict | None = None
        if not partial and actions:
            t0 = time.perf_counter()
            from agent_web_compiler.extractors.nav_graph import NavGraphBuilder

            nav_graph = NavGraphBuilder().build(actions, source_url=source_url)
            nav_graph_dict = nav_graph.to_dict()
            timings["nav_graph_ms"] = (time.perf_counter() - t0) * 1000

        # --- Stage 3d: Build provenance index ---
        provenance_index = self._build_provenance_index(blocks)

        # --- Stage 4: Align provenance ---
        if not partial and config.include_provenance:
            t0 = time.perf_counter()
            from agent_web_compiler.aligners.dom_aligner import DOMAligner

            blocks, actions = DOMAligner().align(blocks, actions, html, config)
            timings["align_ms"] = (time.perf_counter() - t0) * 1000

        # --- Stage 5: Validate ---
        t0 = time.perf_counter()
        from agent_web_compiler.pipeline.validator import DocumentValidator

        blocks, actions, quality = DocumentValidator().validate(
            blocks, actions, cleaned_html, config,
        )
        quality.dynamic_rendered = dynamic_rendered
        timings["validate_ms"] = (time.perf_counter() - t0) * 1000

        # --- Stage 6: Build canonical markdown ---
        t0 = time.perf_counter()
        from agent_web_compiler.exporters.markdown_exporter import to_markdown

        canonical_markdown = to_markdown(blocks)
        timings["markdown_ms"] = (time.perf_counter() - t0) * 1000

        # --- Stage 6b: Token budget compression ---
        if config.token_budget is not None and config.token_budget > 0:
            t0 = time.perf_counter()
            from agent_web_compiler.exporters.token_budget import (
                TokenBudgetController,
            )

            budget_ctrl = TokenBudgetController(config.token_budget)
            canonical_markdown = budget_ctrl.to_budget_markdown(blocks)
            timings["token_budget_ms"] = (time.perf_counter() - t0) * 1000

        timings["total_ms"] = (time.perf_counter() - pipeline_start) * 1000

        # --- Merge warnings ---
        if partial:
            warnings.append("Compilation result is partial due to timeout")
        quality.warnings.extend(warnings)

        # --- Extract title ---
        title = self._extract_title(html, blocks)

        # --- Build document ---
        debug: dict[str, Any] = {}
        if config.debug:
            debug["timings"] = timings
            if render_metadata:
                debug["render"] = {
                    k: v
                    for k, v in render_metadata.items()
                    if k not in ("screenshot_png",)
                }
                if "screenshot_png" in render_metadata:
                    debug["screenshot_png"] = render_metadata["screenshot_png"]

        doc_id = AgentDocument.make_doc_id(html)

        doc = AgentDocument(
            doc_id=doc_id,
            source_type=SourceType.HTML,
            source_url=source_url,
            title=title,
            blocks=blocks,
            canonical_markdown=canonical_markdown,
            actions=actions,
            navigation_graph=nav_graph_dict,
            assets=assets,
            provenance_index=provenance_index,
            quality=quality,
            compiled_at=datetime.now(timezone.utc),
            debug=debug,
        )

        # --- Cache store ---
        if cache is not None and content_hash is not None:
            try:
                cache.put(content_hash, doc)
                logger.debug("Cached result for %s", content_hash)
            except Exception as exc:
                logger.warning("Failed to cache result: %s", exc)

        return doc

    @staticmethod
    def _build_provenance_index(blocks: list[Block]) -> dict[str, list[str]]:
        """Build a reverse lookup from section paths to block IDs.

        Maps each unique section path (joined with ' > ') to the list of
        block IDs that belong to that section.

        Args:
            blocks: List of blocks with section_path populated.

        Returns:
            Dict mapping section path strings to lists of block IDs.
        """
        index: dict[str, list[str]] = {}
        for block in blocks:
            key = " > ".join(block.section_path) if block.section_path else "(root)"
            if key not in index:
                index[key] = []
            index[key].append(block.id)
        return index

    @staticmethod
    def _maybe_render(
        html: str,
        source_url: str,
        config: CompileConfig,
    ) -> tuple[str, bool, dict[str, Any], float]:
        """Conditionally render a page with Playwright.

        For RenderMode.ALWAYS, always renders. For RenderMode.AUTO, checks the
        needs_rendering heuristic first and only renders if needed.

        Args:
            html: Raw HTML already fetched via HTTP.
            source_url: URL to render.
            config: Compilation config.

        Returns:
            Tuple of (html, was_rendered, render_metadata, render_time_ms).
            If not rendered, returns the original html with empty metadata.
        """
        from agent_web_compiler.sources.playwright_fetcher import (
            PlaywrightFetcher,
            detect_needs_rendering,
        )

        should_render = config.render == RenderMode.ALWAYS

        if config.render == RenderMode.AUTO:
            should_render = detect_needs_rendering(html)
            if not should_render:
                logger.debug(
                    "AUTO render: page does not appear to need rendering, skipping"
                )
                return html, False, {}, 0.0

        if not should_render:
            return html, False, {}, 0.0

        logger.info("Rendering %s with Playwright", source_url)
        t0 = time.perf_counter()

        fetcher = PlaywrightFetcher()
        result = fetcher.fetch_sync(source_url, config)

        render_time_ms = (time.perf_counter() - t0) * 1000
        return result.content, True, result.metadata, render_time_ms

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
