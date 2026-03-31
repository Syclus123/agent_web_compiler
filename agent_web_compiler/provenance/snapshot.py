"""Snapshot objects — versioned captures of page/document state.

Binds evidence to a specific point-in-time capture so citations
remain valid even after the source page changes.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_web_compiler.core.document import AgentDocument

# Package version — imported lazily to avoid circular imports
_COMPILER_VERSION = "0.7.0"


def _make_snapshot_id() -> str:
    """Generate a unique snapshot ID."""
    return f"snap_{uuid.uuid4().hex[:12]}"


@dataclass
class Snapshot:
    """A versioned capture of a page or document."""

    snapshot_id: str
    source_url: str | None = None
    source_file: str | None = None
    content_hash: str = ""  # SHA-256 of the raw content
    timestamp: float = 0.0
    compiler_version: str = ""
    doc_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "snapshot_id": self.snapshot_id,
            "source_url": self.source_url,
            "source_file": self.source_file,
            "content_hash": self.content_hash,
            "timestamp": self.timestamp,
            "compiler_version": self.compiler_version,
            "doc_id": self.doc_id,
            "metadata": self.metadata,
        }

    @staticmethod
    def from_document(doc: AgentDocument) -> Snapshot:
        """Create a snapshot from a compiled document.

        Uses the document's canonical markdown for the content hash,
        and captures source URL, file, doc_id, and timing.
        """
        content = doc.canonical_markdown or doc.title or ""
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        return Snapshot(
            snapshot_id=_make_snapshot_id(),
            source_url=doc.source_url,
            source_file=doc.source_file,
            content_hash=content_hash,
            timestamp=time.time(),
            compiler_version=_COMPILER_VERSION,
            doc_id=doc.doc_id,
            metadata={
                "schema_version": doc.schema_version,
                "block_count": doc.block_count,
                "action_count": doc.action_count,
            },
        )


class SnapshotStore:
    """Stores and retrieves page snapshots for evidence binding.

    In-memory store. For persistence, serialize snapshots via to_dict().
    """

    def __init__(self) -> None:
        self._snapshots: dict[str, Snapshot] = {}
        self._by_url: dict[str, list[str]] = {}  # url -> [snapshot_ids]

    def capture(self, doc: AgentDocument) -> Snapshot:
        """Create and store a snapshot from a compiled document."""
        snap = Snapshot.from_document(doc)
        self._snapshots[snap.snapshot_id] = snap
        if snap.source_url:
            self._by_url.setdefault(snap.source_url, []).append(snap.snapshot_id)
        return snap

    def get(self, snapshot_id: str) -> Snapshot | None:
        """Retrieve a snapshot by ID."""
        return self._snapshots.get(snapshot_id)

    def get_by_url(self, url: str) -> list[Snapshot]:
        """Retrieve all snapshots for a given URL, oldest first."""
        ids = self._by_url.get(url, [])
        snapshots = [self._snapshots[sid] for sid in ids if sid in self._snapshots]
        snapshots.sort(key=lambda s: s.timestamp)
        return snapshots

    def get_latest(self, url: str) -> Snapshot | None:
        """Retrieve the most recent snapshot for a URL."""
        snapshots = self.get_by_url(url)
        return snapshots[-1] if snapshots else None

    def list_all(self) -> list[Snapshot]:
        """List all stored snapshots, oldest first."""
        snapshots = list(self._snapshots.values())
        snapshots.sort(key=lambda s: s.timestamp)
        return snapshots
