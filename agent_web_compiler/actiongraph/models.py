"""Data models for action graph, page states, and API candidates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PageState:
    """A snapshot of the page's available actions and visible content."""

    state_id: str
    url: str | None = None
    dom_hash: str | None = None
    visible_block_ids: list[str] = field(default_factory=list)
    available_action_ids: list[str] = field(default_factory=list)
    timestamp: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "state_id": self.state_id,
            "url": self.url,
            "dom_hash": self.dom_hash,
            "visible_block_ids": self.visible_block_ids,
            "available_action_ids": self.available_action_ids,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


@dataclass
class StateTransition:
    """An observed effect of executing an action."""

    transition_id: str
    from_state_id: str
    action_id: str
    to_state_id: str
    effect_type: str = "unknown"  # "navigate", "expand", "filter", "submit", "download", "modal"
    dom_changed: bool = False
    url_changed: bool = False
    new_block_ids: list[str] = field(default_factory=list)
    removed_block_ids: list[str] = field(default_factory=list)
    network_calls: list[str] = field(default_factory=list)  # endpoint URLs
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "transition_id": self.transition_id,
            "from_state_id": self.from_state_id,
            "action_id": self.action_id,
            "to_state_id": self.to_state_id,
            "effect_type": self.effect_type,
            "dom_changed": self.dom_changed,
            "url_changed": self.url_changed,
            "new_block_ids": self.new_block_ids,
            "removed_block_ids": self.removed_block_ids,
            "network_calls": self.network_calls,
            "metadata": self.metadata,
        }


@dataclass
class NetworkRequest:
    """A captured network request from a page interaction."""

    url: str
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)
    body: str | None = None
    response_status: int = 0
    response_content_type: str = ""
    response_size: int = 0
    triggered_by_action: str | None = None  # action_id
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        result: dict[str, Any] = {
            "url": self.url,
            "method": self.method,
            "headers": self.headers,
            "params": self.params,
            "response_status": self.response_status,
            "response_content_type": self.response_content_type,
            "response_size": self.response_size,
            "timestamp": self.timestamp,
        }
        if self.body is not None:
            result["body"] = self.body
        if self.triggered_by_action is not None:
            result["triggered_by_action"] = self.triggered_by_action
        return result


@dataclass
class APICandidate:
    """A synthesized pseudo-API endpoint derived from UI actions.

    NOT a confirmed public API -- a candidate inferred from network traces
    and URL/form patterns.
    """

    api_id: str
    derived_from_action_id: str | None = None
    endpoint: str = ""
    method: str = "GET"
    params_schema: dict[str, str] = field(default_factory=dict)  # param_name -> type hint
    headers_pattern: dict[str, str] = field(default_factory=dict)
    response_schema_hint: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    safety_level: str = "unknown"  # "read_only", "write", "auth_required", "unknown"
    recommended_mode: str = "browser"  # "api", "browser", "confirm"
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "api_id": self.api_id,
            "derived_from_action_id": self.derived_from_action_id,
            "endpoint": self.endpoint,
            "method": self.method,
            "params_schema": self.params_schema,
            "headers_pattern": self.headers_pattern,
            "response_schema_hint": self.response_schema_hint,
            "confidence": self.confidence,
            "safety_level": self.safety_level,
            "recommended_mode": self.recommended_mode,
            "description": self.description,
            "metadata": self.metadata,
        }

    def is_safe_to_call(self) -> bool:
        """Return True if this API candidate is safe for automated calling."""
        return self.safety_level == "read_only" and self.confidence >= 0.7


@dataclass
class ActionGraphModel:
    """Complete action graph for a page or set of pages.

    Models the page as a state machine: states are snapshots of available
    actions, transitions are the effects of executing those actions, and
    API candidates are synthesized machine-callable interfaces.
    """

    states: list[PageState] = field(default_factory=list)
    transitions: list[StateTransition] = field(default_factory=list)
    api_candidates: list[APICandidate] = field(default_factory=list)

    def get_state(self, state_id: str) -> PageState | None:
        """Look up a state by ID, or return None."""
        for s in self.states:
            if s.state_id == state_id:
                return s
        return None

    def get_transitions_from(self, state_id: str) -> list[StateTransition]:
        """Return all transitions originating from a given state."""
        return [t for t in self.transitions if t.from_state_id == state_id]

    def get_reachable_states(self, from_state_id: str) -> list[str]:
        """Return IDs of states reachable in one step from the given state."""
        seen: set[str] = set()
        result: list[str] = []
        for t in self.transitions:
            if t.from_state_id == from_state_id and t.to_state_id not in seen:
                seen.add(t.to_state_id)
                result.append(t.to_state_id)
        return result

    def get_safe_apis(self) -> list[APICandidate]:
        """Return API candidates that are safe for automated calling."""
        return [c for c in self.api_candidates if c.is_safe_to_call()]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the full graph to a plain dict."""
        return {
            "states": [s.to_dict() for s in self.states],
            "transitions": [t.to_dict() for t in self.transitions],
            "api_candidates": [c.to_dict() for c in self.api_candidates],
        }
