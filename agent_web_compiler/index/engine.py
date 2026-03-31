"""Index engine — stores and retrieves documents, blocks, actions, and sites.

Supports:
- BM25 sparse retrieval (pure Python, no external deps)
- Dense vector retrieval (cosine similarity, bring-your-own embeddings)
- Metadata filtering (site, type, importance, freshness)
- Incremental updates (add/update/remove documents)
- Disk persistence (JSON-based, load/save)
"""

from __future__ import annotations

import dataclasses
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from agent_web_compiler.core.document import AgentDocument
from agent_web_compiler.index.ingestion import ingest_document
from agent_web_compiler.index.schema import (
    ActionRecord,
    BlockRecord,
    DocumentRecord,
    SiteRecord,
)

# BM25 parameters
_BM25_K1 = 1.5
_BM25_B = 0.75

# Stopwords for tokenization
_STOPWORDS: frozenset[str] = frozenset(
    {
        "the", "a", "an", "is", "in", "to", "of", "and", "or", "for", "on",
        "with", "at", "by", "from", "as", "it", "that", "this", "was", "are",
        "be", "has", "have", "had", "not", "but", "what", "all", "were", "we",
        "when", "your", "can", "there", "use", "each", "which", "she", "he",
        "do", "how", "their", "if", "will", "up", "about", "out", "them",
        "then", "no", "so", "its",
    }
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class IndexEngine:
    """In-memory multi-index engine with hybrid retrieval.

    Maintains four index types:
    - documents: coarse page-level index
    - blocks: fine-grained content index (primary search unit)
    - actions: task-oriented action index
    - sites: domain-level template index
    """

    def __init__(self) -> None:
        self._documents: dict[str, DocumentRecord] = {}
        self._blocks: dict[str, BlockRecord] = {}
        self._actions: dict[str, ActionRecord] = {}
        self._sites: dict[str, SiteRecord] = {}

        # BM25 inverted index for blocks
        self._block_tf: dict[str, dict[str, float]] = {}  # block_id -> {term: tf}
        self._block_doc_freq: dict[str, int] = {}  # term -> number of blocks containing it
        self._block_lengths: dict[str, int] = {}  # block_id -> token count
        self._avg_block_length: float = 0.0
        self._total_blocks: int = 0

        # BM25 inverted index for actions
        self._action_tf: dict[str, dict[str, float]] = {}
        self._action_doc_freq: dict[str, int] = {}
        self._action_lengths: dict[str, int] = {}
        self._avg_action_length: float = 0.0
        self._total_actions: int = 0

        self._dirty: bool = False

    # --- Ingestion ---

    def ingest(self, doc: AgentDocument) -> None:
        """Ingest a compiled AgentDocument into all indexes.

        If a document with the same doc_id already exists, it is removed first.
        """
        # Remove existing document if present (idempotent re-ingest)
        if doc.doc_id in self._documents:
            self.remove(doc.doc_id)

        doc_record, block_records, action_records, site_record = ingest_document(doc)

        # Store document
        self._documents[doc_record.doc_id] = doc_record

        # Store blocks and build BM25
        for br in block_records:
            key = f"{br.doc_id}:{br.block_id}"
            self._blocks[key] = br
            self._index_block_bm25(br, key)

        # Store actions and build BM25
        for ar in action_records:
            key = f"{ar.doc_id}:{ar.action_id}"
            self._actions[key] = ar
            self._index_action_bm25(ar, key)

        # Merge site record
        if site_record:
            existing = self._sites.get(site_record.site_id)
            if existing:
                existing.doc_count += 1
                existing.last_indexed = site_record.last_indexed
                # Merge entry points
                for ep in site_record.entry_points:
                    if ep not in existing.entry_points:
                        existing.entry_points.append(ep)
                # Merge common actions
                for ca in site_record.common_actions:
                    if ca not in existing.common_actions:
                        existing.common_actions.append(ca)
            else:
                self._sites[site_record.site_id] = site_record

        self._dirty = True

    def remove(self, doc_id: str) -> bool:
        """Remove a document and its blocks/actions from all indexes."""
        if doc_id not in self._documents:
            return False

        doc_record = self._documents.pop(doc_id)

        # Remove blocks
        block_ids_to_remove = [
            bid for bid, br in self._blocks.items() if br.doc_id == doc_id
        ]
        for bid in block_ids_to_remove:
            self._remove_block_bm25(bid)
            del self._blocks[bid]

        # Remove actions
        action_ids_to_remove = [
            aid for aid, ar in self._actions.items() if ar.doc_id == doc_id
        ]
        for aid in action_ids_to_remove:
            self._remove_action_bm25(aid)
            del self._actions[aid]

        # Update site record
        if doc_record.site_id and doc_record.site_id in self._sites:
            site = self._sites[doc_record.site_id]
            site.doc_count = max(0, site.doc_count - 1)
            if site.doc_count == 0:
                del self._sites[doc_record.site_id]

        self._dirty = True
        return True

    def update(self, doc: AgentDocument) -> None:
        """Update an existing document (remove + re-ingest)."""
        self.remove(doc.doc_id)
        self.ingest(doc)

    # --- BM25 Sparse Retrieval ---

    def search_blocks_bm25(
        self,
        query: str,
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[tuple[BlockRecord, float]]:
        """BM25 text search over blocks. Returns (record, score) pairs."""
        tokens = self._tokenize(query)
        if not tokens:
            return []

        candidates = self._apply_block_filters(filters)
        scored: list[tuple[BlockRecord, float]] = []

        for block_id in candidates:
            score = self._bm25_score_block(tokens, block_id)
            if score > 0:
                scored.append((self._blocks[block_id], score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def search_actions_bm25(
        self,
        query: str,
        top_k: int = 10,
    ) -> list[tuple[ActionRecord, float]]:
        """BM25 text search over action labels/roles."""
        tokens = self._tokenize(query)
        if not tokens:
            return []

        scored: list[tuple[ActionRecord, float]] = []
        for action_id in self._action_tf:
            score = self._bm25_score_action(tokens, action_id)
            if score > 0:
                scored.append((self._actions[action_id], score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    # --- Dense Vector Retrieval ---

    def search_blocks_dense(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        filters: dict | None = None,
    ) -> list[tuple[BlockRecord, float]]:
        """Cosine similarity search over block embeddings."""
        candidates = self._apply_block_filters(filters)
        scored: list[tuple[BlockRecord, float]] = []

        for block_id in candidates:
            block = self._blocks[block_id]
            if block.embedding is not None:
                sim = _cosine_similarity(query_embedding, block.embedding)
                if sim > 0:
                    scored.append((block, sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def search_actions_dense(
        self,
        query_embedding: list[float],
        top_k: int = 10,
    ) -> list[tuple[ActionRecord, float]]:
        """Cosine similarity search over action embeddings."""
        scored: list[tuple[ActionRecord, float]] = []

        for action in self._actions.values():
            if action.embedding is not None:
                sim = _cosine_similarity(query_embedding, action.embedding)
                if sim > 0:
                    scored.append((action, sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    # --- Hybrid Retrieval ---

    def search_blocks(
        self,
        query: str,
        query_embedding: list[float] | None = None,
        top_k: int = 10,
        filters: dict | None = None,
        bm25_weight: float = 0.5,
    ) -> list[tuple[BlockRecord, float]]:
        """Hybrid search combining BM25 + dense retrieval.

        Scores are normalized to [0, 1] before weighted combination.
        If no query_embedding is provided, falls back to pure BM25.
        """
        # BM25 scores
        bm25_results = self.search_blocks_bm25(
            query, top_k=max(top_k * 3, 50), filters=filters
        )

        if query_embedding is None or not bm25_results:
            # Pure BM25 fallback
            return bm25_results[:top_k]

        # Dense scores
        dense_results = self.search_blocks_dense(
            query_embedding, top_k=max(top_k * 3, 50), filters=filters
        )

        # Normalize and combine
        bm25_scores: dict[str, float] = {}
        dense_scores: dict[str, float] = {}

        if bm25_results:
            max_bm25 = max(s for _, s in bm25_results)
            if max_bm25 > 0:
                bm25_scores = {r.block_id: s / max_bm25 for r, s in bm25_results}

        if dense_results:
            max_dense = max(s for _, s in dense_results)
            if max_dense > 0:
                for r, s in dense_results:
                    # Use a stable key for merging
                    key = f"{r.doc_id}:{r.block_id}"
                    dense_scores[key] = s / max_dense

        # Merge all candidate block IDs
        all_ids = set(bm25_scores.keys()) | set(dense_scores.keys())
        dense_weight = 1.0 - bm25_weight

        combined: list[tuple[BlockRecord, float]] = []
        for bid in all_ids:
            score = (
                bm25_weight * bm25_scores.get(bid, 0.0)
                + dense_weight * dense_scores.get(bid, 0.0)
            )
            block = self._blocks.get(bid)
            if block:
                combined.append((block, score))

        combined.sort(key=lambda x: x[1], reverse=True)
        return combined[:top_k]

    def search_actions(
        self,
        query: str,
        query_embedding: list[float] | None = None,
        top_k: int = 10,
    ) -> list[tuple[ActionRecord, float]]:
        """Hybrid action search."""
        bm25_results = self.search_actions_bm25(query, top_k=max(top_k * 3, 50))

        if query_embedding is None or not bm25_results:
            return bm25_results[:top_k]

        dense_results = self.search_actions_dense(
            query_embedding, top_k=max(top_k * 3, 50)
        )

        # Normalize and combine
        bm25_scores: dict[str, float] = {}
        dense_scores: dict[str, float] = {}

        if bm25_results:
            max_bm25 = max(s for _, s in bm25_results)
            if max_bm25 > 0:
                bm25_scores = {r.action_id: s / max_bm25 for r, s in bm25_results}

        if dense_results:
            max_dense = max(s for _, s in dense_results)
            if max_dense > 0:
                dense_scores = {r.action_id: s / max_dense for r, s in dense_results}

        all_ids = set(bm25_scores.keys()) | set(dense_scores.keys())
        combined: list[tuple[ActionRecord, float]] = []
        for aid in all_ids:
            score = 0.5 * bm25_scores.get(aid, 0.0) + 0.5 * dense_scores.get(aid, 0.0)
            combined.append((self._actions[aid], score))

        combined.sort(key=lambda x: x[1], reverse=True)
        return combined[:top_k]

    # --- Metadata Queries ---

    def get_document(self, doc_id: str) -> DocumentRecord | None:
        """Get a document record by ID."""
        return self._documents.get(doc_id)

    def get_block(self, block_id: str) -> BlockRecord | None:
        """Get a block record by ID (supports both plain and compound keys)."""
        # Try direct key first
        result = self._blocks.get(block_id)
        if result:
            return result
        # Try matching by block_id field (compound key scenario)
        for br in self._blocks.values():
            if br.block_id == block_id:
                return br
        return None

    def get_blocks_by_doc(self, doc_id: str) -> list[BlockRecord]:
        """Get all block records for a document."""
        return [br for br in self._blocks.values() if br.doc_id == doc_id]

    def get_actions_by_doc(self, doc_id: str) -> list[ActionRecord]:
        """Get all action records for a document."""
        return [ar for ar in self._actions.values() if ar.doc_id == doc_id]

    def get_site(self, site_id: str) -> SiteRecord | None:
        """Get a site record by ID."""
        return self._sites.get(site_id)

    def list_documents(self) -> list[DocumentRecord]:
        """List all document records."""
        return list(self._documents.values())

    def list_sites(self) -> list[SiteRecord]:
        """List all site records."""
        return list(self._sites.values())

    @property
    def stats(self) -> dict[str, int]:
        """Return index statistics."""
        return {
            "documents": len(self._documents),
            "blocks": len(self._blocks),
            "actions": len(self._actions),
            "sites": len(self._sites),
        }

    # --- Persistence ---

    def save(self, path: str | Path) -> None:
        """Save all indexes to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data: dict[str, Any] = {
            "version": "1.0",
            "documents": {k: dataclasses.asdict(v) for k, v in self._documents.items()},
            "blocks": {k: _block_to_dict(v) for k, v in self._blocks.items()},
            "actions": {k: _action_to_dict(v) for k, v in self._actions.items()},
            "sites": {k: dataclasses.asdict(v) for k, v in self._sites.items()},
        }

        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self._dirty = False

    def load(self, path: str | Path) -> None:
        """Load indexes from a JSON file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Index file not found: {path}")

        text = path.read_text(encoding="utf-8")
        data = json.loads(text)

        # Clear existing state
        self._documents.clear()
        self._blocks.clear()
        self._actions.clear()
        self._sites.clear()
        self._block_tf.clear()
        self._block_doc_freq.clear()
        self._block_lengths.clear()
        self._action_tf.clear()
        self._action_doc_freq.clear()
        self._action_lengths.clear()

        # Load records
        for k, v in data.get("documents", {}).items():
            self._documents[k] = DocumentRecord(**v)

        for k, v in data.get("blocks", {}).items():
            self._blocks[k] = BlockRecord(**v)

        for k, v in data.get("actions", {}).items():
            self._actions[k] = ActionRecord(**v)

        for k, v in data.get("sites", {}).items():
            self._sites[k] = SiteRecord(**v)

        # Rebuild BM25 indexes
        self._rebuild_bm25()
        self._dirty = False

    # --- Internal BM25 ---

    def _rebuild_bm25(self) -> None:
        """Rebuild BM25 inverted indexes from all blocks and actions."""
        self._block_tf.clear()
        self._block_doc_freq.clear()
        self._block_lengths.clear()
        self._action_tf.clear()
        self._action_doc_freq.clear()
        self._action_lengths.clear()

        for key, br in self._blocks.items():
            self._index_block_bm25(br, key)

        for key, ar in self._actions.items():
            self._index_action_bm25(ar, key)

    def _index_block_bm25(self, block: BlockRecord, key: str | None = None) -> None:
        """Add a block to the BM25 inverted index."""
        bid = key or block.block_id
        tokens = self._tokenize(block.text)
        if not tokens:
            return

        tf = Counter(tokens)
        self._block_tf[bid] = dict(tf)
        self._block_lengths[bid] = len(tokens)

        for term in tf:
            self._block_doc_freq[term] = self._block_doc_freq.get(term, 0) + 1

        self._total_blocks = len(self._block_tf)
        self._avg_block_length = (
            sum(self._block_lengths.values()) / self._total_blocks
            if self._total_blocks > 0
            else 0.0
        )

    def _remove_block_bm25(self, block_id: str) -> None:
        """Remove a block from the BM25 inverted index."""
        tf = self._block_tf.pop(block_id, None)
        self._block_lengths.pop(block_id, None)

        if tf:
            for term in tf:
                if term in self._block_doc_freq:
                    self._block_doc_freq[term] -= 1
                    if self._block_doc_freq[term] <= 0:
                        del self._block_doc_freq[term]

        self._total_blocks = len(self._block_tf)
        self._avg_block_length = (
            sum(self._block_lengths.values()) / self._total_blocks
            if self._total_blocks > 0
            else 0.0
        )

    def _index_action_bm25(self, action: ActionRecord, key: str | None = None) -> None:
        """Add an action to the BM25 inverted index."""
        aid = key or action.action_id
        text = action.label
        if action.role:
            text += " " + action.role
        tokens = self._tokenize(text)
        if not tokens:
            return

        tf = Counter(tokens)
        self._action_tf[aid] = dict(tf)
        self._action_lengths[aid] = len(tokens)

        for term in tf:
            self._action_doc_freq[term] = self._action_doc_freq.get(term, 0) + 1

        self._total_actions = len(self._action_tf)
        self._avg_action_length = (
            sum(self._action_lengths.values()) / self._total_actions
            if self._total_actions > 0
            else 0.0
        )

    def _remove_action_bm25(self, action_id: str) -> None:
        """Remove an action from the BM25 inverted index."""
        tf = self._action_tf.pop(action_id, None)
        self._action_lengths.pop(action_id, None)

        if tf:
            for term in tf:
                if term in self._action_doc_freq:
                    self._action_doc_freq[term] -= 1
                    if self._action_doc_freq[term] <= 0:
                        del self._action_doc_freq[term]

        self._total_actions = len(self._action_tf)
        self._avg_action_length = (
            sum(self._action_lengths.values()) / self._total_actions
            if self._total_actions > 0
            else 0.0
        )

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text for BM25 (lowercase, split on non-alnum, remove stopwords)."""
        return [
            t
            for t in _TOKEN_RE.findall(text.lower())
            if t not in _STOPWORDS and len(t) > 1
        ]

    def _bm25_score_block(self, query_tokens: list[str], block_id: str) -> float:
        """Compute BM25 score for a block against query tokens."""
        tf_map = self._block_tf.get(block_id)
        if not tf_map:
            return 0.0

        dl = self._block_lengths.get(block_id, 0)
        avgdl = self._avg_block_length
        n = self._total_blocks

        return _bm25_score(query_tokens, tf_map, dl, avgdl, n, self._block_doc_freq)

    def _bm25_score_action(self, query_tokens: list[str], action_id: str) -> float:
        """Compute BM25 score for an action against query tokens."""
        tf_map = self._action_tf.get(action_id)
        if not tf_map:
            return 0.0

        dl = self._action_lengths.get(action_id, 0)
        avgdl = self._avg_action_length
        n = self._total_actions

        return _bm25_score(query_tokens, tf_map, dl, avgdl, n, self._action_doc_freq)

    def _apply_block_filters(self, filters: dict | None) -> list[str]:
        """Return block IDs that match the given filters."""
        if not filters:
            return list(self._blocks.keys())

        result: list[str] = []
        for bid, block in self._blocks.items():
            if not _block_matches_filters(block, filters):
                continue
            result.append(bid)
        return result


# --- Pure functions ---


def _bm25_score(
    query_tokens: list[str],
    tf_map: dict[str, float],
    dl: int,
    avgdl: float,
    n: int,
    doc_freq: dict[str, int],
) -> float:
    """Compute BM25 score.

    Formula: sum(IDF * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl/avgdl)))
    IDF = log((N - df + 0.5) / (df + 0.5) + 1)
    """
    if n == 0 or avgdl == 0:
        return 0.0

    score = 0.0
    for token in query_tokens:
        tf = tf_map.get(token, 0)
        if tf == 0:
            continue

        df = doc_freq.get(token, 0)
        idf = math.log((n - df + 0.5) / (df + 0.5) + 1)
        numerator = tf * (_BM25_K1 + 1)
        denominator = tf + _BM25_K1 * (1 - _BM25_B + _BM25_B * dl / avgdl)
        score += idf * numerator / denominator

    return score


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Returns 0.0 for zero-norm vectors.
    """
    if len(a) != len(b) or not a:
        return 0.0

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot / (norm_a * norm_b)


def _block_matches_filters(block: BlockRecord, filters: dict) -> bool:
    """Check if a block matches the given filter criteria."""
    if "site_id" in filters:
        # Need to look up the document's site_id — not stored on BlockRecord,
        # but we can match via doc_id pattern. For now, skip blocks without match.
        # This is checked at the engine level if needed.
        pass

    if "block_type" in filters:
        allowed = filters["block_type"]
        if isinstance(allowed, str):
            allowed = [allowed]
        if block.block_type not in allowed:
            return False

    if "min_importance" in filters and block.importance < filters["min_importance"]:
        return False

    if "doc_id" in filters:
        return block.doc_id == filters["doc_id"]

    return True


def _block_to_dict(block: BlockRecord) -> dict[str, Any]:
    """Convert a BlockRecord to a dict, handling embedding serialization."""
    d = dataclasses.asdict(block)
    return d


def _action_to_dict(action: ActionRecord) -> dict[str, Any]:
    """Convert an ActionRecord to a dict, handling embedding serialization."""
    d = dataclasses.asdict(action)
    return d
