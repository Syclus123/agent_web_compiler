"""Tests for QueryPlanner — intent classification and plan generation."""

from __future__ import annotations

import pytest

from agent_web_compiler.search.query_planner import (
    QueryIntent,
    QueryPlanner,
)


@pytest.fixture
def planner() -> QueryPlanner:
    return QueryPlanner()


# --- Intent classification ---


class TestIntentClassification:
    """Test that queries are classified to the correct intent."""

    def test_fact_query_default(self, planner: QueryPlanner) -> None:
        plan = planner.plan("What is the refund policy?")
        assert plan.intent == QueryIntent.FACT

    def test_fact_query_simple(self, planner: QueryPlanner) -> None:
        plan = planner.plan("How much does it cost?")
        assert plan.intent == QueryIntent.FACT

    def test_evidence_query_show_me(self, planner: QueryPlanner) -> None:
        plan = planner.plan("Show me evidence of the pricing change")
        assert plan.intent == QueryIntent.EVIDENCE

    def test_evidence_query_quote(self, planner: QueryPlanner) -> None:
        plan = planner.plan("Quote the relevant section about compliance")
        assert plan.intent == QueryIntent.EVIDENCE

    def test_evidence_query_citation(self, planner: QueryPlanner) -> None:
        plan = planner.plan("Give me a citation for the claim")
        assert plan.intent == QueryIntent.EVIDENCE

    def test_navigation_query_go_to(self, planner: QueryPlanner) -> None:
        plan = planner.plan("Go to the pricing page")
        assert plan.intent == QueryIntent.NAVIGATION

    def test_navigation_query_visit(self, planner: QueryPlanner) -> None:
        plan = planner.plan("Visit the home page")
        assert plan.intent == QueryIntent.NAVIGATION

    def test_task_query_download(self, planner: QueryPlanner) -> None:
        plan = planner.plan("Download the PDF report")
        assert plan.intent == QueryIntent.TASK

    def test_task_query_click(self, planner: QueryPlanner) -> None:
        plan = planner.plan("Click the submit button")
        assert plan.intent == QueryIntent.TASK

    def test_task_query_fill(self, planner: QueryPlanner) -> None:
        plan = planner.plan("Fill in the search box and submit")
        assert plan.intent == QueryIntent.TASK

    def test_task_over_navigation_when_task_words(self, planner: QueryPlanner) -> None:
        """'Go to X and download Y' should be TASK, not NAVIGATION."""
        plan = planner.plan("Go to the page and download the file")
        assert plan.intent == QueryIntent.TASK

    def test_hybrid_evidence_and_task(self, planner: QueryPlanner) -> None:
        """When evidence + task overlap, should be HYBRID."""
        plan = planner.plan("Show me evidence and click the source link")
        assert plan.intent == QueryIntent.HYBRID


# --- Plan structure ---


class TestPlanGeneration:
    """Test that plans have correct steps and stop conditions."""

    def test_fact_plan_has_search_blocks(self, planner: QueryPlanner) -> None:
        plan = planner.plan("What is the return policy?")
        assert len(plan.search_steps) >= 1
        assert plan.search_steps[0].tool == "search_blocks"

    def test_evidence_plan_has_min_evidence_score(self, planner: QueryPlanner) -> None:
        plan = planner.plan("Show me evidence of the claim")
        assert len(plan.search_steps) >= 1
        step = plan.search_steps[0]
        assert step.tool == "search_blocks"
        assert step.args.get("min_evidence_score") == 0.7

    def test_navigation_plan_has_search_actions(self, planner: QueryPlanner) -> None:
        plan = planner.plan("Navigate to the pricing page")
        assert len(plan.search_steps) >= 1
        assert plan.search_steps[0].tool == "search_actions"

    def test_task_plan_has_multiple_steps(self, planner: QueryPlanner) -> None:
        plan = planner.plan("Download the annual report")
        tools = [s.tool for s in plan.search_steps]
        assert "search_actions" in tools
        assert "search_blocks" in tools

    def test_fact_stop_condition(self, planner: QueryPlanner) -> None:
        plan = planner.plan("How many employees?")
        assert plan.stop_condition == "enough_evidence"

    def test_navigation_stop_condition(self, planner: QueryPlanner) -> None:
        plan = planner.plan("Navigate to about page")
        assert plan.stop_condition == "action_found"

    def test_task_stop_condition(self, planner: QueryPlanner) -> None:
        plan = planner.plan("Click the download button")
        assert plan.stop_condition == "task_complete"


# --- Confidence ---


class TestConfidence:
    """Test confidence estimation."""

    def test_short_query_lower_confidence(self, planner: QueryPlanner) -> None:
        short = planner.plan("refund?")
        long = planner.plan("What is the refund policy for subscription plans?")
        assert short.confidence < long.confidence

    def test_hybrid_lower_confidence(self, planner: QueryPlanner) -> None:
        hybrid = planner.plan("Show me evidence and click the source link")
        fact = planner.plan("What is the refund policy for annual plans?")
        assert hybrid.confidence < fact.confidence

    def test_confidence_in_range(self, planner: QueryPlanner) -> None:
        for q in ["test", "Show me proof", "Navigate to home", "Download file"]:
            plan = planner.plan(q)
            assert 0.0 <= plan.confidence <= 1.0


# --- QueryPlan data ---


class TestQueryPlanData:
    """Test QueryPlan dataclass fields."""

    def test_query_preserved(self, planner: QueryPlanner) -> None:
        plan = planner.plan("some query")
        assert plan.query == "some query"

    def test_search_step_has_description(self, planner: QueryPlanner) -> None:
        plan = planner.plan("What is the price?")
        for step in plan.search_steps:
            assert step.description, "Every step should have a description"
