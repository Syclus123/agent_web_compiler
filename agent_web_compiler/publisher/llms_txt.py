"""Generate /llms.txt — a concise site overview for LLMs.

The llms.txt format (llmstxt.org) provides LLMs with a clear,
structured summary of what a site offers. This generator creates
it automatically from compiled pages.

Format:
    # Site Name
    > Brief description of the site

    ## Main Sections
    - [Section Name](url): Description

    ## API / Actions
    - [Action](url): What it does

    ## Important Pages
    - [Page Title](url): Summary
"""

from __future__ import annotations

from urllib.parse import urlparse

from agent_web_compiler.core.document import AgentDocument

# Target token budget (rough char estimate: 1 token ≈ 4 chars)
_MAX_CHARS = 8000  # ~2000 tokens


def _derive_site_name(docs: list[AgentDocument]) -> str:
    """Derive site name from the first document's URL or title."""
    for doc in docs:
        if doc.source_url:
            parsed = urlparse(doc.source_url)
            if parsed.hostname:
                return parsed.hostname
    if docs and docs[0].title:
        return docs[0].title
    return "Site"


def _group_by_section(docs: list[AgentDocument]) -> dict[str, list[AgentDocument]]:
    """Group documents by their first URL path segment."""
    sections: dict[str, list[AgentDocument]] = {}
    for doc in docs:
        section = "General"
        if doc.source_url:
            parsed = urlparse(doc.source_url)
            parts = [p for p in parsed.path.strip("/").split("/") if p]
            if parts:
                section = parts[0].replace("-", " ").replace("_", " ").title()
        sections.setdefault(section, []).append(doc)
    return sections


def _collect_action_roles(docs: list[AgentDocument]) -> list[str]:
    """Collect unique action roles across all documents."""
    seen: set[str] = set()
    roles: list[str] = []
    for doc in docs:
        for action in doc.actions:
            role = action.role or action.label
            if role and role not in seen:
                seen.add(role)
                roles.append(role)
    return roles


def _top_heading(doc: AgentDocument) -> str:
    """Get the first heading text from a document, or its title."""
    for block in doc.blocks:
        if block.type.value == "heading" and block.text.strip():
            return block.text.strip()
    return doc.title or ""


def generate_llms_txt(
    docs: list[AgentDocument],
    site_name: str = "",
    site_url: str = "",
    site_description: str = "",
) -> str:
    """Generate a /llms.txt file from compiled pages.

    Args:
        docs: Compiled AgentDocuments representing site pages.
        site_name: Site name for the header. Auto-derived if empty.
        site_url: The top-level site URL (used for derivation fallback).
        site_description: Brief site description. Auto-derived if empty.

    Returns:
        A string conforming to the llms.txt format.

    Raises:
        ValueError: If docs is empty.
    """
    if not docs:
        raise ValueError("At least one AgentDocument is required.")

    if not site_name:
        site_name = _derive_site_name(docs)

    if not site_description:
        # Use the title of the first doc as a fallback
        site_description = f"Content from {site_name}"

    lines: list[str] = []

    # Header
    lines.append(f"# {site_name}")
    lines.append(f"> {site_description}")
    lines.append("")

    # Main Sections
    sections = _group_by_section(docs)
    if sections:
        lines.append("## Main Sections")
        for section_name, section_docs in sections.items():
            # Pick the first doc as representative
            rep = section_docs[0]
            url = rep.source_url or ""
            desc = _top_heading(rep)
            lines.append(f"- [{section_name}]({url}): {desc}")
        lines.append("")

    # API / Actions
    roles = _collect_action_roles(docs)
    if roles:
        lines.append("## API / Actions")
        for role in roles:
            # Find the action's source page
            label = role.replace("_", " ").title()
            lines.append(f"- {label}")
        lines.append("")

    # Important Pages — sorted by block count descending
    sorted_docs = sorted(docs, key=lambda d: len(d.blocks), reverse=True)
    lines.append("## Important Pages")
    for doc in sorted_docs:
        url = doc.source_url or ""
        title = doc.title or _top_heading(doc) or url
        summary = _top_heading(doc) if _top_heading(doc) != title else ""
        if summary:
            lines.append(f"- [{title}]({url}): {summary}")
        else:
            lines.append(f"- [{title}]({url})")

    result = "\n".join(lines)

    # Truncate to budget if needed
    if len(result) > _MAX_CHARS:
        result = result[:_MAX_CHARS].rsplit("\n", 1)[0]

    return result
