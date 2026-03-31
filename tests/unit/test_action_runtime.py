"""Tests for the action runtime — plan generation for different task types."""

from __future__ import annotations

from agent_web_compiler.search.action_runtime import (
    ActionRuntime,
    ExecutionPlan,
    ExecutionStep,
)
from agent_web_compiler.search.retriever import SearchResult

# --- Fixtures ---


def _make_action_result(
    action_id: str = "a_001",
    action_type: str = "click",
    label: str = "Click me",
    selector: str = "button.primary",
    role: str | None = None,
    score: float = 0.8,
    doc_id: str = "doc_1",
) -> SearchResult:
    """Create a mock SearchResult for an action."""
    return SearchResult(
        kind="action",
        score=score,
        doc_id=doc_id,
        action_id=action_id,
        text=label,
        metadata={
            "action_type": action_type,
            "role": role,
            "selector": selector,
            "confidence": 0.9,
        },
    )


# --- ExecutionStep ---


class TestExecutionStep:
    def test_to_dict_minimal(self) -> None:
        step = ExecutionStep(
            step_number=1,
            action_type="navigate",
            target="https://example.com",
            description="Go to example",
        )
        d = step.to_dict()
        assert d["step_number"] == 1
        assert d["action_type"] == "navigate"
        assert d["target"] == "https://example.com"
        assert "value" not in d
        assert "action_id" not in d

    def test_to_dict_with_value_and_action_id(self) -> None:
        step = ExecutionStep(
            step_number=2,
            action_type="fill",
            target="input#name",
            value="John",
            description="Enter name",
            action_id="a_001",
            doc_id="doc_1",
        )
        d = step.to_dict()
        assert d["value"] == "John"
        assert d["action_id"] == "a_001"
        assert d["doc_id"] == "doc_1"


# --- ExecutionPlan ---


class TestExecutionPlan:
    def test_empty_plan_to_markdown(self) -> None:
        plan = ExecutionPlan(task="do something", estimated_actions=0)
        md = plan.to_markdown()
        assert "do something" in md
        assert "No steps generated" in md

    def test_plan_with_steps_to_markdown(self) -> None:
        plan = ExecutionPlan(
            task="login to site",
            steps=[
                ExecutionStep(1, "navigate", "https://example.com/login", description="Go to login"),
                ExecutionStep(2, "fill", "input#user", value="admin", description="Enter username"),
                ExecutionStep(3, "click", "button#submit", description="Submit"),
            ],
            confidence=0.8,
            requires_auth=True,
            estimated_actions=3,
        )
        md = plan.to_markdown()
        assert "login to site" in md
        assert "80%" in md
        assert "authentication" in md.lower()
        assert "navigate" in md.lower()
        assert "admin" in md

    def test_to_browser_commands_navigate(self) -> None:
        plan = ExecutionPlan(
            task="visit site",
            steps=[ExecutionStep(1, "navigate", "https://example.com")],
        )
        cmds = plan.to_browser_commands()
        assert len(cmds) == 1
        assert cmds[0] == {"type": "navigate", "url": "https://example.com"}

    def test_to_browser_commands_click(self) -> None:
        plan = ExecutionPlan(
            task="click button",
            steps=[ExecutionStep(1, "click", "button.submit", action_id="a_1")],
        )
        cmds = plan.to_browser_commands()
        assert cmds[0]["type"] == "click"
        assert cmds[0]["selector"] == "button.submit"
        assert cmds[0]["action_id"] == "a_1"

    def test_to_browser_commands_fill(self) -> None:
        plan = ExecutionPlan(
            task="fill form",
            steps=[ExecutionStep(1, "fill", "input#email", value="a@b.com")],
        )
        cmds = plan.to_browser_commands()
        assert cmds[0]["type"] == "fill"
        assert cmds[0]["value"] == "a@b.com"

    def test_to_browser_commands_select(self) -> None:
        plan = ExecutionPlan(
            task="select option",
            steps=[ExecutionStep(1, "select", "select#country", value="US")],
        )
        cmds = plan.to_browser_commands()
        assert cmds[0]["type"] == "select"
        assert cmds[0]["value"] == "US"

    def test_to_browser_commands_wait(self) -> None:
        plan = ExecutionPlan(
            task="wait",
            steps=[ExecutionStep(1, "wait", "2000")],
        )
        cmds = plan.to_browser_commands()
        assert cmds[0] == {"type": "wait", "ms": 2000}

    def test_to_browser_commands_wait_invalid_ms(self) -> None:
        plan = ExecutionPlan(
            task="wait",
            steps=[ExecutionStep(1, "wait", "invalid")],
        )
        cmds = plan.to_browser_commands()
        assert cmds[0] == {"type": "wait", "ms": 1000}

    def test_to_browser_commands_compile(self) -> None:
        plan = ExecutionPlan(
            task="compile page",
            steps=[ExecutionStep(1, "compile", "https://example.com")],
        )
        cmds = plan.to_browser_commands()
        assert cmds[0] == {"type": "navigate", "url": "https://example.com"}

    def test_to_dict(self) -> None:
        plan = ExecutionPlan(
            task="test",
            steps=[ExecutionStep(1, "click", "button")],
            confidence=0.7,
            requires_auth=False,
            estimated_actions=1,
        )
        d = plan.to_dict()
        assert d["task"] == "test"
        assert len(d["steps"]) == 1
        assert d["confidence"] == 0.7
        assert d["requires_auth"] is False
        assert d["estimated_actions"] == 1


