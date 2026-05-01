"""Tests for BrowserHarnessFetcher.

These tests are designed to run **without** browser-harness installed — we
verify import laziness and error messaging. A separate integration test
(marked ``@pytest.mark.integration``) exercises the real fetcher when BH
is present in the environment.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.core.errors import FetchError, RenderError
from agent_web_compiler.sources import resolve_fetcher
from agent_web_compiler.sources.browser_harness_fetcher import BrowserHarnessFetcher


def _install_fake_bh(monkeypatch: pytest.MonkeyPatch, helpers: MagicMock) -> None:
    """Install a fake ``browser_harness.helpers`` into sys.modules."""
    fake_pkg = types.ModuleType("browser_harness")
    fake_pkg.helpers = helpers  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "browser_harness", fake_pkg)
    monkeypatch.setitem(sys.modules, "browser_harness.helpers", helpers)


def _make_fake_helpers(
    html: str = "<html><body><h1>Hi</h1></body></html>",
    url: str = "https://example.com/final",
    title: str = "Example",
) -> MagicMock:
    helpers = MagicMock()
    helpers.new_tab.return_value = "target-id"
    helpers.wait_for_load.return_value = True
    helpers.wait.return_value = None
    helpers.page_info.return_value = {
        "url": url,
        "title": title,
        "w": 1280,
        "h": 720,
        "sx": 0,
        "sy": 0,
        "pw": 1280,
        "ph": 3000,
    }
    helpers.js.return_value = html
    helpers.capture_screenshot.return_value = "/tmp/nonexistent-shot.png"
    return helpers


# ---------------------------------------------------------------------------
# Lazy import + installation surface
# ---------------------------------------------------------------------------


def test_construction_does_not_require_browser_harness() -> None:
    """The ctor must not import BH — we can instantiate before installing it."""
    fetcher = BrowserHarnessFetcher(bu_name="test")
    assert fetcher.bu_name == "test"
    assert fetcher._bh is None  # type: ignore[attr-defined]


def test_missing_browser_harness_raises_fetch_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Calling fetch without BH installed yields a FetchError (not ImportError)."""
    # Make sure BH is *not* importable.
    monkeypatch.setitem(sys.modules, "browser_harness", None)

    fetcher = BrowserHarnessFetcher()
    with pytest.raises(FetchError, match="browser-harness is not installed"):
        fetcher.fetch_sync("https://example.com", CompileConfig())


def test_non_http_url_rejected_early() -> None:
    """file:// / about: / etc. must be refused before importing BH."""
    fetcher = BrowserHarnessFetcher()
    with pytest.raises(FetchError, match="only supports http"):
        fetcher.fetch_sync("about:blank", CompileConfig())
    with pytest.raises(FetchError, match="only supports http"):
        fetcher.fetch_sync("file:///tmp/x.html", CompileConfig())


# ---------------------------------------------------------------------------
# Happy path with a fake BH helpers module
# ---------------------------------------------------------------------------


def test_fetch_success_populates_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    helpers = _make_fake_helpers()
    _install_fake_bh(monkeypatch, helpers)

    fetcher = BrowserHarnessFetcher(bu_name="test-awc", capture_screenshot=False)
    result = fetcher.fetch_sync("https://example.com", CompileConfig())

    assert "<h1>Hi</h1>" in result.content
    assert result.url == "https://example.com/final"
    assert result.metadata["renderer"] == "browser-harness"
    assert result.metadata["bu_name"] == "test-awc"
    assert result.metadata["page_title"] == "Example"
    assert result.metadata["viewport"] == {"w": 1280, "h": 720}
    assert result.metadata["needs_rendering"] is False
    # capture_screenshot=False  →  no screenshot_png key
    assert "screenshot_png" not in result.metadata

    # Flow ordering: new_tab → wait_for_load → page_info → js
    helpers.new_tab.assert_called_once_with("https://example.com")
    helpers.wait_for_load.assert_called_once()
    helpers.js.assert_called_once()


def test_dialog_blocks_fetch_with_render_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """If page_info signals a blocking dialog, we must fail fast."""
    helpers = _make_fake_helpers()
    helpers.page_info.return_value = {
        "dialog": {"type": "alert", "message": "Leave site?"}
    }
    _install_fake_bh(monkeypatch, helpers)

    fetcher = BrowserHarnessFetcher()
    with pytest.raises(RenderError, match="blocked by a native dialog"):
        fetcher.fetch_sync("https://example.com", CompileConfig())


def test_bh_runtime_exception_wrapped_as_render_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown BH exceptions are surfaced as RenderError with context."""
    helpers = _make_fake_helpers()
    helpers.js.side_effect = RuntimeError("CDP disconnected")
    _install_fake_bh(monkeypatch, helpers)

    fetcher = BrowserHarnessFetcher()
    with pytest.raises(RenderError, match="browser-harness failed"):
        fetcher.fetch_sync("https://example.com", CompileConfig())


# ---------------------------------------------------------------------------
# Registry resolution
# ---------------------------------------------------------------------------


def test_resolve_fetcher_returns_instance() -> None:
    f = resolve_fetcher("browser_harness", bu_name="x")
    assert isinstance(f, BrowserHarnessFetcher)
    assert f.bu_name == "x"

    # Aliases
    assert isinstance(resolve_fetcher("bh"), BrowserHarnessFetcher)
    assert isinstance(resolve_fetcher("browser-harness"), BrowserHarnessFetcher)


def test_resolve_fetcher_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown fetcher"):
        resolve_fetcher("not-a-fetcher")
