"""Lightweight site crawler -- discovers and compiles pages from a domain.

NOT a general-purpose web crawler. Designed for bounded site-level indexing:
- Stays within the same domain
- Respects max_pages limit
- Polite: configurable delay between requests
- Discovers links from compiled navigation graphs and actions
- Feeds results into AgentSearch for indexing

Usage:
    from agent_web_compiler.sources.crawler import SiteCrawler

    crawler = SiteCrawler()
    results = crawler.crawl("https://docs.example.com/")

    # Or with AgentSearch
    from agent_web_compiler import AgentSearch
    search = AgentSearch()
    search.crawl_site("https://docs.example.com/", max_pages=50)
"""

from __future__ import annotations

import fnmatch
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urldefrag, urljoin, urlparse

from agent_web_compiler.core.action import ActionType
from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.core.document import AgentDocument

if TYPE_CHECKING:
    from agent_web_compiler.search.agent_search import AgentSearch

logger = logging.getLogger(__name__)


@dataclass
class CrawlResult:
    """Result from crawling a site."""

    seed_url: str
    domain: str
    pages_crawled: int = 0
    pages_failed: int = 0
    total_blocks: int = 0
    total_actions: int = 0
    elapsed_seconds: float = 0.0
    errors: dict[str, str] = field(default_factory=dict)  # url -> error message
    urls_crawled: list[str] = field(default_factory=list)


@dataclass
class CrawlConfig:
    """Configuration for site crawling.

    Attributes:
        max_pages: Maximum number of pages to crawl.
        delay_seconds: Politeness delay between requests in seconds.
        max_depth: Maximum link depth from the seed URL.
        same_domain_only: Whether to restrict crawling to the seed domain.
        exclude_patterns: URL patterns to skip (glob-style, matched against path).
        include_patterns: URL patterns to include (if set, only matching URLs are crawled).
        timeout_per_page: Timeout in seconds for fetching each page.
    """

    max_pages: int = 50
    delay_seconds: float = 0.5
    max_depth: int = 3
    same_domain_only: bool = True
    exclude_patterns: list[str] = field(default_factory=list)
    include_patterns: list[str] = field(default_factory=list)
    timeout_per_page: float = 15.0


