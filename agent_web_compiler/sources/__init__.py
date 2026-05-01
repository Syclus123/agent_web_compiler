"""Source fetchers — strategies for pulling raw content into the pipeline.

Default fetchers exposed here:

- :class:`HTTPFetcher`       — httpx-based HTTP(S) fetcher (the default)
- :class:`PlaywrightFetcher` — headless-Chromium renderer for SPA-heavy pages
                               (requires the ``browser`` extra)

The following fetcher is **lazy-loaded** to keep its optional dependency out
of the top-level import graph:

- :class:`BrowserHarnessFetcher` — drives the user's own running Chrome via
  ``browser-harness``. Access as::

      from agent_web_compiler.sources.browser_harness_fetcher import BrowserHarnessFetcher

  or (more ergonomic) through :meth:`PipelineBuilder.with_fetcher("browser_harness")`.
"""

from __future__ import annotations

from agent_web_compiler.sources.crawler import SiteCrawler
from agent_web_compiler.sources.file_reader import FileReader
from agent_web_compiler.sources.http_fetcher import HTTPFetcher
from agent_web_compiler.sources.playwright_fetcher import (
    PlaywrightFetcher,
    detect_needs_rendering,
)

__all__ = [
    "HTTPFetcher",
    "FileReader",
    "PlaywrightFetcher",
    "SiteCrawler",
    "detect_needs_rendering",
    "resolve_fetcher",
]


def resolve_fetcher(name: str, **kwargs):  # noqa: ANN003, ANN201 — intentional soft typing
    """Resolve a fetcher by short name.

    Supported names:
        - ``"http"``              → :class:`HTTPFetcher`
        - ``"playwright"``        → :class:`PlaywrightFetcher`
        - ``"browser_harness"``   → :class:`BrowserHarnessFetcher` (lazy)
        - ``"bh"``                → alias for ``"browser_harness"``

    This is a thin helper used by :meth:`PipelineBuilder.with_fetcher` and the
    CLI. Unknown names raise ``ValueError``. BH-specific kwargs (``bu_name``,
    ``wait_after_load_ms``, ``capture_screenshot``, ``activate_tab``) pass
    through unchanged.
    """
    normalized = name.lower().strip()
    if normalized == "http":
        return HTTPFetcher()
    if normalized == "playwright":
        return PlaywrightFetcher(**kwargs)
    if normalized in ("browser_harness", "bh", "browser-harness"):
        # Lazy import — keep browser-harness optional.
        from agent_web_compiler.sources.browser_harness_fetcher import (
            BrowserHarnessFetcher,
        )

        return BrowserHarnessFetcher(**kwargs)
    raise ValueError(
        f"Unknown fetcher: {name!r}. "
        "Expected one of: http, playwright, browser_harness."
    )
