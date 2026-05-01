"""Tests for LiveActionExecutor / LiveRuntime / evidence adapter.

These tests run **without** browser-harness installed. We stub out the
``browser_harness.helpers`` module with a MagicMock so the code paths execute
end-to-end without touching a real Chrome.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

from agent_web_compiler.actiongraph.hybrid_executor import ExecutionDecision
from agent_web_compiler.actiongraph.models import APICandidate
from agent_web_compiler.core.action import Action, ActionType, StateEffect
from agent_web_compiler.core.document import AgentDocument, SourceType
from agent_web_compiler.runtime.browser_harness import (
    LiveActionExecutor,
    LiveRuntime,
    build_evidence,
)


def _install_fake_bh(monkeypatch: pytest.MonkeyPatch, helpers: MagicMock) -> None:
    fake_pkg = types.ModuleType("browser_harness")
    fake_pkg.helpers = helpers  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "browser_harness", fake_pkg)
    monkeypatch.setitem(sys.modules, "browser_harness.helpers", helpers)


def _helpers_with_pages(before_html: str = "<html>v1</html>",
                        after_html: str = "<html>v2</html>",
                        before_url: str = "https://example.com/a",
                        after_url: str = "https://example.com/a") -> MagicMock:
    """Return a helpers mock whose page_info + js responses alternate to
    simulate a page transition across two successive snapshots."""
    helpers = MagicMock()
    helpers.wait.return_value = None
    helpers.wait_for_load.return_value = True
    helpers.capture_screenshot.return_value = "/tmp/shot.png"
    # page_info alternates before → after; cycle in case the executor calls
    # more than twice.
    helpers.page_info.side_effect = [
        {"url": before_url, "title": "Before", "w": 1280, "h": 720, "sx": 0, "sy": 0, "pw": 1280, "ph": 2000},
        {"url": after_url, "title": "After", "w": 1280, "h": 720, "sx": 0, "sy": 0, "pw": 1280, "ph": 2000},
    ] * 10

    # js: alternate between outerHTML snapshots and "resolve rect" / other calls.
    # We detect intent by looking at the expression prefix.
    rect_pattern = {"x": 100.0, "y": 200.0, "w": 50.0, "h": 20.0}

    call_log: list[str] = []

    def _js(expression: str, target_id: object = None) -> object:
        call_log.append(expression)
        if "outerHTML" in expression:
            # Alternate before/after based on how many outerHTML calls we've seen.
            n = sum(1 for e in call_log if "outerHTML" in e)
            return before_html if n == 1 else after_html
        if "getBoundingClientRect" in expression:
            return rect_pattern
        if "dispatchEvent" in expression:
            return None
        if "fetch(" in expression:
            return '{"ok": true}'
        return None

    helpers.js.side_effect = _js
    helpers.click_at_xy.return_value = None
    helpers.type_text.return_value = None
    helpers.new_tab.return_value = "tid"
    helpers.upload_file.return_value = None
    helpers.http_get.return_value = '{"repos": []}'
    return helpers


def _make_action(
    action_id: str = "a1",
    type_: ActionType = ActionType.CLICK,
    selector: str | None = "button.primary",
    label: str = "Sign in",
    role: str | None = "submit",
    value_schema: dict | None = None,
    state_effect: StateEffect | None = None,
) -> Action:
    return Action(
        id=action_id,
        type=type_,
        label=label,
        selector=selector,
        role=role,
        confidence=0.9,
        priority=0.8,
        value_schema=value_schema,
        state_effect=state_effect,
    )


def _make_doc(actions: list[Action] | None = None, url: str = "https://example.com/a") -> AgentDocument:
    return AgentDocument(
        doc_id="doc_test",
        source_type=SourceType.HTML,
        source_url=url,
        title="Test page",
        blocks=[],
        actions=actions or [],
    )


# ---------------------------------------------------------------------------
# LiveActionExecutor — skip / confirm / browser / api paths
# ---------------------------------------------------------------------------


def test_skip_decision_returns_skipped_result() -> None:
    ex = LiveActionExecutor()
    action = _make_action()
    decision = ExecutionDecision(action_id=action.id, mode="skip", reason="nope")
    r = ex.execute(decision, action)
    assert r.mode_used == "skipped"
    assert r.success is False
    assert "nope" in (r.error or "")


def test_confirm_without_auto_confirm_is_skipped() -> None:
    ex = LiveActionExecutor(auto_confirm=False)
    action = _make_action()
    decision = ExecutionDecision(action_id=action.id, mode="confirm", reason="write op")
    r = ex.execute(decision, action)
    assert r.mode_used == "skipped"
    assert "confirmation required" in (r.error or "")


def test_browser_click_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    helpers = _helpers_with_pages()
    _install_fake_bh(monkeypatch, helpers)

    ex = LiveActionExecutor()
    action = _make_action()
    decision = ExecutionDecision(action_id=action.id, mode="browser", reason="default")
    r = ex.execute(decision, action, doc=_make_doc([action]))

    assert r.success is True
    assert r.mode_used == "browser"
    # Coordinate click must have been dispatched.
    helpers.click_at_xy.assert_called_once()
    args, _ = helpers.click_at_xy.call_args
    assert args == (100.0, 200.0)
    # Transition was built with dom change.
    assert r.transition is not None
    assert r.transition.dom_changed is True
    assert r.transition.action_id == action.id


def test_browser_click_missing_selector(monkeypatch: pytest.MonkeyPatch) -> None:
    helpers = _helpers_with_pages()
    # Override js so the rect resolver returns null (element not found).
    def _js(expression: str, target_id: object = None) -> object:
        if "outerHTML" in expression:
            return "<html></html>"
        if "getBoundingClientRect" in expression:
            return None
        return None

    helpers.js.side_effect = _js
    _install_fake_bh(monkeypatch, helpers)

    ex = LiveActionExecutor()
    action = _make_action()
    decision = ExecutionDecision(action_id=action.id, mode="browser", reason="default")
    r = ex.execute(decision, action)
    assert r.success is False
    assert "selector not found" in (r.error or "")


def test_browser_input_types_value(monkeypatch: pytest.MonkeyPatch) -> None:
    helpers = _helpers_with_pages()
    _install_fake_bh(monkeypatch, helpers)

    ex = LiveActionExecutor()
    action = _make_action(
        action_id="a_input",
        type_=ActionType.INPUT,
        selector="input[name=q]",
        label="search box",
        role="query",
        value_schema={"default": "hello"},
    )
    decision = ExecutionDecision(action_id=action.id, mode="browser", reason="default")
    r = ex.execute(decision, action)
    assert r.success is True
    helpers.click_at_xy.assert_called_once()
    helpers.type_text.assert_called_once_with("hello")


def test_api_path_calls_http_get(monkeypatch: pytest.MonkeyPatch) -> None:
    helpers = _helpers_with_pages()
    _install_fake_bh(monkeypatch, helpers)

    ex = LiveActionExecutor()
    action = _make_action(action_id="a_search", type_=ActionType.SUBMIT)
    cand = APICandidate(
        api_id="api1",
        derived_from_action_id=action.id,
        endpoint="https://api.example.com/search",
        method="GET",
        params_schema={"q": "x"},
        confidence=0.9,
        safety_level="read_only",
    )
    decision = ExecutionDecision(
        action_id=action.id,
        mode="api",
        api_candidate=cand,
        reason="safe API",
        confidence=0.9,
    )
    r = ex.execute(decision, action)
    assert r.success is True
    assert r.mode_used == "api"
    # We should have recorded one network call.
    assert len(r.network_calls) == 1
    nc = r.network_calls[0]
    assert nc.method == "GET"
    assert nc.url.startswith("https://api.example.com/search")
    assert "q=x" in nc.url
    helpers.http_get.assert_called_once()


def test_api_failure_falls_back_to_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    helpers = _helpers_with_pages()
    helpers.http_get.side_effect = RuntimeError("network down")
    _install_fake_bh(monkeypatch, helpers)

    ex = LiveActionExecutor()
    action = _make_action()
    cand = APICandidate(
        api_id="api1",
        derived_from_action_id=action.id,
        endpoint="https://api.example.com/x",
        method="GET",
        confidence=0.9,
        safety_level="read_only",
    )
    decision = ExecutionDecision(action_id=action.id, mode="api", api_candidate=cand)
    r = ex.execute(decision, action)
    # Fallback succeeded but the result records the original API failure.
    assert r.success is True  # error field carries the annotation, but no exception bubbled
    assert r.mode_used == "browser"
    assert "api→browser fallback" in (r.error or "")


# ---------------------------------------------------------------------------
# Evidence adapter
# ---------------------------------------------------------------------------


def test_build_evidence_records_transition_and_screenshot(monkeypatch: pytest.MonkeyPatch) -> None:
    helpers = _helpers_with_pages()
    _install_fake_bh(monkeypatch, helpers)

    ex = LiveActionExecutor()
    action = _make_action()
    decision = ExecutionDecision(action_id=action.id, mode="browser")
    r = ex.execute(decision, action, doc=_make_doc([action]))
    ev = build_evidence(r, action, source_url="https://example.com/a")

    assert ev.source_type == "action"
    assert ev.source_url == "https://example.com/a"
    assert ev.dom_path == action.selector
    assert "dom_changed" in ev.text
    assert ev.metadata["execution_mode"] == "browser"
    assert "transition" in ev.metadata
    assert ev.metadata["screenshot_path"] == "/tmp/shot.png"


# ---------------------------------------------------------------------------
# LiveRuntime
# ---------------------------------------------------------------------------


def test_live_runtime_selects_and_runs_matching_action(monkeypatch: pytest.MonkeyPatch) -> None:
    helpers = _helpers_with_pages()
    _install_fake_bh(monkeypatch, helpers)

    a_sign_in = _make_action(
        action_id="a_sign_in",
        type_=ActionType.CLICK,
        label="Sign in",
        role="login",
        selector="a.sign-in",
    )
    a_other = _make_action(
        action_id="a_other", type_=ActionType.CLICK, label="Learn more", role="info",
        selector="a.more",
    )
    doc = _make_doc([a_sign_in, a_other])
    rt = LiveRuntime(doc, executor=LiveActionExecutor())
    outcome = rt.run("sign in please", max_actions=1)

    assert outcome.success is True
    assert len(outcome.actions) == 1
    assert outcome.actions[0].id == "a_sign_in"
    assert len(outcome.evidence) == 1


def test_live_runtime_run_action_missing_id() -> None:
    doc = _make_doc([])
    rt = LiveRuntime(doc, executor=LiveActionExecutor())
    r = rt.run_action("nope")
    assert r.success is False
    assert "not found" in (r.error or "")


def test_live_runtime_empty_selection_returns_zero_actions() -> None:
    doc = _make_doc([_make_action(label="Download", role="download")])
    rt = LiveRuntime(doc, executor=LiveActionExecutor())
    outcome = rt.run("totally unrelated task xyz", max_actions=3)
    assert outcome.actions == []
    assert outcome.results == []
    assert outcome.success is False


# ---------------------------------------------------------------------------
# Middleware upgrade
# ---------------------------------------------------------------------------


def test_middleware_execute_action_plan_mode_matches_translate() -> None:
    """Without an executor, execute_action must equal translate_action."""
    from agent_web_compiler.middleware.browser_middleware import BrowserMiddleware

    html = "<html><body><button id='b'>Go</button></body></html>"
    mw = BrowserMiddleware()
    ctx = mw.on_page_load("https://example.com", html)
    # Pick any available action.
    if not ctx.doc.actions:
        pytest.skip("compiler found no actions in the test HTML")
    aid = ctx.doc.actions[0].id
    assert mw.execute_action(aid) == mw.translate_action(aid)


def test_middleware_execute_action_live_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    helpers = _helpers_with_pages()
    _install_fake_bh(monkeypatch, helpers)

    from agent_web_compiler.middleware.browser_middleware import BrowserMiddleware

    html = "<html><body><button id='b'>Go</button></body></html>"
    ex = LiveActionExecutor()
    mw = BrowserMiddleware(executor=ex)
    ctx = mw.on_page_load("https://example.com", html)
    if not ctx.doc.actions:
        pytest.skip("compiler found no actions in the test HTML")
    aid = ctx.doc.actions[0].id
    result = mw.execute_action(aid)
    # Shape changes to LiveExecutionResult.to_dict() when executor is live.
    assert "mode_used" in result
    assert "success" in result
