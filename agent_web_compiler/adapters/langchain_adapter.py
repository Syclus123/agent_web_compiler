"""Adapter for LangChain/LlamaIndex.

Provides a Tool wrapper and Document loader for LangChain agents.
No hard dependency on langchain — works via duck typing.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from agent_web_compiler.core.block import Block
from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.core.document import AgentDocument


class AWCTool:
    """LangChain-compatible Tool that compiles URLs into AgentDocuments.

    Works with LangChain agents without requiring langchain as a dependency.
    Implements the Tool protocol via duck typing: ``name``, ``description``,
    ``_run``, and ``_arun``.

    Usage::

        from agent_web_compiler.adapters.langchain_adapter import AWCTool

        tool = AWCTool()
        # Pass to a LangChain agent as a tool
        agent = initialize_agent(tools=[tool], ...)
    """

    name: str = "web_compiler"
    description: str = (
        "Compile a webpage into structured semantic blocks with actions, "
        "provenance, and metadata. Input: a URL string. "
        "Output: structured page content as text."
    )

    def __init__(
        self,
        config: CompileConfig | None = None,
        output_format: str = "markdown",
    ) -> None:
        """
        Args:
            config: Compilation config.  Uses defaults when ``None``.
            output_format: How to render the result — ``"markdown"``
                (summary) or ``"json"`` (full serialisation).
        """
        self.config = config or CompileConfig()
        self.output_format = output_format

    def _run(self, url: str) -> str:
        """Synchronously compile a URL.  Called by LangChain agents."""
        from agent_web_compiler.api.compile import compile_url

        doc = compile_url(url, config=self.config)
        return self._format(doc)

    async def _arun(self, url: str) -> str:
        """Async compile — delegates to sync for now."""
        return self._run(url)

    # ── formatting ───────────────────────────────────────────────────

    def _format(self, doc: AgentDocument) -> str:
        if self.output_format == "json":
            return doc.model_dump_json(indent=2)
        return doc.summary_markdown()


class AWCDocumentLoader:
    """LangChain-compatible DocumentLoader that produces structured documents.

    Each :class:`Block` becomes a document dict (mimicking LangChain's
    ``Document(page_content=..., metadata=...)``) with metadata including
    block type, importance, section path, and provenance.

    Usage::

        loader = AWCDocumentLoader()
        docs = loader.load("https://example.com")
    """

    def __init__(self, config: CompileConfig | None = None) -> None:
        self.config = config or CompileConfig()

    def load(self, source: str) -> list[dict[str, Any]]:
        """Load and compile *source* (URL or HTML), returning all blocks.

        Returns a list of dicts with ``page_content`` and ``metadata`` keys,
        matching the LangChain Document shape.
        """
        return list(self.lazy_load(source))

    def lazy_load(self, source: str) -> Generator[dict[str, Any], None, None]:
        """Lazily yield one document dict per block."""
        doc = self._compile(source)
        for block in doc.blocks:
            yield self._block_to_document(block, doc)

    # ── private ──────────────────────────────────────────────────────

    def _compile(self, source: str) -> AgentDocument:
        """Compile a source string (URL or raw HTML)."""
        if source.startswith(("http://", "https://")):
            from agent_web_compiler.api.compile import compile_url
            return compile_url(source, config=self.config)
        else:
            from agent_web_compiler.api.compile import compile_html
            return compile_html(source, config=self.config)

    @staticmethod
    def _block_to_document(block: Block, doc: AgentDocument) -> dict[str, Any]:
        """Convert a Block to a LangChain-compatible Document dict."""
        metadata: dict[str, Any] = {
            "block_id": block.id,
            "block_type": block.type.value,
            "importance": block.importance,
            "order": block.order,
            "section_path": block.section_path,
            "source_url": doc.source_url,
            "doc_id": doc.doc_id,
        }
        if block.level is not None:
            metadata["level"] = block.level
        if block.provenance is not None:
            metadata["provenance_type"] = block.provenance.type

        return {
            "page_content": block.text,
            "metadata": metadata,
        }
