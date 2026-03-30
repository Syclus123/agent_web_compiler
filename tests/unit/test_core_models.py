"""Tests for core data models: Block, Action, Provenance, AgentDocument, errors, config."""

from __future__ import annotations

import pytest

from agent_web_compiler.core.action import Action, ActionType, StateEffect
from agent_web_compiler.core.block import Block, BlockType
from agent_web_compiler.core.config import CompileConfig, CompileMode, RenderMode
from agent_web_compiler.core.document import (
    AgentDocument,
    Quality,
    SiteProfile,
    SourceType,
)
from agent_web_compiler.core.errors import (
    AlignError,
    CompilerError,
    ExportError,
    ExtractError,
    FetchError,
    NormalizeError,
    ParseError,
    RenderError,
    SegmentError,
)
from agent_web_compiler.core.provenance import (
    DOMProvenance,
    PageProvenance,
    Provenance,
    ScreenshotProvenance,
)

# ---------------------------------------------------------------------------
# BlockType enum
# ---------------------------------------------------------------------------


class TestBlockType:
    def test_heading_value(self):
        assert BlockType.HEADING == "heading"

    def test_paragraph_value(self):
        assert BlockType.PARAGRAPH == "paragraph"

    def test_all_members_are_strings(self):
        for member in BlockType:
            assert isinstance(member.value, str)

    def test_known_members(self):
        expected = {
            "heading", "paragraph", "list", "table", "code", "quote",
            "figure_caption", "image", "product_spec", "review", "faq",
            "form_help", "metadata", "unknown",
        }
        actual = {m.value for m in BlockType}
        assert actual == expected


# ---------------------------------------------------------------------------
# ActionType enum
# ---------------------------------------------------------------------------


class TestActionType:
    def test_click_value(self):
        assert ActionType.CLICK == "click"

    def test_all_members_are_strings(self):
        for member in ActionType:
            assert isinstance(member.value, str)

    def test_known_members(self):
        expected = {
            "click", "input", "select", "toggle", "upload",
            "download", "navigate", "submit",
        }
        actual = {m.value for m in ActionType}
        assert actual == expected


# ---------------------------------------------------------------------------
# Block
# ---------------------------------------------------------------------------


class TestBlock:
    def test_creation_with_all_fields(self):
        prov = Provenance(source_url="https://example.com")
        block = Block(
            id="b_001",
            type=BlockType.HEADING,
            text="Introduction",
            html="<h1>Introduction</h1>",
            section_path=["Intro"],
            order=0,
            importance=0.9,
            level=1,
            metadata={"level": 1},
            provenance=prov,
            children=[],
        )
        assert block.id == "b_001"
        assert block.type == BlockType.HEADING
        assert block.text == "Introduction"
        assert block.html == "<h1>Introduction</h1>"
        assert block.section_path == ["Intro"]
        assert block.order == 0
        assert block.importance == 0.9
        assert block.level == 1
        assert block.metadata == {"level": 1}
        assert block.provenance is not None
        assert block.provenance.source_url == "https://example.com"
        assert block.children == []

    def test_defaults(self):
        block = Block(id="b_000", type=BlockType.PARAGRAPH, text="Hello")
        assert block.html is None
        assert block.section_path == []
        assert block.order == 0
        assert block.importance == 0.5
        assert block.level is None
        assert block.metadata == {}
        assert block.provenance is None
        assert block.children == []

    def test_importance_bounds(self):
        with pytest.raises(ValueError):
            Block(id="b_000", type=BlockType.PARAGRAPH, text="x", importance=1.5)
        with pytest.raises(ValueError):
            Block(id="b_000", type=BlockType.PARAGRAPH, text="x", importance=-0.1)


# ---------------------------------------------------------------------------
# Action
# ---------------------------------------------------------------------------


class TestAction:
    def test_creation_with_all_fields(self):
        effect = StateEffect(may_navigate=True, target_url="https://example.com")
        prov = Provenance(source_url="https://example.com")
        action = Action(
            id="a_001_click",
            type=ActionType.CLICK,
            label="Submit",
            selector="#submit-btn",
            role="submit_search",
            value_schema={"type": "string"},
            required_fields=["query"],
            confidence=0.9,
            priority=0.85,
            state_effect=effect,
            provenance=prov,
            group="form",
        )
        assert action.id == "a_001_click"
        assert action.type == ActionType.CLICK
        assert action.label == "Submit"
        assert action.selector == "#submit-btn"
        assert action.role == "submit_search"
        assert action.value_schema == {"type": "string"}
        assert action.required_fields == ["query"]
        assert action.confidence == 0.9
        assert action.priority == 0.85
        assert action.state_effect.may_navigate is True
        assert action.state_effect.target_url == "https://example.com"
        assert action.provenance is not None
        assert action.group == "form"

    def test_defaults(self):
        action = Action(id="a_000_click", type=ActionType.CLICK, label="Go")
        assert action.selector is None
        assert action.role is None
        assert action.value_schema is None
        assert action.required_fields == []
        assert action.confidence == 0.5
        assert action.priority == 0.5
        assert action.state_effect is None
        assert action.provenance is None
        assert action.group is None


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


