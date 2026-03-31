"""Adapter for browser-use framework.

Provides pre-compiled affordances to reduce browser-use's
need for DOM/screenshot analysis. Acts as a compiler-first layer.
"""

from __future__ import annotations

from typing import Any

from agent_web_compiler.core.action import Action, ActionType
from agent_web_compiler.core.document import AgentDocument


class BrowserUseAdapter:
    """Provides pre-compiled page understanding for browser-use agents.

    All methods are pure transforms — no network calls, no framework dependency.
    """

    # ── Page context ─────────────────────────────────────────────────

    def get_page_context(self, doc: AgentDocument) -> dict[str, Any]:
        """Get structured page context for browser-use agent.

        Includes title, main content summary, available actions, and form fields.
        """
        # Summarise main content
        main_blocks = doc.get_main_content(min_importance=0.3)
        summary_lines: list[str] = []
        for block in main_blocks[:15]:  # cap to keep context small
            summary_lines.append(block.text)

        # Collect form fields
        form_fields = self._extract_form_fields(doc)

        return {
            "url": doc.source_url or "",
            "title": doc.title,
            "lang": doc.lang,
            "content_summary": "\n".join(summary_lines),
            "block_count": doc.block_count,
            "action_count": doc.action_count,
            "actions": [self._action_brief(a) for a in doc.actions],
            "form_fields": form_fields,
            "confidence": doc.quality.parse_confidence,
            "warnings": doc.quality.warnings,
        }

    # ── Action plan ──────────────────────────────────────────────────

    def get_action_plan(
        self, doc: AgentDocument, task: str
    ) -> list[dict[str, Any]]:
        """Suggest an action sequence for a given task based on available actions.

        This is a heuristic plan based on keyword matching against the task
        description and action labels/roles. It does **not** call an LLM.

        Returns an ordered list of
        ``{action_id, action_type, selector, description}``.
        """
        task_lower = task.lower()
        scored: list[tuple[float, Action]] = []

        for action in doc.actions:
            score = self._relevance_score(action, task_lower)
            if score > 0:
                scored.append((score, action))

        # Sort by descending relevance, then by priority
        scored.sort(key=lambda t: (t[0], t[1].priority), reverse=True)

        return [
            {
                "action_id": action.id,
                "action_type": action.type.value,
                "selector": action.selector,
                "description": action.label,
            }
            for _score, action in scored
        ]

    # ── Form fill guide ──────────────────────────────────────────────

    def get_form_fill_guide(
        self, doc: AgentDocument, form_selector: str | None = None
    ) -> dict[str, Any]:
        """Get form filling guidance: fields, types, required, suggested values.

        If *form_selector* is provided, only fields whose selector starts
        with that prefix are included.  Otherwise all input/select actions
        are returned.
        """
        fields: list[dict[str, Any]] = []

        for action in doc.actions:
            if action.type not in (
                ActionType.INPUT,
                ActionType.SELECT,
                ActionType.TOGGLE,
                ActionType.UPLOAD,
            ):
                continue

            if form_selector and action.selector and not action.selector.startswith(form_selector):
                continue

            field_info: dict[str, Any] = {
                "action_id": action.id,
                "label": action.label,
                "type": action.type.value,
                "selector": action.selector,
                "required": action.id in {
                    rf for a in doc.actions
                    if a.type == ActionType.SUBMIT
                    for rf in a.required_fields
                },
            }
            if action.value_schema:
                field_info["value_schema"] = action.value_schema
            fields.append(field_info)

        # Find matching submit action(s)
        submit_actions = [
            {"action_id": a.id, "label": a.label, "selector": a.selector}
            for a in doc.actions
            if a.type == ActionType.SUBMIT
        ]

        return {
            "fields": fields,
            "submit_actions": submit_actions,
        }

    # ── Private helpers ──────────────────────────────────────────────

    @staticmethod
    def _action_brief(action: Action) -> dict[str, Any]:
        """Compact action dict for the page context."""
        return {
            "id": action.id,
            "type": action.type.value,
            "label": action.label,
            "selector": action.selector,
            "group": action.group,
        }

    @staticmethod
    def _extract_form_fields(doc: AgentDocument) -> list[dict[str, str | None]]:
        """Pull input/select/toggle actions as form fields."""
        fields: list[dict[str, str | None]] = []
        for action in doc.actions:
            if action.type in (ActionType.INPUT, ActionType.SELECT, ActionType.TOGGLE):
                fields.append({
                    "id": action.id,
                    "label": action.label,
                    "type": action.type.value,
                    "selector": action.selector,
                })
        return fields

    @staticmethod
    def _relevance_score(action: Action, task_lower: str) -> float:
        """Heuristic relevance of an action to a task description."""
        score = 0.0
        label_lower = action.label.lower()
        role_lower = (action.role or "").lower()

        # Direct keyword overlap
        task_words = set(task_lower.split())
        label_words = set(label_lower.split())
        overlap = task_words & label_words
        score += len(overlap) * 0.3

        # Role match
        for word in task_words:
            if word in role_lower:
                score += 0.5

        # Boost high-priority actions slightly
        score += action.priority * 0.1

        return score
