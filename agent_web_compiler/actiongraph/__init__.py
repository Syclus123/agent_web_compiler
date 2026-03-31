"""Action Graph & UI-to-API Synthesizer.

Upgrades page interactions from "click buttons" to "understand state machines
and synthesize machine-callable interfaces."

Core components:
- ActionGraph: page-level state machine with typed actions
- APICandidate: synthesized pseudo-API from UI actions
- PageState: snapshot of available actions at a point in time
- StateTransition: observed effect of executing an action
- HybridExecutor: API-first, browser-fallback execution
"""

from agent_web_compiler.actiongraph.api_synthesizer import APISynthesizer
from agent_web_compiler.actiongraph.graph_builder import ActionGraphBuilder
from agent_web_compiler.actiongraph.hybrid_executor import ExecutionDecision, HybridExecutor
from agent_web_compiler.actiongraph.models import (
    ActionGraphModel,
    APICandidate,
    NetworkRequest,
    PageState,
    StateTransition,
)

__all__ = [
    "ActionGraphBuilder",
    "ActionGraphModel",
    "APICandidate",
    "APISynthesizer",
    "ExecutionDecision",
    "HybridExecutor",
    "NetworkRequest",
    "PageState",
    "StateTransition",
]
