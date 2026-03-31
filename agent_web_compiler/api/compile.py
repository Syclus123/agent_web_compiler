"""Public compile functions — the main entry points for agent-web-compiler.

Usage:
    from agent_web_compiler import compile_url, compile_html

    # Compile a URL
    doc = compile_url("https://example.com")

    # Compile raw HTML
    doc = compile_html("<html><body><h1>Hello</h1><p>World</p></body></html>")
"""

from __future__ import annotations

import json as _json

from agent_web_compiler.api.batch import BatchResult
from agent_web_compiler.core.config import CompileConfig, CompileMode, RenderMode
from agent_web_compiler.core.document import AgentDocument
from agent_web_compiler.core.errors import FetchError


def _looks_like_json(content: str) -> bool:
    """Heuristic check: does the content look like a JSON response?"""
    stripped = content.lstrip()
    return stripped.startswith("{") or stripped.startswith("[")


def compile_json(
    content: str | dict,
    *,
    source_url: str | None = None,
    mode: str = "balanced",
    include_actions: bool = True,
    debug: bool = False,
    config: CompileConfig | None = None,
) -> AgentDocument:
    """Compile a JSON API response into an AgentDocument.

    Args:
        content: JSON string or already-parsed dict.
        source_url: Optional URL of the API endpoint.
        mode: Compilation mode.
        include_actions: Whether to extract action affordances.
        debug: Whether to include debug metadata.
        config: Full config object (overrides individual params if provided).

    Returns:
        An AgentDocument with semantic blocks representing the API response.

    Raises:
        ParseError: If content is an invalid JSON string.
    """
    if config is None:
        config = CompileConfig(
            mode=CompileMode(mode),
            include_actions=include_actions,
            debug=debug,
        )

    from agent_web_compiler.pipeline.api_compiler import APICompiler

    compiler = APICompiler()
    return compiler.compile(content, source_url=source_url, config=config)


def compile_html(
    html: str,
    *,
    source_url: str | None = None,
    mode: str = "balanced",
    include_actions: bool = True,
    include_provenance: bool = True,
    debug: bool = False,
    config: CompileConfig | None = None,
) -> AgentDocument:
    """Compile raw HTML into an AgentDocument.

    Args:
        html: Raw HTML string to compile.
        source_url: Optional URL of the source (for provenance).
        mode: Compilation mode — "fast", "balanced", or "high_recall".
        include_actions: Whether to extract action affordances.
        include_provenance: Whether to include provenance tracking.
        debug: Whether to include debug metadata.
        config: Full config object (overrides individual params if provided).

    Returns:
        An AgentDocument with semantic blocks, actions, and provenance.

    Raises:
        CompilerError: If compilation fails.
    """
    if config is None:
        config = CompileConfig(
            mode=CompileMode(mode),
            include_actions=include_actions,
            include_provenance=include_provenance,
            debug=debug,
        )

    # Detect JSON content and route to API compiler
    if _looks_like_json(html):
        try:
            _json.loads(html)
            return compile_json(html, source_url=source_url, config=config)
        except (ValueError, TypeError):
            pass  # Not valid JSON, treat as HTML

    from agent_web_compiler.pipeline.compiler import HTMLCompiler

    compiler = HTMLCompiler()
    return compiler.compile(html, source_url=source_url, config=config)


def compile_url(
    url: str,
    *,
    mode: str = "balanced",
    render: str = "off",
    include_actions: bool = True,
    include_provenance: bool = True,
    debug: bool = False,
    timeout: float = 30.0,
    config: CompileConfig | None = None,
) -> AgentDocument:
    """Fetch a URL and compile it into an AgentDocument.

    Args:
        url: URL to fetch and compile.
        mode: Compilation mode — "fast", "balanced", or "high_recall".
        render: Render mode — "off", "auto", or "always".
        include_actions: Whether to extract action affordances.
        include_provenance: Whether to include provenance tracking.
        debug: Whether to include debug metadata.
        timeout: HTTP fetch timeout in seconds.
        config: Full config object (overrides individual params if provided).

    Returns:
        An AgentDocument with semantic blocks, actions, and provenance.

    Raises:
        FetchError: If the URL cannot be fetched.
        CompilerError: If compilation fails.
    """
    if config is None:
        config = CompileConfig(
            mode=CompileMode(mode),
            render=RenderMode(render),
            include_actions=include_actions,
            include_provenance=include_provenance,
            debug=debug,
            timeout_seconds=timeout,
        )

    from agent_web_compiler.sources.http_fetcher import HTTPFetcher

    fetcher = HTTPFetcher()
    result = fetcher.fetch_sync(url, config)

    if not isinstance(result.content, str):
        raise FetchError(
            f"Expected text content from {url}, got bytes",
            context={"url": url, "content_type": result.content_type},
        )

    return compile_html(
        result.content,
        source_url=url,
        config=config,
    )


def compile_file(
    path: str,
    *,
    mode: str = "balanced",
    include_actions: bool = True,
    include_provenance: bool = True,
    debug: bool = False,
    config: CompileConfig | None = None,
) -> AgentDocument:
    """Compile a local file (HTML or PDF) into an AgentDocument.

    Args:
        path: Path to the file.
        mode: Compilation mode.
        include_actions: Whether to extract action affordances.
        include_provenance: Whether to include provenance tracking.
        debug: Whether to include debug metadata.
        config: Full config object.

    Returns:
        An AgentDocument.

    Raises:
        CompilerError: If compilation fails.
    """
    if config is None:
        config = CompileConfig(
            mode=CompileMode(mode),
            include_actions=include_actions,
            include_provenance=include_provenance,
            debug=debug,
        )

    from agent_web_compiler.sources.file_reader import FileReader

    reader = FileReader()
    result = reader.read(path)

    if result.content_type == "application/pdf":
        from agent_web_compiler.pipeline.pdf_compiler import PDFCompiler

        compiler = PDFCompiler()
        return compiler.compile(result.content, source_file=path, config=config)

    if result.content_type == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ):
        from agent_web_compiler.pipeline.docx_compiler import DOCXCompiler

        compiler_docx = DOCXCompiler()
        content_bytes = (
            result.content
            if isinstance(result.content, bytes)
            else result.content.encode("utf-8")
        )
        return compiler_docx.compile(content_bytes, source_file=path, config=config)

    if result.content_type == "application/json":
        content_str = result.content if isinstance(result.content, str) else result.content.decode("utf-8")
        return compile_json(content_str, source_url=None, config=config)

    # Default: treat as HTML
    content = result.content if isinstance(result.content, str) else result.content.decode("utf-8")
    return compile_html(content, source_url=None, config=config)


def compile_batch(
    items: list[dict],
    config: CompileConfig | None = None,
    max_concurrency: int = 5,
) -> BatchResult:
    """Compile multiple sources in parallel with shared context.

    When multiple URLs share a domain, automatically learns a SiteProfile
    and applies it to improve normalization.

    Args:
        items: List of dicts with "source" (required) and "source_type" (optional, default "auto").
        config: Shared compilation config. Uses defaults if not provided.
        max_concurrency: Maximum number of concurrent compilations.

    Returns:
        A BatchResult with compiled documents and any errors.
    """
    from agent_web_compiler.api.batch import BatchCompiler, BatchItem

    batch_items = [
        BatchItem(
            source=item["source"],
            source_type=item.get("source_type", "auto"),
        )
        for item in items
    ]

    compiler = BatchCompiler()
    return compiler.compile_batch(batch_items, config=config, max_concurrency=max_concurrency)
