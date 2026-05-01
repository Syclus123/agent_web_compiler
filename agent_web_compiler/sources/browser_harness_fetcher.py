"""Browser-Harness fetcher — use the user's real Chrome as the rendering source.

This fetcher speaks to ``browser-harness`` (https://github.com/browser-use/browser-harness),
a minimal CDP helper library that attaches to the user's already-running Chrome over a
single websocket. Compared to :class:`PlaywrightFetcher`, this gives AWC three concrete
wins:

1. **Real logged-in session** — cookies, SSO, SaaS backends, LinkedIn/Gmail all Just Work.
2. **Real fingerprint** — no "Playwright-launched Chromium" bot signal.
3. **No cold start** — the BH daemon persists; each fetch is a single CDP round-trip.

browser-harness is an **optional** dependency. AWC never imports it at package-import
time. ``FetchError`` is raised (not ``ImportError``) if the user asks for this fetcher
without having it installed, so pipelines can catch it and fall back cleanly.

Example:

    from agent_web_compiler.sources.browser_harness_fetcher import BrowserHarnessFetcher
    from agent_web_compiler.core.config import CompileConfig

    fetcher = BrowserHarnessFetcher(bu_name="awc")
    result = fetcher.fetch_sync("https://linkedin.com/in/me", CompileConfig())
    # result.content   → rendered HTML from the user's own Chrome
    # result.metadata  → screenshot_png, page_title, viewport, …

Design notes:

- We keep *every* BH-specific concern inside this module. ``core`` / ``pipeline`` /
  ``provenance`` must not grow a new import path for BH.
- We never launch a BH daemon ourselves — ``browser_harness.helpers`` does the
  ``ensure_daemon()`` dance lazily on the first ``cdp(...)`` call. AWC's job is
  purely to translate BH primitives into :class:`FetchResult`.
"""

from __future__ import annotations

import os
import time
from typing import Any

from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.core.errors import FetchError, RenderError
from agent_web_compiler.core.interfaces import FetchResult

# HTTP(S) schemes we delegate directly to BH's bundled ``http_get`` when the caller
# explicitly opts into ``prefer_http=True``. Everything else (about:, javascript:,
# file:) is rejected early — BH's ``new_tab`` would accept them but the semantics
# would leak the agent's real session in surprising ways.
_SUPPORTED_SCHEMES = ("http://", "https://")


def _import_browser_harness() -> Any:
    """Lazy import of ``browser_harness.helpers``.

    Raises:
        FetchError: If browser-harness is not installed. We wrap the ImportError
            in FetchError (not RenderError) because from the pipeline's point of
            view the fetch is what failed — no rendering was ever attempted.
    """
    try:
        from browser_harness import helpers as bh  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover — depends on user env
        raise FetchError(
            "browser-harness is not installed. "
            "Install with: pip install 'agent-web-compiler[harness]' "
            "and follow the BH setup guide "
            "(https://github.com/browser-use/browser-harness#setup-prompt) "
            "to connect it to your Chrome.",
            cause=exc,
            context={"hint": "browser-harness is an optional dependency"},
        ) from exc
    return bh


