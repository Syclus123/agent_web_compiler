"""REST API server for agent-web-compiler.

Provides a FastAPI application with endpoints for compiling content
into AgentDocuments and retrieving specific output facets.

Note: For very large HTML inputs, consider chunking or streaming.
The server does not enforce a hard request size limit, but payloads
larger than ~10MB may cause slowdowns or memory pressure.

Usage:
    from agent_web_compiler.serving.rest_server import create_app

    app = create_app()
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from agent_web_compiler.core.config import CompileConfig, CompileMode, RenderMode
from agent_web_compiler.core.document import SCHEMA_VERSION, AgentDocument
from agent_web_compiler.core.errors import CompilerError, FetchError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class CompileRequest(BaseModel):
    """Request body for compilation endpoints."""

    url: str | None = Field(None, description="URL to fetch and compile")
    html: str | None = Field(None, description="Raw HTML to compile")
    file_path: str | None = Field(None, description="Local file path to compile")
    mode: str = Field("balanced", description="Compilation mode: fast, balanced, high_recall")
    render: str = Field("off", description="Render mode: off, auto, always")
    include_actions: bool = Field(True, description="Extract action affordances")
    include_provenance: bool = Field(True, description="Include provenance tracking")
    query: str | None = Field(None, description="Query for query-aware compilation")
    debug: bool = Field(False, description="Include debug metadata")


class CompileBlocksRequest(CompileRequest):
    """Request body for the blocks endpoint with filtering."""

    min_importance: float = Field(0.0, ge=0.0, le=1.0, description="Minimum importance threshold")
    block_types: list[str] | None = Field(None, description="Filter to specific block types")


class CompileActionsRequest(CompileRequest):
    """Request body for the actions endpoint with filtering."""

    group: str | None = Field(None, description="Filter to a specific action group")


class MarkdownResponse(BaseModel):
    """Response body for the markdown endpoint."""

    markdown: str


class BlocksResponse(BaseModel):
    """Response body for the blocks endpoint."""

    blocks: list[dict[str, Any]]


class ActionsResponse(BaseModel):
    """Response body for the actions endpoint."""

    actions: list[dict[str, Any]]


class HealthResponse(BaseModel):
    """Response body for the health check endpoint."""

    status: str
    version: str


# ---------------------------------------------------------------------------
# Live runtime / BH-skill request models
# ---------------------------------------------------------------------------


class LiveRunRequest(BaseModel):
    """Request body for ``POST /v1/live/run``.

    Drives :class:`LiveRuntime` through browser-harness: compile the URL,
    pick the best-matching actions for ``task``, execute them via BH, and
    return the outcome with evidence.
    """

    url: str = Field(..., description="URL to compile and act on")
    task: str = Field(..., description="Natural-language task")
    bu_name: str = Field("awc", description="browser-harness session scope (BU_NAME)")
    max_actions: int = Field(1, ge=1, description="Max actions to attempt")
    auto_confirm: bool = Field(
        False, description="Auto-approve confirm-required actions"
    )
    dry_run: bool = Field(False, description="Compile + plan only; no execution")
    fetcher: str = Field(
        "browser_harness",
        description=(
            "Fetcher backend used to compile the initial page. Defaults to "
            "browser_harness so the compile step and the live execution share "
            "the same session."
        ),
    )


class PublishBHSkillRequest(BaseModel):
    """Request body for ``POST /v1/publish/bh-skill``."""

    url: str = Field(..., description="URL to compile")
    task: str = Field("scraping", description="BH task filename stem")
    fetcher: str = Field(
        "http",
        description="Fetcher backend: http, playwright, or browser_harness",
    )
    out_repo: str | None = Field(
        None,
        description=(
            "Optional local BH repo path. When set, the skill is written under "
            "<out_repo>/agent-workspace/domain-skills/<site>/<task>.md."
        ),
    )
    overwrite: bool = Field(False, description="Overwrite existing skill file")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_compile_request(req: CompileRequest) -> None:
    """Validate that exactly one source is provided.

    Raises:
        HTTPException: If zero or multiple sources are specified.
    """
    sources = [s for s in (req.url, req.html, req.file_path) if s is not None]
    if len(sources) == 0:
        raise HTTPException(
            status_code=400,
            detail="Exactly one of 'url', 'html', or 'file_path' must be provided.",
        )
    if len(sources) > 1:
        raise HTTPException(
            status_code=400,
            detail="Only one of 'url', 'html', or 'file_path' may be provided.",
        )


def _build_config(req: CompileRequest) -> CompileConfig:
    """Build a CompileConfig from a request."""
    try:
        mode = CompileMode(req.mode)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode '{req.mode}'. Must be one of: fast, balanced, high_recall.",
        ) from exc

    try:
        render = RenderMode(req.render)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid render '{req.render}'. Must be one of: off, auto, always.",
        ) from exc

    return CompileConfig(
        mode=mode,
        render=render,
        include_actions=req.include_actions,
        include_provenance=req.include_provenance,
        query=req.query,
        debug=req.debug,
    )


def _compile_from_request(req: CompileRequest) -> tuple[AgentDocument, float]:
    """Run compilation based on the request source.

    Returns:
        A tuple of (AgentDocument, compile_time_seconds).

    Raises:
        HTTPException: On input validation or compilation errors.
    """
    _validate_compile_request(req)
    config = _build_config(req)

    t0 = time.monotonic()

    try:
        if req.url is not None:
            from agent_web_compiler.api.compile import compile_url

            doc = compile_url(req.url, config=config)
            return doc, time.monotonic() - t0

        if req.html is not None:
            from agent_web_compiler.api.compile import compile_html

            doc = compile_html(req.html, config=config)
            return doc, time.monotonic() - t0

        if req.file_path is not None:
            from agent_web_compiler.api.compile import compile_file

            doc = compile_file(req.file_path, config=config)
            return doc, time.monotonic() - t0

    except FetchError as exc:
        logger.warning("Fetch error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "FETCH_ERROR",
                "message": "Failed to fetch the requested resource.",
            },
        ) from exc
    except CompilerError as exc:
        logger.error("Compilation error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "COMPILATION_ERROR",
                "message": "An error occurred during compilation.",
                "stage": exc.stage,
            },
        ) from exc
    except Exception as exc:
        logger.error("Unexpected error during compilation: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "INTERNAL_ERROR",
                "message": "An unexpected internal error occurred.",
            },
        ) from exc

    # Unreachable due to _validate_compile_request, but satisfy type checker
    raise HTTPException(status_code=400, detail="No source provided.")  # pragma: no cover


def _compile_headers(doc: AgentDocument, compile_time_s: float) -> dict[str, str]:
    """Build response headers with compilation metadata."""
    return {
        "X-Compile-Time-Ms": str(int(compile_time_s * 1000)),
        "X-Block-Count": str(doc.block_count),
        "X-Action-Count": str(doc.action_count),
    }


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Create the FastAPI application with all compilation endpoints."""
    app = FastAPI(
        title="agent-web-compiler",
        description="Compile the Human Web into the Agent Web.",
        version=SCHEMA_VERSION,
    )

    # CORS middleware — permissive defaults for development; tighten in production.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # POST /v1/compile — full AgentDocument
    # ------------------------------------------------------------------

    @app.post("/v1/compile", response_model=None)
    def compile_endpoint(req: CompileRequest) -> JSONResponse:
        """Compile content into a full AgentDocument."""
        doc, compile_time = _compile_from_request(req)
        return JSONResponse(
            content=doc.model_dump(mode="json"),
            headers=_compile_headers(doc, compile_time),
        )

    # ------------------------------------------------------------------
    # POST /v1/compile/markdown — markdown only
    # ------------------------------------------------------------------

    @app.post("/v1/compile/markdown", response_model=None)
    def compile_markdown_endpoint(req: CompileRequest) -> JSONResponse:
        """Compile content and return only the canonical markdown."""
        doc, compile_time = _compile_from_request(req)
        return JSONResponse(
            content={"markdown": doc.canonical_markdown},
            headers=_compile_headers(doc, compile_time),
        )

    # ------------------------------------------------------------------
    # POST /v1/compile/blocks — blocks with filtering
    # ------------------------------------------------------------------

    @app.post("/v1/compile/blocks", response_model=None)
    def compile_blocks_endpoint(req: CompileBlocksRequest) -> JSONResponse:
        """Compile content and return filtered blocks."""
        doc, compile_time = _compile_from_request(req)

        blocks = doc.blocks

        # Filter by importance
        if req.min_importance > 0.0:
            blocks = [b for b in blocks if b.importance >= req.min_importance]

        # Filter by block types
        if req.block_types:
            type_set = set(req.block_types)
            blocks = [b for b in blocks if b.type in type_set or b.type.value in type_set]

        return JSONResponse(
            content={"blocks": [b.model_dump(mode="json") for b in blocks]},
            headers=_compile_headers(doc, compile_time),
        )

    # ------------------------------------------------------------------
    # POST /v1/compile/actions — actions with filtering
    # ------------------------------------------------------------------

    @app.post("/v1/compile/actions", response_model=None)
    def compile_actions_endpoint(req: CompileActionsRequest) -> JSONResponse:
        """Compile content and return filtered actions."""
        doc, compile_time = _compile_from_request(req)

        actions = doc.actions

        # Filter by group
        if req.group is not None:
            actions = [a for a in actions if a.group == req.group]

        return JSONResponse(
            content={"actions": [a.model_dump(mode="json") for a in actions]},
            headers=_compile_headers(doc, compile_time),
        )

    # ------------------------------------------------------------------
    # POST /v1/compile/stream — SSE streaming compilation
    # ------------------------------------------------------------------

    @app.post("/v1/compile/stream", response_model=None)
    async def compile_stream_endpoint(req: CompileRequest) -> StreamingResponse:
        """Stream compilation events via Server-Sent Events.

        Each event is formatted as an SSE message with ``event:`` and
        ``data:`` fields. Event types: ``block``, ``action``, ``progress``,
        ``complete``, ``budget_reached``, ``error``.
        """
        import json

        _validate_compile_request(req)
        config = _build_config(req)

        from agent_web_compiler.pipeline.stream_compiler import StreamCompiler

        compiler = StreamCompiler()

        # Determine source HTML
        html: str | None = req.html
        source_url: str | None = req.url

        if req.url is not None and html is None:
            try:
                from agent_web_compiler.sources.http_fetcher import HTTPFetcher

                fetcher = HTTPFetcher()
                result = fetcher.fetch_sync(req.url, config)
                if not isinstance(result.content, str):
                    raise HTTPException(
                        status_code=400,
                        detail="Expected text content from URL.",
                    )
                html = result.content
            except FetchError as exc:
                raise HTTPException(
                    status_code=400,
                    detail={"error_code": "FETCH_ERROR", "message": str(exc)},
                ) from exc

        if req.file_path is not None and html is None:
            from agent_web_compiler.sources.file_reader import FileReader

            reader = FileReader()
            file_result = reader.read(req.file_path)
            html = (
                file_result.content
                if isinstance(file_result.content, str)
                else file_result.content.decode("utf-8")
            )

        if html is None:
            raise HTTPException(status_code=400, detail="No source provided.")

        async def event_generator():  # type: ignore[return]
            async for event in compiler.compile_stream_async(
                html, source_url=source_url, config=config
            ):
                sse_data = json.dumps(
                    {
                        "event_type": event.event_type,
                        "data": event.data,
                        "sequence": event.sequence,
                    }
                )
                yield f"event: {event.event_type}\ndata: {sse_data}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ------------------------------------------------------------------
    # GET /health
    # ------------------------------------------------------------------

    @app.get("/health", response_model=HealthResponse)
    def health_endpoint() -> HealthResponse:
        """Health check endpoint."""
        return HealthResponse(status="ok", version=SCHEMA_VERSION)

    # ------------------------------------------------------------------
    # GET /schema
    # ------------------------------------------------------------------

    @app.get("/schema")
    def schema_endpoint() -> dict[str, Any]:
        """Return the AgentDocument JSON Schema."""
        return AgentDocument.model_json_schema()

    # ------------------------------------------------------------------
    # POST /v1/live/run — compile + plan + act via browser-harness
    # ------------------------------------------------------------------

    @app.post("/v1/live/run", response_model=None)
    def live_run_endpoint(req: LiveRunRequest) -> JSONResponse:
        """Run a task against a URL with browser-harness as the executor.

        Requires the ``harness`` optional extra and a running BH daemon.
        """
        try:
            from agent_web_compiler.runtime.browser_harness import (
                LiveActionExecutor,
                LiveRuntime,
            )
        except ImportError as e:
            raise HTTPException(
                status_code=503,
                detail=(
                    "browser-harness runtime is not available. "
                    "Install with: pip install 'agent-web-compiler[harness]'. "
                    f"Details: {e}"
                ),
            ) from e

        try:
            executor = LiveActionExecutor(
                bu_name=req.bu_name, auto_confirm=req.auto_confirm
            )
            runtime = LiveRuntime.from_url(req.url, executor=executor, fetcher=req.fetcher)
        except CompilerError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        except FetchError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e

        if req.dry_run:
            actions = runtime._select_actions(  # noqa: SLF001 — purpose-built
                req.task, max_actions=req.max_actions
            )
            return JSONResponse(
                content={
                    "dry_run": True,
                    "url": req.url,
                    "task": req.task,
                    "planned_actions": [
                        {
                            "id": a.id,
                            "type": a.type.value,
                            "label": a.label,
                            "selector": a.selector,
                        }
                        for a in actions
                    ],
                }
            )

        outcome = runtime.run(req.task, max_actions=req.max_actions)
        return JSONResponse(content=outcome.to_dict())

    # ------------------------------------------------------------------
    # POST /v1/publish/bh-skill — render a BH domain-skill from a URL
    # ------------------------------------------------------------------

    @app.post("/v1/publish/bh-skill", response_model=None)
    def publish_bh_skill_endpoint(req: PublishBHSkillRequest) -> JSONResponse:
        """Render a browser-harness-compatible domain-skill markdown."""
        from agent_web_compiler.api.compile import compile_url
        from agent_web_compiler.publisher import DomainSkillPublisher

        try:
            doc = compile_url(req.url, fetcher=req.fetcher)
        except (CompilerError, FetchError) as e:
            raise HTTPException(status_code=502, detail=str(e)) from e

        skill = DomainSkillPublisher().generate_from_document(doc, task=req.task)
        payload: dict[str, Any] = {
            "domain": skill.domain,
            "task": skill.task,
            "filename": skill.filename(),
            "api_count": skill.api_count,
            "selector_count": skill.selector_count,
            "markdown": skill.markdown,
        }
        if req.out_repo:
            try:
                target = skill.write_to_repo(req.out_repo, overwrite=req.overwrite)
            except FileExistsError as e:
                raise HTTPException(status_code=409, detail=str(e)) from e
            payload["written_to"] = str(target)
        return JSONResponse(content=payload)

    return app
