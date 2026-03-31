"""Tests for the pluggable embedding system."""

from __future__ import annotations

import math

import pytest

from agent_web_compiler.index.embeddings import (
    CallableEmbedder,
    Embedder,
    TFIDFEmbedder,
)

# ---------------------------------------------------------------------------
# TFIDFEmbedder
# ---------------------------------------------------------------------------


class TestTFIDFEmbedderFit:
    """Tests for TFIDFEmbedder.fit()."""

    def test_fit_builds_vocabulary(self) -> None:
        embedder = TFIDFEmbedder(max_features=100)
        embedder.fit(["hello world", "world foo bar"])
        assert embedder._fitted is True
        assert embedder.dim > 0

    def test_fit_returns_self(self) -> None:
        embedder = TFIDFEmbedder()
        result = embedder.fit(["hello world"])
        assert result is embedder

    def test_fit_empty_raises(self) -> None:
        embedder = TFIDFEmbedder()
        with pytest.raises(ValueError, match="empty"):
            embedder.fit([])

    def test_fit_respects_max_features(self) -> None:
        texts = ["alpha bravo charlie delta echo foxtrot golf hotel"]
        embedder = TFIDFEmbedder(max_features=3)
        embedder.fit(texts)
        assert embedder.dim <= 3

    def test_fit_respects_min_df(self) -> None:
        texts = ["hello world", "hello foo", "bar baz"]
        # "hello" appears in 2 docs, others in 1
        embedder = TFIDFEmbedder(min_df=2)
        embedder.fit(texts)
        assert "hello" in embedder._vocabulary
        # words appearing in only 1 doc should be excluded
        assert "baz" not in embedder._vocabulary


class TestTFIDFEmbedderEmbed:
    """Tests for TFIDFEmbedder.embed()."""

    def test_embed_before_fit_raises(self) -> None:
        embedder = TFIDFEmbedder()
        with pytest.raises(RuntimeError, match="fitted"):
            embedder.embed("hello")

    def test_embed_returns_correct_dim(self) -> None:
        embedder = TFIDFEmbedder(max_features=50)
        embedder.fit(["hello world", "world foo", "foo bar baz"])
        vec = embedder.embed("hello world")
        assert len(vec) == embedder.dim

    def test_embed_is_normalized(self) -> None:
        embedder = TFIDFEmbedder()
        embedder.fit(["hello world test", "foo bar baz", "hello foo test"])
        vec = embedder.embed("hello world test")

        norm = math.sqrt(sum(v * v for v in vec))
        # Should be unit length (or zero if all-zero)
        if norm > 0:
            assert abs(norm - 1.0) < 1e-6

    def test_embed_zero_vector_for_unknown_terms(self) -> None:
        embedder = TFIDFEmbedder()
        embedder.fit(["hello world", "foo bar"])
        vec = embedder.embed("zzzzz qqqqq")
        assert all(v == 0.0 for v in vec)

    def test_embed_zero_vector_is_not_normalized(self) -> None:
        """Zero vector should remain zero, not cause division by zero."""
        embedder = TFIDFEmbedder()
        embedder.fit(["hello world"])
        vec = embedder.embed("zzzzz qqqqq")
        assert all(v == 0.0 for v in vec)

    def test_same_text_gives_same_embedding(self) -> None:
        embedder = TFIDFEmbedder()
        embedder.fit(["hello world", "foo bar"])
        v1 = embedder.embed("hello world")
        v2 = embedder.embed("hello world")
        assert v1 == v2

    def test_similar_texts_have_higher_similarity(self) -> None:
        embedder = TFIDFEmbedder()
        corpus = [
            "python programming language software development",
            "java programming language software engineering",
            "ruby programming language web development",
            "cooking recipes kitchen food ingredients meals",
            "baking desserts cakes pastry flour sugar",
            "gardening plants flowers soil water sunshine",
        ]
        embedder.fit(corpus)

        v_python = embedder.embed("python programming language software")
        v_java = embedder.embed("java programming language software")
        v_cooking = embedder.embed("cooking recipes kitchen food")

        sim_related = _cosine_sim(v_python, v_java)
        sim_unrelated = _cosine_sim(v_python, v_cooking)

        # Programming languages share more terms than programming vs cooking
        assert sim_related >= sim_unrelated

        assert sim_related > sim_unrelated


