"""Query planner — classifies queries and generates search/execution plans.

Determines whether a query is factual, evidential, navigational, or task-oriented,
then generates an appropriate plan of search/action steps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class QueryIntent(str, Enum):
    """Classification of user query intent."""

    FACT = "fact"  # "What is the refund policy?"
    EVIDENCE = "evidence"  # "Show me proof of X"
    NAVIGATION = "navigation"  # "Go to pricing page"
    TASK = "task"  # "Download the PDF and extract data"
    HYBRID = "hybrid"  # Mixed intent


@dataclass
class SearchStep:
    """A single step in a search plan."""

    tool: str  # "search_blocks", "search_actions", "execute_action", "compile_url"
    args: dict = field(default_factory=dict)
    description: str = ""


@dataclass
class QueryPlan:
    """A plan of steps to answer a query."""

    intent: QueryIntent
    query: str
    search_steps: list[SearchStep] = field(default_factory=list)
    stop_condition: str = "enough_evidence"
    confidence: float = 0.5


# --- Keyword patterns for intent classification ---

_TASK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(download|click|fill|submit|go\s+to|navigate|open|upload)\b", re.I),
    re.compile(r"\bfind\s+the\s+button\b", re.I),
]

_EVIDENCE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(show\s+me|prove|evidence|source|citation|quote|excerpt)\b", re.I),
]

_NAVIGATION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(go\s+to|open|visit|navigate\s+to)\b", re.I),
    re.compile(r"\b(pricing\s+page|home\s*page|about\s+page|contact\s+page)\b", re.I),
]


class QueryPlanner:
    """Plans how to answer a query using the available search capabilities.

    Uses keyword-based heuristics to classify intent, then generates a list
    of search steps appropriate for that intent.
    """

    def plan(
        self,
        query: str,
        available_sites: list[str] | None = None,
    ) -> QueryPlan:
        """Analyze a query and produce a search plan.

        Args:
            query: The user's natural-language query.
            available_sites: Optional list of indexed site domains for context.

        Returns:
            A QueryPlan with classified intent and ordered search steps.
        """
        intent = self._classify_intent(query)
        steps = self._generate_steps(intent, query)
        stop_condition = self._stop_condition_for(intent)
        confidence = self._estimate_confidence(intent, query)

        return QueryPlan(
            intent=intent,
            query=query,
            search_steps=steps,
            stop_condition=stop_condition,
            confidence=confidence,
        )

    def _classify_intent(self, query: str) -> QueryIntent:
        """Classify the query intent using keyword patterns.

        Checks patterns in order of specificity: task > evidence > navigation > fact.
        If multiple intents match, returns HYBRID.
        """
        matches: set[QueryIntent] = set()

        if any(p.search(query) for p in _TASK_PATTERNS):
            matches.add(QueryIntent.TASK)

        if any(p.search(query) for p in _EVIDENCE_PATTERNS):
            matches.add(QueryIntent.EVIDENCE)

        if any(p.search(query) for p in _NAVIGATION_PATTERNS):
            matches.add(QueryIntent.NAVIGATION)

        if not matches:
            return QueryIntent.FACT

        # Navigation keywords overlap with task keywords ("go to", "open").
        # If both match, prefer task when non-navigation task words are present.
        if matches == {QueryIntent.TASK, QueryIntent.NAVIGATION}:
            # Check for task-specific words beyond the shared ones
            task_only = re.compile(
                r"\b(download|click|fill|submit|upload)\b", re.I
            )
            if task_only.search(query):
                return QueryIntent.TASK
            return QueryIntent.NAVIGATION

        if len(matches) > 1:
            return QueryIntent.HYBRID

        return matches.pop()

    def _generate_steps(
        self, intent: QueryIntent, query: str
    ) -> list[SearchStep]:
        """Generate search steps for the classified intent."""
        if intent == QueryIntent.FACT:
            return [
                SearchStep(
                    tool="search_blocks",
                    args={},
                    description="Search content blocks for factual answer",
                ),
            ]

        if intent == QueryIntent.EVIDENCE:
            return [
                SearchStep(
                    tool="search_blocks",
                    args={"min_evidence_score": 0.7},
                    description="Search blocks with high evidence score",
                ),
            ]

        if intent == QueryIntent.NAVIGATION:
            return [
                SearchStep(
                    tool="search_actions",
                    args={"type": "navigate"},
                    description="Search for navigation actions",
                ),
            ]

        if intent == QueryIntent.TASK:
            return [
                SearchStep(
                    tool="search_actions",
                    args={},
                    description="Search for relevant actions",
                ),
                SearchStep(
                    tool="search_blocks",
                    args={},
                    description="Search blocks for context",
                ),
                SearchStep(
                    tool="execute_action",
                    args={},
                    description="Execute matched action if confident",
                ),
            ]

        # HYBRID
        return [
            SearchStep(
                tool="search_blocks",
                args={},
                description="Search content blocks",
            ),
            SearchStep(
                tool="search_actions",
                args={},
                description="Search for relevant actions",
            ),
        ]

    def _stop_condition_for(self, intent: QueryIntent) -> str:
        """Return the stop condition string for a given intent."""
        conditions = {
            QueryIntent.FACT: "enough_evidence",
            QueryIntent.EVIDENCE: "high_confidence_evidence",
            QueryIntent.NAVIGATION: "action_found",
            QueryIntent.TASK: "task_complete",
            QueryIntent.HYBRID: "enough_evidence",
        }
        return conditions[intent]

    def _estimate_confidence(self, intent: QueryIntent, query: str) -> float:
        """Estimate planner confidence based on intent clarity.

        Higher confidence when the intent is unambiguous and the query is
        well-formed (has enough tokens to be meaningful).
        """
        # Base confidence by intent clarity
        base = {
            QueryIntent.FACT: 0.6,
            QueryIntent.EVIDENCE: 0.7,
            QueryIntent.NAVIGATION: 0.8,
            QueryIntent.TASK: 0.7,
            QueryIntent.HYBRID: 0.4,
        }[intent]

        # Short queries are less confident
        word_count = len(query.split())
        if word_count < 3:
            base *= 0.8
        elif word_count > 8:
            base = min(base * 1.1, 1.0)

        return round(base, 2)
