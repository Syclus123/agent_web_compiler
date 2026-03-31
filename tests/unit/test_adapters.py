"""Tests for framework adapters — OpenAI, Anthropic, browser-use, LangChain."""

from __future__ import annotations

import pytest

from agent_web_compiler.adapters.anthropic_adapter import AnthropicAdapter
from agent_web_compiler.adapters.browser_use_adapter import BrowserUseAdapter
from agent_web_compiler.adapters.langchain_adapter import AWCDocumentLoader, AWCTool
from agent_web_compiler.adapters.openai_adapter import OpenAIAdapter
from agent_web_compiler.core.action import Action, ActionType, StateEffect
from agent_web_compiler.core.block import Block, BlockType
from agent_web_compiler.core.document import AgentDocument, Quality, SourceType

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_doc(
    *,
    title: str = "Test Page",
    url: str = "https://example.com",
    blocks: list[Block] | None = None,
    actions: list[Action] | None = None,
    confidence: float = 0.9,
) -> AgentDocument:
    """Build a minimal AgentDocument for testing adapters."""
    if blocks is None:
        blocks = [
            Block(id="b_001", type=BlockType.HEADING, text="Welcome", order=0, level=1, importance=0.9),
            Block(id="b_002", type=BlockType.PARAGRAPH, text="Hello world.", order=1, importance=0.7),
            Block(
                id="b_003", type=BlockType.CODE, text="print('hi')", order=2, importance=0.5,
                section_path=["Welcome"],
            ),
        ]
    if actions is None:
        actions = [
            Action(
                id="a_search",
                type=ActionType.INPUT,
                label="Search",
                selector="#search",
                role="search_input",
                confidence=0.8,
                priority=0.7,
            ),
            Action(
                id="a_submit",
                type=ActionType.SUBMIT,
                label="Submit Search",
                selector="#submit",
                role="submit_search",
                required_fields=["a_search"],
                confidence=0.9,
                priority=0.9,
            ),
            Action(
                id="a_nav_about",
                type=ActionType.NAVIGATE,
                label="About",
                selector="a.about",
                state_effect=StateEffect(may_navigate=True, target_url="https://example.com/about"),
                confidence=0.95,
                priority=0.4,
            ),
        ]
    return AgentDocument(
        doc_id="sha256:test1234",
        source_type=SourceType.HTML,
        source_url=url,
        title=title,
        lang="en",
        blocks=blocks,
        actions=actions,
        quality=Quality(parse_confidence=confidence, block_count=len(blocks), action_count=len(actions)),
    )


@pytest.fixture()
def sample_doc() -> AgentDocument:
    return _make_doc()


@pytest.fixture()
def empty_doc() -> AgentDocument:
    return _make_doc(title="", url="", blocks=[], actions=[], confidence=1.0)


# ===========================================================================
# OpenAI Adapter
# ===========================================================================


class TestOpenAIAdapter:
    def test_to_cua_observation_shape(self, sample_doc: AgentDocument):
        adapter = OpenAIAdapter()
        obs = adapter.to_cua_observation(sample_doc)

        assert obs["type"] == "observation"
        assert obs["url"] == "https://example.com"
        assert obs["title"] == "Test Page"
        assert isinstance(obs["accessibility_tree"], str)
        assert obs["action_count"] == 3

    def test_to_cua_observation_contains_blocks(self, sample_doc: AgentDocument):
        adapter = OpenAIAdapter()
        obs = adapter.to_cua_observation(sample_doc)
        tree = obs["accessibility_tree"]

        assert "Welcome" in tree
        assert "Hello world." in tree
        assert "[HEADING]" in tree
        assert "[PARAGRAPH]" in tree

    def test_to_cua_observation_contains_actions(self, sample_doc: AgentDocument):
        adapter = OpenAIAdapter()
        tree = adapter.to_cua_observation(sample_doc)["accessibility_tree"]

        assert "[ACTIONS]" in tree
        assert "a_search" in tree
        assert "a_submit" in tree

    def test_to_chat_messages_single_message(self, sample_doc: AgentDocument):
        adapter = OpenAIAdapter()
        msgs = adapter.to_chat_messages(sample_doc)

        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        assert isinstance(msgs[0]["content"], str)

    def test_to_chat_messages_custom_role(self, sample_doc: AgentDocument):
        adapter = OpenAIAdapter()
        msgs = adapter.to_chat_messages(sample_doc, role="system")
        assert msgs[0]["role"] == "system"

    def test_to_chat_messages_content(self, sample_doc: AgentDocument):
        adapter = OpenAIAdapter()
        content = adapter.to_chat_messages(sample_doc)[0]["content"]

        assert "# Test Page" in content
        assert "Hello world." in content
        assert "Available Actions" in content
        assert "a_search" in content

    def test_to_tool_definitions_count(self, sample_doc: AgentDocument):
        adapter = OpenAIAdapter()
        tools = adapter.to_tool_definitions(sample_doc)

        assert len(tools) == 3

    def test_to_tool_definitions_shape(self, sample_doc: AgentDocument):
        adapter = OpenAIAdapter()
        tools = adapter.to_tool_definitions(sample_doc)

        for tool in tools:
            assert tool["type"] == "function"
            assert "function" in tool
            assert "name" in tool["function"]
            assert "description" in tool["function"]
            assert "parameters" in tool["function"]

    def test_input_action_has_value_param(self, sample_doc: AgentDocument):
        adapter = OpenAIAdapter()
        tools = adapter.to_tool_definitions(sample_doc)

        search_tool = next(t for t in tools if "a_search" in t["function"]["name"])
        props = search_tool["function"]["parameters"]["properties"]
        assert "value" in props
        required = search_tool["function"]["parameters"]["required"]
        assert "value" in required

    def test_empty_doc(self, empty_doc: AgentDocument):
        adapter = OpenAIAdapter()

        obs = adapter.to_cua_observation(empty_doc)
        assert obs["action_count"] == 0

        msgs = adapter.to_chat_messages(empty_doc)
        assert len(msgs) == 1

        tools = adapter.to_tool_definitions(empty_doc)
        assert tools == []


