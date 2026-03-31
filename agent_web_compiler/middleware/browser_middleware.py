"""Browser agent middleware — compiler-first, browser-fallback.

Sits between a browser automation tool and an LLM, providing:

1. Auto-compile every page the browser visits
2. Provide structured representation to the LLM
3. Only fall back to raw screenshot/DOM when compilation is uncertain
4. Track page history as a sequence of AgentDocuments
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from agent_web_compiler.api.compile import compile_html
from agent_web_compiler.core.action import Action, ActionType
from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.core.document import AgentDocument

# Confidence threshold below which we suggest screenshot fallback
_DEFAULT_FALLBACK_THRESHOLD = 0.5


@dataclass
class PageVisit:
    """Record of a page visit with compiled output."""

    url: str
    doc: AgentDocument
    timestamp: float
    screenshot: bytes | None = None


@dataclass
class PageContext:
    """Compiled page context ready for LLM consumption."""

    doc: AgentDocument
    confidence: float
    needs_fallback: bool

    def to_llm_prompt(self, format: str = "agent_prompt") -> str:
        """Generate LLM-ready prompt from the compiled page.

        Args:
            format: ``"agent_prompt"`` (default) for a compact action-oriented
                prompt, or ``"summary"`` for a brief markdown summary.
        """
        parts: list[str] = []

        if self.doc.title:
            parts.append(f"Page: {self.doc.title}")
        if self.doc.source_url:
            parts.append(f"URL: {self.doc.source_url}")

        if self.needs_fallback:
            parts.append(
                "[Warning: page compilation confidence is low — "
                "consider using a screenshot for visual verification.]"
            )

        parts.append("")

        if format == "summary":
            parts.append(self.doc.summary_markdown())
        else:
            # Default: action-oriented prompt
            for block in self.doc.get_main_content(min_importance=0.3):
                parts.append(block.text)

            if self.doc.actions:
                parts.append("\nAvailable actions:")
                for action in self.doc.actions:
                    line = f"  [{action.id}] {action.label} ({action.type.value})"
                    if action.selector:
                        line += f" -> {action.selector}"
                    parts.append(line)

        return "\n".join(parts)

    def to_action_list(self) -> list[dict[str, Any]]:
        """Get available actions as a simple list of dicts."""
        return [
            {
                "action_id": a.id,
                "type": a.type.value,
                "label": a.label,
                "selector": a.selector,
                "priority": a.priority,
            }
            for a in self.doc.actions
        ]


class BrowserMiddleware:
    """Middleware layer between browser and LLM agent.

    Usage::

        middleware = BrowserMiddleware(config=CompileConfig())

        # When browser navigates to a page:
        page_context = middleware.on_page_load(url, html, screenshot=screenshot_bytes)

        # Feed page_context to the LLM instead of raw HTML/screenshot
        llm_input = page_context.to_llm_prompt()

        # When LLM wants to take an action:
        browser_command = middleware.translate_action(action_id="a_001_submit")
    """

    def __init__(
        self,
        config: CompileConfig | None = None,
        history_size: int = 10,
        fallback_threshold: float = _DEFAULT_FALLBACK_THRESHOLD,
    ) -> None:
        self.config = config or CompileConfig()
        self.history: list[PageVisit] = []
        self.history_size = history_size
        self.fallback_threshold = fallback_threshold
        self._current_doc: AgentDocument | None = None

    # ── Page lifecycle ───────────────────────────────────────────────

    def on_page_load(
        self,
        url: str,
        html: str,
        screenshot: bytes | None = None,
    ) -> PageContext:
        """Compile a newly loaded page and return structured context.

        Args:
            url: The page URL.
            html: Raw HTML of the page.
            screenshot: Optional screenshot bytes for fallback.

        Returns:
            A :class:`PageContext` ready for LLM consumption.
        """
        doc = compile_html(html, source_url=url, config=self.config)
        self._current_doc = doc

        visit = PageVisit(
            url=url,
            doc=doc,
            timestamp=time.time(),
            screenshot=screenshot,
        )
        self.history.append(visit)

        # Trim history
        if len(self.history) > self.history_size:
            self.history = self.history[-self.history_size:]

        confidence = doc.quality.parse_confidence
        needs_fallback = confidence < self.fallback_threshold

        return PageContext(
            doc=doc,
            confidence=confidence,
            needs_fallback=needs_fallback,
        )

    # ── Action translation ───────────────────────────────────────────

    def translate_action(self, action_id: str) -> dict[str, Any]:
        """Translate an AgentDocument action ID to a browser command.

        Returns a dict with keys:
        ``{"type": "click"|"fill"|"navigate"|..., "selector": "...", ...}``

        Raises:
            ValueError: If no current document or action not found.
        """
        if self._current_doc is None:
            raise ValueError("No page loaded — call on_page_load first.")

        action = self._find_action(action_id)
        if action is None:
            raise ValueError(
                f"Action '{action_id}' not found in current page. "
                f"Available: {[a.id for a in self._current_doc.actions]}"
            )

        return self._action_to_browser_command(action)

    # ── History ──────────────────────────────────────────────────────

    def get_history_summary(self) -> str:
        """Get a summary of recent page visits for context."""
        if not self.history:
            return "No pages visited yet."

        lines: list[str] = ["Recent page visits:"]
        for i, visit in enumerate(self.history, 1):
            title = visit.doc.title or "(untitled)"
            lines.append(
                f"  {i}. {title} — {visit.url} "
                f"({visit.doc.block_count} blocks, {visit.doc.action_count} actions)"
            )
        return "\n".join(lines)

    # ── Fallback detection ───────────────────────────────────────────

    def needs_screenshot_fallback(self) -> bool:
        """Check if the current page compilation is uncertain enough to need screenshot."""
        if self._current_doc is None:
            return True
        return self._current_doc.quality.parse_confidence < self.fallback_threshold

    # ── Private helpers ──────────────────────────────────────────────

    def _find_action(self, action_id: str) -> Action | None:
        """Look up an action by ID in the current document."""
        if self._current_doc is None:
            return None
        for action in self._current_doc.actions:
            if action.id == action_id:
                return action
        return None

    @staticmethod
    def _action_to_browser_command(action: Action) -> dict[str, Any]:
        """Map an Action to a browser automation command dict."""
        base: dict[str, Any] = {
            "action_id": action.id,
            "selector": action.selector,
        }

        if action.type == ActionType.CLICK:
            return {**base, "type": "click"}
        elif action.type == ActionType.INPUT:
            return {**base, "type": "fill", "value": ""}
        elif action.type == ActionType.SELECT:
            return {**base, "type": "select", "value": ""}
        elif action.type == ActionType.NAVIGATE:
            target_url = (
                action.state_effect.target_url
                if action.state_effect
                else None
            )
            return {**base, "type": "navigate", "url": target_url or ""}
        elif action.type == ActionType.SUBMIT or action.type == ActionType.TOGGLE or action.type == ActionType.DOWNLOAD:
            return {**base, "type": "click"}
        elif action.type == ActionType.UPLOAD:
            return {**base, "type": "upload", "file_path": ""}
        else:
            return {**base, "type": "click"}
