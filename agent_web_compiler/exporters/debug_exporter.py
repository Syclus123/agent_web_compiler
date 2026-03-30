"""Debug exporter — creates rich debug bundles from compiled documents."""

from __future__ import annotations

from agent_web_compiler.core.document import AgentDocument
from agent_web_compiler.exporters.json_exporter import to_dict


def to_debug_bundle(doc: AgentDocument) -> dict:
    """Create a debug bundle with full metadata.

    The bundle includes the full document data plus summary statistics
    useful for debugging and inspection.

    Args:
        doc: The compiled document.

    Returns:
        Dict containing full document data and debug summary.
    """
    data = to_dict(doc)

    bundle: dict = {
        "document": data,
        "summary": {
            "block_count": len(doc.blocks),
            "action_count": len(doc.actions),
            "block_types": _count_by_key(doc.blocks, lambda b: b.type.value),
            "action_types": _count_by_key(doc.actions, lambda a: a.type.value),
            "warnings": list(doc.quality.warnings),
        },
    }

    # Include timing from debug dict if present
    if "timings" in doc.debug:
        bundle["summary"]["timings"] = doc.debug["timings"]

    if "pipeline_stages" in doc.debug:
        bundle["summary"]["pipeline_stages"] = doc.debug["pipeline_stages"]

    return bundle


def _count_by_key(items: list, key_fn) -> dict[str, int]:  # type: ignore[type-arg]
    """Count items grouped by a key function."""
    counts: dict[str, int] = {}
    for item in items:
        k = key_fn(item)
        counts[k] = counts.get(k, 0) + 1
    return counts
