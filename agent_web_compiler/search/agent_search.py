"""AgentSearch — the unified high-level SDK.

This is the primary entry point for the search capabilities.
Combines compilation, indexing, retrieval, answering, and action planning
into a single coherent API.

Usage:
    from agent_web_compiler.search import AgentSearch

    search = AgentSearch()

    # Index some content
    search.ingest_url("https://docs.example.com/api")
    search.ingest_file("report.pdf")

    # Search for content
    results = search.search("What is the rate limit?")

    # Get grounded answers
    answer = search.answer("What authentication methods are supported?")
    print(answer.to_markdown())

    # Plan and execute tasks
    plan = search.plan("Download the enterprise pricing PDF")
    print(plan.to_markdown())

    # Save/load index
    search.save("my_index.json")
    search.load("my_index.json")
"""

from __future__ import annotations

from typing import Any

from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.core.document import AgentDocument
from agent_web_compiler.index import IndexEngine
from agent_web_compiler.search.action_runtime import ActionRuntime, ExecutionPlan
from agent_web_compiler.search.grounded_answer import GroundedAnswer, GroundedAnswerer
from agent_web_compiler.search.retriever import Retriever, SearchResponse, SearchResult


class AgentSearch:
    """High-level search SDK that combines compile + index + search + answer.

    Provides a unified API over the compilation pipeline, index engine,
    retriever, grounded answerer, and action runtime. Manages a single
    in-memory index that can be persisted to disk.
    """

    def __init__(self, config: CompileConfig | None = None) -> None:
        self.config = config or CompileConfig()
        self._engine = IndexEngine()
        self._retriever = Retriever(self._engine)
        self._answerer = GroundedAnswerer(self._retriever)
        self._runtime = ActionRuntime(self._retriever)

    # --- Ingestion ---

    def ingest(self, doc: AgentDocument) -> None:
        """Ingest a pre-compiled AgentDocument into the index."""
        self._engine.ingest(doc)

    def ingest_html(
        self, html: str, source_url: str | None = None
    ) -> AgentDocument:
        """Compile HTML and ingest into the index.

        Args:
            html: Raw HTML string.
            source_url: Optional source URL for provenance.

        Returns:
            The compiled AgentDocument.
        """
        from agent_web_compiler.api.compile import compile_html

        doc = compile_html(html, source_url=source_url, config=self.config)
        self._engine.ingest(doc)
        return doc

    def ingest_url(self, url: str) -> AgentDocument:
        """Fetch, compile, and ingest a URL.

        Args:
            url: URL to fetch and compile.

        Returns:
            The compiled AgentDocument.

        Raises:
            FetchError: If the URL cannot be fetched.
            CompilerError: If compilation fails.
        """
        from agent_web_compiler.api.compile import compile_url

        doc = compile_url(url, config=self.config)
        self._engine.ingest(doc)
        return doc

    def ingest_file(self, path: str) -> AgentDocument:
        """Compile a file and ingest into the index.

        Args:
            path: Path to the file (HTML, PDF, DOCX, JSON).

        Returns:
            The compiled AgentDocument.

        Raises:
            CompilerError: If compilation fails.
        """
        from agent_web_compiler.api.compile import compile_file

        doc = compile_file(path, config=self.config)
        self._engine.ingest(doc)
        return doc

    # --- Search ---

    def search(self, query: str, top_k: int = 10, **kwargs: Any) -> SearchResponse:
        """Search for relevant blocks and actions.

        Args:
            query: Natural-language search query.
            top_k: Maximum number of results to return.
            **kwargs: Passed through to Retriever.search().

        Returns:
            A SearchResponse with ranked results and metadata.
        """
        return self._retriever.search(query, top_k=top_k, **kwargs)

    def search_blocks(
        self, query: str, top_k: int = 10, **kwargs: Any
    ) -> list[SearchResult]:
        """Search for content blocks only.

        Args:
            query: Natural-language search query.
            top_k: Maximum number of results.
            **kwargs: Passed through to Retriever.search_blocks().

        Returns:
            A list of SearchResult objects for matching blocks.
        """
        return self._retriever.search_blocks(query, top_k=top_k, **kwargs)

    def search_actions(
        self, query: str, top_k: int = 10
    ) -> list[SearchResult]:
        """Search for executable actions only.

        Args:
            query: Natural-language search query.
            top_k: Maximum number of results.

        Returns:
            A list of SearchResult objects for matching actions.
        """
        return self._retriever.search_actions(query, top_k=top_k)

    # --- Answering ---

    def answer(self, query: str, top_k: int = 5, **kwargs: Any) -> GroundedAnswer:
        """Search and compose a grounded answer with citations.

        Args:
            query: Natural-language question.
            top_k: Maximum number of evidence results.
            **kwargs: Passed through to GroundedAnswerer.answer().

        Returns:
            A GroundedAnswer with citations and confidence.
        """
        return self._answerer.answer(query, top_k=top_k, **kwargs)

    # --- Planning ---

    def plan(self, query: str) -> ExecutionPlan:
        """Generate an execution plan for a task query.

        Args:
            query: Natural-language task description.

        Returns:
            An ExecutionPlan with ordered browser automation steps.
        """
        return self._runtime.plan_task(query)

    # --- Index Management ---

    def save(self, path: str) -> None:
        """Persist the index to disk.

        Args:
            path: File path for the index JSON file.
        """
        self._engine.save(path)

    def load(self, path: str) -> None:
        """Load the index from disk.

        Args:
            path: File path of the index JSON file.

        Raises:
            FileNotFoundError: If the index file does not exist.
        """
        self._engine.load(path)

    @property
    def stats(self) -> dict[str, int]:
        """Return index statistics.

        Returns:
            Dict with counts: documents, blocks, actions, sites.
        """
        return self._engine.stats
