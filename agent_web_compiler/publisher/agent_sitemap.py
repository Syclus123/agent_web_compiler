"""Generate /agent-sitemap.xml — an agent-optimized sitemap.

Extends the standard sitemap format with agent-specific metadata:
block counts, action counts, content types, and importance.

Format:
<?xml version="1.0" encoding="UTF-8"?>
<agent-sitemap xmlns="https://agent-web-compiler.dev/sitemap/0.1">
  <page>
    <url>https://example.com/api</url>
    <title>API Reference</title>
    <blocks>42</blocks>
    <actions>7</actions>
    <content-types>heading,paragraph,table,code</content-types>
    <importance>0.9</importance>
    <last-compiled>2026-03-31T12:00:00Z</last-compiled>
  </page>
</agent-sitemap>
"""

from __future__ import annotations

from collections import Counter
from xml.sax.saxutils import escape

from agent_web_compiler.core.document import AgentDocument

_NAMESPACE = "https://agent-web-compiler.dev/sitemap/0.1"


def _page_importance(doc: AgentDocument) -> float:
    """Compute page-level importance as mean block importance."""
    if not doc.blocks:
        return 0.0
    total = sum(b.importance for b in doc.blocks)
    return round(total / len(doc.blocks), 2)


def _content_types(doc: AgentDocument) -> str:
    """Comma-separated list of unique block types in the document."""
    counter: Counter[str] = Counter()
    for block in doc.blocks:
        counter[block.type.value] += 1
    # Return sorted by frequency descending
    return ",".join(t for t, _ in counter.most_common())


def _page_xml(doc: AgentDocument) -> str:
    """Generate XML for a single page entry."""
    url = escape(doc.source_url or "")
    title = escape(doc.title or "")
    blocks = len(doc.blocks)
    actions = len(doc.actions)
    types = escape(_content_types(doc))
    importance = _page_importance(doc)
    compiled_at = doc.compiled_at.strftime("%Y-%m-%dT%H:%M:%SZ")

    return (
        f"  <page>\n"
        f"    <url>{url}</url>\n"
        f"    <title>{title}</title>\n"
        f"    <blocks>{blocks}</blocks>\n"
        f"    <actions>{actions}</actions>\n"
        f"    <content-types>{types}</content-types>\n"
        f"    <importance>{importance}</importance>\n"
        f"    <last-compiled>{compiled_at}</last-compiled>\n"
        f"  </page>"
    )


def generate_agent_sitemap(
    docs: list[AgentDocument],
    site_url: str = "",
) -> str:
    """Generate /agent-sitemap.xml from compiled pages.

    Args:
        docs: Compiled AgentDocuments representing site pages.
        site_url: The top-level site URL (unused in output, reserved).

    Returns:
        XML string conforming to the agent-sitemap format.

    Raises:
        ValueError: If docs is empty.
    """
    if not docs:
        raise ValueError("At least one AgentDocument is required.")

    pages_xml = "\n".join(_page_xml(doc) for doc in docs)

    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<agent-sitemap xmlns="{_NAMESPACE}">\n'
        f"{pages_xml}\n"
        f"</agent-sitemap>"
    )
