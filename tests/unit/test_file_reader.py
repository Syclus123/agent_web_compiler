"""Tests for FileReader."""

from __future__ import annotations

import pytest

from agent_web_compiler.core.errors import FetchError
from agent_web_compiler.sources.file_reader import FileReader


@pytest.fixture
def reader() -> FileReader:
    return FileReader()


class TestFileReader:
    def test_read_html_file(self, reader, tmp_path):
        html_file = tmp_path / "test.html"
        html_file.write_text("<html><body><p>Hello</p></body></html>", encoding="utf-8")
        result = reader.read(str(html_file))
        assert result.content_type == "text/html"
        assert "<p>Hello</p>" in result.content
        assert result.status_code == 200

    def test_read_htm_extension(self, reader, tmp_path):
        htm_file = tmp_path / "test.htm"
        htm_file.write_text("<html><body>Hi</body></html>", encoding="utf-8")
        result = reader.read(str(htm_file))
        assert result.content_type == "text/html"

    def test_read_txt_file(self, reader, tmp_path):
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("plain text content", encoding="utf-8")
        result = reader.read(str(txt_file))
        assert result.content_type == "text/plain"
        assert result.content == "plain text content"

    def test_nonexistent_file_raises_fetch_error(self, reader, tmp_path):
        fake_path = tmp_path / "nonexistent.html"
        with pytest.raises(FetchError, match="File not found"):
            reader.read(str(fake_path))

    def test_directory_raises_fetch_error(self, reader, tmp_path):
        with pytest.raises(FetchError, match="not a file"):
            reader.read(str(tmp_path))

    def test_content_type_html(self, reader, tmp_path):
        f = tmp_path / "page.html"
        f.write_text("<html></html>", encoding="utf-8")
        result = reader.read(str(f))
        assert result.content_type == "text/html"

    def test_content_type_json(self, reader, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('{"key": "value"}', encoding="utf-8")
        result = reader.read(str(f))
        assert result.content_type == "application/json"

    def test_content_type_unknown_extension(self, reader, tmp_path):
        f = tmp_path / "data.xyz"
        f.write_text("something", encoding="utf-8")
        result = reader.read(str(f))
        assert result.content_type == "application/octet-stream"

    def test_metadata_includes_file_info(self, reader, tmp_path):
        f = tmp_path / "test.html"
        f.write_text("<html></html>", encoding="utf-8")
        result = reader.read(str(f))
        assert "file_path" in result.metadata
        assert "file_size" in result.metadata
        assert "extension" in result.metadata
        assert result.metadata["extension"] == ".html"

    def test_url_is_file_uri(self, reader, tmp_path):
        f = tmp_path / "test.html"
        f.write_text("<html></html>", encoding="utf-8")
        result = reader.read(str(f))
        assert result.url.startswith("file://")

    def test_fetch_error_preserves_stage(self, reader, tmp_path):
        fake_path = tmp_path / "missing.html"
        with pytest.raises(FetchError) as exc_info:
            reader.read(str(fake_path))
        assert exc_info.value.stage == "fetch"
