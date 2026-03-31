"""Tests for the API compiler."""

from __future__ import annotations

import json

import pytest

from agent_web_compiler.core.block import BlockType
from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.core.document import SourceType
from agent_web_compiler.core.errors import ParseError
from agent_web_compiler.pipeline.api_compiler import APICompiler


@pytest.fixture
def compiler() -> APICompiler:
    return APICompiler()


class TestAPICompilerBasic:
    def test_compile_dict(self, compiler: APICompiler) -> None:
        data = {"title": "Test", "body": "Hello world"}
        doc = compiler.compile(data)
        assert doc.source_type == SourceType.API
        assert len(doc.blocks) > 0

    def test_compile_json_string(self, compiler: APICompiler) -> None:
        json_str = json.dumps({"name": "Test", "value": 42})
        doc = compiler.compile(json_str)
        assert doc.source_type == SourceType.API

    def test_invalid_json_raises(self, compiler: APICompiler) -> None:
        with pytest.raises(ParseError):
            compiler.compile("not valid json {{{")

    def test_source_url_preserved(self, compiler: APICompiler) -> None:
        doc = compiler.compile({"key": "value"}, source_url="https://api.example.com/data")
        assert doc.source_url == "https://api.example.com/data"

    def test_doc_id_deterministic(self, compiler: APICompiler) -> None:
        data = {"key": "value"}
        doc1 = compiler.compile(data)
        doc2 = compiler.compile(data)
        assert doc1.doc_id == doc2.doc_id

    def test_canonical_markdown_populated(self, compiler: APICompiler) -> None:
        doc = compiler.compile({"title": "Hello", "body": "World"})
        assert doc.canonical_markdown != ""


class TestAPICompilerBlockMapping:
    """Test JSON structure → block type mapping."""

    def test_top_level_keys_become_headings(self, compiler: APICompiler) -> None:
        doc = compiler.compile({"section_a": "content", "section_b": "more"})
        headings = [b for b in doc.blocks if b.type == BlockType.HEADING]
        assert len(headings) >= 2

    def test_string_values_become_paragraphs(self, compiler: APICompiler) -> None:
        doc = compiler.compile({"info": "This is a paragraph"})
        paragraphs = [b for b in doc.blocks if b.type == BlockType.PARAGRAPH]
        assert len(paragraphs) >= 1
        assert any("This is a paragraph" in b.text for b in paragraphs)

    def test_number_values_become_metadata(self, compiler: APICompiler) -> None:
        doc = compiler.compile({"count": 42})
        meta_blocks = [b for b in doc.blocks if b.type == BlockType.METADATA]
        assert len(meta_blocks) >= 1
        assert any("42" in b.text for b in meta_blocks)

    def test_boolean_values_become_metadata(self, compiler: APICompiler) -> None:
        doc = compiler.compile({"active": True})
        meta_blocks = [b for b in doc.blocks if b.type == BlockType.METADATA]
        assert len(meta_blocks) >= 1
        assert any("true" in b.text for b in meta_blocks)

    def test_array_of_objects_becomes_table(self, compiler: APICompiler) -> None:
        data = {
            "users": [
                {"name": "Alice", "age": "30"},
                {"name": "Bob", "age": "25"},
            ]
        }
        doc = compiler.compile(data)
        tables = [b for b in doc.blocks if b.type == BlockType.TABLE]
        assert len(tables) >= 1
        table = tables[0]
        assert table.metadata["headers"] == ["name", "age"]
        assert table.metadata["row_count"] == 2

    def test_array_of_strings_becomes_list(self, compiler: APICompiler) -> None:
        data = {"tags": ["python", "rust", "go"]}
        doc = compiler.compile(data)
        lists = [b for b in doc.blocks if b.type == BlockType.LIST]
        assert len(lists) >= 1
        assert "python" in lists[0].text

    def test_nested_objects_become_subsections(self, compiler: APICompiler) -> None:
        data = {
            "user": {
                "profile": {
                    "name": "Alice",
                }
            }
        }
        doc = compiler.compile(data)
        # Should have nested section paths
        blocks_with_path = [b for b in doc.blocks if len(b.section_path) >= 2]
        assert len(blocks_with_path) > 0

    def test_empty_array_no_blocks(self, compiler: APICompiler) -> None:
        doc = compiler.compile({"items": []})
        # Should only have the heading for "items", no list/table block
        non_heading = [b for b in doc.blocks if b.type != BlockType.HEADING]
        assert len(non_heading) == 0

    def test_null_values_skipped(self, compiler: APICompiler) -> None:
        doc = compiler.compile({"present": "yes", "absent": None})
        texts = [b.text for b in doc.blocks]
        assert "None" not in texts


