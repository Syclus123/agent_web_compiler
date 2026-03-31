"""Playwright-based browser rendering fetcher.

Uses Playwright to render JavaScript-heavy pages and capture rendered HTML,
accessibility tree, screenshots, and debug metadata. Playwright is an optional
dependency — the fetcher raises a clear error if it is not installed.
"""

from __future__ import annotations

import re
import time
from typing import Any

from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.core.errors import RenderError
from agent_web_compiler.core.interfaces import FetchResult

# SPA framework markers that indicate a page likely needs JS rendering.
_SPA_MARKERS = (
    "data-reactroot",
    "__next",
    "__nuxt",
    "__vue",
    "ng-app",
    "ng-version",
    "data-server-rendered",
    "ember-application",
    "data-svelte",
)

# Noscript patterns that suggest JS is required.
_NOSCRIPT_PATTERNS = re.compile(
    r"<noscript[^>]*>.*?(enable\s+javascript|javascript\s+is\s+required|"
    r"javascript\s+is\s+disabled|you\s+need\s+to\s+enable|"
    r"this\s+app\s+works\s+best\s+with\s+javascript)",
    re.IGNORECASE | re.DOTALL,
)


def _ensure_playwright() -> None:
    """Verify playwright is importable; raise a clear error if not."""
    try:
        import playwright  # noqa: F401
    except ImportError as exc:
        raise RenderError(
            "Playwright is not installed. Install it with: "
            "pip install 'agent-web-compiler[browser]' && python -m playwright install chromium",
            cause=exc,
            context={"hint": "playwright is an optional dependency for browser rendering"},
        ) from exc


def detect_needs_rendering(html: str) -> bool:
    """Heuristic: does this HTML look like it needs JS rendering?

    Checks for:
    - <noscript> tags with "enable JavaScript" style messages
    - SPA framework marker attributes/ids
    - Very little visible text relative to HTML size (skeleton page)

    Args:
        html: Raw HTML string from an HTTP fetch.

    Returns:
        True if the page likely needs browser rendering.
    """
    # Check noscript messages
    if _NOSCRIPT_PATTERNS.search(html):
        return True

    # Check SPA framework markers
    html_lower = html.lower()
    for marker in _SPA_MARKERS:
        if marker.lower() in html_lower:
            return True

    # Check for very little text content relative to HTML size.
    # Strip all tags and see what's left.
    text_only = re.sub(r"<[^>]+>", "", html)
    text_only = re.sub(r"\s+", " ", text_only).strip()
    return len(html) > 1000 and len(text_only) < len(html) * 0.05


