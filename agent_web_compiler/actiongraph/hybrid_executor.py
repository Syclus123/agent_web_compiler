"""Hybrid executor -- prefers API calls, falls back to browser automation.

Execution strategy:
1. If a safe, high-confidence API candidate exists -> use API
2. If API confidence is low -> use browser automation
3. If action is high-risk (write, auth) -> require confirmation
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from agent_web_compiler.actiongraph.models import APICandidate
from agent_web_compiler.core.action import Action
from agent_web_compiler.core.document import AgentDocument


@dataclass
class ExecutionDecision:
    """A decision about how to execute an action."""

    action_id: str
    mode: str  # "api", "browser", "confirm", "skip"
    api_candidate: APICandidate | None = None
    reason: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        result: dict[str, Any] = {
            "action_id": self.action_id,
            "mode": self.mode,
            "reason": self.reason,
            "confidence": self.confidence,
        }
        if self.api_candidate is not None:
            result["api_candidate"] = self.api_candidate.to_dict()
        return result


# Confidence thresholds
_API_CONFIDENCE_THRESHOLD = 0.7
_SKIP_CONFIDENCE_THRESHOLD = 0.2


class HybridExecutor:
    """Decides execution mode for each action: API, browser, or confirm.

    For each action, finds the best matching API candidate and decides:
    - api: safe, high-confidence API exists -> call it directly
    - browser: no good API or low confidence -> drive browser
    - confirm: write or auth-required action -> ask user first
    - skip: very low confidence or unknown -> skip
    """

    def decide(
        self, action: Action, api_candidates: list[APICandidate]
    ) -> ExecutionDecision:
        """Decide how to execute a single action.

        Args:
            action: The action to execute.
            api_candidates: Available API candidates to match against.

        Returns:
            An ExecutionDecision with mode and reasoning.
        """
        # Find the best matching API candidate for this action
        best = self._find_best_candidate(action, api_candidates)

        if best is not None:
            if best.is_safe_to_call():
                return ExecutionDecision(
                    action_id=action.id,
                    mode="api",
                    api_candidate=best,
                    reason=f"Safe API candidate with confidence {best.confidence:.2f}",
                    confidence=best.confidence,
                )

            if best.safety_level in ("write", "auth_required"):
                return ExecutionDecision(
                    action_id=action.id,
                    mode="confirm",
                    api_candidate=best,
                    reason=f"API requires confirmation: safety={best.safety_level}",
                    confidence=best.confidence,
                )

            if best.confidence >= _API_CONFIDENCE_THRESHOLD:
                return ExecutionDecision(
                    action_id=action.id,
                    mode="api",
                    api_candidate=best,
                    reason=f"API candidate above threshold: {best.confidence:.2f}",
                    confidence=best.confidence,
                )

        # No good API candidate -- fall back to browser
        return ExecutionDecision(
            action_id=action.id,
            mode="browser",
            reason="No suitable API candidate; using browser automation",
            confidence=action.confidence,
        )

    def decide_all(
        self, doc: AgentDocument, api_candidates: list[APICandidate]
    ) -> list[ExecutionDecision]:
        """Decide execution mode for all actions in a document.

        Args:
            doc: The compiled document with actions.
            api_candidates: Available API candidates.

        Returns:
            List of ExecutionDecision, one per action.
        """
        return [self.decide(action, api_candidates) for action in doc.actions]

    def generate_api_call(
        self, candidate: APICandidate, params: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Generate a ready-to-execute API call specification.

        Args:
            candidate: The API candidate to call.
            params: Optional parameters to pass.

        Returns:
            A dict describing the HTTP request to make:
            {
                "method": "GET",
                "url": "https://...",
                "headers": {...},
                "params": {...},  # for GET
                "body": {...},    # for POST
            }
        """
        effective_params = dict(candidate.params_schema)  # defaults/types
        if params:
            effective_params.update(params)

        call: dict[str, Any] = {
            "method": candidate.method,
            "url": candidate.endpoint,
            "headers": dict(candidate.headers_pattern),
        }

        if candidate.method in ("GET", "HEAD", "OPTIONS"):
            # Append params as query string
            if effective_params:
                separator = "&" if "?" in candidate.endpoint else "?"
                query = urlencode(
                    {k: v for k, v in effective_params.items() if v},
                    doseq=True,
                )
                if query:
                    call["url"] = f"{candidate.endpoint}{separator}{query}"
            call["params"] = effective_params
        else:
            # POST/PUT/PATCH -> send as body
            call["body"] = effective_params

        return call

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_best_candidate(
        self, action: Action, candidates: list[APICandidate]
    ) -> APICandidate | None:
        """Find the best API candidate matching an action.

        Matches by derived_from_action_id first, then by endpoint similarity.
        """
        # Direct match by action ID
        for c in candidates:
            if c.derived_from_action_id == action.id:
                return c

        # Match by target URL if action has one
        target_url = action.state_effect.target_url if action.state_effect else None
        if target_url:
            best: APICandidate | None = None
            best_confidence = 0.0
            for c in candidates:
                if (target_url in c.endpoint or c.endpoint in target_url) and c.confidence > best_confidence:
                        best = c
                        best_confidence = c.confidence
            if best is not None:
                return best

        return None