class TestAPICompilerPagination:
    """Test pagination action extraction."""

    def test_next_url_action(self, compiler: APICompiler) -> None:
        data = {
            "results": [{"id": "1"}],
            "next": "https://api.example.com/data?page=2",
        }
        doc = compiler.compile(data)
        nav_actions = [a for a in doc.actions if a.type.value == "navigate"]
        assert len(nav_actions) >= 1
        action = nav_actions[0]
        assert action.role == "next_page"
        assert action.state_effect is not None
        assert action.state_effect.target_url == "https://api.example.com/data?page=2"

    def test_previous_url_action(self, compiler: APICompiler) -> None:
        data = {
            "results": [{"id": "1"}],
            "previous": "https://api.example.com/data?page=1",
        }
        doc = compiler.compile(data)
        nav_actions = [a for a in doc.actions if a.role == "previous_page"]
        assert len(nav_actions) >= 1

    def test_pagination_keys_not_in_blocks(self, compiler: APICompiler) -> None:
        data = {
            "items": [{"id": "1"}],
            "next": "https://api.example.com?page=2",
        }
        doc = compiler.compile(data)
        headings = [b.text for b in doc.blocks if b.type == BlockType.HEADING]
        assert "next" not in headings

    def test_no_actions_when_disabled(self, compiler: APICompiler) -> None:
        data = {"next": "https://api.example.com?page=2"}
        config = CompileConfig(include_actions=False)
        doc = compiler.compile(data, config=config)
        assert len(doc.actions) == 0


class TestAPICompilerTitle:
    def test_title_from_title_key(self, compiler: APICompiler) -> None:
        doc = compiler.compile({"title": "My API Response", "data": "stuff"})
        assert doc.title == "My API Response"

    def test_title_from_name_key(self, compiler: APICompiler) -> None:
        doc = compiler.compile({"name": "Widget", "price": 10})
        assert doc.title == "Widget"

    def test_no_title_empty_string(self, compiler: APICompiler) -> None:
        doc = compiler.compile({"data": [1, 2, 3]})
        assert doc.title == ""


class TestAPICompilerDebug:
    def test_debug_timings(self, compiler: APICompiler) -> None:
        config = CompileConfig(debug=True)
        doc = compiler.compile({"key": "value"}, config=config)
        assert "timings" in doc.debug
        assert "parse_ms" in doc.debug["timings"]
        assert "total_ms" in doc.debug["timings"]

    def test_no_debug_by_default(self, compiler: APICompiler) -> None:
        doc = compiler.compile({"key": "value"})
        assert doc.debug == {}


class TestCompileHtmlJsonDetection:
    """Test that compile_html detects JSON and routes to API compiler."""

    def test_json_string_routed_to_api_compiler(self) -> None:
        from agent_web_compiler.api.compile import compile_html

        json_str = json.dumps({"title": "API Response", "count": 42})
        doc = compile_html(json_str)
        assert doc.source_type == SourceType.API

    def test_html_not_routed_to_api_compiler(self) -> None:
        from agent_web_compiler.api.compile import compile_html

        doc = compile_html("<html><body><p>Hello</p></body></html>")
        assert doc.source_type == SourceType.HTML
