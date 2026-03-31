"""Ingestion utilities — convert AgentDocument to index records."""

from __future__ import annotations

import re
import time
from collections import Counter
from urllib.parse import urlparse

from agent_web_compiler.core.document import AgentDocument
from agent_web_compiler.index.schema import (
    ActionRecord,
    BlockRecord,
    DocumentRecord,
    SiteRecord,
)

# Stopwords for keyword extraction (small, standard set)
_STOPWORDS: frozenset[str] = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "in",
        "to",
        "of",
        "and",
        "or",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "it",
        "that",
        "this",
        "was",
        "are",
        "be",
        "has",
        "have",
        "had",
        "not",
        "but",
        "what",
        "all",
        "were",
        "we",
        "when",
        "your",
        "can",
        "there",
        "use",
        "each",
        "which",
        "she",
        "he",
        "do",
        "how",
        "their",
        "if",
        "will",
        "up",
        "about",
        "out",
        "them",
        "then",
        "no",
        "so",
        "its",
    }
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _extract_site_id(url: str | None, source_file: str | None = None) -> str | None:
    """Extract domain from a URL, or directory from file path."""
    if url:
        try:
            parsed = urlparse(url)
            return parsed.netloc or None
        except Exception:
            pass
    if source_file:
        # Use parent directory name as pseudo site_id for local files
        from pathlib import Path

        parent = Path(source_file).resolve().parent.name
        return f"local:{parent}" if parent else "local"
    return None


def _tokenize(text: str) -> list[str]:
    """Lowercase tokenize, removing stopwords."""
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS and len(t) > 1]


def _extract_keywords(text: str, top_k: int = 10) -> list[str]:
    """Extract top-k keywords by term frequency."""
    tokens = _tokenize(text)
    if not tokens:
        return []
    counts = Counter(tokens)
    return [word for word, _ in counts.most_common(top_k)]


def _compute_evidence_score(block: object) -> float:
    """Compute evidence score for a block — higher for blocks with rich content.

    Blocks with entities, provenance, tables, or code are more useful as evidence.
    """
    score = 0.3  # baseline

    # Access via attribute since Block is a pydantic model
    block_type = getattr(block, "type", None)
    metadata = getattr(block, "metadata", {})
    provenance = getattr(block, "provenance", None)
    text = getattr(block, "text", "")

    # Table and code blocks are strong evidence
    type_val = block_type.value if hasattr(block_type, "value") else str(block_type)
    if type_val in ("table", "code", "product_spec"):
        score += 0.3
    elif type_val in ("heading", "list", "faq"):
        score += 0.1

    # Blocks with entities are more useful
    if metadata.get("entities"):
        score += 0.15

    # Blocks with provenance are traceable
    if provenance is not None:
        score += 0.1

    # Longer text tends to be more informative (up to a point)
    if len(text) > 200:
        score += 0.1
    elif len(text) > 50:
        score += 0.05

    return min(score, 1.0)


def _build_summary(doc: AgentDocument) -> str:
    """Build a summary from the first 2 headings and first paragraph."""
    parts: list[str] = []
    headings_found = 0
    para_found = False

    for block in doc.blocks:
        type_val = block.type.value if hasattr(block.type, "value") else str(block.type)
        if type_val == "heading" and headings_found < 2:
            parts.append(block.text.strip())
            headings_found += 1
        elif type_val == "paragraph" and not para_found:
            # Take first 200 chars of first paragraph
            text = block.text.strip()
            parts.append(text[:200])
            para_found = True
        if headings_found >= 2 and para_found:
            break

    return " | ".join(parts) if parts else doc.title or ""


def _extract_entity_summary(doc: AgentDocument) -> list[str]:
    """Collect entity names from block metadata across the document."""
    entities: list[str] = []
    seen: set[str] = set()
    for block in doc.blocks:
        for entity in block.metadata.get("entities", []):
            name = entity if isinstance(entity, str) else str(entity)
            if name not in seen:
                seen.add(name)
                entities.append(name)
    return entities


def ingest_document(
    doc: AgentDocument,
) -> tuple[DocumentRecord, list[BlockRecord], list[ActionRecord], SiteRecord | None]:
    """Convert a compiled AgentDocument into index records.

    Returns:
        A tuple of (document_record, block_records, action_records, site_record_or_none).
        site_record is None if no source_url is present.
    """
    now = time.time()
    site_id = _extract_site_id(doc.source_url, doc.source_file)

    # Document record
    doc_record = DocumentRecord(
        doc_id=doc.doc_id,
        title=doc.title,
        url=doc.source_url,
        site_id=site_id,
        source_type=doc.source_type.value if hasattr(doc.source_type, "value") else str(doc.source_type),
        summary=_build_summary(doc),
        block_count=len(doc.blocks),
        action_count=len(doc.actions),
        entity_summary=_extract_entity_summary(doc),
        timestamp=now,
        freshness_score=1.0,
    )

    # Block records
    block_records: list[BlockRecord] = []
    for block in doc.blocks:
        type_val = block.type.value if hasattr(block.type, "value") else str(block.type)
        text = block.text or ""

        # Summary: first sentence or first 100 chars
        summary = text[:100].split(".")[0] if text else ""

        block_records.append(
            BlockRecord(
                block_id=block.id,
                doc_id=doc.doc_id,
                block_type=type_val,
                text=text,
                section_path=list(block.section_path),
                summary=summary,
                keywords=_extract_keywords(text),
                importance=block.importance,
                evidence_score=_compute_evidence_score(block),
                page=block.metadata.get("page"),
                bbox=block.metadata.get("bbox"),
                timestamp=now,
            )
        )

    # Action records
    action_records: list[ActionRecord] = []
    for action in doc.actions:
        type_val = action.type.value if hasattr(action.type, "value") else str(action.type)
        action_records.append(
            ActionRecord(
                action_id=action.id,
                doc_id=doc.doc_id,
                site_id=site_id,
                action_type=type_val,
                label=action.label,
                role=action.role,
                selector=action.selector,
                value_schema=action.value_schema,
                required_fields=list(action.required_fields),
                confidence=action.confidence,
                timestamp=now,
            )
        )

    # Site record
    site_record: SiteRecord | None = None
    if site_id:
        noise_patterns: list[str] = []
        if doc.site_profile and doc.site_profile.noise_patterns:
            noise_patterns = list(doc.site_profile.noise_patterns)

        template_sig = None
        if doc.site_profile and doc.site_profile.template_signature:
            template_sig = doc.site_profile.template_signature

        entry_points: list[str] = []
        if doc.source_url:
            entry_points = [doc.source_url]

        common_actions = [a.label for a in doc.actions[:5]]

        site_record = SiteRecord(
            site_id=site_id,
            template_signature=template_sig,
            common_actions=common_actions,
            entry_points=entry_points,
            noise_patterns=noise_patterns,
            doc_count=1,
            last_indexed=now,
        )

    return doc_record, block_records, action_records, site_record
