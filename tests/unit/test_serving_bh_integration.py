"""Tests for MCP + REST live-runtime / bh-skill endpoints.

The MCP handlers are exercised **directly** (not through mcp's stdio layer),
which is how the existing MCP tests in this repo do it too — keeps the unit
tests fast and avoids pulling mcp as a test dependency.

BH is stubbed with a MagicMock so ``live_run`` exercises the entire handler
flow without requiring a real daemon.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# MCP live_run + publish_bh_skill
# ---------------------------------------------------------------------------


_FAKE_HTML = """\
<html><head><title>BH demo</title></head>
<body>
  <main>
    <h1>Browser Harness demo</h1>
    <button id="star" class="btn-primary">Star repository</button>
    <button id="fork" class="btn-secondary">Fork repository</button>
  </main>
</body></html>
"""


def _install_fake_bh(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Install a MagicMock browser_harness.helpers."""
    helpers = MagicMock()
    helpers.new_tab.return_value = "tid"
    helpers.wait.return_value = None
    helpers.wait_for_load.return_value = True
    helpers.capture_screenshot.return_value = "/tmp/shot.png"
    helpers.click_at_xy.return_value = None
    helpers.type_text.return_value = None
    helpers.page_info.return_value = {
        "url": "https://example.com/",
        "title": "BH demo",
        "w": 1280, "h": 720, "sx": 0, "sy": 0, "pw": 1280, "ph": 2000,
    }
    # js: alternate outerHTML snapshots + always return a hit rect
    call_log: list[str] = []

    def _js(expression: str, target_id: object = None) -> object:
        call_log.append(expression)
        if "outerHTML" in expression:
            return _FAKE_HTML
        if "getBoundingClientRect" in expression:
            return {"x": 100.0, "y": 100.0, "w": 50.0, "h": 20.0}
        return None

    helpers.js.side_effect = _js

    fake_pkg = types.ModuleType("browser_harness")
    fake_pkg.helpers = helpers  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "browser_harness", fake_pkg)
    monkeypatch.setitem(sys.modules, "browser_harness.helpers", helpers)
    return helpers


def _install_fake_fetcher(monkeypatch: pytest.MonkeyPatch, html: str = _FAKE_HTML) -> None:
    """Patch every HTTPFetcher import path so compile_url doesn't touch the network."""
    from agent_web_compiler import sources as sources_pkg
    from agent_web_compiler.core.interfaces import FetchResult
    from agent_web_compiler.sources import http_fetcher

    class _StubFetcher:
        def fetch_sync(self, url: str, config):  # noqa: ANN001
            return FetchResult(
                content=html,
                content_type="text/html",
                url=url,
                status_code=200,
                headers={},
                metadata={"renderer": "stub"},
            )

        async def fetch(self, url: str, config):  # noqa: ANN001
            return self.fetch_sync(url, config)

    # The real HTTPFetcher class lives in sources.http_fetcher, but sources/__init__.py
    # already imported it and resolve_fetcher / compile_url reference it via *both*
    # paths. Patch both so every code path sees the stub.
    monkeypatch.setattr(http_fetcher, "HTTPFetcher", _StubFetcher)
    monkeypatch.setattr(sources_pkg, "HTTPFetcher", _StubFetcher)


def test_mcp_tool_registry_includes_new_tools() -> None:
    from agent_web_compiler.serving.mcp_server import _TOOL_HANDLERS, TOOLS

    names = {t["name"] for t in TOOLS}
    assert "live_run" in names
    assert "publish_bh_skill" in names
    assert "live_run" in _TOOL_HANDLERS
    assert "publish_bh_skill" in _TOOL_HANDLERS


