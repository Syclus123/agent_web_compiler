"""LiveActionExecutor — turn ``HybridExecutor`` decisions into real browser actions.

``agent_web_compiler.actiongraph.HybridExecutor`` produces an
:class:`ExecutionDecision` that says *how* an action should be executed (API,
browser, confirm, skip) but deliberately leaves the *actual execution*
unimplemented — AWC is a compiler, not a driver.

This module closes that loop by binding a decision to `browser-harness
<https://github.com/browser-use/browser-harness>`_ as the browser backend.
Each call to :meth:`LiveActionExecutor.execute` produces a
:class:`LiveExecutionResult` that carries:

- the mode AWC actually used (``"api"`` / ``"browser"`` / ``"skipped"``)
- a :class:`StateTransition` — so the execution feeds back into ``ActionGraph``
- a list of :class:`NetworkRequest` — one per HTTP call made on this action
- an optional screenshot path — for :class:`Evidence` records

The executor deliberately re-uses BH's own domain-skill flavour of browser
operation: **coordinate clicks via ``click_at_xy`` on the element's center
rectangle**, not selector-based clicks. This is what BH's SKILL.md calls out
as "compositor-level" and it's what actually works through iframes / shadow
DOM / cross-origin boundaries.

Design constraints (mirror those in
:mod:`agent_web_compiler.sources.browser_harness_fetcher`):

1. ``browser_harness`` is a lazy import — the module can be imported even
   when BH is not installed; ``execute`` is where the import actually happens.
2. No daemon management. No retries framework. BH's own ``ensure_daemon()`` is
   in charge; we just call helpers.
3. API failures degrade to browser — a soft fallback inside a single call so
   the caller sees one end-to-end result, not a pair of "tried API, then
   tried browser".
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from agent_web_compiler.actiongraph.hybrid_executor import ExecutionDecision
from agent_web_compiler.actiongraph.models import (
    NetworkRequest,
    PageState,
    StateTransition,
)
from agent_web_compiler.core.action import Action, ActionType
from agent_web_compiler.core.errors import CompilerError

if TYPE_CHECKING:  # pragma: no cover
    from agent_web_compiler.core.document import AgentDocument


# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------


@dataclass
class LiveExecutionResult:
    """Outcome of one :meth:`LiveActionExecutor.execute` call.

    Fields:
        action_id:      The :class:`Action.id` that was executed.
        mode_used:      ``"api"`` | ``"browser"`` | ``"skipped"`` — the mode AWC
                        ended up using. May differ from the requested decision
                        if the API path fell back to browser.
        success:        ``True`` iff the action completed without raising.
        transition:     The observed :class:`StateTransition` (browser mode only;
                        ``None`` for pure API calls, which don't change DOM state
                        as AWC observes it).
        network_calls:  All :class:`NetworkRequest` triggered by this action.
                        For API mode, the single call we made. For browser
                        mode, currently always empty (BH does not expose a
                        network event stream through the helpers module).
        screenshot_path: Path to a PNG captured after the action settled.
                        ``None`` if ``capture_screenshot=False``.
        error:          Human-readable error on failure, else ``None``.
        decision:       The :class:`ExecutionDecision` we acted on — captured
                        verbatim so callers can audit the reasoning.
    """

    action_id: str
    mode_used: str
    success: bool
    transition: StateTransition | None = None
    network_calls: list[NetworkRequest] = field(default_factory=list)
    screenshot_path: str | None = None
    error: str | None = None
    decision: ExecutionDecision | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON / logging."""
        d: dict[str, Any] = {
            "action_id": self.action_id,
            "mode_used": self.mode_used,
            "success": self.success,
            "screenshot_path": self.screenshot_path,
            "error": self.error,
        }
        if self.transition is not None:
            d["transition"] = self.transition.to_dict()
        if self.network_calls:
            d["network_calls"] = [nc.to_dict() for nc in self.network_calls]
        if self.decision is not None:
            d["decision"] = self.decision.to_dict()
        return d


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


