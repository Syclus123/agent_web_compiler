"""Comprehensive tests for the index engine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_web_compiler.core.action import Action, ActionType
from agent_web_compiler.core.block import Block, BlockType
from agent_web_compiler.core.document import AgentDocument, SourceType
from agent_web_compiler.index.engine import IndexEngine, _bm25_score, _cosine_similarity
from agent_web_compiler.index.ingestion import ingest_document

# --- Fixtures ---


def _make_block(
    id: str,
    type: BlockType = BlockType.PARAGRAPH,
    text: str = "Default block text.",
    importance: float = 0.5,
    section_path: list[str] | None = None,
    order: int = 0,
    metadata: dict | None = None,
) -> Block:
    return Block(
        id=id,
        type=type,
        text=text,
        importance=importance,
        section_path=section_path or [],
        order=order,
        metadata=metadata or {},
    )


def _make_action(
    id: str,
    type: ActionType = ActionType.CLICK,
    label: str = "Click me",
    role: str | None = None,
    selector: str | None = None,
    confidence: float = 0.5,
) -> Action:
    return Action(
        id=id,
        type=type,
        label=label,
        role=role,
        selector=selector,
        confidence=confidence,
    )


def _make_doc(
    doc_id: str = "doc_001",
    title: str = "Test Document",
    source_url: str = "https://example.com/page",
    blocks: list[Block] | None = None,
    actions: list[Action] | None = None,
) -> AgentDocument:
    return AgentDocument(
        doc_id=doc_id,
        source_type=SourceType.HTML,
        source_url=source_url,
        title=title,
        blocks=blocks or [],
        actions=actions or [],
    )


def _sample_doc() -> AgentDocument:
    """Create a sample document with blocks and actions for testing."""
    blocks = [
        _make_block("b_001", BlockType.HEADING, "Introduction to Machine Learning", importance=0.9, order=0),
        _make_block("b_002", BlockType.PARAGRAPH, "Machine learning is a subset of artificial intelligence that enables systems to learn from data.", importance=0.7, order=1, section_path=["Introduction to Machine Learning"]),
        _make_block("b_003", BlockType.PARAGRAPH, "Deep learning uses neural networks with many layers to model complex patterns.", importance=0.6, order=2, section_path=["Introduction to Machine Learning"]),
        _make_block("b_004", BlockType.CODE, "import tensorflow as tf\nmodel = tf.keras.Sequential()", importance=0.5, order=3, section_path=["Introduction to Machine Learning", "Code Examples"]),
        _make_block("b_005", BlockType.TABLE, "Framework | Stars | Language\nTensorFlow | 180k | Python\nPyTorch | 75k | Python", importance=0.8, order=4, section_path=["Comparison"]),
    ]
    actions = [
        _make_action("a_001", ActionType.CLICK, "Search", role="submit_search", selector="#search-btn"),
        _make_action("a_002", ActionType.INPUT, "Search query input", role="search_input", selector="#search-input"),
        _make_action("a_003", ActionType.NAVIGATE, "Next page", role="next_page"),
    ]
    return _make_doc(blocks=blocks, actions=actions)


def _second_doc() -> AgentDocument:
    """Create a second document for multi-doc tests."""
    blocks = [
        _make_block("b_101", BlockType.HEADING, "Python Programming Guide", importance=0.9, order=0),
        _make_block("b_102", BlockType.PARAGRAPH, "Python is a versatile programming language used for web development and data science.", importance=0.7, order=1, section_path=["Python Programming Guide"]),
        _make_block("b_103", BlockType.LIST, "Features: dynamic typing, garbage collection, large standard library", importance=0.5, order=2, section_path=["Features"]),
    ]
    actions = [
        _make_action("a_101", ActionType.CLICK, "Download Python", role="download"),
    ]
    return _make_doc(
        doc_id="doc_002",
        title="Python Guide",
        source_url="https://python.org/guide",
        blocks=blocks,
        actions=actions,
    )


# --- Ingestion Tests ---


class TestIngestion:
    def test_ingest_creates_records(self) -> None:
        engine = IndexEngine()
        doc = _sample_doc()
        engine.ingest(doc)

        assert engine.stats["documents"] == 1
        assert engine.stats["blocks"] == 5
        assert engine.stats["actions"] == 3
        assert engine.stats["sites"] == 1

    def test_ingest_document_record_fields(self) -> None:
        engine = IndexEngine()
        doc = _sample_doc()
        engine.ingest(doc)

        dr = engine.get_document("doc_001")
        assert dr is not None
        assert dr.doc_id == "doc_001"
        assert dr.title == "Test Document"
        assert dr.url == "https://example.com/page"
        assert dr.site_id == "example.com"
        assert dr.source_type == "html"
        assert dr.block_count == 5
        assert dr.action_count == 3

    def test_ingest_block_records(self) -> None:
        engine = IndexEngine()
        doc = _sample_doc()
        engine.ingest(doc)

        blocks = engine.get_blocks_by_doc("doc_001")
        assert len(blocks) == 5
        types = {b.block_type for b in blocks}
        assert "heading" in types
        assert "paragraph" in types
        assert "code" in types
        assert "table" in types

    def test_ingest_action_records(self) -> None:
        engine = IndexEngine()
        doc = _sample_doc()
        engine.ingest(doc)

        actions = engine.get_actions_by_doc("doc_001")
        assert len(actions) == 3
        labels = {a.label for a in actions}
        assert "Search" in labels
        assert "Next page" in labels

    def test_ingest_site_record(self) -> None:
        engine = IndexEngine()
        doc = _sample_doc()
        engine.ingest(doc)

        site = engine.get_site("example.com")
        assert site is not None
        assert site.site_id == "example.com"
        assert site.doc_count == 1

    def test_ingest_multiple_docs_same_site(self) -> None:
        engine = IndexEngine()
        doc1 = _sample_doc()
        doc2 = _make_doc(
            doc_id="doc_002",
            title="Second Page",
            source_url="https://example.com/page2",
            blocks=[_make_block("b_201", BlockType.PARAGRAPH, "Second page content")],
        )
        engine.ingest(doc1)
        engine.ingest(doc2)

        site = engine.get_site("example.com")
        assert site is not None
        assert site.doc_count == 2
        assert engine.stats["documents"] == 2

    def test_ingest_doc_without_url(self) -> None:
        doc = _make_doc(doc_id="doc_nourl", source_url=None)
        engine = IndexEngine()
        engine.ingest(doc)

        dr = engine.get_document("doc_nourl")
        assert dr is not None
        assert dr.site_id is None
        assert engine.stats["sites"] == 0

    def test_ingest_document_function(self) -> None:
        doc = _sample_doc()
        doc_record, block_records, action_records, site_record = ingest_document(doc)

        assert doc_record.doc_id == "doc_001"
        assert len(block_records) == 5
        assert len(action_records) == 3
        assert site_record is not None
        assert site_record.site_id == "example.com"


# --- BM25 Search Tests ---


class TestBM25Search:
    def test_basic_query(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        results = engine.search_blocks_bm25("machine learning", top_k=5)
        assert len(results) > 0
        # The heading and paragraph about ML should rank high
        top_ids = {r.block_id for r, _ in results[:3]}
        assert "b_001" in top_ids or "b_002" in top_ids

    def test_empty_query(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        results = engine.search_blocks_bm25("", top_k=5)
        assert results == []

    def test_stopword_only_query(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        results = engine.search_blocks_bm25("the a an is", top_k=5)
        assert results == []

    def test_no_match_query(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        results = engine.search_blocks_bm25("quantum entanglement", top_k=5)
        assert results == []

    def test_scores_are_positive(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        results = engine.search_blocks_bm25("neural networks", top_k=5)
        for _, score in results:
            assert score > 0

    def test_top_k_limit(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        results = engine.search_blocks_bm25("learning", top_k=2)
        assert len(results) <= 2

    def test_filter_by_block_type(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        results = engine.search_blocks_bm25(
            "tensorflow", top_k=10, filters={"block_type": "code"}
        )
        for record, _ in results:
            assert record.block_type == "code"

    def test_filter_by_block_type_list(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        results = engine.search_blocks_bm25(
            "tensorflow python", top_k=10, filters={"block_type": ["code", "table"]}
        )
        for record, _ in results:
            assert record.block_type in ("code", "table")

    def test_filter_by_min_importance(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        results = engine.search_blocks_bm25(
            "learning", top_k=10, filters={"min_importance": 0.7}
        )
        for record, _ in results:
            assert record.importance >= 0.7

    def test_filter_by_doc_id(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())
        engine.ingest(_second_doc())

        results = engine.search_blocks_bm25(
            "python programming", top_k=10, filters={"doc_id": "doc_002"}
        )
        for record, _ in results:
            assert record.doc_id == "doc_002"

    def test_action_bm25_search(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        results = engine.search_actions_bm25("search", top_k=5)
        assert len(results) > 0
        # "Search" action should match
        labels = {r.label for r, _ in results}
        assert "Search" in labels or "Search query input" in labels

    def test_multi_doc_search(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())
        engine.ingest(_second_doc())

        results = engine.search_blocks_bm25("python programming", top_k=10)
        assert len(results) > 0
        doc_ids = {r.doc_id for r, _ in results}
        assert "doc_002" in doc_ids


# --- Dense Search Tests ---


class TestDenseSearch:
    def test_cosine_similarity_identical(self) -> None:
        v = [1.0, 2.0, 3.0]
        assert abs(_cosine_similarity(v, v) - 1.0) < 1e-9

    def test_cosine_similarity_orthogonal(self) -> None:
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(_cosine_similarity(a, b)) < 1e-9

    def test_cosine_similarity_zero_vector(self) -> None:
        a = [0.0, 0.0, 0.0]
        b = [1.0, 2.0, 3.0]
        assert _cosine_similarity(a, b) == 0.0

    def test_cosine_similarity_different_lengths(self) -> None:
        a = [1.0, 2.0]
        b = [1.0, 2.0, 3.0]
        assert _cosine_similarity(a, b) == 0.0

    def test_cosine_similarity_empty(self) -> None:
        assert _cosine_similarity([], []) == 0.0

    def test_dense_search_with_embeddings(self) -> None:
        engine = IndexEngine()
        doc = _sample_doc()
        engine.ingest(doc)

        # Manually set embeddings on blocks (compound key: doc_id:block_id)
        engine._blocks["doc_001:b_001"].embedding = [1.0, 0.0, 0.0]
        engine._blocks["doc_001:b_002"].embedding = [0.9, 0.1, 0.0]
        engine._blocks["doc_001:b_003"].embedding = [0.0, 1.0, 0.0]

        results = engine.search_blocks_dense([1.0, 0.0, 0.0], top_k=3)
        assert len(results) > 0
        # b_001 should be the top result (exact match)
        assert results[0][0].block_id == "b_001"
        assert abs(results[0][1] - 1.0) < 1e-6

    def test_dense_search_no_embeddings(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        results = engine.search_blocks_dense([1.0, 0.0, 0.0], top_k=5)
        assert results == []

    def test_dense_action_search(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        engine._actions["doc_001:a_001"].embedding = [1.0, 0.0]
        engine._actions["doc_001:a_002"].embedding = [0.5, 0.5]

        results = engine.search_actions_dense([1.0, 0.0], top_k=2)
        assert len(results) > 0
        assert results[0][0].action_id == "a_001"


# --- Hybrid Search Tests ---


class TestHybridSearch:
    def test_hybrid_bm25_only(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        results = engine.search_blocks("machine learning", top_k=5)
        assert len(results) > 0

    def test_hybrid_with_embedding(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        # Set embeddings
        engine._blocks["doc_001:b_001"].embedding = [1.0, 0.0, 0.0]
        engine._blocks["doc_001:b_002"].embedding = [0.9, 0.1, 0.0]
        engine._blocks["doc_001:b_003"].embedding = [0.8, 0.2, 0.0]
        engine._blocks["doc_001:b_004"].embedding = [0.0, 0.0, 1.0]
        engine._blocks["doc_001:b_005"].embedding = [0.0, 1.0, 0.0]

        results = engine.search_blocks(
            "machine learning",
            query_embedding=[1.0, 0.0, 0.0],
            top_k=5,
            bm25_weight=0.5,
        )
        assert len(results) > 0

    def test_hybrid_weight_pure_bm25(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        engine._blocks["doc_001:b_001"].embedding = [1.0, 0.0, 0.0]
        engine._blocks["doc_001:b_002"].embedding = [0.0, 1.0, 0.0]

        results_bm25 = engine.search_blocks(
            "machine learning",
            query_embedding=[0.0, 1.0, 0.0],
            top_k=5,
            bm25_weight=1.0,
        )
        # With bm25_weight=1.0, dense shouldn't affect ranking
        assert len(results_bm25) > 0

    def test_hybrid_action_search(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        results = engine.search_actions("search query", top_k=3)
        assert len(results) > 0

    def test_hybrid_with_filters(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        results = engine.search_blocks(
            "tensorflow",
            top_k=5,
            filters={"block_type": "code"},
        )
        for record, _ in results:
            assert record.block_type == "code"


# --- Metadata Query Tests ---


class TestMetadataQueries:
    def test_get_document(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        assert engine.get_document("doc_001") is not None
        assert engine.get_document("nonexistent") is None

    def test_get_block(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        block = engine.get_block("b_001")
        assert block is not None
        assert block.block_id == "b_001"
        assert engine.get_block("nonexistent") is None

    def test_get_blocks_by_doc(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())
        engine.ingest(_second_doc())

        blocks = engine.get_blocks_by_doc("doc_001")
        assert len(blocks) == 5
        assert all(b.doc_id == "doc_001" for b in blocks)

        blocks2 = engine.get_blocks_by_doc("doc_002")
        assert len(blocks2) == 3

    def test_get_actions_by_doc(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        actions = engine.get_actions_by_doc("doc_001")
        assert len(actions) == 3

    def test_get_site(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        site = engine.get_site("example.com")
        assert site is not None
        assert site.site_id == "example.com"
        assert engine.get_site("nonexistent.com") is None

    def test_list_documents(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())
        engine.ingest(_second_doc())

        docs = engine.list_documents()
        assert len(docs) == 2

    def test_list_sites(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())
        engine.ingest(_second_doc())

        sites = engine.list_sites()
        assert len(sites) == 2


# --- Persistence Tests ---


class TestPersistence:
    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())
        engine.ingest(_second_doc())

        save_path = tmp_path / "index.json"
        engine.save(save_path)

        assert save_path.exists()

        engine2 = IndexEngine()
        engine2.load(save_path)

        assert engine2.stats == engine.stats
        assert engine2.get_document("doc_001") is not None
        assert engine2.get_document("doc_002") is not None
        assert len(engine2.get_blocks_by_doc("doc_001")) == 5
        assert len(engine2.get_actions_by_doc("doc_001")) == 3

    def test_save_load_preserves_search(self, tmp_path: Path) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        save_path = tmp_path / "index.json"
        engine.save(save_path)

        engine2 = IndexEngine()
        engine2.load(save_path)

        results = engine2.search_blocks_bm25("machine learning", top_k=5)
        assert len(results) > 0

    def test_load_nonexistent_raises(self) -> None:
        engine = IndexEngine()
        with pytest.raises(FileNotFoundError):
            engine.load("/nonexistent/path/index.json")

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        save_path = tmp_path / "subdir" / "deep" / "index.json"
        engine.save(save_path)
        assert save_path.exists()

    def test_save_load_valid_json(self, tmp_path: Path) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        save_path = tmp_path / "index.json"
        engine.save(save_path)

        data = json.loads(save_path.read_text())
        assert "version" in data
        assert "documents" in data
        assert "blocks" in data
        assert "actions" in data
        assert "sites" in data


# --- Incremental Update Tests ---


class TestIncrementalUpdates:
    def test_remove_document(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        assert engine.stats["documents"] == 1
        assert engine.stats["blocks"] == 5

        result = engine.remove("doc_001")
        assert result is True

        assert engine.stats["documents"] == 0
        assert engine.stats["blocks"] == 0
        assert engine.stats["actions"] == 0
        assert engine.stats["sites"] == 0

    def test_remove_nonexistent(self) -> None:
        engine = IndexEngine()
        result = engine.remove("nonexistent")
        assert result is False

    def test_remove_preserves_other_docs(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())
        engine.ingest(_second_doc())

        engine.remove("doc_001")

        assert engine.stats["documents"] == 1
        assert engine.get_document("doc_002") is not None
        assert len(engine.get_blocks_by_doc("doc_002")) == 3

    def test_update_document(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        # Update with modified doc
        updated = _make_doc(
            doc_id="doc_001",
            title="Updated Title",
            blocks=[_make_block("b_new", BlockType.PARAGRAPH, "Completely new content")],
            actions=[],
        )
        engine.update(updated)

        assert engine.stats["documents"] == 1
        assert engine.stats["blocks"] == 1
        dr = engine.get_document("doc_001")
        assert dr is not None
        assert dr.title == "Updated Title"

    def test_remove_updates_site_count(self) -> None:
        engine = IndexEngine()
        doc1 = _sample_doc()
        doc2 = _make_doc(
            doc_id="doc_002",
            source_url="https://example.com/other",
            blocks=[_make_block("b_201", BlockType.PARAGRAPH, "Other content")],
        )
        engine.ingest(doc1)
        engine.ingest(doc2)

        site = engine.get_site("example.com")
        assert site is not None
        assert site.doc_count == 2

        engine.remove("doc_001")
        site = engine.get_site("example.com")
        assert site is not None
        assert site.doc_count == 1

    def test_remove_last_doc_removes_site(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        engine.remove("doc_001")
        assert engine.get_site("example.com") is None

    def test_search_after_remove(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())
        engine.ingest(_second_doc())

        engine.remove("doc_001")

        results = engine.search_blocks_bm25("machine learning", top_k=5)
        for record, _ in results:
            assert record.doc_id != "doc_001"


# --- Stats Tests ---


class TestStats:
    def test_empty_stats(self) -> None:
        engine = IndexEngine()
        assert engine.stats == {
            "documents": 0,
            "blocks": 0,
            "actions": 0,
            "sites": 0,
        }

    def test_stats_after_ingest(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())
        stats = engine.stats
        assert stats["documents"] == 1
        assert stats["blocks"] == 5
        assert stats["actions"] == 3
        assert stats["sites"] == 1

    def test_stats_after_remove(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())
        engine.remove("doc_001")
        assert engine.stats == {
            "documents": 0,
            "blocks": 0,
            "actions": 0,
            "sites": 0,
        }


# --- Edge Cases ---


class TestEdgeCases:
    def test_empty_index_search(self) -> None:
        engine = IndexEngine()
        assert engine.search_blocks_bm25("anything", top_k=5) == []
        assert engine.search_blocks_dense([1.0, 0.0], top_k=5) == []
        assert engine.search_actions_bm25("anything", top_k=5) == []

    def test_duplicate_doc_overwrites(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())
        engine.ingest(_sample_doc())

        # Second ingest of same doc_id should overwrite
        assert engine.stats["documents"] == 1
        assert engine.stats["blocks"] == 5

    def test_doc_with_no_blocks(self) -> None:
        engine = IndexEngine()
        doc = _make_doc(blocks=[], actions=[])
        engine.ingest(doc)

        assert engine.stats["documents"] == 1
        assert engine.stats["blocks"] == 0

    def test_doc_with_no_actions(self) -> None:
        engine = IndexEngine()
        doc = _make_doc(
            blocks=[_make_block("b_1", text="Some content")],
            actions=[],
        )
        engine.ingest(doc)

        assert engine.stats["actions"] == 0

    def test_block_with_empty_text(self) -> None:
        engine = IndexEngine()
        doc = _make_doc(blocks=[_make_block("b_empty", text="")])
        engine.ingest(doc)

        results = engine.search_blocks_bm25("anything", top_k=5)
        # Empty text block should not match anything
        assert all(r.block_id != "b_empty" for r, _ in results)

    def test_very_long_query(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        long_query = "machine learning " * 100
        results = engine.search_blocks_bm25(long_query, top_k=5)
        # Should not crash
        assert isinstance(results, list)

    def test_special_characters_in_query(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        results = engine.search_blocks_bm25("machine-learning!@#$%", top_k=5)
        # Should still work (tokenizer handles special chars)
        assert isinstance(results, list)


# --- BM25 Score Function Tests ---


class TestBM25ScoreFunction:
    def test_bm25_score_basic(self) -> None:
        tf_map = {"machine": 2, "learning": 1}
        score = _bm25_score(
            query_tokens=["machine", "learning"],
            tf_map=tf_map,
            dl=10,
            avgdl=10.0,
            n=100,
            doc_freq={"machine": 10, "learning": 5},
        )
        assert score > 0

    def test_bm25_score_no_match(self) -> None:
        tf_map = {"machine": 2, "learning": 1}
        score = _bm25_score(
            query_tokens=["quantum"],
            tf_map=tf_map,
            dl=10,
            avgdl=10.0,
            n=100,
            doc_freq={"quantum": 3},
        )
        assert score == 0.0

    def test_bm25_score_zero_corpus(self) -> None:
        score = _bm25_score(
            query_tokens=["test"],
            tf_map={"test": 1},
            dl=5,
            avgdl=0.0,
            n=0,
            doc_freq={"test": 1},
        )
        assert score == 0.0

    def test_bm25_higher_tf_higher_score(self) -> None:
        """Document with higher term frequency should score higher."""
        high_tf = _bm25_score(
            query_tokens=["learning"],
            tf_map={"learning": 5},
            dl=10,
            avgdl=10.0,
            n=100,
            doc_freq={"learning": 10},
        )
        low_tf = _bm25_score(
            query_tokens=["learning"],
            tf_map={"learning": 1},
            dl=10,
            avgdl=10.0,
            n=100,
            doc_freq={"learning": 10},
        )
        assert high_tf > low_tf

    def test_bm25_rarer_term_higher_idf(self) -> None:
        """Rarer terms should contribute more to score."""
        rare = _bm25_score(
            query_tokens=["quantum"],
            tf_map={"quantum": 1},
            dl=10,
            avgdl=10.0,
            n=1000,
            doc_freq={"quantum": 2},
        )
        common = _bm25_score(
            query_tokens=["common"],
            tf_map={"common": 1},
            dl=10,
            avgdl=10.0,
            n=1000,
            doc_freq={"common": 500},
        )
        assert rare > common


# --- Ingestion Utility Tests ---


class TestIngestionUtilities:
    def test_keywords_extracted(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        block = engine.get_block("b_002")
        assert block is not None
        assert len(block.keywords) > 0
        assert "machine" in block.keywords or "learning" in block.keywords

    def test_evidence_score_table_higher(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        table_block = engine.get_block("b_005")
        para_block = engine.get_block("b_002")
        assert table_block is not None
        assert para_block is not None
        assert table_block.evidence_score > para_block.evidence_score

    def test_summary_built(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        dr = engine.get_document("doc_001")
        assert dr is not None
        assert len(dr.summary) > 0

    def test_section_path_preserved(self) -> None:
        engine = IndexEngine()
        engine.ingest(_sample_doc())

        block = engine.get_block("b_002")
        assert block is not None
        assert block.section_path == ["Introduction to Machine Learning"]