# ===========================================================================
# Anthropic Adapter
# ===========================================================================


class TestAnthropicAdapter:
    def test_to_computer_use_result_shape(self, sample_doc: AgentDocument):
        adapter = AnthropicAdapter()
        result = adapter.to_computer_use_result(sample_doc)

        assert result["type"] == "tool_result"
        assert isinstance(result["content"], str)
        assert "metadata" in result
        assert result["metadata"]["title"] == "Test Page"

    def test_to_xml_content_structure(self, sample_doc: AgentDocument):
        adapter = AnthropicAdapter()
        xml = adapter.to_xml_content(sample_doc)

        assert xml.startswith("<page>")
        assert xml.endswith("</page>")
        assert "<metadata>" in xml
        assert "<content>" in xml
        assert "<actions>" in xml

    def test_to_xml_content_blocks(self, sample_doc: AgentDocument):
        adapter = AnthropicAdapter()
        xml = adapter.to_xml_content(sample_doc)

        assert '<block' in xml
        assert 'id="b_001"' in xml
        assert 'type="heading"' in xml
        assert "Welcome" in xml
        assert "Hello world." in xml

    def test_to_xml_content_actions(self, sample_doc: AgentDocument):
        adapter = AnthropicAdapter()
        xml = adapter.to_xml_content(sample_doc)

        assert '<action' in xml
        assert 'id="a_search"' in xml
        assert 'type="input"' in xml

    def test_to_xml_content_metadata(self, sample_doc: AgentDocument):
        adapter = AnthropicAdapter()
        xml = adapter.to_xml_content(sample_doc)

        assert "<title>Test Page</title>" in xml
        assert "<url>https://example.com</url>" in xml
        assert "<lang>en</lang>" in xml

    def test_xml_escapes_special_chars(self):
        doc = _make_doc(
            title="A & B <test>",
            blocks=[Block(id="b_1", type=BlockType.PARAGRAPH, text='x < y & "z"', order=0)],
            actions=[],
        )
        adapter = AnthropicAdapter()
        xml = adapter.to_xml_content(doc)

        assert "A &amp; B &lt;test&gt;" in xml
        assert "x &lt; y &amp;" in xml

    def test_to_tool_definitions_count(self, sample_doc: AgentDocument):
        adapter = AnthropicAdapter()
        tools = adapter.to_tool_definitions(sample_doc)
        assert len(tools) == 3

    def test_to_tool_definitions_shape(self, sample_doc: AgentDocument):
        adapter = AnthropicAdapter()
        tools = adapter.to_tool_definitions(sample_doc)

        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            assert tool["input_schema"]["type"] == "object"

    def test_input_action_has_value_param(self, sample_doc: AgentDocument):
        adapter = AnthropicAdapter()
        tools = adapter.to_tool_definitions(sample_doc)

        search_tool = next(t for t in tools if "a_search" in t["name"])
        props = search_tool["input_schema"]["properties"]
        assert "value" in props

    def test_empty_doc_no_actions_section(self, empty_doc: AgentDocument):
        adapter = AnthropicAdapter()
        xml = adapter.to_xml_content(empty_doc)
        assert "<actions>" not in xml


# ===========================================================================
# BrowserUse Adapter
# ===========================================================================


