"""Build action graphs from compiled AgentDocuments.

Analyzes actions, navigation, and page structure to create a
state machine model of the page's interactive capabilities.
"""

from __future__ import annotations

import hashlib
from typing import Any

from agent_web_compiler.actiongraph.models import (
    ActionGraphModel,
    PageState,
    StateTransition,
)
from agent_web_compiler.core.action import Action, ActionType
from agent_web_compiler.core.document import AgentDocument

# Effect type constants
EFFECT_NAVIGATE = "navigate"
EFFECT_SUBMIT = "submit"
EFFECT_DOWNLOAD = "download"
EFFECT_EXPAND = "expand"
EFFECT_FILTER = "filter"
EFFECT_MODAL = "modal"
EFFECT_UNKNOWN = "unknown"

# Action types that typically filter/sort without navigation
_FILTER_ROLES = frozenset({"filter", "sort", "pagination", "next_page", "prev_page"})


class ActionGraphBuilder:
    """Builds action graphs from compiled documents.

    For each document, creates a PageState containing the visible blocks
    and available actions, then infers transitions based on action types
    and state effects.
    """

    def build_from_document(self, doc: AgentDocument) -> ActionGraphModel:
        """Build an action graph from a single compiled document.

        Args:
            doc: A compiled AgentDocument with blocks and actions.

        Returns:
            An ActionGraphModel with one state and inferred transitions.
        """
        state = self._create_page_state(doc)
        transitions = self._infer_transitions(doc, state)

        # Collect unique target states from transitions
        target_states: list[PageState] = []
        seen_ids: set[str] = {state.state_id}
        for t in transitions:
            if t.to_state_id not in seen_ids:
                seen_ids.add(t.to_state_id)
                target_states.append(PageState(
                    state_id=t.to_state_id,
                    url=t.metadata.get("target_url"),
                ))

        return ActionGraphModel(
            states=[state, *target_states],
            transitions=transitions,
        )

    def build_from_documents(self, docs: list[AgentDocument]) -> ActionGraphModel:
        """Build a multi-page action graph from multiple documents.

        Links states across documents by matching target URLs to document
        source URLs.

        Args:
            docs: List of compiled AgentDocuments.

        Returns:
            An ActionGraphModel spanning all documents.
        """
        if not docs:
            return ActionGraphModel()

        all_states: list[PageState] = []
        all_transitions: list[StateTransition] = []

        # Build per-document states
        url_to_state: dict[str, str] = {}
        for doc in docs:
            state = self._create_page_state(doc)
            all_states.append(state)
            if doc.source_url:
                url_to_state[doc.source_url] = state.state_id

        # Build transitions, resolving cross-document links
        for doc, state in zip(docs, all_states):
            transitions = self._infer_transitions(doc, state)
            for t in transitions:
                target_url = t.metadata.get("target_url")
                if target_url and target_url in url_to_state:
                    # Link to the existing state for that URL
                    t.to_state_id = url_to_state[target_url]
                    t.metadata["cross_document"] = True
            all_transitions.extend(transitions)

        # Add placeholder states for unresolved targets
        existing_ids = {s.state_id for s in all_states}
        for t in all_transitions:
            if t.to_state_id not in existing_ids:
                existing_ids.add(t.to_state_id)
                all_states.append(PageState(
                    state_id=t.to_state_id,
                    url=t.metadata.get("target_url"),
                ))

        return ActionGraphModel(
            states=all_states,
            transitions=all_transitions,
        )

    def _create_page_state(self, doc: AgentDocument) -> PageState:
        """Create a PageState snapshot from a document."""
        state_id = _make_state_id(doc.doc_id, doc.source_url)
        return PageState(
            state_id=state_id,
            url=doc.source_url,
            dom_hash=doc.doc_id,
            visible_block_ids=[b.id for b in doc.blocks],
            available_action_ids=[a.id for a in doc.actions],
        )

    def _infer_transitions(
        self, doc: AgentDocument, state: PageState
    ) -> list[StateTransition]:
        """Infer state transitions from the document's actions.

        Each action produces one transition. The effect type and target
        state are determined by the action type and its state effects.
        """
        transitions: list[StateTransition] = []
        for action in doc.actions:
            effect = self._classify_effect(action)
            target_url = (
                action.state_effect.target_url
                if action.state_effect
                else None
            )

            # Determine target state ID
            if target_url:
                to_state_id = _make_state_id("target", target_url)
            else:
                # Same-page effect or unknown target
                to_state_id = _make_state_id("effect", f"{state.state_id}_{action.id}")

            url_changed = effect == EFFECT_NAVIGATE
            dom_changed = effect in (EFFECT_EXPAND, EFFECT_FILTER, EFFECT_SUBMIT, EFFECT_MODAL)

            metadata: dict[str, Any] = {}
            if target_url:
                metadata["target_url"] = target_url
            if action.role:
                metadata["action_role"] = action.role

            transition_id = f"t_{state.state_id}_{action.id}"
            transitions.append(StateTransition(
                transition_id=transition_id,
                from_state_id=state.state_id,
                action_id=action.id,
                to_state_id=to_state_id,
                effect_type=effect,
                dom_changed=dom_changed,
                url_changed=url_changed,
                metadata=metadata,
            ))
        return transitions

    def _classify_effect(self, action: Action) -> str:
        """Classify the expected effect type of an action.

        Uses the action type and state effects to determine what kind
        of state change executing this action would produce.
        """
        se = action.state_effect

        # Check for modal first (any action type can open a modal)
        if se and se.may_open_modal:
            return EFFECT_MODAL

        if action.type == ActionType.NAVIGATE:
            return EFFECT_NAVIGATE

        if action.type == ActionType.SUBMIT:
            return EFFECT_SUBMIT

        if action.type == ActionType.DOWNLOAD:
            return EFFECT_DOWNLOAD

        if action.type == ActionType.TOGGLE:
            return EFFECT_EXPAND

        # Check role-based classification
        if action.role and action.role in _FILTER_ROLES:
            return EFFECT_FILTER

        if action.type in (ActionType.SELECT, ActionType.INPUT):
            return EFFECT_FILTER

        return EFFECT_UNKNOWN


def _make_state_id(prefix: str, key: str | None) -> str:
    """Generate a deterministic state ID from a prefix and key."""
    safe_key = key or prefix or "unknown"
    short_hash = hashlib.sha256(safe_key.encode("utf-8")).hexdigest()[:12]
    return f"s_{prefix}_{short_hash}"
