"""Tests for PipelineBuilder — pluggable pipeline stages and hooks."""

from __future__ import annotations

from agent_web_compiler.core.block import Block, BlockType
from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.pipeline.builder import PipelineBuilder

SAMPLE_HTML = """
<html><body>
<h1>Test Page</h1>
<p>This is a test paragraph with enough content to be meaningful.</p>
<ul><li>Item A</li><li>Item B</li></ul>
<a href="/link">Click here</a>
<button>Submit</button>
</body></html>
"""


class TestDefaultPipeline:
    """PipelineBuilder with no customization should match HTMLCompiler output."""

    def test_default_produces_blocks(self):
        pipeline = PipelineBuilder().build()
        doc = pipeline.compile(SAMPLE_HTML)
        assert doc.block_count > 0

    def test_default_produces_actions(self):
        pipeline = PipelineBuilder().build()
        doc = pipeline.compile(SAMPLE_HTML)
        assert doc.action_count > 0

    def test_default_has_title(self):
        pipeline = PipelineBuilder().build()
        doc = pipeline.compile(SAMPLE_HTML)
        assert doc.title == "Test Page"

    def test_default_has_markdown(self):
        pipeline = PipelineBuilder().build()
        doc = pipeline.compile(SAMPLE_HTML)
        assert "Test Page" in doc.canonical_markdown


class TestStageReplacement:
    """Test replacing individual pipeline stages."""

    def test_custom_normalizer(self):
        class PassthroughNormalizer:
            def normalize(self, html, config):
                return html  # no cleaning

        pipeline = PipelineBuilder().with_normalizer(PassthroughNormalizer()).build()
        doc = pipeline.compile(SAMPLE_HTML)
        assert doc.block_count > 0

    def test_custom_segmenter(self):
        class SingleBlockSegmenter:
            def segment(self, html, config):
                return [Block(id="custom_001", type=BlockType.PARAGRAPH, text="Custom block", order=0)]

        pipeline = PipelineBuilder().with_segmenter(SingleBlockSegmenter()).build()
        doc = pipeline.compile(SAMPLE_HTML)
        assert doc.block_count == 1
        assert doc.blocks[0].text == "Custom block"

    def test_custom_action_extractor(self):
        class NoActionExtractor:
            def extract(self, html, config):
                return []

        pipeline = PipelineBuilder().with_action_extractor(NoActionExtractor()).build()
        doc = pipeline.compile(SAMPLE_HTML)
        assert doc.action_count == 0


class TestSkipStages:
    """Test skipping pipeline stages."""

    def test_skip_actions(self):
        pipeline = PipelineBuilder().skip_actions().build()
        doc = pipeline.compile(SAMPLE_HTML)
        assert doc.action_count == 0
        assert doc.block_count > 0

    def test_skip_salience(self):
        pipeline = PipelineBuilder().skip_salience().build()
        doc = pipeline.compile(SAMPLE_HTML)
        assert doc.block_count > 0

    def test_skip_entities(self):
        pipeline = PipelineBuilder().skip_entities().build()
        doc = pipeline.compile(SAMPLE_HTML)
        # No entities in metadata
        for block in doc.blocks:
            assert "entities" not in block.metadata

    def test_skip_provenance(self):
        pipeline = PipelineBuilder().skip_provenance().build()
        doc = pipeline.compile(SAMPLE_HTML, config=CompileConfig(include_provenance=True))
        # Provenance should be from segmenter (if any) but not from aligner
        assert doc.block_count > 0

    def test_skip_validation(self):
        pipeline = PipelineBuilder().skip_validation().build()
        doc = pipeline.compile(SAMPLE_HTML)
        assert doc.block_count > 0

    def test_skip_multiple(self):
        pipeline = (
            PipelineBuilder()
            .skip_actions()
            .skip_salience()
            .skip_entities()
            .skip_validation()
            .build()
        )
        doc = pipeline.compile(SAMPLE_HTML)
        assert doc.block_count > 0
        assert doc.action_count == 0


class TestHooks:
    """Test pipeline hooks."""

    def test_before_normalize_hook(self):
        calls: list[str] = []

        def hook(html, config):
            calls.append("before_normalize")
            return None  # don't modify

        pipeline = PipelineBuilder().on_before_normalize(hook).build()
        pipeline.compile(SAMPLE_HTML)
        assert "before_normalize" in calls

    def test_before_normalize_can_modify_html(self):
        def inject_heading(html, config):
            return html.replace("<h1>Test Page</h1>", "<h1>Modified Title</h1>")

        pipeline = PipelineBuilder().on_before_normalize(inject_heading).build()
        doc = pipeline.compile(SAMPLE_HTML)
        assert doc.title == "Modified Title"

    def test_after_normalize_hook(self):
        calls: list[str] = []

        def hook(html, config):
            calls.append(f"after_normalize:{len(html)}")
            return None

        pipeline = PipelineBuilder().on_after_normalize(hook).build()
        pipeline.compile(SAMPLE_HTML)
        assert len(calls) == 1
        assert calls[0].startswith("after_normalize:")

    def test_after_segment_hook(self):
        def filter_short_blocks(blocks, config):
            return [b for b in blocks if len(b.text) > 20]

        pipeline = PipelineBuilder().on_after_segment(filter_short_blocks).build()
        doc = pipeline.compile(SAMPLE_HTML)
        for block in doc.blocks:
            assert len(block.text) > 20

    def test_on_block_created_hook(self):
        tags: list[str] = []

        def tag_block(block):
            tags.append(block.type.value)
            return None  # don't modify

        pipeline = PipelineBuilder().on_block_created(tag_block).build()
        doc = pipeline.compile(SAMPLE_HTML)
        assert len(tags) == doc.block_count

    def test_after_extract_actions_hook(self):
        def boost_priority(actions, config):
            for a in actions:
                a.priority = min(a.priority + 0.1, 1.0)
            return actions

        pipeline = PipelineBuilder().on_after_extract_actions(boost_priority).build()
        doc = pipeline.compile(SAMPLE_HTML)
        # Actions should have boosted priority
        assert doc.action_count > 0

    def test_after_compile_hook(self):
        def add_metadata(doc):
            doc.debug["custom"] = "injected"
            return doc

        pipeline = PipelineBuilder().on_after_compile(add_metadata).build()
        doc = pipeline.compile(SAMPLE_HTML, config=CompileConfig(debug=True))
        assert doc.debug.get("custom") == "injected"

    def test_multiple_hooks_chain(self):
        order: list[int] = []

        def hook1(html, config):
            order.append(1)
            return None

        def hook2(html, config):
            order.append(2)
            return None

        pipeline = (
            PipelineBuilder()
            .on_before_normalize(hook1)
            .on_before_normalize(hook2)
            .build()
        )
        pipeline.compile(SAMPLE_HTML)
        assert order == [1, 2]


class TestBuilderFluent:
    """Test the fluent builder API."""

    def test_chaining(self):
        pipeline = (
            PipelineBuilder()
            .skip_actions()
            .skip_salience()
            .on_before_normalize(lambda h, c: None)
            .build()
        )
        assert pipeline is not None

    def test_build_returns_custom_pipeline(self):
        from agent_web_compiler.pipeline.builder import CustomPipeline
        pipeline = PipelineBuilder().build()
        assert isinstance(pipeline, CustomPipeline)

    def test_empty_html(self):
        pipeline = PipelineBuilder().build()
        doc = pipeline.compile("")
        assert doc.block_count == 0