class ConfirmationRequiredError(CompilerError):
    """Raised when an action requires user confirmation but ``auto_confirm`` is off."""


# Coordinate-click resolution: BH's preferred mode. We run a JS snippet in-page
# to find the element, scroll it into view, and return its bounding-box center.
# Returns ``null`` when no element matches — caller should treat that as a miss.
_RESOLVE_RECT_JS = """
(function(sel) {
  const e = document.querySelector(sel);
  if (!e) return null;
  try { e.scrollIntoView({block: 'center', inline: 'center'}); } catch (_) {}
  const r = e.getBoundingClientRect();
  return {x: r.left + r.width / 2, y: r.top + r.height / 2,
          w: r.width, h: r.height};
})(%s);
"""

# SPA-settle: after an action, wait briefly for readyState==complete before
# snapshotting the page. Mirrors the "wait(2)" trick from BH's domain-skills.
_DEFAULT_POST_ACTION_WAIT_MS = 800


def _import_bh() -> Any:
    """Lazy-import ``browser_harness.helpers``.

    Raises:
        CompilerError: If BH is not installed.
    """
    try:
        from browser_harness import helpers as bh  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover — depends on user env
        raise CompilerError(
            "browser-harness is not installed. "
            "Install with: pip install 'agent-web-compiler[harness]'",
            cause=exc,
        ) from exc
    return bh


def _dom_hash(html: str | None) -> str:
    if not html:
        return ""
    return hashlib.sha256(html.encode("utf-8", errors="replace")).hexdigest()[:16]


