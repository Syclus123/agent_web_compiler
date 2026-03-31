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

from typing import TYPE_CHECKING, Any

from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.core.document import AgentDocument
from agent_web_compiler.index import IndexEngine
from agent_web_compiler.index.embeddings import Embedder
from agent_web_compiler.search.action_runtime import ActionRuntime, ExecutionPlan

if TYPE_CHECKING:
    from agent_web_compiler.sources.crawler import CrawlResult

from agent_web_compiler.search.grounded_answer import GroundedAnswer, GroundedAnswerer
from agent_web_compiler.search.retriever import Retriever, SearchResponse, SearchResult


class AgentSearch:
    """High-level search SDK that combines compile + index + search + answer.

    Provides a unified API over the compilation pipeline, index engine,
    retriever, grounded answerer, and action runtime. Manages a single
    in-memory index that can be persisted to disk.

    If an ``embedder`` is provided, ingested blocks and actions will have
    their embeddings computed automatically, and search queries will be
    embedded for hybrid (BM25 + dense) retrieval.
    """

    def __init__(
        self,
        config: CompileConfig | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        self.config = config or CompileConfig()
        self._embedder = embedder
        self._engine = IndexEngine()
        self._retriever = Retriever(self._engine)
        self._answerer = GroundedAnswerer(self._retriever)
        self._runtime = ActionRuntime(self._retriever)

    # --- Ingestion ---

    def ingest(self, doc: AgentDocument) -> None:
        """Ingest a pre-compiled AgentDocument into the index.

        If an embedder is configured, block and action embeddings are
        computed before insertion so that hybrid retrieval is available.
        """
        if self._embedder is not None:
            self._embed_document(doc)
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
        from agent_web_compiler.pipeline.compiler import HTMLCompiler

        doc = HTMLCompiler().compile(html, source_url=source_url, config=self.config)
        self.ingest(doc)
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
        from agent_web_compiler.sources.http_fetcher import HTTPFetcher

        fetcher = HTTPFetcher()
        result = fetcher.fetch_sync(url, self.config)
        content = result.content if isinstance(result.content, str) else result.content.decode("utf-8")
        doc = self.ingest_html(content, source_url=url)
        return doc

    def crawl_site(
        self,
        seed_url: str,
        max_pages: int = 50,
        delay_seconds: float = 0.5,
        max_depth: int = 3,
    ) -> CrawlResult:
        """Crawl a site and ingest all discovered pages into the index.

        Starts from seed_url, discovers links via BFS, compiles each page,
        and adds it to the search index. Stays within the same domain.

        Args:
            seed_url: Starting URL. The crawler stays on this domain.
            max_pages: Maximum number of pages to crawl.
            delay_seconds: Politeness delay between requests.
            max_depth: Maximum link depth from the seed URL.

        Returns:
            A CrawlResult with crawl statistics and any errors.
        """
        from agent_web_compiler.sources.crawler import CrawlConfig, SiteCrawler

        crawl_config = CrawlConfig(
            max_pages=max_pages,
            delay_seconds=delay_seconds,
            max_depth=max_depth,
        )
        crawler = SiteCrawler(config=crawl_config)
        return crawler.crawl(seed_url, search=self)

    def ingest_file(self, path: str) -> AgentDocument:
        """Compile a file and ingest into the index.

        Args:
            path: Path to the file (HTML, PDF, DOCX, JSON).

        Returns:
            The compiled AgentDocument.

        Raises:
            CompilerError: If compilation fails.
        """
        from agent_web_compiler.sources.file_reader import FileReader

        reader = FileReader()
        result = reader.read(path)

        if result.content_type == "application/pdf":
            from agent_web_compiler.pipeline.pdf_compiler import PDFCompiler

            doc = PDFCompiler().compile(result.content, source_file=path, config=self.config)
        elif result.content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            from agent_web_compiler.pipeline.docx_compiler import DOCXCompiler

            doc = DOCXCompiler().compile(result.content, source_file=path, config=self.config)
        else:
            content = result.content if isinstance(result.content, str) else result.content.decode("utf-8")
            doc = self.ingest_html(content)
            doc.source_file = str(path)
            return doc  # already ingested by ingest_html

        self.ingest(doc)
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
        if self._embedder is not None and "query_embedding" not in kwargs:
            kwargs["query_embedding"] = self._embedder.embed(query)
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
        if self._embedder is not None and "query_embedding" not in kwargs:
            kwargs["query_embedding"] = self._embedder.embed(query)
        return self._retriever.search_blocks(query, top_k=top_k, **kwargs)

    def search_actions(
        self, query: str, top_k: int = 10, **kwargs: Any
    ) -> list[SearchResult]:
        """Search for executable actions only.

        Args:
            query: Natural-language search query.
            top_k: Maximum number of results.
            **kwargs: Passed through to Retriever.search_actions().

        Returns:
            A list of SearchResult objects for matching actions.
        """
        if self._embedder is not None and "query_embedding" not in kwargs:
            kwargs["query_embedding"] = self._embedder.embed(query)
        return self._retriever.search_actions(query, top_k=top_k, **kwargs)

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

    # --- Private helpers ---

    def _embed_document(self, doc: AgentDocument) -> None:
        """Compute and attach embeddings for blocks and actions in a document.

        Called automatically during ingest when an embedder is configured.
        Stores embeddings so the ingestion layer can populate index records.

        Block embeddings are stored in ``block.metadata["_embedding"]``.
        Action embeddings are stored as a private ``_embedding`` attribute
        via ``object.__setattr__`` (Actions are Pydantic models without a
        metadata dict).
        """
        if self._embedder is None:
            return

        # Embed blocks
        block_texts = [block.text or "" for block in doc.blocks]
        if block_texts:
            embeddings = self._embedder.embed_batch(block_texts)
            for block, emb in zip(doc.blocks, embeddings):
                block.metadata["_embedding"] = emb

        # Embed actions
        action_texts = [action.label or "" for action in doc.actions]
        if action_texts:
            embeddings = self._embedder.embed_batch(action_texts)
            for action, emb in zip(doc.actions, embeddings):
                object.__setattr__(action, "_embedding", emb)
