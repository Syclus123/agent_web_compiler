"""REST API server for agent-web-compiler.

Provides a FastAPI application with endpoints for compiling content
into AgentDocuments and retrieving specific output facets.

Usage:
    from agent_web_compiler.serving.rest_server import create_app

    app = create_app()
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

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


def _compile_from_request(req: CompileRequest) -> AgentDocument:
    """Run compilation based on the request source.

    Raises:
        HTTPException: On input validation or compilation errors.
    """
    _validate_compile_request(req)
    config = _build_config(req)

    try:
        if req.url is not None:
            from agent_web_compiler.api.compile import compile_url

            return compile_url(req.url, config=config)

        if req.html is not None:
            from agent_web_compiler.api.compile import compile_html

            return compile_html(req.html, config=config)

        if req.file_path is not None:
            from agent_web_compiler.api.compile import compile_file

            return compile_file(req.file_path, config=config)

    except FetchError as exc:
        logger.warning("Fetch error: %s", exc, exc_info=True)
        raise HTTPException(status_code=400, detail=f"Fetch error: {exc}") from exc
    except CompilerError as exc:
        logger.error("Compilation error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Compilation error: {exc}") from exc
    except Exception as exc:
        logger.error("Unexpected error during compilation: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {type(exc).__name__}: {exc}",
        ) from exc

    # Unreachable due to _validate_compile_request, but satisfy type checker
    raise HTTPException(status_code=400, detail="No source provided.")  # pragma: no cover


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
    def compile_endpoint(req: CompileRequest) -> dict[str, Any]:
        """Compile content into a full AgentDocument."""
        doc = _compile_from_request(req)
        return doc.model_dump(mode="json")

    # ------------------------------------------------------------------
    # POST /v1/compile/markdown — markdown only
    # ------------------------------------------------------------------

    @app.post("/v1/compile/markdown", response_model=MarkdownResponse)
    def compile_markdown_endpoint(req: CompileRequest) -> MarkdownResponse:
        """Compile content and return only the canonical markdown."""
        doc = _compile_from_request(req)
        return MarkdownResponse(markdown=doc.canonical_markdown)

    # ------------------------------------------------------------------
    # POST /v1/compile/blocks — blocks with filtering
    # ------------------------------------------------------------------

    @app.post("/v1/compile/blocks", response_model=BlocksResponse)
    def compile_blocks_endpoint(req: CompileBlocksRequest) -> BlocksResponse:
        """Compile content and return filtered blocks."""
        doc = _compile_from_request(req)

        blocks = doc.blocks

        # Filter by importance
        if req.min_importance > 0.0:
            blocks = [b for b in blocks if b.importance >= req.min_importance]

        # Filter by block types
        if req.block_types:
            type_set = set(req.block_types)
            blocks = [b for b in blocks if b.type in type_set or b.type.value in type_set]

        return BlocksResponse(
            blocks=[b.model_dump(mode="json") for b in blocks],
        )

    # ------------------------------------------------------------------
    # POST /v1/compile/actions — actions with filtering
    # ------------------------------------------------------------------

    @app.post("/v1/compile/actions", response_model=ActionsResponse)
    def compile_actions_endpoint(req: CompileActionsRequest) -> ActionsResponse:
        """Compile content and return filtered actions."""
        doc = _compile_from_request(req)

        actions = doc.actions

        # Filter by group
        if req.group is not None:
            actions = [a for a in actions if a.group == req.group]

        return ActionsResponse(
            actions=[a.model_dump(mode="json") for a in actions],
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

    return app