class TestTFIDFEmbedderBatch:
    """Tests for TFIDFEmbedder.embed_batch()."""

    def test_embed_batch_returns_list(self) -> None:
        embedder = TFIDFEmbedder()
        embedder.fit(["hello world", "foo bar"])
        results = embedder.embed_batch(["hello", "foo"])
        assert len(results) == 2
        assert all(isinstance(r, list) for r in results)

    def test_embed_batch_matches_individual(self) -> None:
        embedder = TFIDFEmbedder()
        embedder.fit(["hello world", "foo bar"])
        batch = embedder.embed_batch(["hello world", "foo bar"])
        individual = [embedder.embed("hello world"), embedder.embed("foo bar")]
        assert batch == individual

    def test_embed_batch_empty(self) -> None:
        embedder = TFIDFEmbedder()
        embedder.fit(["hello"])
        results = embedder.embed_batch([])
        assert results == []


class TestTFIDFEmbedderDim:
    """Tests for TFIDFEmbedder.dim property."""

    def test_dim_before_fit(self) -> None:
        embedder = TFIDFEmbedder()
        assert embedder.dim == 0

    def test_dim_after_fit(self) -> None:
        embedder = TFIDFEmbedder(max_features=10)
        embedder.fit(["alpha bravo charlie"])
        assert embedder.dim > 0
        assert embedder.dim <= 10


# ---------------------------------------------------------------------------
# CallableEmbedder
# ---------------------------------------------------------------------------


class TestCallableEmbedder:
    """Tests for CallableEmbedder."""

    def test_embed_delegates_to_fn(self) -> None:
        called_with: list[str] = []

        def fake_embed(text: str) -> list[float]:
            called_with.append(text)
            return [1.0, 2.0, 3.0]

        embedder = CallableEmbedder(fake_embed)
        result = embedder.embed("hello")
        assert result == [1.0, 2.0, 3.0]
        assert called_with == ["hello"]

    def test_embed_batch_uses_embed_fn_by_default(self) -> None:
        calls: list[str] = []

        def fake_embed(text: str) -> list[float]:
            calls.append(text)
            return [float(len(text))]

        embedder = CallableEmbedder(fake_embed)
        results = embedder.embed_batch(["hi", "hello"])
        assert len(results) == 2
        assert calls == ["hi", "hello"]

    def test_embed_batch_uses_batch_fn_when_provided(self) -> None:
        embed_calls: list[str] = []
        batch_calls: list[list[str]] = []

        def fake_embed(text: str) -> list[float]:
            embed_calls.append(text)
            return [1.0]

        def fake_batch(texts: list[str]) -> list[list[float]]:
            batch_calls.append(texts)
            return [[float(len(t))] for t in texts]

        embedder = CallableEmbedder(fake_embed, batch_fn=fake_batch)
        results = embedder.embed_batch(["hi", "hello"])
        assert len(results) == 2
        assert embed_calls == []  # embed_fn should NOT have been called
        assert len(batch_calls) == 1


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


class TestEmbedderProtocol:
    """Tests that both embedders satisfy the Embedder protocol."""

    def test_tfidf_is_embedder(self) -> None:
        embedder = TFIDFEmbedder()
        assert isinstance(embedder, Embedder)

    def test_callable_is_embedder(self) -> None:
        embedder = CallableEmbedder(lambda t: [0.0])
        assert isinstance(embedder, Embedder)

    def test_custom_class_satisfies_protocol(self) -> None:
        class MyEmbedder:
            def embed(self, text: str) -> list[float]:
                return [0.0]

            def embed_batch(self, texts: list[str]) -> list[list[float]]:
                return [[0.0] for _ in texts]

        assert isinstance(MyEmbedder(), Embedder)

    def test_non_embedder_fails_protocol(self) -> None:
        class NotAnEmbedder:
            pass

        assert not isinstance(NotAnEmbedder(), Embedder)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cosine_sim(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
