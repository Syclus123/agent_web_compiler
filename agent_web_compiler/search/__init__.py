"""Search layer — query planning, hybrid retrieval, and grounded answering.

Provides a multi-stage search pipeline over indexed Agent Web objects:
1. Query understanding (intent classification + plan generation)
2. Hybrid retrieval (BM25 + dense + structured re-ranking)
3. Grounded answering (citation-backed, provenance-traced answers)
4. Action runtime (task decomposition into execution plans)
5. AgentSearch (unified high-level SDK)
"""

from agent_web_compiler.search.action_runtime import (
    ActionRuntime,
    ExecutionPlan,
    ExecutionStep,
)
from agent_web_compiler.search.agent_search import AgentSearch
from agent_web_compiler.search.grounded_answer import (
    Citation,
    GroundedAnswer,
    GroundedAnswerer,
)
from agent_web_compiler.search.query_planner import (
    QueryIntent,
    QueryPlan,
    QueryPlanner,
    SearchStep,
)
from agent_web_compiler.search.retriever import (
    Retriever,
    SearchResponse,
    SearchResult,
)

__all__ = [
    "ActionRuntime",
    "AgentSearch",
    "Citation",
    "ExecutionPlan",
    "ExecutionStep",
    "GroundedAnswer",
    "GroundedAnswerer",
    "QueryIntent",
    "QueryPlan",
    "QueryPlanner",
    "Retriever",
    "SearchResponse",
    "SearchResult",
    "SearchStep",
]
