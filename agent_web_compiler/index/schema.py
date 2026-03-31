"""Index record schemas — search-optimized representations of compiled objects."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DocumentRecord:
    """Document-level index record for coarse retrieval."""

    doc_id: str
    title: str
    url: str | None = None
    site_id: str | None = None  # domain name
    source_type: str = "html"
    summary: str = ""  # first N chars or generated summary
    block_count: int = 0
    action_count: int = 0
    entity_summary: list[str] = field(default_factory=list)  # key entities
    timestamp: float = 0.0
    freshness_score: float = 1.0


@dataclass
class BlockRecord:
    """Block-level index record — the primary search unit."""

    block_id: str
    doc_id: str
    block_type: str  # heading, paragraph, table, code, etc.
    text: str
    section_path: list[str] = field(default_factory=list)
    summary: str = ""  # first sentence or heading
    keywords: list[str] = field(default_factory=list)  # extracted keywords
    importance: float = 0.5
    evidence_score: float = 0.5  # how useful as evidence
    page: int | None = None
    bbox: list[float] | None = None
    embedding: list[float] | None = None  # dense vector
    timestamp: float = 0.0


@dataclass
class ActionRecord:
    """Action-level index record for task-oriented queries."""

    action_id: str
    doc_id: str
    action_type: str  # click, input, submit, navigate, etc.
    label: str
    site_id: str | None = None
    role: str | None = None  # submit_search, login, next_page, etc.
    selector: str | None = None
    value_schema: dict | None = None
    required_fields: list[str] = field(default_factory=list)
    embedding: list[float] | None = None
    confidence: float = 0.5
    timestamp: float = 0.0


@dataclass
class SiteRecord:
    """Site-level record for template awareness and deduplication."""

    site_id: str  # domain
    template_signature: str | None = None
    common_actions: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    noise_patterns: list[str] = field(default_factory=list)
    doc_count: int = 0
    last_indexed: float = 0.0
