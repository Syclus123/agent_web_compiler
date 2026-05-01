"""browser-harness runtime — live execution of AWC decisions.

This subpackage is the **executor** side of the AWC × browser-harness bridge.
It turns `HybridExecutor.decide(...)` outputs into real browser actions via
BH, while preserving AWC's evidence chain (``StateTransition`` /
``NetworkRequest`` / screenshots).

Exports:

- :class:`LiveExecutionResult` — outcome of executing one decision
- :class:`LiveActionExecutor`  — low-level decision → BH translator
- :class:`LiveRuntime`         — high-level "compile + plan + act" orchestrator
- :func:`build_evidence`       — helper to materialize EvidenceRecord from a
  :class:`LiveExecutionResult`
- :class:`SkillHints`          — structured hints parsed back from BH
  ``domain-skills/*.md`` (reverse adapter)
- :func:`load_skill_hints`     — load + merge every skill markdown under a
  BH ``agent-workspace/domain-skills/`` tree for a given domain
- :func:`parse_skill_markdown` — pure-function parser used by
  :func:`load_skill_hints`
- :func:`skill_hints_hook`     — produce an ``on_block_created`` hook that
  boosts importance for blocks whose DOM path matches a BH-curated selector

All classes in this module keep ``browser_harness`` as a lazy import, mirroring
the design of :mod:`agent_web_compiler.sources.browser_harness_fetcher`.
"""

from __future__ import annotations

from agent_web_compiler.runtime.browser_harness.evidence_adapter import build_evidence
from agent_web_compiler.runtime.browser_harness.live_executor import (
    LiveActionExecutor,
    LiveExecutionResult,
)
from agent_web_compiler.runtime.browser_harness.live_runtime import LiveRuntime
from agent_web_compiler.runtime.browser_harness.skill_hints import (
    SkillHints,
    load_skill_hints,
    parse_skill_markdown,
    skill_hints_hook,
)

__all__ = [
    "LiveActionExecutor",
    "LiveExecutionResult",
    "LiveRuntime",
    "SkillHints",
    "build_evidence",
    "load_skill_hints",
    "parse_skill_markdown",
    "skill_hints_hook",
]
