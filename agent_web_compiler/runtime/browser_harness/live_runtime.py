"""LiveRuntime — high-level compile → plan → act orchestrator.

``LiveRuntime`` is the one-line entry point that most callers actually want:

    >>> from agent_web_compiler.runtime.browser_harness import LiveRuntime
    >>> rt = LiveRuntime.from_url("https://example.com")
    >>> outcomes = rt.run("click the 'Sign in' button")

Under the hood it wires:

1. :class:`BrowserHarnessFetcher` — fetch the page from the user's real Chrome
2. AWC's compilation pipeline — produce an :class:`AgentDocument`
3. :class:`APISynthesizer` + :class:`HybridExecutor` — decide per-action
4. :class:`LiveActionExecutor` — execute against BH
5. :func:`build_evidence` — every execution becomes an :class:`Evidence`

Why: this makes "Compile → Index → Act" a **single in-process closure**. A
user drops a URL and a task, AWC understands what's on the page, picks the
right actions, and drives the real browser — with each step provable.

The runtime never launches Chrome, never retries, never logs. It is a thin
composer over existing AWC components; keep it that way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from agent_web_compiler.actiongraph.api_synthesizer import APISynthesizer
from agent_web_compiler.actiongraph.hybrid_executor import HybridExecutor
from agent_web_compiler.core.action import Action
from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.runtime.browser_harness.evidence_adapter import build_evidence
from agent_web_compiler.runtime.browser_harness.live_executor import (
    LiveActionExecutor,
    LiveExecutionResult,
)

if TYPE_CHECKING:  # pragma: no cover
    from agent_web_compiler.core.document import AgentDocument
    from agent_web_compiler.provenance.evidence import Evidence


# ---------------------------------------------------------------------------
# Public result types
# ---------------------------------------------------------------------------


@dataclass
class RunOutcome:
    """Result of a single :meth:`LiveRuntime.run` call.

    Attributes:
        task:       The original natural-language task string.
        actions:    The actions AWC selected for this task (top N by relevance).
        results:    :class:`LiveExecutionResult` for each action in order.
        evidence:   :class:`Evidence` per successful execution.
    """

    task: str
    actions: list[Action] = field(default_factory=list)
    results: list[LiveExecutionResult] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """True iff every action succeeded. Empty runs count as failed."""
        return bool(self.results) and all(r.success for r in self.results)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "task": self.task,
            "success": self.success,
            "actions": [
                {"id": a.id, "type": a.type.value, "label": a.label, "selector": a.selector}
                for a in self.actions
            ],
            "results": [r.to_dict() for r in self.results],
            "evidence": [e.to_dict() for e in self.evidence],
        }


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------


class LiveRuntime:
    """Compile + plan + act — everything in one object.

    Typical usage:

        >>> rt = LiveRuntime.from_url("https://github.com/browser-use/browser-harness")
        >>> rt.run("star the repository", max_actions=1)

    You can also pre-compile and hand AWC a document:

        >>> from agent_web_compiler import compile_url
        >>> doc = compile_url(url, fetcher="browser_harness")
        >>> rt = LiveRuntime(doc)
        >>> rt.run("...")
    """

    def __init__(
        self,
        doc: AgentDocument,
        *,
        executor: LiveActionExecutor | None = None,
        synthesizer: APISynthesizer | None = None,
        hybrid: HybridExecutor | None = None,
    ) -> None:
        self.doc = doc
        self.executor = executor or LiveActionExecutor()
        self._synth = synthesizer or APISynthesizer()
        self._hybrid = hybrid or HybridExecutor()
        # Cache API candidates — they're deterministic per-doc.
        self._api_candidates = self._synth.synthesize_from_document(doc)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        config: CompileConfig | None = None,
        executor: LiveActionExecutor | None = None,
        fetcher: str = "browser_harness",
    ) -> LiveRuntime:
        """Compile ``url`` with BH and build a :class:`LiveRuntime`.

        Defaults to ``fetcher="browser_harness"`` so the compilation itself
        goes through the user's real Chrome — this keeps the session cookies
        consistent between "see the page" and "act on the page".
        """
        from agent_web_compiler.api.compile import compile_url

        doc = compile_url(url, fetcher=fetcher, config=config)
        return cls(doc, executor=executor)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(
        self,
        task: str,
        *,
        max_actions: int = 1,
        stop_on_error: bool = True,
    ) -> RunOutcome:
        """Execute ``task`` against the compiled page.

        The pipeline is:

        1. ``_select_actions`` — pick the top-N actions whose labels/roles
           match the task (cheap heuristic match — no LLM call).
        2. ``HybridExecutor.decide_all`` — API-first decisions.
        3. ``LiveActionExecutor.execute_all`` — actually do it.
        4. ``build_evidence`` — one :class:`Evidence` per successful result.

        ``max_actions`` caps the fan-out. Set to a larger value for multi-step
        tasks ("fill in name, email, submit") once you're confident the
        selector is accurate.
        """
        actions = self._select_actions(task, max_actions=max_actions)
        if not actions:
            return RunOutcome(task=task)

        decisions = [self._hybrid.decide(a, self._api_candidates) for a in actions]
        results = self.executor.execute_all(
            decisions, actions, doc=self.doc, stop_on_error=stop_on_error
        )

        evidence: list[Evidence] = []
        source_url = self.doc.source_url
        # Build a lookup so evidence attaches to the right action record.
        by_id = {a.id: a for a in actions}
        for r in results:
            if r.success:
                a = by_id.get(r.action_id)
                if a is not None:
                    evidence.append(build_evidence(r, a, source_url=source_url))

        return RunOutcome(task=task, actions=actions, results=results, evidence=evidence)

    def run_action(self, action_id: str) -> LiveExecutionResult:
        """Execute exactly one pre-selected action by id.

        Useful when another layer (e.g. an LLM) has already decided *which*
        affordance to fire and you just want to close the loop.
        """
        action = self._find_action(action_id)
        if action is None:
            return LiveExecutionResult(
                action_id=action_id,
                mode_used="skipped",
                success=False,
                error=f"action {action_id!r} not found in document",
            )
        decision = self._hybrid.decide(action, self._api_candidates)
        return self.executor.execute(decision, action, doc=self.doc)

    # ------------------------------------------------------------------
    # Action selection — deliberately simple, no LLM
    # ------------------------------------------------------------------

    def _select_actions(self, task: str, *, max_actions: int) -> list[Action]:
        """Pick up to ``max_actions`` best-matching actions for ``task``.

        Scoring: keyword overlap against label + role substring match.
        Priority is used only as a *tiebreaker* — an action with zero
        label/role match is not selected even if it has a high priority.
        That matches the principle that "no match" means "don't act".
        """
        lower = task.lower()
        tokens = {t for t in lower.split() if t}
        scored: list[tuple[float, Action]] = []
        for action in self.doc.actions:
            label_tokens = {t for t in (action.label or "").lower().split() if t}
            role = (action.role or "").lower()
            match_score = 0.0
            match_score += 0.3 * len(tokens & label_tokens)
            for tok in tokens:
                if tok and tok in role:
                    match_score += 0.5
            if match_score <= 0:
                continue  # no textual relevance — don't fire this action
            total = match_score + 0.1 * action.priority  # priority = tiebreaker
            scored.append((total, action))
        scored.sort(key=lambda p: (p[0], p[1].priority), reverse=True)
        return [a for _s, a in scored[:max_actions]]

    def _find_action(self, action_id: str) -> Action | None:
        for a in self.doc.actions:
            if a.id == action_id:
                return a
        return None
