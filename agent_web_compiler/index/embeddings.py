"""Pluggable embedding providers for semantic search.

Built-in:
- TFIDFEmbedder: Sparse TF-IDF vectors (no external deps, works offline)
- CallableEmbedder: Wraps any function(text) -> list[float]

Optional (requires extra deps):
- Users can bring their own embedding function

Usage:
    from agent_web_compiler.index.embeddings import TFIDFEmbedder

    embedder = TFIDFEmbedder()
    embedder.fit(["text1", "text2", "text3"])  # Build vocabulary
    vec = embedder.embed("search query")
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Callable
from typing import Protocol, runtime_checkable

_TOKEN_RE = re.compile(r"[a-z0-9]+")


@runtime_checkable
class Embedder(Protocol):
    """Protocol for embedding providers."""

    def embed(self, text: str) -> list[float]:
        """Embed a single text into a dense vector."""
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts. Default: call embed() in a loop."""
        ...


class TFIDFEmbedder:
    """TF-IDF based embedder -- works offline, no external dependencies.

    Builds a vocabulary from training texts, then represents each text
    as a TF-IDF vector in that vocabulary space. Vectors are normalized
    to unit length for cosine similarity compatibility.
    """

    def __init__(self, max_features: int = 500, min_df: int = 1) -> None:
        """Initialize with vocabulary size limit.

        Args:
            max_features: Maximum number of terms in the vocabulary.
            min_df: Minimum document frequency for a term to be included.
        """
        self.max_features = max_features
        self.min_df = min_df
        self._vocabulary: dict[str, int] = {}
        self._idf: dict[str, float] = {}
        self._fitted = False

    def fit(self, texts: list[str]) -> TFIDFEmbedder:
        """Build vocabulary and IDF from training texts.

        Args:
            texts: List of training documents.

        Returns:
            self, for method chaining.

        Raises:
            ValueError: If texts is empty.
        """
        if not texts:
            raise ValueError("Cannot fit on empty text list.")

        n_docs = len(texts)

        # Tokenize all texts and compute document frequency
        doc_freq: Counter[str] = Counter()
        for text in texts:
            tokens = set(self._tokenize(text))
            for token in tokens:
                doc_freq[token] += 1

        # Filter by min_df and select top max_features by document frequency
        eligible = [
            (term, df)
            for term, df in doc_freq.items()
            if df >= self.min_df
        ]
        # Sort by df descending, then alphabetically for stability
        eligible.sort(key=lambda x: (-x[1], x[0]))
        selected = eligible[: self.max_features]

        # Build vocabulary mapping: term -> index
        self._vocabulary = {term: idx for idx, (term, _) in enumerate(selected)}

        # Compute IDF = log(N / (1 + df))
        self._idf = {
            term: math.log(n_docs / (1 + df))
            for term, df in selected
        }

        self._fitted = True
        return self

    def embed(self, text: str) -> list[float]:
        """Embed text as a normalized TF-IDF vector.

        Args:
            text: Text to embed.

        Returns:
            A list of floats with length equal to vocabulary size.

        Raises:
            RuntimeError: If fit() has not been called.
        """
        if not self._fitted:
            raise RuntimeError(
                "TFIDFEmbedder has not been fitted. Call fit() first."
            )

        dim = len(self._vocabulary)
        if dim == 0:
            return []

        # Tokenize and compute term frequency
        tokens = self._tokenize(text)
        tf = Counter(tokens)

        # Build TF-IDF vector
        vector = [0.0] * dim
        for term, count in tf.items():
            if term in self._vocabulary:
                idx = self._vocabulary[term]
                idf = self._idf.get(term, 0.0)
                vector[idx] = count * idf

        # L2 normalize
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0.0:
            vector = [v / norm for v in vector]

        return vector

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts.

        Args:
            texts: List of texts to embed.

        Returns:
            A list of embedding vectors.
        """
        return [self.embed(t) for t in texts]

    @property
    def dim(self) -> int:
        """Embedding dimension (vocabulary size)."""
        return len(self._vocabulary)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Tokenize text: lowercase, split on non-alphanumeric."""
        return _TOKEN_RE.findall(text.lower())


class CallableEmbedder:
    """Wraps any callable(text) -> list[float] as an Embedder.

    Usage:
        # With OpenAI
        import openai
        client = openai.Client()
        embedder = CallableEmbedder(
            lambda text: client.embeddings.create(
                model="text-embedding-3-small", input=text
            ).data[0].embedding
        )

        # With sentence-transformers
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        embedder = CallableEmbedder(lambda text: model.encode(text).tolist())
    """

    def __init__(
        self,
        embed_fn: Callable[[str], list[float]],
        batch_fn: Callable[[list[str]], list[list[float]]] | None = None,
    ) -> None:
        """Initialize with embedding function.

        Args:
            embed_fn: A callable that takes a string and returns a list of floats.
            batch_fn: Optional batch embedding function. If not provided,
                embed_fn is called in a loop.
        """
        self._embed_fn = embed_fn
        self._batch_fn = batch_fn

    def embed(self, text: str) -> list[float]:
        """Embed a single text.

        Args:
            text: Text to embed.

        Returns:
            A list of floats representing the embedding.
        """
        return self._embed_fn(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts.

        Args:
            texts: List of texts to embed.

        Returns:
            A list of embedding vectors.
        """
        if self._batch_fn is not None:
            return self._batch_fn(texts)
        return [self._embed_fn(t) for t in texts]