def test_mcp_live_run_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dry-run path should not touch BH — returns a plan only."""
    _install_fake_fetcher(monkeypatch)
    # Don't need BH installed for dry-run.
    from agent_web_compiler.serving.mcp_server import _handle_live_run

    result_json = _handle_live_run(
        {
            "task": "star the repository",
            "url": "https://example.com/repo",
            "dry_run": True,
            "max_actions": 2,
            "fetcher": "http",  # tests stub HTTPFetcher, not BH
        }
    )
    result = json.loads(result_json)
    assert result["dry_run"] is True
    assert result["url"] == "https://example.com/repo"
    # There's at least one button labelled "Star repository" — it should match.
    labels = [a["label"].lower() for a in result["planned_actions"]]
    assert any("star" in lab for lab in labels)


def test_mcp_live_run_full(monkeypatch: pytest.MonkeyPatch) -> None:
    """Full live run — uses the stubbed BH helpers."""
    _install_fake_fetcher(monkeypatch)
    _install_fake_bh(monkeypatch)
    from agent_web_compiler.serving.mcp_server import _handle_live_run

    result_json = _handle_live_run(
        {
            "task": "star the repository",
            "url": "https://example.com/repo",
            "fetcher": "http",
        }
    )
    result = json.loads(result_json)
    # outcome.to_dict() has these keys
    assert "task" in result
    assert "results" in result
    assert "evidence" in result
    # Ran at least one action
    assert len(result["results"]) >= 1


def test_mcp_live_run_rejects_missing_args() -> None:
    from agent_web_compiler.serving.mcp_server import _handle_live_run

    with pytest.raises(ValueError, match="task"):
        _handle_live_run({"url": "https://x"})
    with pytest.raises(ValueError, match="url"):
        _handle_live_run({"task": "t"})


def test_mcp_publish_bh_skill_markdown_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_fetcher(monkeypatch)
    from agent_web_compiler.serving.mcp_server import _handle_publish_bh_skill

    result_json = _handle_publish_bh_skill(
        {"url": "https://github.com/browser-use/browser-harness", "task": "scraping"}
    )
    result = json.loads(result_json)
    assert result["domain"] == "github.com"
    assert result["task"] == "scraping"
    assert "# github.com — Scraping" in result["markdown"]
    assert "written_to" not in result  # no out_repo given


def test_mcp_publish_bh_skill_writes_to_repo(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _install_fake_fetcher(monkeypatch)
    from agent_web_compiler.serving.mcp_server import _handle_publish_bh_skill

    result_json = _handle_publish_bh_skill(
        {
            "url": "https://github.com/x/y",
            "task": "scraping",
            "out_repo": str(tmp_path),
            "overwrite": True,
        }
    )
    result = json.loads(result_json)
    assert "written_to" in result
    # (path imported at top)
    assert Path(result["written_to"]).exists()
    assert Path(result["written_to"]).name == "scraping.md"


# ---------------------------------------------------------------------------
# REST /v1/live/run + /v1/publish/bh-skill
# ---------------------------------------------------------------------------


def _test_client() -> object:
    """Construct a FastAPI TestClient only if fastapi+httpx are available."""
    try:
        from fastapi.testclient import TestClient
    except ImportError:  # pragma: no cover
        pytest.skip("fastapi not installed")
    from agent_web_compiler.serving.rest_server import create_app

    return TestClient(create_app())


def test_rest_live_run_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_fetcher(monkeypatch)
    client = _test_client()
    r = client.post(
        "/v1/live/run",
        json={
            "url": "https://example.com/repo",
            "task": "star the repository",
            "dry_run": True,
            "max_actions": 2,
            "fetcher": "http",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["dry_run"] is True
    assert data["url"] == "https://example.com/repo"


def test_rest_live_run_full(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_fetcher(monkeypatch)
    _install_fake_bh(monkeypatch)
    client = _test_client()
    r = client.post(
        "/v1/live/run",
        json={
            "url": "https://example.com/repo",
            "task": "star the repository",
            "fetcher": "http",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "results" in data


def test_rest_publish_bh_skill_stdout_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_fetcher(monkeypatch)
    client = _test_client()
    r = client.post(
        "/v1/publish/bh-skill",
        json={"url": "https://github.com/x/y", "task": "scraping"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["domain"] == "github.com"
    assert "# github.com — Scraping" in data["markdown"]


def test_rest_publish_bh_skill_writes(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _install_fake_fetcher(monkeypatch)
    client = _test_client()
    r = client.post(
        "/v1/publish/bh-skill",
        json={
            "url": "https://github.com/x/y",
            "task": "scraping",
            "out_repo": str(tmp_path),
            "overwrite": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "written_to" in data
    # (path imported at top)
    assert Path(data["written_to"]).exists()


def test_rest_publish_bh_skill_conflict_without_overwrite(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _install_fake_fetcher(monkeypatch)
    client = _test_client()
    body = {
        "url": "https://github.com/x/y",
        "task": "scraping",
        "out_repo": str(tmp_path),
        "overwrite": False,
    }
    r1 = client.post("/v1/publish/bh-skill", json=body)
    assert r1.status_code == 200
    r2 = client.post("/v1/publish/bh-skill", json=body)
    assert r2.status_code == 409