# --- ActionRuntime ---


class TestActionRuntime:
    def test_plan_navigation_with_url(self) -> None:
        runtime = ActionRuntime()
        plan = runtime.plan_task("go to https://example.com/pricing")
        assert len(plan.steps) >= 1
        assert plan.steps[0].action_type == "navigate"
        assert "example.com" in plan.steps[0].target

    def test_plan_navigation_without_url(self) -> None:
        runtime = ActionRuntime()
        plan = runtime.plan_task("go to the pricing page")
        assert len(plan.steps) >= 1
        assert plan.steps[0].action_type == "navigate"

    def test_plan_download_task(self) -> None:
        runtime = ActionRuntime()
        plan = runtime.plan_task("download the enterprise pricing PDF")
        assert any(s.action_type == "click" for s in plan.steps)
        assert "download" in plan.task.lower()

    def test_plan_download_with_url(self) -> None:
        runtime = ActionRuntime()
        plan = runtime.plan_task("download the file from https://example.com/report.pdf")
        # Should have navigate + click
        assert len(plan.steps) >= 2
        assert plan.steps[0].action_type == "navigate"

    def test_plan_search_task(self) -> None:
        runtime = ActionRuntime()
        plan = runtime.plan_task("search for authentication docs")
        assert any(s.action_type == "fill" for s in plan.steps)
        assert any(s.action_type == "click" for s in plan.steps)

    def test_plan_search_with_url(self) -> None:
        runtime = ActionRuntime()
        plan = runtime.plan_task("search for rate limit on https://docs.example.com")
        assert plan.steps[0].action_type == "navigate"
        fill_steps = [s for s in plan.steps if s.action_type == "fill"]
        assert len(fill_steps) >= 1
        assert "rate limit" in fill_steps[0].value

    def test_plan_login_task(self) -> None:
        runtime = ActionRuntime()
        plan = runtime.plan_task("log in to the admin panel")
        assert plan.requires_auth is True
        assert any(s.action_type == "fill" for s in plan.steps)
        assert any(s.action_type == "click" for s in plan.steps)
        # Should have username, password fills and submit
        fill_steps = [s for s in plan.steps if s.action_type == "fill"]
        assert len(fill_steps) >= 2

    def test_plan_with_search_results(self) -> None:
        actions = [
            _make_action_result("a_1", "navigate", "Go to pricing", "a.pricing"),
            _make_action_result("a_2", "click", "Download PDF", "a.download"),
        ]
        runtime = ActionRuntime()
        plan = runtime.plan_task("download the pricing PDF", search_results=actions)
        # Should use the download action
        assert any(s.action_id == "a_2" for s in plan.steps)

    def test_plan_with_input_action_results(self) -> None:
        actions = [
            _make_action_result("a_1", "input", "Search field", "input.search", role="search"),
            _make_action_result("a_2", "submit", "Submit search", "button.search", role="submit_search"),
        ]
        runtime = ActionRuntime()
        plan = runtime.plan_task("search for API documentation", search_results=actions)
        fill_steps = [s for s in plan.steps if s.action_type == "fill"]
        assert len(fill_steps) >= 1
        assert fill_steps[0].action_id == "a_1"

    def test_plan_empty_task_no_results(self) -> None:
        """Task that doesn't match any pattern and has no actions."""
        runtime = ActionRuntime()
        plan = runtime.plan_task("something vague")
        # Should produce an empty or minimal plan
        assert plan.confidence < 0.5

    def test_plan_confidence_with_actions(self) -> None:
        actions = [
            _make_action_result("a_1", "click", "Button", "button", score=0.9),
        ]
        runtime = ActionRuntime()
        plan = runtime.plan_task("click the button", search_results=actions)
        # Should have reasonable confidence
        assert plan.confidence >= 0.4

    def test_plan_confidence_without_actions(self) -> None:
        runtime = ActionRuntime()
        plan = runtime.plan_task("go to https://example.com")
        # Pattern-only plan should have moderate confidence
        assert 0.2 <= plan.confidence <= 0.7

    def test_plan_fill_with_value(self) -> None:
        runtime = ActionRuntime()
        plan = runtime.plan_task("fill the email field with user@example.com")
        fill_steps = [s for s in plan.steps if s.action_type == "fill"]
        assert len(fill_steps) >= 1
        assert fill_steps[0].value == "user@example.com"

    def test_steps_from_actions(self) -> None:
        """Test that action results get correctly converted to steps."""
        actions = [
            _make_action_result("a_1", "navigate", "Home", "a.home"),
            _make_action_result("a_2", "input", "Name field", "input#name"),
            _make_action_result("a_3", "submit", "Submit", "button#submit"),
        ]
        runtime = ActionRuntime()
        steps = runtime._steps_from_actions(actions)
        assert len(steps) == 3
        assert steps[0].action_type == "navigate"
        assert steps[1].action_type == "fill"
        assert steps[1].value == ""
        assert steps[2].action_type == "click"

    def test_plan_auth_detection(self) -> None:
        runtime = ActionRuntime()
        plan_auth = runtime.plan_task("sign in with my credentials")
        assert plan_auth.requires_auth is True

        plan_no_auth = runtime.plan_task("go to the pricing page")
        assert plan_no_auth.requires_auth is False
