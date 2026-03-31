"""Tests for the site crawler module.

All tests are offline — HTTP fetching and compilation are mocked.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from agent_web_compiler.core.action import Action, ActionType, StateEffect
from agent_web_compiler.core.document import AgentDocument, Quality, SourceType
from agent_web_compiler.sources.crawler import (
    CrawlConfig,
    CrawlResult,
    SiteCrawler,
    _extract_links,
    _is_non_html_extension,
    _normalise_url,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc(
    url: str,
    actions: list[Action] | None = None,
    navigation_graph: dict | None = None,
    blocks: list | None = None,
) -> AgentDocument:
    """Create a minimal AgentDocument for testing."""
    return AgentDocument(
        doc_id=AgentDocument.make_doc_id(url),
        source_type=SourceType.HTML,
        source_url=url,
        title=f"Page: {url}",
        blocks=blocks or [],
        actions=actions or [],
        navigation_graph=navigation_graph,
        quality=Quality(),
    )


def _make_navigate_action(target_url: str) -> Action:
    """Create a NAVIGATE action pointing to target_url."""
    return Action(
        id=f"a_{hash(target_url) % 10000}",
        type=ActionType.NAVIGATE,
        label=f"Link to {target_url}",
        state_effect=StateEffect(may_navigate=True, target_url=target_url),
    )


def _make_fake_fetcher_and_compiler(
    pages: dict[str, AgentDocument],
) -> tuple[MagicMock, MagicMock]:
    """Create mock fetcher and compiler that serve pre-built pages.

    Returns (fetcher, compiler) mocks suitable for SiteCrawler constructor injection.
    """
    fetcher = MagicMock()

    def fake_fetch_sync(url: str, config: Any) -> MagicMock:
        normalised = _normalise_url(url)
        for page_url in pages:
            if _normalise_url(page_url) == normalised:
                result = MagicMock()
                result.content = f"<html><body>Content of {url}</body></html>"
                return result
        raise Exception(f"Not found: {url}")

    fetcher.fetch_sync.side_effect = fake_fetch_sync

    compiler = MagicMock()

    def fake_compile(
        html: str, source_url: str = "", config: Any = None
    ) -> AgentDocument:
        normalised = _normalise_url(source_url)
        for page_url, doc in pages.items():
            if _normalise_url(page_url) == normalised:
                return doc
        raise Exception(f"No mock page for {source_url}")

    compiler.compile.side_effect = fake_compile

    return fetcher, compiler


# ---------------------------------------------------------------------------
# CrawlConfig defaults
# ---------------------------------------------------------------------------


class TestCrawlConfig:
    def test_defaults(self) -> None:
        cfg = CrawlConfig()
        assert cfg.max_pages == 50
        assert cfg.delay_seconds == 0.5
        assert cfg.max_depth == 3
        assert cfg.same_domain_only is True
        assert cfg.exclude_patterns == []
        assert cfg.include_patterns == []
        assert cfg.timeout_per_page == 15.0

    def test_custom_values(self) -> None:
        cfg = CrawlConfig(max_pages=10, delay_seconds=1.0, max_depth=2)
        assert cfg.max_pages == 10
        assert cfg.delay_seconds == 1.0
        assert cfg.max_depth == 2


# ---------------------------------------------------------------------------
# CrawlResult fields
# ---------------------------------------------------------------------------


class TestCrawlResult:
    def test_defaults(self) -> None:
        r = CrawlResult(seed_url="https://example.com", domain="example.com")
        assert r.seed_url == "https://example.com"
        assert r.domain == "example.com"
        assert r.pages_crawled == 0
        assert r.pages_failed == 0
        assert r.total_blocks == 0
        assert r.total_actions == 0
        assert r.elapsed_seconds == 0.0
        assert r.errors == {}
        assert r.urls_crawled == []


# ---------------------------------------------------------------------------
# URL normalisation
# ---------------------------------------------------------------------------


class TestNormaliseUrl:
    def test_strips_fragment(self) -> None:
        assert _normalise_url("https://ex.com/page#section") == "https://ex.com/page"

    def test_strips_trailing_slash(self) -> None:
        assert _normalise_url("https://ex.com/page/") == "https://ex.com/page"

    def test_preserves_root_slash(self) -> None:
        assert _normalise_url("https://ex.com/") == "https://ex.com/"

    def test_no_change_needed(self) -> None:
        assert _normalise_url("https://ex.com/page") == "https://ex.com/page"


# ---------------------------------------------------------------------------
# Non-HTML extension check
# ---------------------------------------------------------------------------


class TestNonHtmlExtension:
    def test_html_paths(self) -> None:
        assert _is_non_html_extension("/docs/guide") is False
        assert _is_non_html_extension("/docs/guide.html") is False
        assert _is_non_html_extension("/docs/guide.htm") is False

    def test_non_html_paths(self) -> None:
        assert _is_non_html_extension("/img/logo.png") is True
        assert _is_non_html_extension("/file.pdf") is True
        assert _is_non_html_extension("/style.css") is True
        assert _is_non_html_extension("/script.js") is True

    def test_no_extension(self) -> None:
        assert _is_non_html_extension("/api/endpoint") is False


# ---------------------------------------------------------------------------
# Link extraction
# ---------------------------------------------------------------------------


class TestExtractLinks:
    def test_from_navigate_actions(self) -> None:
        doc = _make_doc(
            "https://docs.example.com/",
            actions=[
                _make_navigate_action("/getting-started"),
                _make_navigate_action("https://docs.example.com/api"),
            ],
        )
        links = _extract_links(doc, "https://docs.example.com/")
        assert "https://docs.example.com/getting-started" in links
        assert "https://docs.example.com/api" in links

    def test_from_navigation_graph(self) -> None:
        nav_graph = {
            "nodes": [
                {"id": "n1", "label": "Home", "url": "/", "node_type": "page"},
                {"id": "n2", "label": "Guide", "url": "/guide", "node_type": "page"},
                {"id": "n3", "label": "Modal", "url": None, "node_type": "modal"},
            ],
            "edges": [],
        }
        doc = _make_doc("https://docs.example.com/", navigation_graph=nav_graph)
        links = _extract_links(doc, "https://docs.example.com/")
        assert "https://docs.example.com/" in links
        assert "https://docs.example.com/guide" in links
        assert len(links) == 2  # modal node excluded (no url)

    def test_no_links(self) -> None:
        doc = _make_doc("https://example.com/")
        links = _extract_links(doc, "https://example.com/")
        assert links == []

    def test_skips_actions_without_target_url(self) -> None:
        action = Action(
            id="a_1",
            type=ActionType.NAVIGATE,
            label="Empty link",
            state_effect=StateEffect(may_navigate=True, target_url=None),
        )
        doc = _make_doc("https://example.com/", actions=[action])
        links = _extract_links(doc, "https://example.com/")
        assert links == []

    def test_skips_non_navigate_actions(self) -> None:
        action = Action(
            id="a_1",
            type=ActionType.CLICK,
            label="A button",
            state_effect=StateEffect(target_url="https://example.com/other"),
        )
        doc = _make_doc("https://example.com/", actions=[action])
        links = _extract_links(doc, "https://example.com/")
        assert links == []

    def test_relative_url_resolution(self) -> None:
        doc = _make_doc(
            "https://docs.example.com/guide/",
            actions=[_make_navigate_action("../api")],
        )
        links = _extract_links(doc, "https://docs.example.com/guide/")
        assert "https://docs.example.com/api" in links


# ---------------------------------------------------------------------------
# URL filtering (_should_crawl)
# ---------------------------------------------------------------------------


class TestShouldCrawl:
    def test_same_domain(self) -> None:
        crawler = SiteCrawler(CrawlConfig(same_domain_only=True))
        assert crawler._should_crawl("https://example.com/page", "example.com") is True
        assert crawler._should_crawl("https://other.com/page", "example.com") is False

    def test_cross_domain_allowed(self) -> None:
        crawler = SiteCrawler(CrawlConfig(same_domain_only=False))
        assert crawler._should_crawl("https://other.com/page", "example.com") is True

    def test_exclude_patterns(self) -> None:
        crawler = SiteCrawler(CrawlConfig(exclude_patterns=["*/admin/*", "*/login"]))
        assert (
            crawler._should_crawl(
                "https://example.com/admin/settings", "example.com"
            )
            is False
        )
        assert (
            crawler._should_crawl("https://example.com/login", "example.com") is False
        )
        assert (
            crawler._should_crawl("https://example.com/docs/api", "example.com")
            is True
        )

    def test_include_patterns(self) -> None:
        crawler = SiteCrawler(CrawlConfig(include_patterns=["/docs/*"]))
        assert (
            crawler._should_crawl("https://example.com/docs/api", "example.com")
            is True
        )
        assert (
            crawler._should_crawl("https://example.com/blog/post", "example.com")
            is False
        )

    def test_skips_non_html_extensions(self) -> None:
        crawler = SiteCrawler()
        assert (
            crawler._should_crawl("https://example.com/image.png", "example.com")
            is False
        )
        assert (
            crawler._should_crawl("https://example.com/file.pdf", "example.com")
            is False
        )
        assert (
            crawler._should_crawl("https://example.com/page", "example.com") is True
        )


# ---------------------------------------------------------------------------
# Crawl integration (injected mock fetcher + compiler)
# ---------------------------------------------------------------------------


class TestSiteCrawlerCrawl:
    """Test the crawl() method with injected mock fetcher and compiler."""

    def test_basic_crawl(self) -> None:
        """Crawl a simple two-page site."""
        pages = {
            "https://docs.example.com/": _make_doc(
                "https://docs.example.com/",
                actions=[_make_navigate_action("/guide")],
            ),
            "https://docs.example.com/guide": _make_doc(
                "https://docs.example.com/guide",
            ),
        }
        fetcher, compiler = _make_fake_fetcher_and_compiler(pages)
        crawler = SiteCrawler(
            CrawlConfig(max_pages=10, delay_seconds=0),
            fetcher=fetcher,
            compiler=compiler,
        )
        result = crawler.crawl("https://docs.example.com/")

        assert result.pages_crawled == 2
        assert result.pages_failed == 0
        assert len(result.urls_crawled) == 2
        assert result.domain == "docs.example.com"

    def test_max_pages_limit(self) -> None:
        """Crawl stops at max_pages."""
        pages = {
            "https://example.com/": _make_doc(
                "https://example.com/",
                actions=[
                    _make_navigate_action("/a"),
                    _make_navigate_action("/b"),
                    _make_navigate_action("/c"),
                ],
            ),
            "https://example.com/a": _make_doc("https://example.com/a"),
            "https://example.com/b": _make_doc("https://example.com/b"),
            "https://example.com/c": _make_doc("https://example.com/c"),
        }
        fetcher, compiler = _make_fake_fetcher_and_compiler(pages)
        crawler = SiteCrawler(
            CrawlConfig(max_pages=2, delay_seconds=0),
            fetcher=fetcher,
            compiler=compiler,
        )
        result = crawler.crawl("https://example.com/")

        assert result.pages_crawled == 2

    def test_max_depth_limit(self) -> None:
        """Crawl stops discovering links beyond max_depth."""
        pages = {
            "https://example.com/": _make_doc(
                "https://example.com/",
                actions=[_make_navigate_action("/a")],
            ),
            "https://example.com/a": _make_doc(
                "https://example.com/a",
                actions=[_make_navigate_action("/b")],
            ),
            "https://example.com/b": _make_doc(
                "https://example.com/b",
                actions=[_make_navigate_action("/c")],
            ),
            "https://example.com/c": _make_doc("https://example.com/c"),
        }
        fetcher, compiler = _make_fake_fetcher_and_compiler(pages)
        crawler = SiteCrawler(
            CrawlConfig(max_pages=100, max_depth=2, delay_seconds=0),
            fetcher=fetcher,
            compiler=compiler,
        )
        result = crawler.crawl("https://example.com/")

        # seed(depth=0) -> /a(depth=1) -> /b(depth=2) -> /c would be depth=3 (blocked)
        assert result.pages_crawled == 3
        assert "https://example.com/c" not in result.urls_crawled

    def test_fetch_failure_counted(self) -> None:
        """Failed fetches are recorded in errors."""
        pages = {
            "https://example.com/": _make_doc(
                "https://example.com/",
                actions=[_make_navigate_action("/broken")],
            ),
            # /broken intentionally missing from pages dict
        }
        fetcher, compiler = _make_fake_fetcher_and_compiler(pages)
        crawler = SiteCrawler(
            CrawlConfig(max_pages=10, delay_seconds=0),
            fetcher=fetcher,
            compiler=compiler,
        )
        result = crawler.crawl("https://example.com/")

        assert result.pages_crawled == 1
        assert result.pages_failed == 1
        assert "https://example.com/broken" in result.errors

    def test_cross_domain_links_filtered(self) -> None:
        """Cross-domain links are not followed."""
        pages = {
            "https://example.com/": _make_doc(
                "https://example.com/",
                actions=[_make_navigate_action("https://other.com/page")],
            ),
        }
        fetcher, compiler = _make_fake_fetcher_and_compiler(pages)
        crawler = SiteCrawler(
            CrawlConfig(max_pages=10, delay_seconds=0),
            fetcher=fetcher,
            compiler=compiler,
        )
        result = crawler.crawl("https://example.com/")

        assert result.pages_crawled == 1
        assert len(result.urls_crawled) == 1

    def test_deduplicates_urls(self) -> None:
        """Same URL (with fragment/trailing slash variants) is only crawled once."""
        pages = {
            "https://example.com/": _make_doc(
                "https://example.com/",
                actions=[
                    _make_navigate_action("/page"),
                    _make_navigate_action("/page/"),
                    _make_navigate_action("/page#section"),
                ],
            ),
            "https://example.com/page": _make_doc("https://example.com/page"),
        }
        fetcher, compiler = _make_fake_fetcher_and_compiler(pages)
        crawler = SiteCrawler(
            CrawlConfig(max_pages=10, delay_seconds=0),
            fetcher=fetcher,
            compiler=compiler,
        )
        result = crawler.crawl("https://example.com/")

        assert result.pages_crawled == 2  # seed + /page (only once)

    def test_crawl_with_search_ingest(self) -> None:
        """When search is provided, ingest is called for each page."""
        pages = {
            "https://example.com/": _make_doc(
                "https://example.com/",
                actions=[_make_navigate_action("/page")],
            ),
            "https://example.com/page": _make_doc("https://example.com/page"),
        }
        fetcher, compiler = _make_fake_fetcher_and_compiler(pages)
        mock_search = MagicMock()
        crawler = SiteCrawler(
            CrawlConfig(max_pages=10, delay_seconds=0),
            fetcher=fetcher,
            compiler=compiler,
        )
        result = crawler.crawl("https://example.com/", search=mock_search)

        assert mock_search.ingest.call_count == 2
        assert result.pages_crawled == 2

    def test_nav_graph_link_discovery(self) -> None:
        """Links are discovered from the navigation_graph dict."""
        nav_graph = {
            "nodes": [
                {"id": "n1", "label": "API", "url": "/api", "node_type": "page"},
            ],
            "edges": [],
        }
        pages = {
            "https://example.com/": _make_doc(
                "https://example.com/",
                navigation_graph=nav_graph,
            ),
            "https://example.com/api": _make_doc("https://example.com/api"),
        }
        fetcher, compiler = _make_fake_fetcher_and_compiler(pages)
        crawler = SiteCrawler(
            CrawlConfig(max_pages=10, delay_seconds=0),
            fetcher=fetcher,
            compiler=compiler,
        )
        result = crawler.crawl("https://example.com/")

        assert result.pages_crawled == 2
        assert "https://example.com/api" in result.urls_crawled

    def test_elapsed_seconds_populated(self) -> None:
        """elapsed_seconds is set after crawl."""
        pages = {
            "https://example.com/": _make_doc("https://example.com/"),
        }
        fetcher, compiler = _make_fake_fetcher_and_compiler(pages)
        crawler = SiteCrawler(
            CrawlConfig(max_pages=5, delay_seconds=0),
            fetcher=fetcher,
            compiler=compiler,
        )
        result = crawler.crawl("https://example.com/")

        assert result.elapsed_seconds >= 0.0


# ---------------------------------------------------------------------------
# AgentSearch.crawl_site integration
# ---------------------------------------------------------------------------


class TestAgentSearchCrawlSite:
    """Test the crawl_site convenience method on AgentSearch."""

    def test_crawl_site_calls_crawler(self) -> None:
        """crawl_site creates a SiteCrawler and passes self as search.

        We patch the SiteCrawler class used inside crawl_site to verify
        the wiring without needing real HTTP or compilation.
        """
        from unittest.mock import patch

        from agent_web_compiler.search.agent_search import AgentSearch

        mock_result = CrawlResult(
            seed_url="https://example.com/",
            domain="example.com",
            pages_crawled=3,
        )

        with patch(
            "agent_web_compiler.sources.crawler.SiteCrawler"
        ) as mock_crawler_cls:
            mock_crawler_instance = MagicMock()
            mock_crawler_cls.return_value = mock_crawler_instance
            mock_crawler_instance.crawl.return_value = mock_result

            search = AgentSearch()
            result = search.crawl_site(
                "https://example.com/", max_pages=10, delay_seconds=0.1
            )

            assert result.pages_crawled == 3
            assert result.domain == "example.com"
            mock_crawler_instance.crawl.assert_called_once_with(
                "https://example.com/", search=search
            )