class BrowserHarnessFetcher:
    """Fetch URLs using the user's own Chrome via ``browser-harness``.

    Parameters:
        bu_name: Value of the ``BU_NAME`` environment variable scope used by
            browser-harness to pick the right daemon socket. Each value maps to
            one isolated daemon → one isolated browser session. Defaults to
            ``"awc"`` so AWC's fetches don't collide with a developer's default
            BH shell.
        wait_after_load_ms: Extra sleep (in ms) after ``wait_for_load()`` returns.
            Gives React/Vue SPAs time to hydrate past ``document.readyState ==
            "complete"`` — the same 2-second trick BH's ``github/scraping.md``
            domain-skill relies on.
        capture_screenshot: If ``True`` (default) ship a PNG in ``metadata``
            under ``"screenshot_png"``. Turn off for bulk crawls where the
            extra base64 hop is a hotspot.
        activate_tab: If ``True`` call ``Target.activateTarget`` so the user
            visually sees which tab AWC is operating on. Off by default for
            batch compile runs.
    """

    # Default extra-wait — long enough for most SPAs, short enough to not destroy
    # throughput. Mirrors BH's ``wait(2)`` convention in domain-skills.
    _DEFAULT_EXTRA_WAIT_MS = 1500

    def __init__(
        self,
        *,
        bu_name: str = "awc",
        wait_after_load_ms: int = _DEFAULT_EXTRA_WAIT_MS,
        capture_screenshot: bool = True,
        activate_tab: bool = False,
    ) -> None:
        self.bu_name = bu_name
        self.wait_after_load_ms = wait_after_load_ms
        self.capture_screenshot = capture_screenshot
        self.activate_tab = activate_tab
        # Scoping the BU_NAME is the ONE piece of global state we touch. We use
        # ``setdefault`` so an outer caller that already set BU_NAME wins —
        # this keeps AWC composable inside a larger BH session.
        os.environ.setdefault("BU_NAME", bu_name)
        self._bh: Any | None = None  # lazy-loaded

    # ------------------------------------------------------------------
    # Lazy helper accessor
    # ------------------------------------------------------------------

    def _helpers(self) -> Any:
        """Return (and memoize) the ``browser_harness.helpers`` module."""
        if self._bh is None:
            self._bh = _import_browser_harness()
        return self._bh

    # ------------------------------------------------------------------
    # Public fetch surface
    # ------------------------------------------------------------------

    def fetch_sync(self, url: str, config: CompileConfig) -> FetchResult:
        """Fetch ``url`` synchronously using the user's Chrome.

        The flow:
            new_tab(url) → wait_for_load() → optional extra wait →
            page_info()  → js('document.documentElement.outerHTML') →
            optional capture_screenshot()

        Args:
            url: Target URL. Only ``http://`` and ``https://`` are accepted.
            config: Compilation config. ``timeout_seconds`` caps the BH
                ``wait_for_load`` deadline.

        Returns:
            :class:`FetchResult` with rendered HTML and BH-specific metadata.

        Raises:
            FetchError: Unsupported scheme, or BH not installed.
            RenderError: BH failed at any step after the tab was opened.
        """
        if not url.startswith(_SUPPORTED_SCHEMES):
            raise FetchError(
                f"BrowserHarnessFetcher only supports http(s) URLs, got: {url}",
                context={"url": url},
            )

        bh = self._helpers()
        start = time.monotonic()

        try:
            # new_tab is deliberately used instead of goto_url — goto would
            # clobber whatever the user is looking at. This is the one rule
            # BH's SKILL.md calls out explicitly.
            bh.new_tab(url)

            loaded = bh.wait_for_load(timeout=config.timeout_seconds)
            if self.wait_after_load_ms > 0:
                bh.wait(self.wait_after_load_ms / 1000.0)

            info = bh.page_info() or {}
            # If a native dialog is blocking the JS thread, page_info returns a
            # {"dialog": ...} sentinel and further ``js`` calls will hang. Fail
            # fast with RenderError so the pipeline can report it cleanly.
            if "dialog" in info:
                raise RenderError(
                    "Browser tab is blocked by a native dialog — "
                    "dismiss it manually and retry.",
                    context={"url": url, "dialog": info["dialog"]},
                )

            html = bh.js("return document.documentElement.outerHTML")

            metadata: dict[str, Any] = {
                "renderer": "browser-harness",
                "bu_name": self.bu_name,
                "response_time_s": round(time.monotonic() - start, 3),
                "ready_state_complete": bool(loaded),
                "page_title": info.get("title", ""),
                "viewport": {
                    "w": info.get("w"),
                    "h": info.get("h"),
                },
                "scroll": {
                    "x": info.get("sx"),
                    "y": info.get("sy"),
                },
                "page_size": {
                    "w": info.get("pw"),
                    "h": info.get("ph"),
                },
                # Flag consumed by detect_needs_rendering() consumers that want
                # to know "this HTML came from a real browser already".
                "needs_rendering": False,
            }

            if self.capture_screenshot:
                shot_path = bh.capture_screenshot()
                try:
                    with open(shot_path, "rb") as f:
                        metadata["screenshot_png"] = f.read()
                    metadata["screenshot_path"] = shot_path
                except OSError:  # pragma: no cover — disk weirdness
                    # A missing screenshot is not fatal — we have HTML already.
                    metadata["screenshot_png"] = None

        except FetchError:
            raise
        except RenderError:
            raise
        except Exception as exc:  # pragma: no cover — BH runtime surface
            elapsed = time.monotonic() - start
            raise RenderError(
                f"browser-harness failed while loading {url}: {exc}",
                cause=exc,
                context={
                    "url": url,
                    "bu_name": self.bu_name,
                    "elapsed_s": round(elapsed, 3),
                },
            ) from exc

        # ``info["url"]`` reflects redirects / post-JS history.pushState. Fall
        # back to the request URL if BH didn't give us one (rare; e.g. about:
        # pages that shouldn't have reached this code path).
        final_url = info.get("url") or url

        return FetchResult(
            content=html or "",
            content_type="text/html",
            url=final_url,
            status_code=200,  # BH does not expose HTTP status — assume 200 on success
            headers={},
            metadata=metadata,
        )

    async def fetch(self, url: str, config: CompileConfig) -> FetchResult:
        """Async alias for :meth:`fetch_sync`.

        BH itself is fully synchronous under the hood — the daemon round-trip
        is blocking. We expose an ``async`` method so :class:`Fetcher` protocol
        callers that ``await fetcher.fetch(...)`` still work.
        """
        return self.fetch_sync(url, config)
