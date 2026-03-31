"""Tests for the SitePublisher SDK."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent_web_compiler.core.action import Action, ActionType
from agent_web_compiler.core.block import Block, BlockType
from agent_web_compiler.core.document import AgentDocument, SourceType
from agent_web_compiler.publisher.site_publisher import SitePublisher

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc(
    doc_id: str = "sha256:abc123",
    title: str = "Test Page",
    source_url: str = "https://example.com/page",
    blocks: list[Block] | None = None,
    actions: list[Action] | None = None,
) -> AgentDocument:
    """Create a minimal AgentDocument for testing."""
    return AgentDocument(
        doc_id=doc_id,
        source_type=SourceType.HTML,
        source_url=source_url,
        title=title,
        blocks=blocks
        or [
            Block(
                id="b_001",
                type=BlockType.HEADING,
                text="Getting Started",
                importance=0.9,
                order=0,
                section_path=["Getting Started"],
            ),
            Block(
                id="b_002",
                type=BlockType.PARAGRAPH,
                text="Welcome to the API documentation.",
                importance=0.7,
                order=1,
                section_path=["Getting Started"],
            ),
        ],
        actions=actions
        or [
            Action(
                id="a_login",
                type=ActionType.CLICK,
                label="Login",
                selector="#login-btn",
                confidence=0.9,
            ),
        ],
    )


def _make_doc2() -> AgentDocument:
    """Create a second distinct document."""
    return _make_doc(
        doc_id="sha256:def456",
        title="API Reference",
        source_url="https://example.com/api",
        blocks=[
            Block(
                id="b_010",
                type=BlockType.HEADING,
                text="Endpoints",
                importance=0.9,
                order=0,
            ),
            Block(
                id="b_011",
                type=BlockType.CODE,
                text="GET /api/v1/users",
                importance=0.8,
                order=1,
            ),
        ],
        actions=[
            Action(
                id="a_try_it",
                type=ActionType.CLICK,
                label="Try it",
                confidence=0.7,
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Basic operations
# ---------------------------------------------------------------------------


class TestAddPages:
    def test_add_page_increments_count(self) -> None:
        pub = SitePublisher()
        assert pub.page_count == 0
        pub.add_page(_make_doc())
        assert pub.page_count == 1

    def test_add_pages_adds_multiple(self) -> None:
        pub = SitePublisher()
        pub.add_pages([_make_doc(), _make_doc2()])
        assert pub.page_count == 2

    def test_docs_returns_copy(self) -> None:
        pub = SitePublisher()
        doc = _make_doc()
        pub.add_page(doc)
        docs = pub.docs
        assert len(docs) == 1
        # Mutating returned list should not affect publisher
        docs.clear()
        assert pub.page_count == 1


# ---------------------------------------------------------------------------
# Auto-derivation
# ---------------------------------------------------------------------------


class TestAutoDerivation:
    def test_auto_derive_site_name_from_title(self) -> None:
        pub = SitePublisher()
        doc = _make_doc(title="My Great Docs")
        pub.add_page(doc)
        summary = pub.summary
        assert summary["site_name"] == "My Great Docs"

    def test_auto_derive_site_url_from_source_url(self) -> None:
        pub = SitePublisher()
        doc = _make_doc(source_url="https://docs.example.com/intro")
        pub.add_page(doc)
        summary = pub.summary
        assert summary["site_url"] == "https://docs.example.com/intro"

    def test_explicit_values_not_overridden(self) -> None:
        pub = SitePublisher(
            site_name="Explicit Name",
            site_url="https://explicit.example.com",
        )
        pub.add_page(_make_doc())
        summary = pub.summary
        assert summary["site_name"] == "Explicit Name"
        assert summary["site_url"] == "https://explicit.example.com"


# ---------------------------------------------------------------------------
# Summary property
# ---------------------------------------------------------------------------


class TestSummary:
    def test_summary_empty(self) -> None:
        pub = SitePublisher(site_name="Empty")
        summary = pub.summary
        assert summary["page_count"] == 0
        assert summary["total_blocks"] == 0
        assert summary["total_actions"] == 0
        assert summary["has_previous_snapshot"] is False
        assert "llms.txt" in summary["files"]
        assert "agent-feed.json" not in summary["files"]

    def test_summary_with_pages(self) -> None:
        pub = SitePublisher(site_name="Test Site")
        pub.add_page(_make_doc())
        pub.add_page(_make_doc2())
        summary = pub.summary
        assert summary["page_count"] == 2
        assert summary["total_blocks"] == 4  # 2 + 2
        assert summary["total_actions"] == 2  # 1 + 1

    def test_summary_includes_delta_feed_when_snapshot_set(self) -> None:
        pub = SitePublisher()
        pub.add_page(_make_doc())
        pub.set_previous_snapshot([_make_doc()])
        summary = pub.summary
        assert "agent-feed.json" in summary["files"]
        assert summary["has_previous_snapshot"] is True


# ---------------------------------------------------------------------------
# Empty publisher
# ---------------------------------------------------------------------------


class TestEmptyPublisher:
    def test_page_count_zero(self) -> None:
        pub = SitePublisher()
        assert pub.page_count == 0

    def test_docs_empty(self) -> None:
        pub = SitePublisher()
        assert pub.docs == []

    def test_summary_zero_counts(self) -> None:
        pub = SitePublisher()
        s = pub.summary
        assert s["page_count"] == 0
        assert s["total_blocks"] == 0
        assert s["total_actions"] == 0


# ---------------------------------------------------------------------------
# Generate files (with mocked generators)
# ---------------------------------------------------------------------------


class TestGenerateLlmsTxt:
    def test_generate_llms_txt_calls_generator(self) -> None:
        """Test that generate_llms_txt delegates to the llms_txt module."""
        pub = SitePublisher(site_name="Test")
        pub.add_page(_make_doc())

        with patch(
            "agent_web_compiler.publisher.llms_txt.generate_llms_txt",
            return_value="# Test\n\nHello",
        ) as mock_gen:
            result = pub.generate_llms_txt()
            assert result == "# Test\n\nHello"
            mock_gen.assert_called_once()
            call_kwargs = mock_gen.call_args
            assert call_kwargs.kwargs["site_name"] == "Test"
            assert len(call_kwargs.kwargs["docs"]) == 1


class TestGenerateAgentJson:
    def test_generate_agent_json_calls_generator(self) -> None:
        pub = SitePublisher(site_name="Test", site_url="https://example.com")
        pub.add_page(_make_doc())

        with patch(
            "agent_web_compiler.publisher.content_json.generate_agent_json",
            return_value='{"name": "Test"}',
        ) as mock_gen:
            result = pub.generate_agent_json()
            assert result == '{"name": "Test"}'
            mock_gen.assert_called_once()


class TestGenerateContentJson:
    def test_generate_content_json_calls_generator(self) -> None:
        pub = SitePublisher(site_name="Test")
        pub.add_page(_make_doc())

        with patch(
            "agent_web_compiler.publisher.content_json.generate_content_json",
            return_value='{"pages": []}',
        ) as mock_gen:
            result = pub.generate_content_json()
            assert result == '{"pages": []}'
            mock_gen.assert_called_once()


class TestGenerateActionsJson:
    def test_generate_actions_json_calls_generator(self) -> None:
        pub = SitePublisher(site_name="Test")
        pub.add_page(_make_doc())

        with patch(
            "agent_web_compiler.publisher.actions_json.generate_actions_json",
            return_value='{"actions": []}',
        ) as mock_gen:
            result = pub.generate_actions_json()
            assert result == '{"actions": []}'
            mock_gen.assert_called_once()


class TestGenerateAgentSitemap:
    def test_generate_agent_sitemap_calls_generator(self) -> None:
        pub = SitePublisher(site_url="https://example.com")
        pub.add_page(_make_doc())

        with patch(
            "agent_web_compiler.publisher.agent_sitemap.generate_agent_sitemap",
            return_value='<?xml version="1.0"?><urlset></urlset>',
        ) as mock_gen:
            result = pub.generate_agent_sitemap()
            assert "<?xml" in result
            mock_gen.assert_called_once()


class TestGenerateDeltaFeed:
    def test_generate_delta_feed_calls_generator(self) -> None:
        pub = SitePublisher(site_name="Test")
        pub.add_page(_make_doc())
        pub.set_previous_snapshot([])

        with patch(
            "agent_web_compiler.publisher.delta_feed.generate_delta_feed",
            return_value='{"changes": []}',
        ) as mock_gen:
            result = pub.generate_delta_feed()
            assert result == '{"changes": []}'
            mock_gen.assert_called_once()
            call_kwargs = mock_gen.call_args.kwargs
            assert call_kwargs["previous_docs"] == []
            assert len(call_kwargs["current_docs"]) == 1


# ---------------------------------------------------------------------------
# generate_all
# ---------------------------------------------------------------------------


class TestGenerateAll:
    def test_generate_all_creates_files(self) -> None:
        """Test generate_all writes all files to the output directory."""
        pub = SitePublisher(site_name="Test", site_url="https://example.com")
        pub.add_page(_make_doc())

        mock_returns = {
            "generate_llms_txt": "# Test",
            "generate_agent_json": '{"name": "Test"}',
            "generate_content_json": '{"pages": []}',
            "generate_actions_json": '{"actions": []}',
            "generate_agent_sitemap": '<?xml version="1.0"?><urlset/>',
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            # Patch all generator methods on the instance
            for method_name, return_val in mock_returns.items():
                setattr(pub, method_name, MagicMock(return_value=return_val))

            files = pub.generate_all(tmpdir)

            assert len(files) == 5
            assert "llms.txt" in files
            assert "agent.json" in files
            assert "content.json" in files
            assert "actions.json" in files
            assert "agent-sitemap.xml" in files

            # Verify files were actually written
            for fname, content in files.items():
                fpath = Path(tmpdir) / fname
                assert fpath.exists()
                assert fpath.read_text(encoding="utf-8") == content

    def test_generate_all_includes_delta_with_snapshot(self) -> None:
        pub = SitePublisher(site_name="Test", site_url="https://example.com")
        pub.add_page(_make_doc())
        pub.set_previous_snapshot([_make_doc()])

        with tempfile.TemporaryDirectory() as tmpdir:
            # Patch all methods
            for method in [
                "generate_llms_txt",
                "generate_agent_json",
                "generate_content_json",
                "generate_actions_json",
                "generate_agent_sitemap",
                "generate_delta_feed",
            ]:
                setattr(pub, method, MagicMock(return_value="content"))

            files = pub.generate_all(tmpdir)
            assert "agent-feed.json" in files

    def test_generate_all_no_delta_without_snapshot(self) -> None:
        pub = SitePublisher(site_name="Test", site_url="https://example.com")
        pub.add_page(_make_doc())

        with tempfile.TemporaryDirectory() as tmpdir:
            for method in [
                "generate_llms_txt",
                "generate_agent_json",
                "generate_content_json",
                "generate_actions_json",
                "generate_agent_sitemap",
            ]:
                setattr(pub, method, MagicMock(return_value="content"))

            files = pub.generate_all(tmpdir)
            assert "agent-feed.json" not in files

    def test_generate_all_creates_output_dir(self) -> None:
        pub = SitePublisher(site_name="Test")
        pub.add_page(_make_doc())

        with tempfile.TemporaryDirectory() as tmpdir:
            nested = Path(tmpdir) / "deep" / "nested" / "output"

            for method in [
                "generate_llms_txt",
                "generate_agent_json",
                "generate_content_json",
                "generate_actions_json",
                "generate_agent_sitemap",
            ]:
                setattr(pub, method, MagicMock(return_value="content"))

            files = pub.generate_all(str(nested))
            assert nested.exists()
            assert len(files) == 5


# ---------------------------------------------------------------------------
# set_previous_snapshot
# ---------------------------------------------------------------------------


class TestPreviousSnapshot:
    def test_set_previous_snapshot_stores_docs(self) -> None:
        pub = SitePublisher()
        prev = [_make_doc()]
        pub.set_previous_snapshot(prev)
        # Verify the snapshot is stored (defensive copy)
        assert len(pub._previous_docs) == 1
        # Mutating original should not affect stored
        prev.clear()
        assert len(pub._previous_docs) == 1


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_defaults(self) -> None:
        pub = SitePublisher()
        assert pub.site_name == ""
        assert pub.site_url == ""
        assert pub.site_description == ""
        assert pub.page_count == 0

    def test_with_all_args(self) -> None:
        pub = SitePublisher(
            site_name="My Docs",
            site_url="https://docs.example.com",
            site_description="Comprehensive documentation",
        )
        assert pub.site_name == "My Docs"
        assert pub.site_url == "https://docs.example.com"
        assert pub.site_description == "Comprehensive documentation"
