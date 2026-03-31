"""Generate /agent-feed.json — incremental update feed for agents.

Instead of re-crawling an entire site, agents can poll this feed
to see what changed since their last visit.

Schema:
{
    "version": "0.1.0",
    "site": "example.com",
    "generated_at": "...",
    "since": "2026-03-30T00:00:00Z",
    "changes": [{
        "url": "/products",
        "change_type": "updated",
        "blocks_added": 3,
        "blocks_removed": 1,
        "blocks_modified": 2,
        "actions_changed": true,
        "summary": "Updated pricing table, added new product"
    }]
}
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from agent_web_compiler.core.document import AgentDocument
from agent_web_compiler.utils.doc_diff import DocumentDiff, diff_documents


def _build_change_entry(
    url: str,
    change_type: str,
    diff: DocumentDiff | None = None,
) -> dict[str, Any]:
    """Build a single change entry for the feed."""
    entry: dict[str, Any] = {
        "url": url,
        "change_type": change_type,
    }

    if diff is not None:
        entry["blocks_added"] = len(diff.blocks_added)
        entry["blocks_removed"] = len(diff.blocks_removed)
        entry["blocks_modified"] = len(diff.blocks_modified)
        entry["actions_changed"] = bool(
            diff.actions_added or diff.actions_removed or diff.actions_modified
        )
        entry["summary"] = diff.summary()
    else:
        # For "added" or "removed" pages, no diff available
        entry["blocks_added"] = 0
        entry["blocks_removed"] = 0
        entry["blocks_modified"] = 0
        entry["actions_changed"] = False
        entry["summary"] = f"Page {change_type}"

    return entry


def generate_delta_feed(
    current_docs: list[AgentDocument] | None = None,
    previous_docs: list[AgentDocument] | None = None,
    site_name: str = "",
    site_url: str = "",
    *,
    old_docs: list[AgentDocument] | None = None,
    new_docs: list[AgentDocument] | None = None,
) -> str:
    """Generate a delta feed showing changes between two snapshots.

    Accepts either ``current_docs``/``previous_docs`` (preferred) or the
    legacy ``old_docs``/``new_docs`` keyword arguments.

    Args:
        current_docs: Current snapshot of compiled pages.
        previous_docs: Previous snapshot of compiled pages.
        site_name: Site name (reserved for future use).
        site_url: The top-level site URL or domain.
        old_docs: Legacy alias for previous_docs.
        new_docs: Legacy alias for current_docs.

    Returns:
        JSON string conforming to the agent-feed.json schema.

    Raises:
        ValueError: If both snapshots are empty.
    """
    # Resolve legacy aliases
    resolved_new = current_docs if current_docs is not None else (new_docs or [])
    resolved_old = previous_docs if previous_docs is not None else (old_docs or [])

    if not resolved_old and not resolved_new:
        raise ValueError("At least one document must be provided.")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Determine the "since" timestamp from old docs
    since = ""
    if resolved_old:
        earliest = min(doc.compiled_at for doc in resolved_old)
        since = earliest.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Index docs by source_url
    old_by_url: dict[str, AgentDocument] = {}
    for doc in resolved_old:
        url = doc.source_url or doc.doc_id
        old_by_url[url] = doc

    new_by_url: dict[str, AgentDocument] = {}
    for doc in resolved_new:
        url = doc.source_url or doc.doc_id
        new_by_url[url] = doc

    changes: list[dict[str, Any]] = []

    # Find updated and removed pages
    for url, old_doc in old_by_url.items():
        if url in new_by_url:
            new_doc = new_by_url[url]
            diff = diff_documents(old_doc, new_doc)
            if diff.has_changes:
                changes.append(_build_change_entry(url, "updated", diff))
        else:
            changes.append(_build_change_entry(url, "removed"))

    # Find added pages
    for url in new_by_url:
        if url not in old_by_url:
            changes.append(_build_change_entry(url, "added"))

    output: dict[str, Any] = {
        "version": "0.1.0",
        "site": site_url,
        "generated_at": now,
        "since": since,
        "changes": changes,
    }

    return json.dumps(output, indent=2, ensure_ascii=False)