class SiteCrawler:
    """Bounded site crawler for documentation/site indexing.

    Starts from a seed URL, discovers links via BFS, and compiles each page.
    Stays within the same domain and respects the max_pages limit.

    Link discovery sources:
    1. Actions with type == NAVIGATE and a target_url in state_effect
    2. Navigation graph nodes with node_type == "page" and a url
    """

    def __init__(
        self,
        config: CrawlConfig | None = None,
        *,
        fetcher: object | None = None,
        compiler: object | None = None,
    ) -> None:
        self.config = config or CrawlConfig()
        self._fetcher = fetcher
        self._compiler = compiler

    def _get_fetcher(self) -> object:
        """Return the HTTP fetcher, creating a default if needed."""
        if self._fetcher is None:
            from agent_web_compiler.sources.http_fetcher import HTTPFetcher

            self._fetcher = HTTPFetcher()
        return self._fetcher

    def _get_compiler(self) -> object:
        """Return the HTML compiler, creating a default if needed."""
        if self._compiler is None:
            from agent_web_compiler.pipeline.compiler import HTMLCompiler

            self._compiler = HTMLCompiler()
        return self._compiler

    def crawl(
        self,
        seed_url: str,
        search: AgentSearch | None = None,
    ) -> CrawlResult:
        """Crawl a site starting from seed_url.

        Uses breadth-first traversal. For each page:
        1. Fetch HTML via HTTPFetcher
        2. Compile with HTMLCompiler
        3. Optionally ingest into AgentSearch index
        4. Extract outgoing links from actions and navigation graph
        5. Filter and enqueue new URLs

        Args:
            seed_url: The starting URL. The domain is extracted from this.
            search: If provided, each compiled page is ingested into the index.

        Returns:
            A CrawlResult summarising what was crawled.
        """
        parsed_seed = urlparse(seed_url)
        domain = parsed_seed.netloc
        compile_config = CompileConfig(timeout_seconds=self.config.timeout_per_page)

        fetcher = self._get_fetcher()
        compiler = self._get_compiler()

        # BFS state: (url, depth)
        queue: deque[tuple[str, int]] = deque()
        visited: set[str] = set()

        seed_normalised = _normalise_url(seed_url)
        queue.append((seed_normalised, 0))
        visited.add(seed_normalised)

        result = CrawlResult(seed_url=seed_url, domain=domain)
        start = time.monotonic()

        while queue and result.pages_crawled < self.config.max_pages:
            url, depth = queue.popleft()

            logger.info("Crawling [depth=%d]: %s", depth, url)

            # Fetch
            try:
                fetch_result = fetcher.fetch_sync(url, compile_config)
                content = (
                    fetch_result.content
                    if isinstance(fetch_result.content, str)
                    else fetch_result.content.decode("utf-8")
                )
            except Exception as exc:
                logger.warning("Failed to fetch %s: %s", url, exc)
                result.pages_failed += 1
                result.errors[url] = str(exc)
                continue

            # Compile
            try:
                doc = compiler.compile(content, source_url=url, config=compile_config)
            except Exception as exc:
                logger.warning("Failed to compile %s: %s", url, exc)
                result.pages_failed += 1
                result.errors[url] = str(exc)
                continue

            # Ingest into search index
            if search is not None:
                try:
                    search.ingest(doc)
                except Exception as exc:
                    logger.warning("Failed to ingest %s: %s", url, exc)
                    # Non-fatal: we still count the page as crawled

            result.pages_crawled += 1
            result.urls_crawled.append(url)
            result.total_blocks += doc.block_count
            result.total_actions += doc.action_count

            # Discover new links (only if we haven't hit max depth)
            if depth < self.config.max_depth:
                discovered = _extract_links(doc, url)
                for link in discovered:
                    normalised = _normalise_url(link)
                    if normalised in visited:
                        continue
                    if not self._should_crawl(normalised, domain):
                        continue
                    visited.add(normalised)
                    queue.append((normalised, depth + 1))

            # Politeness delay (skip after the last page)
            if queue and result.pages_crawled < self.config.max_pages:
                time.sleep(self.config.delay_seconds)

        result.elapsed_seconds = time.monotonic() - start
        logger.info(
            "Crawl complete: %d pages crawled, %d failed in %.1fs",
            result.pages_crawled,
            result.pages_failed,
            result.elapsed_seconds,
        )
        return result

    def _should_crawl(self, url: str, seed_domain: str) -> bool:
        """Decide whether a URL should be enqueued for crawling.

        Checks:
        - same domain (if same_domain_only is set)
        - not matching any exclude_patterns
        - matching include_patterns (if any are set)
        """
        parsed = urlparse(url)

        # Same-domain check
        if self.config.same_domain_only and parsed.netloc != seed_domain:
            return False

        path = parsed.path

        # Exclude patterns (glob against path)
        for pattern in self.config.exclude_patterns:
            if fnmatch.fnmatch(path, pattern):
                return False

        # Include patterns (if specified, URL must match at least one)
        if self.config.include_patterns and not any(
            fnmatch.fnmatch(path, p) for p in self.config.include_patterns
        ):
            return False

        # Skip non-HTML-looking extensions
        return not _is_non_html_extension(path)


def _extract_links(doc: AgentDocument, base_url: str) -> list[str]:
    """Extract outgoing URLs from a compiled AgentDocument.

    Sources:
    1. Actions with type == NAVIGATE and state_effect.target_url
    2. Navigation graph nodes with node_type == "page" and a url
    """
    urls: list[str] = []

    # From actions
    for action in doc.actions:
        if action.type == ActionType.NAVIGATE and action.state_effect:
            target = action.state_effect.target_url
            if target:
                absolute = urljoin(base_url, target)
                urls.append(absolute)

    # From navigation graph
    nav = doc.navigation_graph
    if isinstance(nav, dict):
        nodes = nav.get("nodes", [])
        for node in nodes:
            if isinstance(node, dict) and node.get("node_type") == "page" and node.get("url"):
                absolute = urljoin(base_url, node["url"])
                urls.append(absolute)

    return urls


def _normalise_url(url: str) -> str:
    """Normalise a URL for deduplication.

    - Strips fragment
    - Strips trailing slash (except for root path)
    """
    url_no_frag, _ = urldefrag(url)
    parsed = urlparse(url_no_frag)
    path = parsed.path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return parsed._replace(path=path, fragment="").geturl()


# Common non-HTML file extensions to skip
_NON_HTML_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".pdf", ".zip", ".tar", ".gz", ".bz2",
    ".css", ".js", ".woff", ".woff2", ".ttf", ".eot",
    ".mp3", ".mp4", ".avi", ".mov", ".wmv",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".xml", ".rss", ".atom",
})


def _is_non_html_extension(path: str) -> bool:
    """Return True if the URL path has a known non-HTML extension."""
    # Extract extension from the last path segment
    last_segment = path.rsplit("/", 1)[-1]
    dot_pos = last_segment.rfind(".")
    if dot_pos == -1:
        return False
    ext = last_segment[dot_pos:].lower()
    return ext in _NON_HTML_EXTENSIONS