class TestProvenance:
    def test_dom_provenance(self):
        dom = DOMProvenance(
            dom_path="html > body > p",
            element_tag="p",
            element_id="intro",
            element_classes=["content", "main"],
        )
        assert dom.dom_path == "html > body > p"
        assert dom.element_tag == "p"
        assert dom.element_id == "intro"
        assert dom.element_classes == ["content", "main"]

    def test_page_provenance(self):
        page = PageProvenance(page=1, bbox=[0.0, 0.0, 100.0, 200.0], char_range=[0, 50])
        assert page.page == 1
        assert page.bbox == [0.0, 0.0, 100.0, 200.0]
        assert page.char_range == [0, 50]

    def test_screenshot_provenance(self):
        ss = ScreenshotProvenance(
            screenshot_region_id="region_1",
            screenshot_bbox=[10.0, 20.0, 300.0, 400.0],
        )
        assert ss.screenshot_region_id == "region_1"
        assert ss.screenshot_bbox == [10.0, 20.0, 300.0, 400.0]

    def test_combined_provenance(self):
        prov = Provenance(
            dom=DOMProvenance(dom_path="body > div"),
            page=PageProvenance(page=2),
            screenshot=ScreenshotProvenance(screenshot_region_id="r1"),
            source_url="https://example.com",
            raw_html="<div>hello</div>",
        )
        assert prov.dom is not None
        assert prov.page is not None
        assert prov.screenshot is not None
        assert prov.source_url == "https://example.com"
        assert prov.raw_html == "<div>hello</div>"

    def test_defaults_are_none(self):
        prov = Provenance()
        assert prov.dom is None
        assert prov.page is None
        assert prov.screenshot is None
        assert prov.source_url is None
        assert prov.raw_html is None


# ---------------------------------------------------------------------------
# AgentDocument
# ---------------------------------------------------------------------------


class TestAgentDocument:
    def _make_doc(self, **kwargs):
        defaults = dict(
            doc_id="sha256:abcdef1234567890",
            source_type=SourceType.HTML,
            title="Test",
            blocks=[
                Block(id="b_000", type=BlockType.HEADING, text="Title", order=0, importance=0.9, level=1),
                Block(id="b_001", type=BlockType.PARAGRAPH, text="Content here", order=1, importance=0.7),
                Block(id="b_002", type=BlockType.PARAGRAPH, text="More content", order=2, importance=0.2),
            ],
        )
        defaults.update(kwargs)
        return AgentDocument(**defaults)

    def test_creation(self):
        doc = self._make_doc()
        assert doc.doc_id == "sha256:abcdef1234567890"
        assert doc.source_type == SourceType.HTML
        assert doc.title == "Test"
        assert len(doc.blocks) == 3

    def test_block_count_computed_field(self):
        doc = self._make_doc()
        assert doc.block_count == 3

    def test_action_count_computed_field(self):
        doc = self._make_doc(
            actions=[Action(id="a_000_click", type=ActionType.CLICK, label="Go")]
        )
        assert doc.action_count == 1

    def test_make_doc_id_deterministic(self):
        content = "<html><body>Hello</body></html>"
        id1 = AgentDocument.make_doc_id(content)
        id2 = AgentDocument.make_doc_id(content)
        assert id1 == id2
        assert id1.startswith("sha256:")

    def test_make_doc_id_bytes(self):
        content = b"<html><body>Hello</body></html>"
        doc_id = AgentDocument.make_doc_id(content)
        assert doc_id.startswith("sha256:")

    def test_make_doc_id_different_content(self):
        id1 = AgentDocument.make_doc_id("content A")
        id2 = AgentDocument.make_doc_id("content B")
        assert id1 != id2

    def test_get_blocks_by_type(self):
        doc = self._make_doc()
        paragraphs = doc.get_blocks_by_type(BlockType.PARAGRAPH)
        assert len(paragraphs) == 2
        headings = doc.get_blocks_by_type(BlockType.HEADING)
        assert len(headings) == 1

    def test_get_main_content(self):
        doc = self._make_doc()
        # min_importance=0.3 should include all 3 blocks (0.9, 0.7, 0.2 -> first two)
        # Actually block with importance 0.2 < 0.3, so 2 blocks
        main = doc.get_main_content(min_importance=0.3)
        assert len(main) == 2

    def test_get_main_content_all(self):
        doc = self._make_doc()
        main = doc.get_main_content(min_importance=0.0)
        assert len(main) == 3

    def test_summary_markdown(self):
        doc = self._make_doc()
        md = doc.summary_markdown(max_blocks=10)
        assert "Test" in md
        assert "Title" in md
        assert "Content here" in md

    def test_summary_markdown_limited(self):
        doc = self._make_doc()
        md = doc.summary_markdown(max_blocks=1)
        # Should pick highest importance block (the heading at 0.9)
        assert "Title" in md


