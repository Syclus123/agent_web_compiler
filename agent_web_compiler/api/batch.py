"""Batch compilation -- compile multiple sources with shared context."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from urllib.parse import urlparse

from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.core.document import AgentDocument, SiteProfile


@dataclass
class BatchItem:
    """A single item in a batch compilation request.

    Attributes:
        source: URL or file path to compile.
        source_type: Type hint — "auto", "html", "pdf", "docx".
    """

    source: str
    source_type: str = "auto"  # auto, html, pdf, docx


@dataclass
class BatchResult:
    """Result of a batch compilation.

    Attributes:
        items: Successfully compiled AgentDocuments (in input order, skipping errors).
        site_profile: Learned SiteProfile if multiple pages shared a domain.
        total_time_ms: Wall-clock time for the entire batch.
        errors: Map of source -> error message for failed items.
    """

    items: list[AgentDocument] = field(default_factory=list)
    site_profile: SiteProfile | None = None
    total_time_ms: float = 0.0
    errors: dict[str, str] = field(default_factory=dict)


def _extract_domain(source: str) -> str | None:
    """Extract the domain from a URL, or return None for file paths."""
    if source.startswith(("http://", "https://")):
        parsed = urlparse(source)
        return parsed.netloc or None
    return None


class BatchCompiler:
    """Compiles multiple sources in parallel with shared context.

    When multiple URLs share a domain, automatically learns a SiteProfile
    and applies it to improve normalization.
    """

    def compile_batch(
        self,
        items: list[BatchItem],
        config: CompileConfig | None = None,
        max_concurrency: int = 5,
    ) -> BatchResult:
        """Compile a batch of sources synchronously.

        Args:
            items: List of sources to compile.
            config: Shared compilation config. Uses defaults if not provided.
            max_concurrency: Maximum number of concurrent compilations.

        Returns:
            A BatchResult with compiled documents and any errors.
        """
        if config is None:
            config = CompileConfig()

        start = time.perf_counter()

        results_map: dict[int, AgentDocument] = {}
        errors: dict[str, str] = {}
        learned_profile: SiteProfile | None = None

        # Group by domain for site profile learning
        domain_groups: dict[str, list[int]] = defaultdict(list)
        for i, item in enumerate(items):
            domain = _extract_domain(item.source)
            if domain:
                domain_groups[domain].append(i)

        # For domains with 2+ pages, learn a profile from the first page
        profile_domain: str | None = None
        for domain, indices in domain_groups.items():
            if len(indices) >= 2:
                first_idx = indices[0]
                first_item = items[first_idx]
                try:
                    doc, html = self._compile_single_with_html(first_item, config)
                    results_map[first_idx] = doc

                    # Learn profile from this page
                    from agent_web_compiler.normalizers.site_profile import SiteProfileLearner
                    learner = SiteProfileLearner()
                    learner.observe(domain, html)

                    # Compile second page to strengthen profile
                    if len(indices) >= 2:
                        second_idx = indices[1]
                        second_item = items[second_idx]
                        try:
                            doc2, html2 = self._compile_single_with_html(second_item, config)
                            results_map[second_idx] = doc2
                            learner.observe(domain, html2)
                        except Exception as exc:
                            errors[second_item.source] = str(exc)

                    learned_profile = learner.build_profile(domain)
                    profile_domain = domain
                except Exception as exc:
                    errors[first_item.source] = str(exc)
                # Only learn profile for the first domain with 2+ pages
                break

        # Compile remaining items
        for i, item in enumerate(items):
            if i in results_map:
                continue
            if item.source in errors:
                continue

            try:
                doc = self._compile_single(item, config, learned_profile)
                results_map[i] = doc
            except Exception as exc:
                errors[item.source] = str(exc)

        # Build ordered results list
        ordered_items: list[AgentDocument] = []
        for i in range(len(items)):
            if i in results_map:
                # Attach site profile to documents from the profiled domain
                doc = results_map[i]
                if learned_profile and doc.site_profile is None:
                    domain = _extract_domain(items[i].source)
                    if domain == profile_domain:
                        doc = doc.model_copy(update={"site_profile": learned_profile})
                ordered_items.append(doc)

        total_ms = (time.perf_counter() - start) * 1000

        return BatchResult(
            items=ordered_items,
            site_profile=learned_profile,
            total_time_ms=total_ms,
            errors=errors,
        )

    async def compile_batch_async(
        self,
        items: list[BatchItem],
        config: CompileConfig | None = None,
        max_concurrency: int = 5,
    ) -> BatchResult:
        """Compile a batch of sources asynchronously with concurrency control.

        Args:
            items: List of sources to compile.
            config: Shared compilation config.
            max_concurrency: Maximum number of concurrent compilations.

        Returns:
            A BatchResult with compiled documents and any errors.
        """
        if config is None:
            config = CompileConfig()

        start = time.perf_counter()
        semaphore = asyncio.Semaphore(max_concurrency)

        results_map: dict[int, AgentDocument] = {}
        errors: dict[str, str] = {}
        learned_profile: SiteProfile | None = None
        profile_domain: str | None = None

        # Group by domain for site profile learning
        domain_groups: dict[str, list[int]] = defaultdict(list)
        for i, item in enumerate(items):
            domain = _extract_domain(item.source)
            if domain:
                domain_groups[domain].append(i)

        # Learn profile synchronously from first domain with 2+ pages
        for domain, indices in domain_groups.items():
            if len(indices) >= 2:
                from agent_web_compiler.normalizers.site_profile import SiteProfileLearner
                learner = SiteProfileLearner()

                for idx in indices[:2]:
                    item = items[idx]
                    try:
                        doc, html = self._compile_single_with_html(item, config)
                        results_map[idx] = doc
                        learner.observe(domain, html)
                    except Exception as exc:
                        errors[item.source] = str(exc)

                if learner._domains.get(domain, None) and learner._domains[domain].page_count >= 1:
                    learned_profile = learner.build_profile(domain)
                    profile_domain = domain
                break

        # Compile remaining items concurrently
        async def _compile_item(idx: int, item: BatchItem) -> None:
            async with semaphore:
                try:
                    loop = asyncio.get_event_loop()
                    doc = await loop.run_in_executor(
                        None,
                        self._compile_single,
                        item,
                        config,
                        learned_profile,
                    )
                    results_map[idx] = doc
                except Exception as exc:
                    errors[item.source] = str(exc)

        tasks = []
        for i, item in enumerate(items):
            if i in results_map or item.source in errors:
                continue
            tasks.append(_compile_item(i, item))

        if tasks:
            await asyncio.gather(*tasks)

        # Build ordered results
        ordered_items: list[AgentDocument] = []
        for i in range(len(items)):
            if i in results_map:
                doc = results_map[i]
                if learned_profile and doc.site_profile is None:
                    domain = _extract_domain(items[i].source)
                    if domain == profile_domain:
                        doc = doc.model_copy(update={"site_profile": learned_profile})
                ordered_items.append(doc)

        total_ms = (time.perf_counter() - start) * 1000

        return BatchResult(
            items=ordered_items,
            site_profile=learned_profile,
            total_time_ms=total_ms,
            errors=errors,
        )

    @staticmethod
    def _compile_single(
        item: BatchItem,
        config: CompileConfig,
        profile: SiteProfile | None = None,
    ) -> AgentDocument:
        """Compile a single item."""
        from agent_web_compiler.api.compile import compile_file, compile_url

        source = item.source
        if source.startswith(("http://", "https://")):
            return compile_url(source, config=config)
        else:
            return compile_file(source, config=config)

    @staticmethod
    def _compile_single_with_html(
        item: BatchItem,
        config: CompileConfig,
    ) -> tuple[AgentDocument, str]:
        """Compile a single item and also return the raw HTML for profile learning.

        Returns:
            Tuple of (AgentDocument, raw_html_string).
        """
        from agent_web_compiler.api.compile import compile_html

        source = item.source
        if source.startswith(("http://", "https://")):
            from agent_web_compiler.sources.http_fetcher import HTTPFetcher
            fetcher = HTTPFetcher()
            result = fetcher.fetch_sync(source, config)
            html = result.content if isinstance(result.content, str) else result.content.decode("utf-8")
            doc = compile_html(html, source_url=source, config=config)
            return doc, html
        else:
            from agent_web_compiler.sources.file_reader import FileReader
            reader = FileReader()
            result = reader.read(source)
            html = result.content if isinstance(result.content, str) else result.content.decode("utf-8")
            doc = compile_html(html, config=config)
            return doc, html
