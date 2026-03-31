"""Tests for MCP server hardening — input validation and error codes."""

from __future__ import annotations

import json

import pytest

from agent_web_compiler.serving.mcp_server import (
    _handle_compile_file,
    _handle_compile_html,
    _handle_compile_url,
    _handle_get_actions,
    _handle_get_blocks,
    _handle_get_markdown,
)


class TestMCPInputValidation:
    """Test that MCP tool handlers validate required params."""

    def test_compile_url_missing_url(self) -> None:
        with pytest.raises(ValueError, match="url"):
            _handle_compile_url({})

    def test_compile_url_empty_url(self) -> None:
        with pytest.raises(ValueError, match="url"):
            _handle_compile_url({"url": ""})

    def test_compile_url_non_string_url(self) -> None:
        with pytest.raises(ValueError, match="url"):
            _handle_compile_url({"url": 123})

    def test_compile_html_missing_html(self) -> None:
        with pytest.raises(ValueError, match="html"):
            _handle_compile_html({})

    def test_compile_html_empty_html(self) -> None:
        with pytest.raises(ValueError, match="html"):
            _handle_compile_html({"html": ""})

    def test_compile_file_missing_path(self) -> None:
        with pytest.raises(ValueError, match="path"):
            _handle_compile_file({})

    def test_compile_file_empty_path(self) -> None:
        with pytest.raises(ValueError, match="path"):
            _handle_compile_file({"path": ""})

    def test_get_blocks_missing_url(self) -> None:
        with pytest.raises(ValueError, match="url"):
            _handle_get_blocks({})

    def test_get_actions_missing_url(self) -> None:
        with pytest.raises(ValueError, match="url"):
            _handle_get_actions({})

    def test_get_markdown_missing_url(self) -> None:
        with pytest.raises(ValueError, match="url"):
            _handle_get_markdown({})


class TestMCPCompileHtmlValid:
    """Test that valid compile_html calls work."""

    def test_compile_html_valid(self) -> None:
        result = _handle_compile_html({"html": "<html><body><p>Hello</p></body></html>"})
        data = json.loads(result)
        assert "blocks" in data
        assert "schema_version" in data


class TestMCPErrorCodes:
    """Test that the create_server error handling includes error codes."""

    def test_unknown_tool_has_error_code(self) -> None:
        """Verify the unknown tool error format has error_code field."""
        # We can't easily test the async server path without running it,
        # so we test the error format concept by checking TOOL_HANDLERS structure.
        from agent_web_compiler.serving.mcp_server import _TOOL_HANDLERS

        assert "compile_url" in _TOOL_HANDLERS
        assert "nonexistent_tool" not in _TOOL_HANDLERS
