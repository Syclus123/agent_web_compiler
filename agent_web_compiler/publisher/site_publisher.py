"""SitePublisher — the unified SDK for generating agent-friendly site files.

This is the primary entry point for website publishers who want to
make their content agent-native.

Usage:
    from agent_web_compiler.publisher import SitePublisher

    publisher = SitePublisher(
        site_name="My Docs",
        site_url="https://docs.example.com",
        site_description="API documentation for Example platform",
    )

    # Add compiled pages
    publisher.add_page(doc1)
    publisher.add_page(doc2)

    # Or crawl a site
    publisher.crawl_site("https://docs.example.com/", max_pages=50)

    # Generate all files at once
    publisher.generate_all("output/agent-publish/")

    # Or generate individually
    llms_txt = publisher.generate_llms_txt()
    agent_json = publisher.generate_agent_json()
    content_json = publisher.generate_content_json()
    actions_json = publisher.generate_actions_json()
    sitemap_xml = publisher.generate_agent_sitemap()
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from agent_web_compiler.core.document import AgentDocument

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class SitePublisher:
    """Generates agent-friendly files from compiled web content.

    Collects AgentDocuments (via :meth:`add_page` or :meth:`crawl_site`), then
    generates standardised files for agent consumption.

    The generated files follow emerging agent-web standards:

    - ``llms.txt`` — a structured text overview for LLM consumption
    - ``agent.json`` — machine-readable site manifest
    - ``content.json`` — full semantic content with blocks
    - ``actions.json`` — available interactive affordances
    - ``agent-sitemap.xml`` — XML sitemap with agent metadata
    - ``agent-feed.json`` — delta feed of changes (requires previous snapshot)
    """

    def __init__(
        self,
        site_name: str = "",
        site_url: str = "",
        site_description: str = "",
    ) -> None:
        self.site_name = site_name
        self.site_url = site_url
        self.site_description = site_description
        self._docs: list[AgentDocument] = []
        self._previous_docs: list[AgentDocument] = []

    # ------------------------------------------------------------------
    # Add content
    # ------------------------------------------------------------------

    def add_page(self, doc: AgentDocument) -> None:
        """Add a compiled page to the publisher.

        Args:
            doc: A compiled AgentDocument to include in generated output.
        """
        self._docs.append(doc)

    def add_pages(self, docs: list[AgentDocument]) -> None:
        """Add multiple compiled pages.

        Args:
            docs: List of compiled AgentDocuments.
        """
        self._docs.extend(docs)

    def crawl_site(
        self,
        seed_url: str,
        max_pages: int = 50,
        delay_seconds: float = 0.5,
        max_depth: int = 3,
    ) -> int:
        """Crawl a site and add all discovered pages.

        Uses :class:`SiteCrawler` internally to discover and compile pages,
        then adds each compiled document to the publisher.

        Args:
            seed_url: Starting URL. The crawler stays on this domain.
            max_pages: Maximum number of pages to crawl.
            delay_seconds: Politeness delay between requests.
            max_depth: Maximum link depth from the seed URL.

        Returns:
            Number of pages successfully added.
        """
        from agent_web_compiler.sources.crawler import CrawlConfig, SiteCrawler

        crawl_config = CrawlConfig(
            max_pages=max_pages,
            delay_seconds=delay_seconds,
            max_depth=max_depth,
        )
        crawler = SiteCrawler(config=crawl_config)

        # We crawl without a search engine; instead we use a lightweight
        # collector that captures compiled docs directly.
        _collector = _DocCollector()
        crawler.crawl(seed_url, search=_collector)  # type: ignore[arg-type]

        self._docs.extend(_collector.docs)

        # Auto-derive site metadata from the seed URL if not set
        if not self.site_url:
            self.site_url = seed_url
        if not self.site_name:
            parsed = urlparse(seed_url)
            self.site_name = parsed.netloc

        return len(_collector.docs)

    def set_previous_snapshot(self, docs: list[AgentDocument]) -> None:
        """Set the previous snapshot for delta feed generation.

        Args:
            docs: The previous set of compiled documents. Used to compute
                deltas when generating ``agent-feed.json``.
        """
        self._previous_docs = list(docs)

    # ------------------------------------------------------------------
    # Auto-derivation helpers
    # ------------------------------------------------------------------

    def _ensure_site_metadata(self) -> None:
        """Auto-derive site_name and site_url from docs if not set."""
        if self._docs:
            if not self.site_url and self._docs[0].source_url:
                self.site_url = self._docs[0].source_url
            if not self.site_name and self._docs[0].title:
                self.site_name = self._docs[0].title

    # ------------------------------------------------------------------
    # Generate files
    # ------------------------------------------------------------------

    def generate_llms_txt(self) -> str:
        """Generate ``/llms.txt`` content.

        Returns:
            The llms.txt file content as a string.
        """
        self._ensure_site_metadata()

        from agent_web_compiler.publisher.llms_txt import generate_llms_txt

        return generate_llms_txt(
            docs=self._docs,
            site_name=self.site_name,
            site_url=self.site_url,
            site_description=self.site_description,
        )

    def generate_agent_json(self) -> str:
        """Generate ``/agent.json`` content.

        Returns:
            The agent.json file content as a JSON string.
        """
        self._ensure_site_metadata()

        from agent_web_compiler.publisher.content_json import generate_agent_json

        return generate_agent_json(
            docs=self._docs,
            site_name=self.site_name,
            site_url=self.site_url,
            site_description=self.site_description,
        )

    def generate_content_json(self) -> str:
        """Generate ``/content.json`` content.

        Returns:
            The content.json file content as a JSON string.
        """
        self._ensure_site_metadata()

        from agent_web_compiler.publisher.content_json import generate_content_json

        return generate_content_json(
            docs=self._docs,
            site_name=self.site_name,
            site_url=self.site_url,
            site_description=self.site_description,
        )

    def generate_actions_json(self) -> str:
        """Generate ``/actions.json`` content.

        Returns:
            The actions.json file content as a JSON string.
        """
        self._ensure_site_metadata()

        from agent_web_compiler.publisher.actions_json import generate_actions_json

        return generate_actions_json(
            docs=self._docs,
            site_name=self.site_name,
            site_url=self.site_url,
        )

    def generate_agent_sitemap(self) -> str:
        """Generate ``/agent-sitemap.xml`` content.

        Returns:
            The agent-sitemap.xml file content as an XML string.
        """
        self._ensure_site_metadata()

        from agent_web_compiler.publisher.agent_sitemap import generate_agent_sitemap

        return generate_agent_sitemap(
            docs=self._docs,
            site_url=self.site_url,
        )

    def generate_delta_feed(self) -> str:
        """Generate ``/agent-feed.json`` content (requires previous snapshot).

        Call :meth:`set_previous_snapshot` before this to provide baseline docs.

        Returns:
            The agent-feed.json file content as a JSON string.
        """
        self._ensure_site_metadata()

        from agent_web_compiler.publisher.delta_feed import generate_delta_feed

        return generate_delta_feed(
            current_docs=self._docs,
            previous_docs=self._previous_docs,
            site_name=self.site_name,
            site_url=self.site_url,
        )

    def generate_all(self, output_dir: str) -> dict[str, str]:
        """Generate all files and write to *output_dir*.

        Creates the output directory if it does not exist. Generates every
        standard file, plus the delta feed if a previous snapshot is set.

        Args:
            output_dir: Path to the directory where files will be written.

        Returns:
            Dict mapping filename to generated content for each file.
        """
        self._ensure_site_metadata()
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        files: dict[str, str] = {}

        # Generate each file, catching per-file errors to be robust
        generators: list[tuple[str, str]] = [
            ("llms.txt", "generate_llms_txt"),
            ("agent.json", "generate_agent_json"),
            ("content.json", "generate_content_json"),
            ("actions.json", "generate_actions_json"),
            ("agent-sitemap.xml", "generate_agent_sitemap"),
        ]

        # Include delta feed only if a previous snapshot was set
        if self._previous_docs:
            generators.append(("agent-feed.json", "generate_delta_feed"))

        for filename, method_name in generators:
            try:
                content = getattr(self, method_name)()
                (out / filename).write_text(content, encoding="utf-8")
                files[filename] = content
            except Exception as exc:
                logger.error("Failed to generate %s: %s", filename, exc)
                raise

        return files

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def page_count(self) -> int:
        """Number of pages added."""
        return len(self._docs)

    @property
    def docs(self) -> list[AgentDocument]:
        """Read-only access to the collected documents."""
        return list(self._docs)

    @property
    def summary(self) -> dict:
        """Summary of what will be published.

        Returns:
            Dict with site metadata and content statistics.
        """
        self._ensure_site_metadata()
        total_blocks = sum(doc.block_count for doc in self._docs)
        total_actions = sum(doc.action_count for doc in self._docs)
        return {
            "site_name": self.site_name,
            "site_url": self.site_url,
            "site_description": self.site_description,
            "page_count": self.page_count,
            "total_blocks": total_blocks,
            "total_actions": total_actions,
            "has_previous_snapshot": len(self._previous_docs) > 0,
            "files": [
                "llms.txt",
                "agent.json",
                "content.json",
                "actions.json",
                "agent-sitemap.xml",
            ]
            + (["agent-feed.json"] if self._previous_docs else []),
        }


class _DocCollector:
    """Lightweight stand-in for AgentSearch used during crawl_site.

    SiteCrawler expects an object with an ``ingest(doc)`` method.
    This collector simply accumulates the compiled documents.
    """

    def __init__(self) -> None:
        self.docs: list[AgentDocument] = []

    def ingest(self, doc: AgentDocument) -> None:
        """Capture a compiled document."""
        self.docs.append(doc)
