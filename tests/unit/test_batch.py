"""Tests for batch compilation."""

from __future__ import annotations

import pytest

from agent_web_compiler.api.batch import BatchCompiler, BatchItem, BatchResult, _extract_domain
from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.core.document import AgentDocument


class TestExtractDomain:
    def test_http_url(self):
        assert _extract_domain("https://example.com/page") == "example.com"

    def test_http_url_with_port(self):
        assert _extract_domain("https://example.com:8080/page") == "example.com:8080"

    def test_file_path_returns_none(self):
        assert _extract_domain("/path/to/file.html") is None

    def test_relative_path_returns_none(self):
        assert _extract_domain("file.html") is None


class TestBatchItem:
    def test_defaults(self):
        item = BatchItem(source="https://example.com")
        assert item.source_type == "auto"

    def test_custom_source_type(self):
        item = BatchItem(source="file.pdf", source_type="pdf")
        assert item.source_type == "pdf"


class TestBatchResult:
    def test_defaults(self):
        result = BatchResult()
        assert result.items == []
        assert result.site_profile is None
        assert result.total_time_ms == 0.0
        assert result.errors == {}


class TestBatchCompilerWithHTMLFiles:
    """Test batch compilation using local HTML strings (no network)."""

    def _write_html_file(self, tmp_path, name: str, content: str) -> str:
        """Write an HTML file and return its path."""
        path = tmp_path / name
        path.write_text(content)
        return str(path)

    def test_single_file_batch(self, tmp_path):
        html = "<html><body><h1>Test Page</h1><p>Some content here for testing.</p></body></html>"
        path = self._write_html_file(tmp_path, "page.html", html)

        compiler = BatchCompiler()
        result = compiler.compile_batch([BatchItem(source=path)])

        assert len(result.items) == 1
        assert isinstance(result.items[0], AgentDocument)
        assert result.total_time_ms > 0
        assert len(result.errors) == 0

    def test_multiple_files_batch(self, tmp_path):
        pages = [
            "<html><body><h1>Page One</h1><p>First page content for batch test.</p></body></html>",
            "<html><body><h1>Page Two</h1><p>Second page content for batch test.</p></body></html>",
            "<html><body><h1>Page Three</h1><p>Third page content for batch test.</p></body></html>",
        ]
        paths = [
            self._write_html_file(tmp_path, f"page_{i}.html", html)
            for i, html in enumerate(pages)
        ]

        compiler = BatchCompiler()
        items = [BatchItem(source=p) for p in paths]
        result = compiler.compile_batch(items)

        assert len(result.items) == 3
        assert len(result.errors) == 0

    def test_error_handling_bad_file(self, tmp_path):
        good = self._write_html_file(
            tmp_path, "good.html",
            "<html><body><p>Good content for testing.</p></body></html>",
        )

        compiler = BatchCompiler()
        items = [
            BatchItem(source=good),
            BatchItem(source="/nonexistent/path/to/file.html"),
        ]
        result = compiler.compile_batch(items)

        assert len(result.items) == 1  # Only the good file succeeded
        assert len(result.errors) == 1
        assert "/nonexistent/path/to/file.html" in result.errors

    def test_batch_result_preserves_order(self, tmp_path):
        pages = [
            "<html><body><h1>Alpha</h1><p>Alpha page content for ordering test.</p></body></html>",
            "<html><body><h1>Beta</h1><p>Beta page content for ordering test.</p></body></html>",
        ]
        paths = [
            self._write_html_file(tmp_path, f"page_{i}.html", html)
            for i, html in enumerate(pages)
        ]

        compiler = BatchCompiler()
        items = [BatchItem(source=p) for p in paths]
        result = compiler.compile_batch(items)

        assert len(result.items) == 2
        assert "Alpha" in result.items[0].title
        assert "Beta" in result.items[1].title

    def test_custom_config_applied(self, tmp_path):
        html = "<html><body><h1>Test</h1><p>Content for config testing with enough text.</p></body></html>"
        path = self._write_html_file(tmp_path, "page.html", html)

        config = CompileConfig(include_actions=False, debug=True)
        compiler = BatchCompiler()
        result = compiler.compile_batch([BatchItem(source=path)], config=config)

        assert len(result.items) == 1
        # Debug metadata should be present
        doc = result.items[0]
        assert isinstance(doc, AgentDocument)

    def test_no_site_profile_for_file_paths(self, tmp_path):
        """File paths don't have domains, so no site profile should be learned."""
        pages = [
            "<html><body><h1>Page One</h1><p>Content one for file test.</p></body></html>",
            "<html><body><h1>Page Two</h1><p>Content two for file test.</p></body></html>",
        ]
        paths = [
            self._write_html_file(tmp_path, f"page_{i}.html", html)
            for i, html in enumerate(pages)
        ]

        compiler = BatchCompiler()
        items = [BatchItem(source=p) for p in paths]
        result = compiler.compile_batch(items)

        assert result.site_profile is None


class TestCompileBatchPublicAPI:
    """Test the public compile_batch function in api/compile.py."""

    def test_compile_batch_function(self, tmp_path):
        from agent_web_compiler.api.compile import compile_batch

        html = "<html><body><h1>API Test</h1><p>Testing the public batch API function.</p></body></html>"
        path = tmp_path / "test.html"
        path.write_text(html)

        result = compile_batch([{"source": str(path)}])

        assert len(result.items) == 1
        assert isinstance(result.items[0], AgentDocument)

    def test_compile_batch_with_source_type(self, tmp_path):
        from agent_web_compiler.api.compile import compile_batch

        html = "<html><body><h1>Typed Test</h1><p>Testing with explicit source type.</p></body></html>"
        path = tmp_path / "test.html"
        path.write_text(html)

        result = compile_batch([{"source": str(path), "source_type": "html"}])
        assert len(result.items) == 1


class TestBatchCompilerAsync:
    """Test async batch compilation."""

    @pytest.mark.asyncio
    async def test_async_single_file(self, tmp_path):
        html = "<html><body><h1>Async Test</h1><p>Testing async batch compilation.</p></body></html>"
        path = tmp_path / "async_page.html"
        path.write_text(html)

        compiler = BatchCompiler()
        result = await compiler.compile_batch_async([BatchItem(source=str(path))])

        assert len(result.items) == 1
        assert isinstance(result.items[0], AgentDocument)
        assert result.total_time_ms > 0

    @pytest.mark.asyncio
    async def test_async_multiple_files(self, tmp_path):
        pages = [
            "<html><body><h1>Async One</h1><p>First async page content.</p></body></html>",
            "<html><body><h1>Async Two</h1><p>Second async page content.</p></body></html>",
        ]
        paths = []
        for i, html in enumerate(pages):
            p = tmp_path / f"async_{i}.html"
            p.write_text(html)
            paths.append(str(p))

        compiler = BatchCompiler()
        items = [BatchItem(source=p) for p in paths]
        result = await compiler.compile_batch_async(items, max_concurrency=2)

        assert len(result.items) == 2
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_async_error_handling(self, tmp_path):
        good = tmp_path / "good.html"
        good.write_text("<html><body><p>Good content for async error test.</p></body></html>")

        compiler = BatchCompiler()
        items = [
            BatchItem(source=str(good)),
            BatchItem(source="/nonexistent/async_file.html"),
        ]
        result = await compiler.compile_batch_async(items)

        assert len(result.items) == 1
        assert len(result.errors) == 1
