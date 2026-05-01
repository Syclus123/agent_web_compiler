"""Evidence adapter — translate live BH execution results into AWC Evidence.

AWC's provenance engine expects :class:`~agent_web_compiler.provenance.evidence.Evidence`
objects: block-scoped, DOM-aware, with screenshot references. A
:class:`~LiveExecutionResult` captures the raw artifacts (screenshot path,
state transition, network trace). This module bridges the two so that a
"live run" is first-class provenance, not an afterthought.

Design:

- The adapter is a pure function — no I/O, no stateful engine required. It
  takes an execution result + an originating action and produces an
  :class:`Evidence` instance.
- Big artifacts (PNG bytes) are **referenced by path**, not inlined, to keep
  evidence records JSON-serializable and cheap to pass around.
- When the transition didn't actually change state (``dom_changed=False``,
  ``url_changed=False``) we still emit evidence — a *negative* result is
  valuable data too (e.g. "clicked but nothing happened").
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_web_compiler.provenance.evidence import Evidence, _make_evidence_id

if TYPE_CHECKING:  # pragma: no cover
    from agent_web_compiler.core.action import Action
    from agent_web_compiler.runtime.browser_harness.live_executor import (
        LiveExecutionResult,
    )


def build_evidence(
    result: LiveExecutionResult,
    action: Action,
    *,
    source_url: str | None = None,
    snapshot_id: str | None = None,
) -> Evidence:
    """Materialize an :class:`Evidence` record for one live execution.

    Args:
        result: The :class:`LiveExecutionResult` returned by
            :meth:`LiveActionExecutor.execute`.
        action: The originating :class:`Action`. Used to populate
            ``section_path`` (e.g. action group / label) and ``dom_path``
            (the CSS selector AWC resolved).
        source_url: The URL of the page the action was executed on. Usually
            ``doc.source_url``.
        snapshot_id: Optional link to a :class:`~agent_web_compiler.provenance.snapshot.PageSnapshot`.

    Returns:
        A :class:`Evidence` instance suitable for attaching to a citation or
        a provenance trace. Never raises — any missing fields degrade
        gracefully.
    """
    # Provenance summary: human-readable text that survives JSON round-trips
    # and shows up in `evidence.to_dict()`.
    summary_parts: list[str] = []
    summary_parts.append(f"[{result.mode_used}] {action.type.value} -> {action.label}")
    if result.success:
        summary_parts.append("OK")
    else:
        summary_parts.append(f"FAILED: {result.error or 'unknown'}")
    if result.transition is not None:
        t = result.transition
        if t.url_changed:
            summary_parts.append("url_changed")
        if t.dom_changed:
            summary_parts.append("dom_changed")
        summary_parts.append(f"effect={t.effect_type}")

    metadata: dict[str, object] = {
        "action_type": action.type.value,
        "action_id": action.id,
        "execution_mode": result.mode_used,
        "success": result.success,
    }
    if result.error:
        metadata["error"] = result.error
    if result.screenshot_path:
        metadata["screenshot_path"] = result.screenshot_path
    if result.transition is not None:
        metadata["transition"] = result.transition.to_dict()
    if result.network_calls:
        metadata["network_calls"] = [nc.to_dict() for nc in result.network_calls]

    # Build a loose section path from action.group / action.label, so the
    # evidence is locatable in UI without re-joining to the full action graph.
    section_path: list[str] = []
    if action.group:
        section_path.append(action.group)
    if action.label:
        section_path.append(action.label)

    return Evidence(
        evidence_id=_make_evidence_id(source_url, action.id),
        source_type="action",
        source_url=source_url,
        snapshot_id=snapshot_id,
        block_id=None,
        text=" | ".join(summary_parts),
        section_path=section_path,
        dom_path=action.selector,
        content_type="action_execution",
        timestamp=(result.transition.metadata.get("timestamp", 0.0) if result.transition else 0.0),
        confidence=(action.confidence if result.success else 0.0),
        metadata=metadata,
    )
