"""Compilation cache — disk-backed caching for compiled AgentDocuments.

Caches by content hash so identical content yields a cache hit.
Supports ETag/Last-Modified for HTTP-based incremental updates.

Design goal: cacheable and incrementally updatable for real Agent workflows.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_web_compiler.core.document import AgentDocument

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A cached compilation result."""

    doc_id: str
    content_hash: str
    etag: str | None
    last_modified: str | None
    compiled_json: str
    cached_at: float  # time.time()
    ttl_seconds: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON storage."""
        return {
            "doc_id": self.doc_id,
            "content_hash": self.content_hash,
            "etag": self.etag,
            "last_modified": self.last_modified,
            "compiled_json": self.compiled_json,
            "cached_at": self.cached_at,
            "ttl_seconds": self.ttl_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CacheEntry:
        """Deserialize from a plain dict."""
        return cls(
            doc_id=data["doc_id"],
            content_hash=data["content_hash"],
            etag=data.get("etag"),
            last_modified=data.get("last_modified"),
            compiled_json=data["compiled_json"],
            cached_at=data["cached_at"],
            ttl_seconds=data["ttl_seconds"],
        )


class CompilationCache:
    """Disk-backed cache for compiled AgentDocuments.

    Caches by content hash so identical content = cache hit.
    Supports ETag/Last-Modified for HTTP-based incremental updates.
    If cache_dir is None, all operations are no-ops (caching disabled).
    """

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        default_ttl: float = 3600.0,
    ) -> None:
        """Initialize cache.

        Args:
            cache_dir: Directory to store cache files. None disables caching.
            default_ttl: Default TTL in seconds for cache entries.
        """
        self._enabled = cache_dir is not None
        self._cache_dir: Path | None = None
        self._default_ttl = default_ttl

        if cache_dir is not None:
            self._cache_dir = Path(cache_dir)
            try:
                self._cache_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                logger.warning(
                    "Cannot create cache directory %s: %s. Caching disabled.",
                    cache_dir,
                    exc,
                )
                self._enabled = False
                self._cache_dir = None

    @property
    def enabled(self) -> bool:
        """Whether caching is active."""
        return self._enabled

    def _entry_path(self, content_hash: str) -> Path | None:
        """Return the file path for a cache entry, or None if disabled."""
        if self._cache_dir is None:
            return None
        # Sanitize hash to be filesystem-safe
        safe_hash = content_hash.replace("/", "_").replace(":", "_")
        return self._cache_dir / f"{safe_hash}.json"

    def get(self, content_hash: str) -> AgentDocument | None:
        """Get a cached document by content hash.

        Returns None on cache miss, expired entry, or any read error.
        """
        if not self._enabled:
            return None

        path = self._entry_path(content_hash)
        if path is None or not path.exists():
            return None

        try:
            raw = path.read_text(encoding="utf-8")
            entry = CacheEntry.from_dict(json.loads(raw))
        except (json.JSONDecodeError, KeyError, OSError) as exc:
            logger.debug("Cache read error for %s: %s", content_hash, exc)
            return None

        # Check TTL
        if time.time() - entry.cached_at > entry.ttl_seconds:
            logger.debug("Cache entry expired for %s", content_hash)
            self.invalidate(content_hash)
            return None

        try:
            doc_data = json.loads(entry.compiled_json)
            return AgentDocument.model_validate(doc_data)
        except Exception as exc:
            logger.debug("Cache deserialization error for %s: %s", content_hash, exc)
            self.invalidate(content_hash)
            return None

    def put(
        self,
        content_hash: str,
        doc: AgentDocument,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> None:
        """Cache a compiled document.

        Args:
            content_hash: Content hash key.
            doc: The compiled AgentDocument to cache.
            etag: Optional HTTP ETag for freshness checking.
            last_modified: Optional HTTP Last-Modified for freshness checking.
        """
        if not self._enabled:
            return

        path = self._entry_path(content_hash)
        if path is None:
            return

        compiled_json = json.dumps(
            doc.model_dump(mode="json"), default=str, ensure_ascii=False
        )
        entry = CacheEntry(
            doc_id=doc.doc_id,
            content_hash=content_hash,
            etag=etag,
            last_modified=last_modified,
            compiled_json=compiled_json,
            cached_at=time.time(),
            ttl_seconds=self._default_ttl,
        )

        try:
            path.write_text(
                json.dumps(entry.to_dict(), ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Cache write error for %s: %s", content_hash, exc)

    def invalidate(self, content_hash: str) -> bool:
        """Remove a cache entry.

        Returns True if the entry existed and was removed.
        """
        if not self._enabled:
            return False

        path = self._entry_path(content_hash)
        if path is None or not path.exists():
            return False

        try:
            path.unlink()
            return True
        except OSError as exc:
            logger.warning("Cache invalidate error for %s: %s", content_hash, exc)
            return False

    def clear(self) -> int:
        """Clear all cache entries.

        Returns the number of entries removed.
        """
        if not self._enabled or self._cache_dir is None:
            return 0

        count = 0
        for entry_file in self._cache_dir.glob("*.json"):
            try:
                entry_file.unlink()
                count += 1
            except OSError:
                pass
        return count

    def is_fresh(
        self,
        content_hash: str,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> bool:
        """Check if a cache entry is still fresh.

        Freshness is determined by:
        1. Entry exists and is not expired (TTL check)
        2. If etag is provided, it must match the cached etag
        3. If last_modified is provided, it must match the cached value

        Returns True if the cached entry is still valid.
        """
        if not self._enabled:
            return False

        path = self._entry_path(content_hash)
        if path is None or not path.exists():
            return False

        try:
            raw = path.read_text(encoding="utf-8")
            entry = CacheEntry.from_dict(json.loads(raw))
        except (json.JSONDecodeError, KeyError, OSError):
            return False

        # TTL check
        if time.time() - entry.cached_at > entry.ttl_seconds:
            return False

        # ETag check: if caller provides an etag, it must match
        if etag is not None and entry.etag is not None and etag != entry.etag:
            return False

        # Last-Modified check
        if last_modified is not None and entry.last_modified is not None:
            return last_modified == entry.last_modified

        return True

    @staticmethod
    def hash_content(content: str | bytes) -> str:
        """Compute a content hash for cache keying.

        Args:
            content: The raw content to hash.

        Returns:
            A hex digest string prefixed with 'sha256:'.
        """
        if isinstance(content, str):
            content = content.encode("utf-8")
        return f"sha256:{hashlib.sha256(content).hexdigest()}"
