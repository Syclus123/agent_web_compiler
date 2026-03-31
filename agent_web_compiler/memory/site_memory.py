"""SiteMemory — persistent site-level learning across visits.

Unlike SiteProfile (static template detection), SiteMemory learns
and evolves over time: which pages are most useful, which actions
work, which patterns repeat.

Usage:
    from agent_web_compiler.memory import SiteMemory

    memory = SiteMemory()
    memory.observe(doc1)  # First visit to example.com
    memory.observe(doc2)  # Second visit

    # Get learned insights
    insight = memory.get_insight("example.com")
    entry_points = memory.get_entry_points("example.com")
    nav_patterns = memory.get_navigation_patterns("example.com")
    action_habits = memory.get_common_actions("example.com")

    # Persist
    memory.save("site_memory.json")
    memory.load("site_memory.json")
"""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from agent_web_compiler.core.document import AgentDocument

# After observing this many pages, start computing cross-page patterns.
_MIN_PAGES_FOR_PATTERNS = 3

# Fraction of pages an element must appear in to be considered template.
_TEMPLATE_THRESHOLD = 0.70

# Fraction of pages an action role must appear in to be considered common.
_COMMON_ACTION_THRESHOLD = 0.50


@dataclass
class SiteInsight:
    """Learned insights about a website."""

    domain: str
    pages_observed: int = 0
    first_seen: float = 0.0
    last_seen: float = 0.0

    # Template patterns
    template_blocks: list[str] = field(default_factory=list)
    noise_selectors: list[str] = field(default_factory=list)
    main_content_selector: str | None = None

    # Navigation
    entry_points: list[str] = field(default_factory=list)
    hub_pages: list[str] = field(default_factory=list)
    common_paths: list[list[str]] = field(default_factory=list)

    # Actions
    common_actions: list[dict[str, Any]] = field(default_factory=list)
    search_available: bool = False
    download_available: bool = False
    login_required: bool = False

    # Content
    avg_blocks_per_page: float = 0.0
    dominant_block_types: list[str] = field(default_factory=list)
    content_language: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON persistence."""
        return {
            "domain": self.domain,
            "pages_observed": self.pages_observed,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "template_blocks": self.template_blocks,
            "noise_selectors": self.noise_selectors,
            "main_content_selector": self.main_content_selector,
            "entry_points": self.entry_points,
            "hub_pages": self.hub_pages,
            "common_paths": self.common_paths,
            "common_actions": self.common_actions,
            "search_available": self.search_available,
            "download_available": self.download_available,
            "login_required": self.login_required,
            "avg_blocks_per_page": self.avg_blocks_per_page,
            "dominant_block_types": self.dominant_block_types,
            "content_language": self.content_language,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SiteInsight:
        """Deserialize from a plain dict."""
        return cls(
            domain=data["domain"],
            pages_observed=data.get("pages_observed", 0),
            first_seen=data.get("first_seen", 0.0),
            last_seen=data.get("last_seen", 0.0),
            template_blocks=data.get("template_blocks", []),
            noise_selectors=data.get("noise_selectors", []),
            main_content_selector=data.get("main_content_selector"),
            entry_points=data.get("entry_points", []),
            hub_pages=data.get("hub_pages", []),
            common_paths=data.get("common_paths", []),
            common_actions=data.get("common_actions", []),
            search_available=data.get("search_available", False),
            download_available=data.get("download_available", False),
            login_required=data.get("login_required", False),
            avg_blocks_per_page=data.get("avg_blocks_per_page", 0.0),
            dominant_block_types=data.get("dominant_block_types", []),
            content_language=data.get("content_language"),
        )


@dataclass
class _PageRecord:
    """Internal record of a single page visit."""

    url: str
    block_count: int
    block_types: list[str]
    block_texts: list[str]
    action_roles: list[str]
    outbound_links: int
    timestamp: float


class SiteMemory:
    """Persistent site-level learning that improves over time.

    Accumulates observations from :class:`AgentDocument` instances and
    derives cross-page patterns once enough pages from the same domain
    have been observed.
    """

    def __init__(self) -> None:
        self._sites: dict[str, SiteInsight] = {}
        self._page_history: dict[str, list[_PageRecord]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def observe(self, doc: AgentDocument) -> None:
        """Record a page visit and update site-level memory.

        Args:
            doc: A compiled AgentDocument with source_url set.

        Raises:
            ValueError: If the document has no ``source_url`` or ``source_file``.
        """
        url = doc.source_url
        if not url and doc.source_file:
            url = f"file://{doc.source_file}"
        if not url:
            return  # silently skip documents with no source info

        domain = _extract_domain(url)
        now = time.time()

        # Ensure SiteInsight exists
        if domain not in self._sites:
            self._sites[domain] = SiteInsight(domain=domain, first_seen=now)

        insight = self._sites[domain]
        insight.pages_observed += 1
        insight.last_seen = now

        # Record page-level data
        block_types = [b.type.value if hasattr(b.type, "value") else str(b.type) for b in doc.blocks]
        block_texts = [b.text for b in doc.blocks]
        action_roles = [a.role for a in doc.actions if a.role]
        outbound_links = sum(
            1 for a in doc.actions
            if (a.type.value if hasattr(a.type, "value") else str(a.type)) == "navigate"
        )

        record = _PageRecord(
            url=doc.source_url,
            block_count=len(doc.blocks),
            block_types=block_types,
            block_texts=block_texts,
            action_roles=action_roles,
            outbound_links=outbound_links,
            timestamp=now,
        )
        self._page_history[domain].append(record)

        # Track language from first observation
        if doc.lang and insight.content_language is None:
            insight.content_language = doc.lang

        # Recompute patterns once we have enough pages
        if len(self._page_history[domain]) >= _MIN_PAGES_FOR_PATTERNS:
            self._recompute_patterns(domain)

    def get_insight(self, domain: str) -> SiteInsight | None:
        """Get learned insights for a domain, or ``None``."""
        return self._sites.get(domain)

    def get_entry_points(self, domain: str) -> list[str]:
        """Get recommended starting pages for a domain.

        Returns URLs ordered by outbound link count (hub-ness).
        """
        insight = self._sites.get(domain)
        return list(insight.entry_points) if insight else []

    def get_navigation_patterns(self, domain: str) -> list[list[str]]:
        """Get frequently-traversed URL sequences."""
        insight = self._sites.get(domain)
        return list(insight.common_paths) if insight else []

    def get_common_actions(self, domain: str) -> list[dict[str, Any]]:
        """Get actions that appear on most pages of a domain."""
        insight = self._sites.get(domain)
        return list(insight.common_actions) if insight else []

    def suggest_noise_selectors(self, domain: str) -> list[str]:
        """Get CSS selectors that are likely noise (template, boilerplate)."""
        insight = self._sites.get(domain)
        return list(insight.noise_selectors) if insight else []

    def save(self, path: str) -> None:
        """Persist all site insights to a JSON file.

        Args:
            path: File path to write.
        """
        data: dict[str, Any] = {
            "version": "1.0",
            "sites": {
                domain: insight.to_dict()
                for domain, insight in self._sites.items()
            },
            "page_history": {
                domain: [
                    {
                        "url": r.url,
                        "block_count": r.block_count,
                        "block_types": r.block_types,
                        "block_texts": r.block_texts,
                        "action_roles": r.action_roles,
                        "outbound_links": r.outbound_links,
                        "timestamp": r.timestamp,
                    }
                    for r in records
                ]
                for domain, records in self._page_history.items()
            },
        }
        Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load(self, path: str) -> None:
        """Load site insights from a JSON file.

        Args:
            path: File path to read.

        Raises:
            FileNotFoundError: If the path does not exist.
        """
        text = Path(path).read_text(encoding="utf-8")
        data = json.loads(text)

        self._sites.clear()
        self._page_history.clear()

        for domain, insight_data in data.get("sites", {}).items():
            self._sites[domain] = SiteInsight.from_dict(insight_data)

        for domain, records in data.get("page_history", {}).items():
            for r in records:
                self._page_history[domain].append(
                    _PageRecord(
                        url=r["url"],
                        block_count=r["block_count"],
                        block_types=r.get("block_types", []),
                        block_texts=r.get("block_texts", []),
                        action_roles=r.get("action_roles", []),
                        outbound_links=r.get("outbound_links", 0),
                        timestamp=r.get("timestamp", 0.0),
                    )
                )

    @property
    def domains(self) -> list[str]:
        """Return all observed domains."""
        return sorted(self._sites.keys())

    @property
    def stats(self) -> dict[str, Any]:
        """Return aggregate statistics across all domains."""
        total_pages = sum(i.pages_observed for i in self._sites.values())
        return {
            "domains": len(self._sites),
            "total_pages_observed": total_pages,
            "domains_with_patterns": sum(
                1 for i in self._sites.values()
                if i.pages_observed >= _MIN_PAGES_FOR_PATTERNS
            ),
        }

    # ------------------------------------------------------------------
    # Internal pattern computation
    # ------------------------------------------------------------------

    def _recompute_patterns(self, domain: str) -> None:
        """Recompute cross-page patterns from accumulated page history."""
        records = self._page_history[domain]
        insight = self._sites[domain]
        page_count = len(records)

        # --- Template blocks (texts appearing in >70% of pages) ---
        text_page_counts: Counter[str] = Counter()
        for record in records:
            # Count each unique text once per page
            unique_texts = set(record.block_texts)
            for t in unique_texts:
                text_page_counts[t] += 1

        insight.template_blocks = [
            text for text, count in text_page_counts.items()
            if count / page_count >= _TEMPLATE_THRESHOLD
        ]

        # --- Entry points: pages with most outbound links ---
        pages_by_links = sorted(records, key=lambda r: r.outbound_links, reverse=True)
        seen_urls: set[str] = set()
        entry_points: list[str] = []
        for rec in pages_by_links:
            if rec.url not in seen_urls and rec.outbound_links > 0:
                seen_urls.add(rec.url)
                entry_points.append(rec.url)
            if len(entry_points) >= 5:
                break
        insight.entry_points = entry_points
        insight.hub_pages = entry_points[:3]

        # --- Common actions: roles that appear on >50% of pages ---
        role_page_counts: Counter[str] = Counter()
        for record in records:
            unique_roles = set(record.action_roles)
            for role in unique_roles:
                role_page_counts[role] += 1

        insight.common_actions = [
            {"role": role, "frequency": count / page_count}
            for role, count in role_page_counts.most_common()
            if count / page_count >= _COMMON_ACTION_THRESHOLD
        ]

        # --- Special action flags ---
        insight.search_available = any(
            "search" in role
            for role in role_page_counts
            if role_page_counts[role] / page_count >= _COMMON_ACTION_THRESHOLD
        )
        insight.download_available = any(
            "download" in role
            for role in role_page_counts
        )
        insight.login_required = any(
            "login" in role
            for role in role_page_counts
        )

        # --- Average blocks per page ---
        total_blocks = sum(r.block_count for r in records)
        insight.avg_blocks_per_page = total_blocks / page_count if page_count else 0.0

        # --- Dominant block types (top 3) ---
        all_types: Counter[str] = Counter()
        for record in records:
            all_types.update(record.block_types)
        insight.dominant_block_types = [t for t, _ in all_types.most_common(3)]

        # --- Navigation paths (consecutive URL sequences) ---
        if page_count >= 2:
            urls = [r.url for r in records]
            # Record 2-step sequences
            path_counts: Counter[tuple[str, str]] = Counter()
            for i in range(len(urls) - 1):
                path_counts[(urls[i], urls[i + 1])] += 1
            # Keep paths seen more than once
            insight.common_paths = [
                list(pair) for pair, count in path_counts.most_common(5)
                if count > 1
            ]


# ------------------------------------------------------------------
# Pure helpers
# ------------------------------------------------------------------


def _extract_domain(url: str) -> str:
    """Extract the domain (netloc) from a URL."""
    parsed = urlparse(url)
    return parsed.netloc or parsed.path.split("/")[0]
