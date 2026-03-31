"""Action runtime — translates search results into executable plans.

Takes action search results and generates step-by-step execution plans
that browser automation tools can follow.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from agent_web_compiler.search.retriever import Retriever, SearchResult


@dataclass
class ExecutionStep:
    """A single step in an execution plan."""

    step_number: int
    action_type: str  # "click", "fill", "navigate", "select", "wait", "compile"
    target: str  # selector, URL, or description
    value: str | None = None  # for fill/select steps
    description: str = ""
    action_id: str | None = None  # reference to original action
    doc_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        d: dict[str, Any] = {
            "step_number": self.step_number,
            "action_type": self.action_type,
            "target": self.target,
            "description": self.description,
        }
        if self.value is not None:
            d["value"] = self.value
        if self.action_id is not None:
            d["action_id"] = self.action_id
        if self.doc_id is not None:
            d["doc_id"] = self.doc_id
        return d


@dataclass
class ExecutionPlan:
    """A complete execution plan for a task query."""

    task: str
    steps: list[ExecutionStep] = field(default_factory=list)
    confidence: float = 0.5
    requires_auth: bool = False
    estimated_actions: int = 0

    def to_markdown(self) -> str:
        """Render as human-readable markdown."""
        parts: list[str] = []
        parts.append(f"## Execution Plan: {self.task}")
        parts.append("")
        parts.append(f"**Confidence**: {self.confidence:.0%}")
        if self.requires_auth:
            parts.append("**Requires authentication**: Yes")
        parts.append(f"**Estimated steps**: {self.estimated_actions}")
        parts.append("")

        if not self.steps:
            parts.append("_No steps generated — insufficient action data._")
            return "\n".join(parts)

        for step in self.steps:
            line = f"{step.step_number}. **{step.action_type}** `{step.target}`"
            if step.value is not None:
                line += f" = `{step.value}`"
            parts.append(line)
            if step.description:
                parts.append(f"   _{step.description}_")

        return "\n".join(parts)

    def to_browser_commands(self) -> list[dict[str, Any]]:
        """Convert to browser automation commands.

        Returns a list of command dicts:
        - {"type": "navigate", "url": "..."}
        - {"type": "click", "selector": "..."}
        - {"type": "fill", "selector": "...", "value": "..."}
        - {"type": "select", "selector": "...", "value": "..."}
        - {"type": "wait", "ms": 1000}
        """
        commands: list[dict[str, Any]] = []
        for step in self.steps:
            cmd: dict[str, Any] = {}
            if step.action_type == "navigate":
                cmd = {"type": "navigate", "url": step.target}
            elif step.action_type == "click":
                cmd = {"type": "click", "selector": step.target}
            elif step.action_type == "fill":
                cmd = {
                    "type": "fill",
                    "selector": step.target,
                    "value": step.value or "",
                }
            elif step.action_type == "select":
                cmd = {
                    "type": "select",
                    "selector": step.target,
                    "value": step.value or "",
                }
            elif step.action_type == "wait":
                try:
                    ms = int(step.target)
                except (ValueError, TypeError):
                    ms = 1000
                cmd = {"type": "wait", "ms": ms}
            elif step.action_type == "compile":
                cmd = {"type": "navigate", "url": step.target}
            else:
                # Fallback: treat as click
                cmd = {"type": "click", "selector": step.target}

            if step.action_id:
                cmd["action_id"] = step.action_id
            commands.append(cmd)
        return commands

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "task": self.task,
            "steps": [s.to_dict() for s in self.steps],
            "confidence": self.confidence,
            "requires_auth": self.requires_auth,
            "estimated_actions": self.estimated_actions,
        }


# --- Keyword patterns for task decomposition ---

_URL_PATTERN = re.compile(r"https?://\S+", re.I)
_NAV_PATTERN = re.compile(
    r"\b(?:go\s+to|navigate\s+to|open|visit)\s+(.+?)(?:\s+and\b|$)", re.I
)
_FILL_PATTERN = re.compile(
    r"\b(?:fill|enter|type|input)\s+(?:in\s+)?(?:the\s+)?(.+?)(?:\s+with\s+(.+?))?(?:\s+and\b|$)",
    re.I,
)
_DOWNLOAD_PATTERN = re.compile(r"\bdownload\b", re.I)
_SEARCH_PATTERN = re.compile(r"\bsearch\s+(?:for\s+)?(.+?)(?:\s+and\b|$)", re.I)
_SUBMIT_PATTERN = re.compile(r"\b(?:submit|click\s+submit)\b", re.I)
_LOGIN_PATTERN = re.compile(r"\b(?:log\s*in|sign\s*in)\b", re.I)
_AUTH_PATTERN = re.compile(
    r"\b(?:log\s*in|sign\s*in|auth|password|credential)\b", re.I
)


class ActionRuntime:
    """Generates and manages execution plans from action search results.

    Uses a rule-based approach to decompose task queries into ordered
    execution steps, optionally enriched by search results from the
    retriever.
    """

    def __init__(self, retriever: Retriever | None = None) -> None:
        self.retriever = retriever

    def plan_task(
        self,
        query: str,
        search_results: list[SearchResult] | None = None,
    ) -> ExecutionPlan:
        """Generate an execution plan for a task query.

        If search_results provided, use them directly.
        If retriever available and no results provided, search for relevant actions first.

        Args:
            query: Natural-language task description.
            search_results: Optional pre-fetched search results.

        Returns:
            An ExecutionPlan with ordered steps.
        """
        # Get action results
        actions = search_results or []
        if not actions and self.retriever is not None:
            response = self.retriever.search(query, top_k=10)
            actions = [r for r in response.results if r.kind == "action"]

        steps = self._generate_steps(query, actions)

        requires_auth = bool(_AUTH_PATTERN.search(query))

        confidence = self._estimate_confidence(query, actions, steps)

        return ExecutionPlan(
            task=query,
            steps=steps,
            confidence=confidence,
            requires_auth=requires_auth,
            estimated_actions=len(steps),
        )

    def _generate_steps(
        self, task: str, actions: list[SearchResult]
    ) -> list[ExecutionStep]:
        """Convert matching actions into ordered execution steps.

        Decomposition rules:
        1. Navigation tasks → navigate to URL
        2. Form filling tasks → navigate + fill fields + submit
        3. Download tasks → navigate to page + click download link
        4. Search tasks → fill search field + submit
        5. Login tasks → navigate + fill credentials + submit
        6. Multi-step tasks → decompose into ordered steps
        """
        steps: list[ExecutionStep] = []
        step_num = 1

        # Extract URL from task if present
        url_match = _URL_PATTERN.search(task)
        task_url = url_match.group(0) if url_match else None

        # Check for login/auth task
        if _LOGIN_PATTERN.search(task):
            return self._plan_login(task, actions, task_url)

        # Check for search task
        search_match = _SEARCH_PATTERN.search(task)
        if search_match:
            return self._plan_search(task, actions, task_url, search_match.group(1))

        # Check for download task
        if _DOWNLOAD_PATTERN.search(task):
            return self._plan_download(task, actions, task_url)

        # Check for form filling task
        fill_match = _FILL_PATTERN.search(task)
        if fill_match:
            return self._plan_fill(task, actions, task_url, fill_match)

        # Check for navigation task
        nav_match = _NAV_PATTERN.search(task)
        if nav_match or task_url:
            target = task_url or nav_match.group(1).strip() if nav_match else ""
            steps.append(
                ExecutionStep(
                    step_number=step_num,
                    action_type="navigate",
                    target=target,
                    description=f"Navigate to {target}",
                )
            )
            step_num += 1

        # If we have matching actions from search, append them as steps
        if actions and not steps:
            # Use search results to build steps
            steps = self._steps_from_actions(actions)
        elif actions:
            # Append action-derived steps after navigation
            for action_step in self._steps_from_actions(actions, start_num=step_num):
                steps.append(action_step)

        return steps

    def _plan_login(
        self,
        task: str,
        actions: list[SearchResult],
        task_url: str | None,
    ) -> list[ExecutionStep]:
        """Generate steps for a login task."""
        steps: list[ExecutionStep] = []
        step_num = 1

        # Step 1: Navigate to login page
        nav_target = task_url or "login page"
        nav_action = _find_action_by_type(actions, "navigate")
        steps.append(
            ExecutionStep(
                step_number=step_num,
                action_type="navigate",
                target=nav_action.metadata.get("selector", nav_target)
                if nav_action
                else nav_target,
                description="Navigate to login page",
                action_id=nav_action.action_id if nav_action else None,
                doc_id=nav_action.doc_id if nav_action else None,
            )
        )
        step_num += 1

        # Step 2: Fill username
        username_action = _find_action_by_role(actions, "username") or _find_action_by_type(
            actions, "input"
        )
        steps.append(
            ExecutionStep(
                step_number=step_num,
                action_type="fill",
                target=username_action.metadata.get("selector", 'input[name="username"]')
                if username_action
                else 'input[name="username"]',
                value="",
                description="Enter username",
                action_id=username_action.action_id if username_action else None,
                doc_id=username_action.doc_id if username_action else None,
            )
        )
        step_num += 1

        # Step 3: Fill password
        steps.append(
            ExecutionStep(
                step_number=step_num,
                action_type="fill",
                target='input[name="password"]',
                value="",
                description="Enter password",
            )
        )
        step_num += 1

        # Step 4: Submit
        submit_action = _find_action_by_type(actions, "submit") or _find_action_by_type(
            actions, "click"
        )
        steps.append(
            ExecutionStep(
                step_number=step_num,
                action_type="click",
                target=submit_action.metadata.get("selector", 'button[type="submit"]')
                if submit_action
                else 'button[type="submit"]',
                description="Submit login form",
                action_id=submit_action.action_id if submit_action else None,
                doc_id=submit_action.doc_id if submit_action else None,
            )
        )

        return steps

    def _plan_search(
        self,
        task: str,
        actions: list[SearchResult],
        task_url: str | None,
        search_term: str,
    ) -> list[ExecutionStep]:
        """Generate steps for a search task."""
        steps: list[ExecutionStep] = []
        step_num = 1

        # Step 1: Navigate if URL provided
        if task_url:
            steps.append(
                ExecutionStep(
                    step_number=step_num,
                    action_type="navigate",
                    target=task_url,
                    description=f"Navigate to {task_url}",
                )
            )
            step_num += 1

        # Step 2: Fill search field
        input_action = _find_action_by_role(actions, "search") or _find_action_by_type(
            actions, "input"
        )
        steps.append(
            ExecutionStep(
                step_number=step_num,
                action_type="fill",
                target=input_action.metadata.get("selector", 'input[type="search"]')
                if input_action
                else 'input[type="search"]',
                value=search_term.strip(),
                description=f'Enter search term: "{search_term.strip()}"',
                action_id=input_action.action_id if input_action else None,
                doc_id=input_action.doc_id if input_action else None,
            )
        )
        step_num += 1

        # Step 3: Submit search
        submit_action = _find_action_by_type(actions, "submit") or _find_action_by_role(
            actions, "submit_search"
        )
        steps.append(
            ExecutionStep(
                step_number=step_num,
                action_type="click",
                target=submit_action.metadata.get("selector", 'button[type="submit"]')
                if submit_action
                else 'button[type="submit"]',
                description="Submit search",
                action_id=submit_action.action_id if submit_action else None,
                doc_id=submit_action.doc_id if submit_action else None,
            )
        )

        return steps

    def _plan_download(
        self,
        task: str,
        actions: list[SearchResult],
        task_url: str | None,
    ) -> list[ExecutionStep]:
        """Generate steps for a download task."""
        steps: list[ExecutionStep] = []
        step_num = 1

        # Step 1: Navigate to page if URL provided
        if task_url:
            steps.append(
                ExecutionStep(
                    step_number=step_num,
                    action_type="navigate",
                    target=task_url,
                    description=f"Navigate to {task_url}",
                )
            )
            step_num += 1

        # Step 2: Click download link
        download_action = _find_action_by_type(
            actions, "download"
        ) or _find_action_by_type(actions, "click")
        steps.append(
            ExecutionStep(
                step_number=step_num,
                action_type="click",
                target=download_action.metadata.get("selector", "a[download]")
                if download_action
                else "a[download]",
                description="Click download link",
                action_id=download_action.action_id if download_action else None,
                doc_id=download_action.doc_id if download_action else None,
            )
        )

        return steps

    def _plan_fill(
        self,
        task: str,
        actions: list[SearchResult],
        task_url: str | None,
        fill_match: re.Match[str],
    ) -> list[ExecutionStep]:
        """Generate steps for a form filling task."""
        steps: list[ExecutionStep] = []
        step_num = 1

        # Step 1: Navigate if URL provided
        if task_url:
            steps.append(
                ExecutionStep(
                    step_number=step_num,
                    action_type="navigate",
                    target=task_url,
                    description=f"Navigate to {task_url}",
                )
            )
            step_num += 1

        # Step 2: Fill the field
        field_desc = fill_match.group(1).strip()
        value = fill_match.group(2).strip() if fill_match.group(2) else ""
        input_action = _find_action_by_type(actions, "input")
        steps.append(
            ExecutionStep(
                step_number=step_num,
                action_type="fill",
                target=input_action.metadata.get("selector", f'input[name="{field_desc}"]')
                if input_action
                else f'input[name="{field_desc}"]',
                value=value,
                description=f"Fill {field_desc}",
                action_id=input_action.action_id if input_action else None,
                doc_id=input_action.doc_id if input_action else None,
            )
        )
        step_num += 1

        # Step 3: Submit if submit pattern matches
        if _SUBMIT_PATTERN.search(task):
            submit_action = _find_action_by_type(actions, "submit")
            steps.append(
                ExecutionStep(
                    step_number=step_num,
                    action_type="click",
                    target=submit_action.metadata.get("selector", 'button[type="submit"]')
                    if submit_action
                    else 'button[type="submit"]',
                    description="Submit form",
                    action_id=submit_action.action_id if submit_action else None,
                    doc_id=submit_action.doc_id if submit_action else None,
                )
            )

        return steps

    def _steps_from_actions(
        self,
        actions: list[SearchResult],
        start_num: int = 1,
    ) -> list[ExecutionStep]:
        """Convert search result actions into execution steps."""
        steps: list[ExecutionStep] = []
        step_num = start_num

        for result in actions:
            action_type = result.metadata.get("action_type", "click")
            selector = result.metadata.get("selector", "")

            # Map action types to execution step types
            if action_type == "navigate":
                step_type = "navigate"
            elif action_type == "input":
                step_type = "fill"
            elif action_type == "select":
                step_type = "select"
            elif action_type == "submit":
                step_type = "click"
            else:
                step_type = "click"

            steps.append(
                ExecutionStep(
                    step_number=step_num,
                    action_type=step_type,
                    target=selector or result.text,
                    value="" if step_type in ("fill", "select") else None,
                    description=result.text,
                    action_id=result.action_id,
                    doc_id=result.doc_id,
                )
            )
            step_num += 1

        return steps

    def _estimate_confidence(
        self,
        query: str,
        actions: list[SearchResult],
        steps: list[ExecutionStep],
    ) -> float:
        """Estimate plan confidence based on available evidence."""
        if not steps:
            return 0.1

        # Base: higher when we have matching actions
        if actions:
            # Average action confidence from search scores
            avg_score = sum(a.score for a in actions) / len(actions)
            base = min(avg_score, 0.9)
        else:
            # Pattern-only plan, lower confidence
            base = 0.4

        # Boost for having more steps (indicates complete decomposition)
        if len(steps) >= 3:
            base = min(base + 0.1, 0.95)

        # Penalize if auth required but no auth actions found
        if _AUTH_PATTERN.search(query) and not _find_action_by_role(actions, "login"):
            base *= 0.7

        return round(base, 2)


# --- Helpers ---


def _find_action_by_type(
    actions: list[SearchResult], action_type: str
) -> SearchResult | None:
    """Find the first action matching a given type."""
    for a in actions:
        if a.metadata.get("action_type") == action_type:
            return a
    return None


def _find_action_by_role(
    actions: list[SearchResult], role: str
) -> SearchResult | None:
    """Find the first action matching a given role (substring match)."""
    for a in actions:
        a_role = a.metadata.get("role") or ""
        if role.lower() in a_role.lower():
            return a
    return None