class TestBrowserUseAdapter:
    def test_get_page_context_shape(self, sample_doc: AgentDocument):
        adapter = BrowserUseAdapter()
        ctx = adapter.get_page_context(sample_doc)

        assert ctx["title"] == "Test Page"
        assert ctx["url"] == "https://example.com"
        assert ctx["block_count"] == 3
        assert ctx["action_count"] == 3
        assert isinstance(ctx["actions"], list)
        assert isinstance(ctx["form_fields"], list)
        assert isinstance(ctx["confidence"], float)

    def test_get_page_context_form_fields(self, sample_doc: AgentDocument):
        adapter = BrowserUseAdapter()
        ctx = adapter.get_page_context(sample_doc)
        fields = ctx["form_fields"]

        # Only INPUT/SELECT/TOGGLE become form_fields
        field_ids = {f["id"] for f in fields}
        assert "a_search" in field_ids
        assert "a_submit" not in field_ids  # SUBMIT is not a form field
        assert "a_nav_about" not in field_ids  # NAVIGATE is not a form field

    def test_get_action_plan_returns_relevant(self, sample_doc: AgentDocument):
        adapter = BrowserUseAdapter()
        plan = adapter.get_action_plan(sample_doc, "search for python")

        assert isinstance(plan, list)
        assert len(plan) > 0
        # Search-related actions should rank highest
        action_ids = [a["action_id"] for a in plan]
        assert "a_search" in action_ids

    def test_get_action_plan_empty_task(self, sample_doc: AgentDocument):
        adapter = BrowserUseAdapter()
        plan = adapter.get_action_plan(sample_doc, "xyznonexistent")
        # May still return actions via priority boost
        assert isinstance(plan, list)

    def test_get_form_fill_guide_shape(self, sample_doc: AgentDocument):
        adapter = BrowserUseAdapter()
        guide = adapter.get_form_fill_guide(sample_doc)

        assert "fields" in guide
        assert "submit_actions" in guide
        assert isinstance(guide["fields"], list)
        assert isinstance(guide["submit_actions"], list)

    def test_get_form_fill_guide_required_field(self, sample_doc: AgentDocument):
        adapter = BrowserUseAdapter()
        guide = adapter.get_form_fill_guide(sample_doc)

        search_field = next((f for f in guide["fields"] if f["action_id"] == "a_search"), None)
        assert search_field is not None
        assert search_field["required"] is True

    def test_get_form_fill_guide_filter_by_selector(self, sample_doc: AgentDocument):
        adapter = BrowserUseAdapter()
        guide = adapter.get_form_fill_guide(sample_doc, form_selector="#search")

        # Only fields whose selector starts with "#search"
        for f in guide["fields"]:
            assert f["selector"].startswith("#search")

    def test_empty_doc(self, empty_doc: AgentDocument):
        adapter = BrowserUseAdapter()

        ctx = adapter.get_page_context(empty_doc)
        assert ctx["block_count"] == 0
        assert ctx["actions"] == []

        plan = adapter.get_action_plan(empty_doc, "anything")
        assert plan == []

        guide = adapter.get_form_fill_guide(empty_doc)
        assert guide["fields"] == []
        assert guide["submit_actions"] == []


# ===========================================================================
# LangChain Adapter
# ===========================================================================


class TestAWCTool:
    def test_has_required_attributes(self):
        tool = AWCTool()
        assert hasattr(tool, "name")
        assert hasattr(tool, "description")
        assert tool.name == "web_compiler"
        assert isinstance(tool.description, str)
        assert len(tool.description) > 10

    def test_has_run_methods(self):
        tool = AWCTool()
        assert callable(getattr(tool, "_run", None))
        assert callable(getattr(tool, "_arun", None))

    def test_custom_config(self):
        from agent_web_compiler.core.config import CompileConfig, CompileMode

        cfg = CompileConfig(mode=CompileMode.FAST)
        tool = AWCTool(config=cfg, output_format="json")

        assert tool.config.mode == CompileMode.FAST
        assert tool.output_format == "json"


class TestAWCDocumentLoader:
    def test_has_load_methods(self):
        loader = AWCDocumentLoader()
        assert callable(getattr(loader, "load", None))
        assert callable(getattr(loader, "lazy_load", None))

    def test_block_to_document_shape(self):
        """Test the static helper directly — no network needed."""
        doc = _make_doc()
        loader = AWCDocumentLoader()
        result = loader._block_to_document(doc.blocks[0], doc)

        assert "page_content" in result
        assert "metadata" in result
        assert result["page_content"] == "Welcome"
        assert result["metadata"]["block_id"] == "b_001"
        assert result["metadata"]["block_type"] == "heading"
        assert result["metadata"]["source_url"] == "https://example.com"
        assert result["metadata"]["importance"] == 0.9

    def test_block_to_document_all_blocks(self):
        doc = _make_doc()
        loader = AWCDocumentLoader()
        docs = [loader._block_to_document(b, doc) for b in doc.blocks]

        assert len(docs) == 3
        for d in docs:
            assert "page_content" in d
            assert "metadata" in d
            assert "block_id" in d["metadata"]