class LiveActionExecutor:
    """Execute :class:`ExecutionDecision` instances against a real browser via BH.

    Parameters:
        bu_name: BH session scope. Same semantics as
            :class:`~agent_web_compiler.sources.browser_harness_fetcher.BrowserHarnessFetcher`.
        auto_confirm: When ``True``, decisions with ``mode="confirm"`` are
            upgraded to their underlying API/browser execution. When ``False``
            (default), they become :class:`ConfirmationRequired` via the
            ``error`` field of :class:`LiveExecutionResult`.
        capture_screenshot: Capture a PNG after each action. Default ``True``.
        post_action_wait_ms: Settle time after each click/submit before the
            post-snapshot. Default 800 ms.
        default_input_value: For ``INPUT`` actions with no ``value_schema``,
            type this string. Default empty (types nothing — useful for
            "focus and let the user finish the input").
    """

    def __init__(
        self,
        *,
        bu_name: str = "awc",
        auto_confirm: bool = False,
        capture_screenshot: bool = True,
        post_action_wait_ms: int = _DEFAULT_POST_ACTION_WAIT_MS,
        default_input_value: str = "",
    ) -> None:
        self.bu_name = bu_name
        self.auto_confirm = auto_confirm
        self.capture_screenshot = capture_screenshot
        self.post_action_wait_ms = post_action_wait_ms
        self.default_input_value = default_input_value
        os.environ.setdefault("BU_NAME", bu_name)
        self._bh: Any | None = None

    def _helpers(self) -> Any:
        if self._bh is None:
            self._bh = _import_bh()
        return self._bh

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    def execute(
        self,
        decision: ExecutionDecision,
        action: Action,
        doc: AgentDocument | None = None,
    ) -> LiveExecutionResult:
        """Execute a single decision.

        The flow is:

        1. Snapshot the live page state (``url``, ``dom_hash``) → ``state_before``
        2. Dispatch by ``decision.mode`` — skip / confirm / api / browser
        3. Snapshot again → ``state_after``, synthesize a :class:`StateTransition`
        4. Optional post-action screenshot
        5. Return a :class:`LiveExecutionResult`

        ``doc`` is optional — it is used to derive an initial ``state_id`` that
        matches :class:`ActionGraphBuilder`'s scheme. If omitted, we synthesize
        a state_id from the live page URL.
        """
        t_start = time.time()

        if decision.mode == "skip":
            return LiveExecutionResult(
                action_id=action.id,
                mode_used="skipped",
                success=False,
                error=decision.reason or "decision mode=skip",
                decision=decision,
            )

        if decision.mode == "confirm" and not self.auto_confirm:
            return LiveExecutionResult(
                action_id=action.id,
                mode_used="skipped",
                success=False,
                error=f"confirmation required: {decision.reason}",
                decision=decision,
            )

        bh = self._helpers()

        # ── state_before ─────────────────────────────────────────────
        before_state = self._snapshot(bh, doc_hint=doc)

        # ── dispatch ────────────────────────────────────────────────
        # Try API path when requested (or when confirm was auto-approved).
        mode_wanted = decision.mode
        if mode_wanted == "confirm":
            # auto_confirm=True — pick api if we have a candidate, else browser
            mode_wanted = "api" if decision.api_candidate is not None else "browser"

        network_calls: list[NetworkRequest] = []
        error: str | None = None
        fallback_note: str | None = None  # informational; does not mark the result as failed
        mode_used = mode_wanted

        try:
            if mode_wanted == "api" and decision.api_candidate is not None:
                try:
                    network_calls = self._execute_api(bh, decision, action, t_start)
                except Exception as api_exc:
                    # Graceful degradation: API failed, drop to browser.
                    error_api = f"{type(api_exc).__name__}: {api_exc}"
                    try:
                        self._execute_browser(bh, action)
                        mode_used = "browser"
                        # Annotate why we fell back so the caller sees it.
                        # This is a NOTE, not an error — the action itself
                        # still succeeded end-to-end via the browser path.
                        fallback_note = f"api→browser fallback: {error_api}"
                    except Exception as browser_exc:
                        raise RuntimeError(
                            f"API failed ({error_api}); "
                            f"browser fallback also failed: {browser_exc}"
                        ) from browser_exc
            elif mode_wanted == "browser":
                self._execute_browser(bh, action)
            else:
                # Unknown mode — be strict, don't silently no-op.
                raise ValueError(
                    f"Unknown execution mode {mode_wanted!r}; "
                    "expected 'api' or 'browser'."
                )

            # Let the page settle.
            if self.post_action_wait_ms > 0:
                bh.wait(self.post_action_wait_ms / 1000.0)

        except Exception as exc:
            return LiveExecutionResult(
                action_id=action.id,
                mode_used=mode_used,
                success=False,
                network_calls=network_calls,
                error=f"{type(exc).__name__}: {exc}",
                decision=decision,
            )

        # ── state_after + transition ─────────────────────────────────
        after_state = self._snapshot(bh, doc_hint=None)
        transition = self._make_transition(action, before_state, after_state, t_start)

        # ── screenshot ───────────────────────────────────────────────
        screenshot_path: str | None = None
        if self.capture_screenshot:
            try:
                screenshot_path = bh.capture_screenshot()
            except Exception:  # pragma: no cover
                # A screenshot failure doesn't invalidate the action result.
                screenshot_path = None

        return LiveExecutionResult(
            action_id=action.id,
            mode_used=mode_used,
            success=error is None,
            transition=transition,
            network_calls=network_calls,
            screenshot_path=screenshot_path,
            error=fallback_note,  # informational note; success=True when only this is set
            decision=decision,
        )

    def execute_all(
        self,
        decisions: list[ExecutionDecision],
        actions: list[Action],
        doc: AgentDocument | None = None,
        *,
        stop_on_error: bool = False,
    ) -> list[LiveExecutionResult]:
        """Execute a batch of decisions in order.

        ``decisions`` and ``actions`` are matched by ``action_id``. If
        ``stop_on_error`` is ``True``, the first failure short-circuits the
        batch (but the already-produced results are still returned).
        """
        by_id = {a.id: a for a in actions}
        results: list[LiveExecutionResult] = []
        for d in decisions:
            action = by_id.get(d.action_id)
            if action is None:
                results.append(
                    LiveExecutionResult(
                        action_id=d.action_id,
                        mode_used="skipped",
                        success=False,
                        error=f"no action with id {d.action_id!r} in supplied list",
                        decision=d,
                    )
                )
                continue
            result = self.execute(d, action, doc=doc)
            results.append(result)
            if stop_on_error and not result.success:
                break
        return results

    # ------------------------------------------------------------------
    # Internals: API path
    # ------------------------------------------------------------------

    def _execute_api(
        self,
        bh: Any,
        decision: ExecutionDecision,
        action: Action,
        t_start: float,
    ) -> list[NetworkRequest]:
        """Call the candidate endpoint via BH's built-in ``http_get`` / in-page ``fetch``.

        Returns the list of :class:`NetworkRequest` records that were made.
        """
        assert decision.api_candidate is not None  # guarded by caller
        cand = decision.api_candidate
        method = (cand.method or "GET").upper()

        network: list[NetworkRequest] = []

        if method in ("GET", "HEAD", "OPTIONS"):
            # Filter empty values — they tend to break strict backends.
            params = {k: v for k, v in cand.params_schema.items() if v not in (None, "")}
            url = cand.endpoint
            if params:
                # Preserve existing query separator if the endpoint already has one.
                sep = "&" if "?" in url else "?"
                # urlencode via bh.http_get's own headers path — we only need a URL suffix.
                from urllib.parse import urlencode

                url = f"{url}{sep}{urlencode(params, doseq=True)}"
            headers = dict(cand.headers_pattern) if cand.headers_pattern else None
            body_text = bh.http_get(url, headers=headers, timeout=30.0)
            network.append(
                NetworkRequest(
                    url=url,
                    method=method,
                    headers=headers or {},
                    response_status=200,
                    response_size=len(body_text or ""),
                    timestamp=t_start,
                    triggered_by_action=action.id,
                )
            )
            return network

        # POST / PUT / PATCH / DELETE — delegate to an in-page ``fetch`` via bh.js.
        # We JSON-serialize everything for safety; caller can override via
        # ``api_candidate.metadata['body']`` if a non-JSON payload is needed.
        payload = (
            cand.metadata.get("body")
            if cand.metadata and "body" in cand.metadata
            else cand.params_schema
        )
        fetch_expr = (
            "return fetch("
            + json.dumps(cand.endpoint)
            + ", {method: "
            + json.dumps(method)
            + ", headers: "
            + json.dumps({"Content-Type": "application/json", **(cand.headers_pattern or {})})
            + ", body: "
            + json.dumps(json.dumps(payload) if payload is not None else None)
            + "}).then(r => r.text());"
        )
        body_text = bh.js(fetch_expr)
        network.append(
            NetworkRequest(
                url=cand.endpoint,
                method=method,
                headers=dict(cand.headers_pattern or {}),
                body=json.dumps(payload) if payload is not None else None,
                response_status=200,
                response_size=len(body_text or ""),
                timestamp=t_start,
                triggered_by_action=action.id,
            )
        )
        return network

    # ------------------------------------------------------------------
    # Internals: Browser path
    # ------------------------------------------------------------------

    def _execute_browser(self, bh: Any, action: Action) -> None:
        """Drive BH to perform the action on the live page.

        Resolution order:

        1. ``NAVIGATE`` + target URL  → ``new_tab(url)``
        2. selector is required       → resolve to bounding-box center → coordinate click
        3. ``INPUT``                  → focus the selector, then ``type_text``
        4. ``SELECT``                 → set value + dispatch ``change`` via JS
        5. ``UPLOAD``                 → ``upload_file``
        """
        if action.type == ActionType.NAVIGATE:
            target_url = action.state_effect.target_url if action.state_effect else None
            if target_url:
                bh.new_tab(target_url)
                bh.wait_for_load(timeout=15.0)
                return
            # Fall through — maybe the selector is a link we can click.

        if action.type == ActionType.UPLOAD:
            if not action.selector:
                raise ValueError("UPLOAD action requires a selector")
            file_path = (action.value_schema or {}).get("file_path", "")
            if not file_path:
                raise ValueError(
                    f"UPLOAD action {action.id!r} has no file_path in value_schema"
                )
            bh.upload_file(action.selector, file_path)
            return

        if not action.selector:
            raise ValueError(
                f"Action {action.id!r} ({action.type.value}) has no selector — "
                "live execution requires either a selector or a navigate target."
            )

        # SELECT via DOM is more reliable than clicking an <option>. Use JS.
        if action.type == ActionType.SELECT:
            value = (action.value_schema or {}).get("default") or (
                action.value_schema or {}
            ).get("value", "")
            bh.js(
                "(function(sel, v) {"
                "const e = document.querySelector(sel);"
                "if (!e) throw new Error('selector not found: ' + sel);"
                "e.value = v;"
                "e.dispatchEvent(new Event('input', {bubbles: true}));"
                "e.dispatchEvent(new Event('change', {bubbles: true}));"
                "})(" + json.dumps(action.selector) + ", " + json.dumps(str(value)) + ");"
            )
            return

        # Coordinate click path (CLICK / SUBMIT / TOGGLE / DOWNLOAD / INPUT).
        rect = bh.js(_RESOLVE_RECT_JS % json.dumps(action.selector))
        if not rect:
            raise RuntimeError(f"selector not found in live DOM: {action.selector!r}")
        x, y = rect["x"], rect["y"]
        bh.click_at_xy(x, y)

        if action.type == ActionType.INPUT:
            value = (action.value_schema or {}).get("default", self.default_input_value)
            if value:
                bh.type_text(str(value))

    # ------------------------------------------------------------------
    # Internals: Snapshots
    # ------------------------------------------------------------------

    def _snapshot(
        self,
        bh: Any,
        *,
        doc_hint: AgentDocument | None,
    ) -> PageState:
        """Take a lightweight :class:`PageState` of the live page.

        We avoid pulling the whole HTML; the ``outerHTML`` is only fetched to
        compute a 16-char DOM hash so that :class:`StateTransition` can report
        ``dom_changed``. This is cheap enough for per-action use.
        """
        try:
            info = bh.page_info() or {}
        except Exception:
            info = {}
        url = info.get("url") or (doc_hint.source_url if doc_hint else None)
        try:
            outer = bh.js("return document.documentElement.outerHTML")
        except Exception:
            outer = None
        state_id_seed = f"{url or ''}{_dom_hash(outer)}"
        state_id = "s_" + hashlib.sha256(state_id_seed.encode()).hexdigest()[:12]
        return PageState(
            state_id=state_id,
            url=url,
            dom_hash=_dom_hash(outer),
            timestamp=time.time(),
            metadata={"live": True, "title": info.get("title", "")},
        )

    @staticmethod
    def _make_transition(
        action: Action,
        before: PageState,
        after: PageState,
        t_start: float,
    ) -> StateTransition:
        """Synthesize a :class:`StateTransition` from two snapshots."""
        url_changed = (before.url or "") != (after.url or "")
        dom_changed = (before.dom_hash or "") != (after.dom_hash or "")

        if url_changed:
            effect_type = "navigate"
        elif action.type == ActionType.SUBMIT:
            effect_type = "submit"
        elif action.type == ActionType.DOWNLOAD:
            effect_type = "download"
        elif dom_changed:
            effect_type = "expand"
        else:
            effect_type = "unknown"

        return StateTransition(
            transition_id=f"t_{action.id}_{int(t_start * 1000)}",
            from_state_id=before.state_id,
            action_id=action.id,
            to_state_id=after.state_id,
            effect_type=effect_type,
            dom_changed=dom_changed,
            url_changed=url_changed,
            metadata={
                "timestamp": t_start,
                "duration_s": round(time.time() - t_start, 3),
                "from_url": before.url,
                "to_url": after.url,
            },
        )