# ---------------------------------------------------------------------------
# Quality
# ---------------------------------------------------------------------------


class TestQuality:
    def test_defaults(self):
        q = Quality()
        assert q.parse_confidence == 1.0
        assert q.ocr_used is False
        assert q.dynamic_rendered is False
        assert q.block_count == 0
        assert q.action_count == 0
        assert q.warnings == []

    def test_custom_values(self):
        q = Quality(
            parse_confidence=0.8,
            ocr_used=True,
            dynamic_rendered=True,
            block_count=10,
            action_count=5,
            warnings=["low confidence"],
        )
        assert q.parse_confidence == 0.8
        assert q.ocr_used is True
        assert q.block_count == 10
        assert q.warnings == ["low confidence"]


# ---------------------------------------------------------------------------
# SiteProfile
# ---------------------------------------------------------------------------


class TestSiteProfile:
    def test_creation(self):
        sp = SiteProfile(
            site="example.com",
            template_signature="abc123",
            header_selectors=["header"],
            footer_selectors=["footer"],
            sidebar_selectors=[".sidebar"],
            main_content_selectors=["main"],
            noise_patterns=["cookie-banner"],
        )
        assert sp.site == "example.com"
        assert sp.template_signature == "abc123"
        assert sp.noise_patterns == ["cookie-banner"]

    def test_defaults(self):
        sp = SiteProfile(site="example.com")
        assert sp.template_signature is None
        assert sp.header_selectors == []
        assert sp.noise_patterns == []


# ---------------------------------------------------------------------------
# CompileConfig
# ---------------------------------------------------------------------------


class TestCompileConfig:
    def test_defaults(self):
        config = CompileConfig()
        assert config.mode == CompileMode.BALANCED
        assert config.render == RenderMode.OFF
        assert config.include_actions is True
        assert config.include_provenance is True
        assert config.include_raw_html is False
        assert config.query is None
        assert config.min_importance == 0.0
        assert config.max_blocks is None
        assert config.pdf_backend == "auto"
        assert config.timeout_seconds == 30.0
        assert config.debug is False

    def test_custom_values(self):
        config = CompileConfig(
            mode=CompileMode.FAST,
            render=RenderMode.ALWAYS,
            include_actions=False,
            include_provenance=False,
            debug=True,
            timeout_seconds=10.0,
            max_blocks=50,
        )
        assert config.mode == CompileMode.FAST
        assert config.render == RenderMode.ALWAYS
        assert config.include_actions is False
        assert config.include_provenance is False
        assert config.debug is True
        assert config.timeout_seconds == 10.0
        assert config.max_blocks == 50


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TestErrors:
    def test_compiler_error_basic(self):
        err = CompilerError("something failed", stage="test")
        assert str(err) == "something failed"
        assert err.stage == "test"
        assert err.cause is None
        assert err.context == {}

    def test_compiler_error_with_cause(self):
        original = ValueError("original error")
        err = CompilerError("wrapped", cause=original, context={"key": "value"})
        assert err.cause is original
        assert err.__cause__ is original
        assert err.context == {"key": "value"}

    @pytest.mark.parametrize(
        "error_cls,expected_stage",
        [
            (FetchError, "fetch"),
            (RenderError, "render"),
            (ParseError, "parse"),
            (NormalizeError, "normalize"),
            (SegmentError, "segment"),
            (ExtractError, "extract"),
            (AlignError, "align"),
            (ExportError, "export"),
        ],
    )
    def test_error_types_preserve_stage(self, error_cls, expected_stage):
        err = error_cls("test error")
        assert err.stage == expected_stage
        assert isinstance(err, CompilerError)

    @pytest.mark.parametrize(
        "error_cls",
        [FetchError, RenderError, ParseError, NormalizeError, SegmentError, ExtractError, AlignError, ExportError],
    )
    def test_error_types_preserve_cause(self, error_cls):
        cause = RuntimeError("root cause")
        err = error_cls("wrapped", cause=cause)
        assert err.cause is cause
        assert err.__cause__ is cause