class PlaywrightFetcher:
    """Fetches web content by rendering in a headless browser via Playwright.

    Captures rendered HTML, accessibility tree, screenshot, console logs,
    and network errors. Supports configurable viewport, wait strategy, and
    resource blocking.

    Playwright is imported lazily — the class can be instantiated even when
    Playwright is not installed, failing only when fetch is actually called.
    """

    def __init__(
        self,
        *,
        viewport_width: int = 1280,
        viewport_height: int = 720,
        wait_until: str = "networkidle",
        extra_wait_ms: int = 500,
        block_resources: list[str] | None = None,
    ) -> None:
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.wait_until = wait_until
        self.extra_wait_ms = extra_wait_ms
        self.block_resources: list[str] = block_resources or []

    async def fetch(self, url: str, config: CompileConfig) -> FetchResult:
        """Render a page with Playwright and return the result.

        Args:
            url: The URL to render.
            config: Compilation config controlling timeout, user_agent, etc.

        Returns:
            FetchResult with rendered HTML content and rich metadata.

        Raises:
            RenderError: On import error, timeout, navigation failure, or crash.
        """
        _ensure_playwright()

        from playwright.async_api import Error as PlaywrightError
        from playwright.async_api import TimeoutError as PlaywrightTimeout
        from playwright.async_api import async_playwright

        start = time.monotonic()
        timeout_ms = int(config.timeout_seconds * 1000)
        console_logs: list[str] = []
        network_errors: list[str] = []

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    context = await browser.new_context(
                        viewport={
                            "width": self.viewport_width,
                            "height": self.viewport_height,
                        },
                        user_agent=config.user_agent,
                    )
                    page = await context.new_page()

                    # Collect console logs
                    page.on(
                        "console",
                        lambda msg: console_logs.append(
                            f"[{msg.type}] {msg.text}"
                        ),
                    )

                    # Collect network errors
                    page.on(
                        "pageerror",
                        lambda exc: network_errors.append(str(exc)),
                    )

                    # Block unwanted resource types for speed
                    if self.block_resources:
                        blocked = set(self.block_resources)

                        async def _route_handler(route: Any) -> None:
                            if route.request.resource_type in blocked:
                                await route.abort()
                            else:
                                await route.continue_()

                        await page.route("**/*", _route_handler)

                    # Navigate
                    await page.goto(
                        url,
                        wait_until=self.wait_until,
                        timeout=timeout_ms,
                    )

                    # Extra wait for hydration / late JS
                    if self.extra_wait_ms > 0:
                        await page.wait_for_timeout(self.extra_wait_ms)

                    # Capture rendered HTML
                    rendered_html = await page.content()

                    # Capture page title
                    title = await page.title()

                    # Capture final URL (after redirects)
                    final_url = page.url

                    # Capture screenshot
                    screenshot_png = await page.screenshot(full_page=True)

                    # Capture accessibility tree
                    accessibility_tree = await page.accessibility.snapshot() or {}

                    # Capture DOM snapshot (serialized outer HTML)
                    dom_snapshot = await page.evaluate(
                        "() => document.documentElement.outerHTML"
                    )

                finally:
                    await browser.close()

        except PlaywrightTimeout as exc:
            elapsed = time.monotonic() - start
            raise RenderError(
                f"Timeout rendering {url} after {config.timeout_seconds}s",
                cause=exc,
                context={
                    "url": url,
                    "timeout_seconds": config.timeout_seconds,
                    "elapsed_s": round(elapsed, 3),
                },
            ) from exc
        except PlaywrightError as exc:
            elapsed = time.monotonic() - start
            msg = str(exc)
            if "crash" in msg.lower() or "disconnected" in msg.lower():
                raise RenderError(
                    f"Browser crashed while rendering {url}: {msg}",
                    cause=exc,
                    context={"url": url, "elapsed_s": round(elapsed, 3)},
                ) from exc
            raise RenderError(
                f"Navigation failed for {url}: {msg}",
                cause=exc,
                context={"url": url, "elapsed_s": round(elapsed, 3)},
            ) from exc

        elapsed = time.monotonic() - start
        render_time_ms = elapsed * 1000

        # Auto-detection: does the rendered page differ meaningfully from a
        # static fetch? We check the rendered HTML for SPA markers as a proxy.
        needs_rendering = detect_needs_rendering(rendered_html)

        content_type = "text/html"

        metadata: dict[str, Any] = {
            "response_time_s": round(elapsed, 3),
            "render_time_ms": round(render_time_ms, 2),
            "screenshot_png": screenshot_png,
            "accessibility_tree": accessibility_tree,
            "dom_snapshot": dom_snapshot,
            "console_logs": console_logs,
            "network_errors": network_errors,
            "needs_rendering": needs_rendering,
            "page_title": title,
            "renderer": "playwright",
        }

        return FetchResult(
            content=rendered_html,
            content_type=content_type,
            url=final_url,
            status_code=200,
            headers={},
            metadata=metadata,
        )

    def fetch_sync(self, url: str, config: CompileConfig) -> FetchResult:
        """Synchronous rendering via Playwright sync API.

        Args:
            url: The URL to render.
            config: Compilation config controlling timeout, user_agent, etc.

        Returns:
            FetchResult with rendered HTML content and rich metadata.

        Raises:
            RenderError: On import error, timeout, navigation failure, or crash.
        """
        _ensure_playwright()

        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        from playwright.sync_api import sync_playwright

        start = time.monotonic()
        timeout_ms = int(config.timeout_seconds * 1000)
        console_logs: list[str] = []
        network_errors: list[str] = []

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    context = browser.new_context(
                        viewport={
                            "width": self.viewport_width,
                            "height": self.viewport_height,
                        },
                        user_agent=config.user_agent,
                    )
                    page = context.new_page()

                    # Collect console logs
                    page.on(
                        "console",
                        lambda msg: console_logs.append(
                            f"[{msg.type}] {msg.text}"
                        ),
                    )

                    # Collect network errors
                    page.on(
                        "pageerror",
                        lambda exc: network_errors.append(str(exc)),
                    )

                    # Block unwanted resource types for speed
                    if self.block_resources:
                        blocked = set(self.block_resources)

                        def _route_handler(route: Any) -> None:
                            if route.request.resource_type in blocked:
                                route.abort()
                            else:
                                route.continue_()

                        page.route("**/*", _route_handler)

                    # Navigate
                    page.goto(
                        url,
                        wait_until=self.wait_until,
                        timeout=timeout_ms,
                    )

                    # Extra wait for hydration / late JS
                    if self.extra_wait_ms > 0:
                        page.wait_for_timeout(self.extra_wait_ms)

                    # Capture rendered HTML
                    rendered_html = page.content()

                    # Capture page title
                    title = page.title()

                    # Capture final URL (after redirects)
                    final_url = page.url

                    # Capture screenshot
                    screenshot_png = page.screenshot(full_page=True)

                    # Capture accessibility tree
                    accessibility_tree = page.accessibility.snapshot() or {}

                    # Capture DOM snapshot
                    dom_snapshot = page.evaluate(
                        "() => document.documentElement.outerHTML"
                    )

                finally:
                    browser.close()

        except PlaywrightTimeout as exc:
            elapsed = time.monotonic() - start
            raise RenderError(
                f"Timeout rendering {url} after {config.timeout_seconds}s",
                cause=exc,
                context={
                    "url": url,
                    "timeout_seconds": config.timeout_seconds,
                    "elapsed_s": round(elapsed, 3),
                },
            ) from exc
        except PlaywrightError as exc:
            elapsed = time.monotonic() - start
            msg = str(exc)
            if "crash" in msg.lower() or "disconnected" in msg.lower():
                raise RenderError(
                    f"Browser crashed while rendering {url}: {msg}",
                    cause=exc,
                    context={"url": url, "elapsed_s": round(elapsed, 3)},
                ) from exc
            raise RenderError(
                f"Navigation failed for {url}: {msg}",
                cause=exc,
                context={"url": url, "elapsed_s": round(elapsed, 3)},
            ) from exc

        elapsed = time.monotonic() - start
        render_time_ms = elapsed * 1000

        needs_rendering = detect_needs_rendering(rendered_html)

        content_type = "text/html"

        metadata: dict[str, Any] = {
            "response_time_s": round(elapsed, 3),
            "render_time_ms": round(render_time_ms, 2),
            "screenshot_png": screenshot_png,
            "accessibility_tree": accessibility_tree,
            "dom_snapshot": dom_snapshot,
            "console_logs": console_logs,
            "network_errors": network_errors,
            "needs_rendering": needs_rendering,
            "page_title": title,
            "renderer": "playwright",
        }

        return FetchResult(
            content=rendered_html,
            content_type=content_type,
            url=final_url,
            status_code=200,
            headers={},
            metadata=metadata,
        )
