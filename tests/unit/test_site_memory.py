"""Tests for SiteMemory — persistent site-level learning."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_web_compiler.core.action import Action, ActionType
from agent_web_compiler.core.block import Block, BlockType
from agent_web_compiler.core.document import AgentDocument, SourceType
from agent_web_compiler.memory.site_memory import SiteInsight, SiteMemory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc(
    doc_id: str = "doc_001",
    source_url: str = "https://example.com/page1",
    title: str = "Test Page",
    blocks: list[Block] | None = None,
    actions: list[Action] | None = None,
    lang: str | None = None,
) -> AgentDocument:
    """Create a minimal AgentDocument for testing."""
    return AgentDocument(
        doc_id=doc_id,
        source_type=SourceType.HTML,
        source_url=source_url,
        title=title,
        lang=lang,
        blocks=blocks or [
            Block(id="b1", type=BlockType.HEADING, text="Welcome", importance=0.9, order=0),
            Block(id="b2", type=BlockType.PARAGRAPH, text="Hello world", importance=0.7, order=1),
        ],
        actions=actions or [],
    )


def _make_docs_for_domain(
    domain: str = "example.com",
    count: int = 4,
    shared_block_text: str = "Shared footer text",
    shared_action_role: str = "search",
) -> list[AgentDocument]:
    """Create several documents from the same domain for pattern detection."""
    docs: list[AgentDocument] = []
    for i in range(count):
        blocks = [
            Block(id=f"b{i}_0", type=BlockType.HEADING, text=f"Page {i} title", importance=0.9, order=0),
            Block(id=f"b{i}_1", type=BlockType.PARAGRAPH, text=f"Unique content for page {i}", importance=0.7, order=1),
            Block(id=f"b{i}_2", type=BlockType.PARAGRAPH, text=shared_block_text, importance=0.3, order=2),
        ]
        actions = [
            Action(
                id=f"a{i}_search",
                type=ActionType.INPUT,
                label="Search",
                selector="input#search",
                role=shared_action_role,
                confidence=0.9,
                priority=0.8,
            ),
            Action(
                id=f"a{i}_nav",
                type=ActionType.NAVIGATE,
                label=f"Link {i}",
                selector=f"a.link-{i}",
                role="navigation",
                confidence=0.8,
                priority=0.5,
            ),
        ]
        docs.append(
            _make_doc(
                doc_id=f"doc_{domain}_{i:03d}",
                source_url=f"https://{domain}/page{i}",
                title=f"Page {i}",
                blocks=blocks,
                actions=actions,
                lang="en",
            )
        )
    return docs


# ---------------------------------------------------------------------------
# SiteInsight tests
# ---------------------------------------------------------------------------


class TestSiteInsight:
    """Tests for the SiteInsight dataclass."""

    def test_to_dict_round_trip(self) -> None:
        insight = SiteInsight(
            domain="example.com",
            pages_observed=5,
            first_seen=1000.0,
            last_seen=2000.0,
            search_available=True,
            dominant_block_types=["paragraph", "heading"],
        )
        d = insight.to_dict()
        restored = SiteInsight.from_dict(d)
        assert restored.domain == "example.com"
        assert restored.pages_observed == 5
        assert restored.search_available is True
        assert restored.dominant_block_types == ["paragraph", "heading"]

    def test_defaults(self) -> None:
        insight = SiteInsight(domain="test.org")
        assert insight.pages_observed == 0
        assert insight.entry_points == []
        assert insight.common_actions == []
        assert insight.search_available is False


# ---------------------------------------------------------------------------
# SiteMemory — basic observe
# ---------------------------------------------------------------------------


class TestSiteMemoryObserve:
    """Tests for SiteMemory.observe()."""

    def test_single_observe(self) -> None:
        mem = SiteMemory()
        doc = _make_doc(source_url="https://example.com/page1")
        mem.observe(doc)

        insight = mem.get_insight("example.com")
        assert insight is not None
        assert insight.pages_observed == 1
        assert insight.domain == "example.com"

    def test_observe_no_url_skips_silently(self) -> None:
        mem = SiteMemory()
        doc = _make_doc(source_url=None)
        # source_url is None — should skip without error
        mem.observe(doc)
        assert mem.stats["total_pages_observed"] == 0

    def test_observe_tracks_language(self) -> None:
        mem = SiteMemory()
        doc = _make_doc(lang="fr")
        mem.observe(doc)
        insight = mem.get_insight("example.com")
        assert insight is not None
        assert insight.content_language == "fr"

    def test_multiple_observes_same_domain(self) -> None:
        mem = SiteMemory()
        for i in range(3):
            doc = _make_doc(doc_id=f"doc_{i}", source_url=f"https://example.com/p{i}")
            mem.observe(doc)

        insight = mem.get_insight("example.com")
        assert insight is not None
        assert insight.pages_observed == 3


# ---------------------------------------------------------------------------
# SiteMemory — pattern detection
# ---------------------------------------------------------------------------


class TestSiteMemoryPatterns:
    """Tests for cross-page pattern detection."""

    def test_template_blocks_detected(self) -> None:
        """After 3+ pages, shared text should be detected as template."""
        mem = SiteMemory()
        docs = _make_docs_for_domain(count=4, shared_block_text="Copyright 2024 Example Inc.")
        for doc in docs:
            mem.observe(doc)

        insight = mem.get_insight("example.com")
        assert insight is not None
        assert "Copyright 2024 Example Inc." in insight.template_blocks

    def test_common_actions_detected(self) -> None:
        """Search role appearing on all pages should be flagged as common."""
        mem = SiteMemory()
        docs = _make_docs_for_domain(count=4, shared_action_role="search")
        for doc in docs:
            mem.observe(doc)

        insight = mem.get_insight("example.com")
        assert insight is not None
        roles = [ca["role"] for ca in insight.common_actions]
        assert "search" in roles

    def test_search_available_flag(self) -> None:
        mem = SiteMemory()
        docs = _make_docs_for_domain(count=4, shared_action_role="search")
        for doc in docs:
            mem.observe(doc)

        insight = mem.get_insight("example.com")
        assert insight is not None
        assert insight.search_available is True

    def test_entry_points(self) -> None:
        """Pages with navigate actions should appear as entry points."""
        mem = SiteMemory()
        docs = _make_docs_for_domain(count=4)
        for doc in docs:
            mem.observe(doc)

        entry = mem.get_entry_points("example.com")
        assert len(entry) > 0
        # All entry points should be valid URLs
        for ep in entry:
            assert ep.startswith("https://")

    def test_dominant_block_types(self) -> None:
        mem = SiteMemory()
        docs = _make_docs_for_domain(count=4)
        for doc in docs:
            mem.observe(doc)

        insight = mem.get_insight("example.com")
        assert insight is not None
        assert len(insight.dominant_block_types) > 0
        assert "paragraph" in insight.dominant_block_types

    def test_avg_blocks_per_page(self) -> None:
        mem = SiteMemory()
        docs = _make_docs_for_domain(count=4)
        for doc in docs:
            mem.observe(doc)

        insight = mem.get_insight("example.com")
        assert insight is not None
        # Each doc has 3 blocks
        assert insight.avg_blocks_per_page == pytest.approx(3.0)

    def test_no_patterns_before_threshold(self) -> None:
        """With fewer than 3 pages, patterns should not be computed."""
        mem = SiteMemory()
        docs = _make_docs_for_domain(count=2)
        for doc in docs:
            mem.observe(doc)

        insight = mem.get_insight("example.com")
        assert insight is not None
        # Before 3 pages, template_blocks and common_actions should be empty
        assert insight.template_blocks == []
        assert insight.common_actions == []


# ---------------------------------------------------------------------------
# SiteMemory — multi-domain
# ---------------------------------------------------------------------------


class TestSiteMemoryMultiDomain:
    """Tests for multi-domain isolation."""

    def test_separate_domains(self) -> None:
        mem = SiteMemory()
        docs_a = _make_docs_for_domain(domain="alpha.com", count=4)
        docs_b = _make_docs_for_domain(domain="beta.org", count=3)

        for doc in docs_a:
            mem.observe(doc)
        for doc in docs_b:
            mem.observe(doc)

        assert "alpha.com" in mem.domains
        assert "beta.org" in mem.domains

        insight_a = mem.get_insight("alpha.com")
        insight_b = mem.get_insight("beta.org")
        assert insight_a is not None and insight_a.pages_observed == 4
        assert insight_b is not None and insight_b.pages_observed == 3

    def test_stats(self) -> None:
        mem = SiteMemory()
        docs = _make_docs_for_domain(domain="example.com", count=4)
        for doc in docs:
            mem.observe(doc)

        stats = mem.stats
        assert stats["domains"] == 1
        assert stats["total_pages_observed"] == 4
        assert stats["domains_with_patterns"] == 1


# ---------------------------------------------------------------------------
# SiteMemory — save / load
# ---------------------------------------------------------------------------


class TestSiteMemorySaveLoad:
    """Tests for persistence."""

    def test_save_and_load(self, tmp_path: Path) -> None:
        mem = SiteMemory()
        docs = _make_docs_for_domain(count=4)
        for doc in docs:
            mem.observe(doc)

        save_path = str(tmp_path / "mem.json")
        mem.save(save_path)

        # Verify file is valid JSON
        data = json.loads(Path(save_path).read_text())
        assert "version" in data
        assert "sites" in data
        assert "example.com" in data["sites"]

        # Load into fresh instance
        mem2 = SiteMemory()
        mem2.load(save_path)

        insight = mem2.get_insight("example.com")
        assert insight is not None
        assert insight.pages_observed == 4
        assert insight.domain == "example.com"

    def test_load_nonexistent_raises(self) -> None:
        mem = SiteMemory()
        with pytest.raises(FileNotFoundError):
            mem.load("/nonexistent/path/memory.json")

    def test_round_trip_preserves_patterns(self, tmp_path: Path) -> None:
        mem = SiteMemory()
        docs = _make_docs_for_domain(count=4, shared_block_text="Shared footer")
        for doc in docs:
            mem.observe(doc)

        save_path = str(tmp_path / "mem.json")
        mem.save(save_path)

        mem2 = SiteMemory()
        mem2.load(save_path)

        insight = mem2.get_insight("example.com")
        assert insight is not None
        assert "Shared footer" in insight.template_blocks
        assert insight.search_available is True


# ---------------------------------------------------------------------------
# SiteMemory — accessor edge cases
# ---------------------------------------------------------------------------


class TestSiteMemoryAccessors:
    """Tests for accessor methods on unknown domains."""

    def test_get_insight_unknown_domain(self) -> None:
        mem = SiteMemory()
        assert mem.get_insight("unknown.com") is None

    def test_get_entry_points_unknown(self) -> None:
        mem = SiteMemory()
        assert mem.get_entry_points("unknown.com") == []

    def test_get_navigation_patterns_unknown(self) -> None:
        mem = SiteMemory()
        assert mem.get_navigation_patterns("unknown.com") == []

    def test_get_common_actions_unknown(self) -> None:
        mem = SiteMemory()
        assert mem.get_common_actions("unknown.com") == []

    def test_suggest_noise_selectors_unknown(self) -> None:
        mem = SiteMemory()
        assert mem.suggest_noise_selectors("unknown.com") == []

    def test_empty_stats(self) -> None:
        mem = SiteMemory()
        stats = mem.stats
        assert stats["domains"] == 0
        assert stats["total_pages_observed"] == 0

    def test_empty_domains(self) -> None:
        mem = SiteMemory()
        assert mem.domains == []
