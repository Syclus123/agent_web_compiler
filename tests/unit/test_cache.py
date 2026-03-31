"""Tests for the compilation cache."""

from __future__ import annotations

import time

import pytest

from agent_web_compiler.core.block import Block, BlockType
from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.core.document import AgentDocument, Quality, SourceType
from agent_web_compiler.pipeline.cache import CacheEntry, CompilationCache


def _make_doc(content: str = "test") -> AgentDocument:
    """Create a minimal AgentDocument for testing."""
    return AgentDocument(
        doc_id=AgentDocument.make_doc_id(content),
        source_type=SourceType.HTML,
        title="Test",
        blocks=[
            Block(id="b_001", type=BlockType.PARAGRAPH, text="Hello world", order=0),
        ],
        canonical_markdown="Hello world\n",
        quality=Quality(block_count=1, action_count=0),
    )


class TestCompilationCacheDisabled:
    """Tests for cache when disabled (cache_dir=None)."""

    def test_disabled_get_returns_none(self) -> None:
        cache = CompilationCache(cache_dir=None)
        assert cache.get("any_hash") is None

    def test_disabled_put_is_noop(self) -> None:
        cache = CompilationCache(cache_dir=None)
        cache.put("any_hash", _make_doc())  # Should not raise

    def test_disabled_invalidate_returns_false(self) -> None:
        cache = CompilationCache(cache_dir=None)
        assert cache.invalidate("any_hash") is False

    def test_disabled_clear_returns_zero(self) -> None:
        cache = CompilationCache(cache_dir=None)
        assert cache.clear() == 0

    def test_disabled_is_fresh_returns_false(self) -> None:
        cache = CompilationCache(cache_dir=None)
        assert cache.is_fresh("any_hash") is False

    def test_enabled_property_false(self) -> None:
        cache = CompilationCache(cache_dir=None)
        assert cache.enabled is False


class TestCompilationCacheEnabled:
    """Tests for cache with a real directory."""

    @pytest.fixture
    def cache(self, tmp_path) -> CompilationCache:
        return CompilationCache(cache_dir=tmp_path / "cache", default_ttl=60.0)

    def test_enabled_property_true(self, cache: CompilationCache) -> None:
        assert cache.enabled is True

    def test_put_and_get(self, cache: CompilationCache) -> None:
        doc = _make_doc()
        content_hash = CompilationCache.hash_content("test")
        cache.put(content_hash, doc)

        retrieved = cache.get(content_hash)
        assert retrieved is not None
        assert retrieved.doc_id == doc.doc_id
        assert retrieved.title == doc.title
        assert len(retrieved.blocks) == 1
        assert retrieved.blocks[0].text == "Hello world"

    def test_get_miss(self, cache: CompilationCache) -> None:
        assert cache.get("nonexistent_hash") is None

    def test_invalidate(self, cache: CompilationCache) -> None:
        doc = _make_doc()
        content_hash = CompilationCache.hash_content("test")
        cache.put(content_hash, doc)

        assert cache.invalidate(content_hash) is True
        assert cache.get(content_hash) is None
        # Second invalidate should return False
        assert cache.invalidate(content_hash) is False

    def test_clear(self, cache: CompilationCache) -> None:
        for i in range(3):
            h = CompilationCache.hash_content(f"content_{i}")
            cache.put(h, _make_doc(f"content_{i}"))

        removed = cache.clear()
        assert removed == 3

        for i in range(3):
            h = CompilationCache.hash_content(f"content_{i}")
            assert cache.get(h) is None

    def test_expired_entry_returns_none(self, tmp_path) -> None:
        cache = CompilationCache(cache_dir=tmp_path / "cache", default_ttl=0.01)
        doc = _make_doc()
        content_hash = CompilationCache.hash_content("test")
        cache.put(content_hash, doc)

        time.sleep(0.02)
        assert cache.get(content_hash) is None

    def test_is_fresh_valid(self, cache: CompilationCache) -> None:
        doc = _make_doc()
        content_hash = CompilationCache.hash_content("test")
        cache.put(content_hash, doc, etag='"abc123"', last_modified="Wed, 01 Jan 2025")

        assert cache.is_fresh(content_hash) is True
        assert cache.is_fresh(content_hash, etag='"abc123"') is True
        assert cache.is_fresh(content_hash, last_modified="Wed, 01 Jan 2025") is True

    def test_is_fresh_stale_etag(self, cache: CompilationCache) -> None:
        doc = _make_doc()
        content_hash = CompilationCache.hash_content("test")
        cache.put(content_hash, doc, etag='"abc123"')

        assert cache.is_fresh(content_hash, etag='"different"') is False

    def test_is_fresh_stale_last_modified(self, cache: CompilationCache) -> None:
        doc = _make_doc()
        content_hash = CompilationCache.hash_content("test")
        cache.put(content_hash, doc, last_modified="Wed, 01 Jan 2025")

        assert cache.is_fresh(content_hash, last_modified="Thu, 02 Jan 2025") is False

    def test_is_fresh_expired_ttl(self, tmp_path) -> None:
        cache = CompilationCache(cache_dir=tmp_path / "cache", default_ttl=0.01)
        content_hash = CompilationCache.hash_content("test")
        cache.put(content_hash, _make_doc())

        time.sleep(0.02)
        assert cache.is_fresh(content_hash) is False


class TestHashContent:
    def test_string_hash(self) -> None:
        h = CompilationCache.hash_content("hello")
        assert h.startswith("sha256:")
        assert len(h) > 10

    def test_bytes_hash(self) -> None:
        h = CompilationCache.hash_content(b"hello")
        assert h.startswith("sha256:")

    def test_deterministic(self) -> None:
        h1 = CompilationCache.hash_content("same content")
        h2 = CompilationCache.hash_content("same content")
        assert h1 == h2

    def test_different_content_different_hash(self) -> None:
        h1 = CompilationCache.hash_content("content a")
        h2 = CompilationCache.hash_content("content b")
        assert h1 != h2


class TestCacheEntry:
    def test_round_trip(self) -> None:
        entry = CacheEntry(
            doc_id="sha256:abc",
            content_hash="sha256:def",
            etag='"etag"',
            last_modified="date",
            compiled_json='{"key": "value"}',
            cached_at=1000.0,
            ttl_seconds=3600.0,
        )
        d = entry.to_dict()
        restored = CacheEntry.from_dict(d)
        assert restored.doc_id == entry.doc_id
        assert restored.etag == entry.etag
        assert restored.cached_at == entry.cached_at


class TestCacheIntegrationWithCompiler:
    """Test cache integration in the HTML pipeline."""

    def test_cache_hit_on_second_compile(self, tmp_path) -> None:
        from agent_web_compiler.pipeline.compiler import HTMLCompiler

        config = CompileConfig(
            cache_dir=str(tmp_path / "cache"),
            cache_ttl=60.0,
        )
        compiler = HTMLCompiler()
        html = "<html><body><h1>Test</h1><p>Content</p></body></html>"

        doc1 = compiler.compile(html, config=config)
        doc2 = compiler.compile(html, config=config)

        assert doc1.doc_id == doc2.doc_id
