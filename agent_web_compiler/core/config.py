"""Typed configuration for the compilation pipeline."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class CompileMode(str, Enum):
    """Compilation mode controlling quality/speed tradeoff."""

    FAST = "fast"
    BALANCED = "balanced"
    HIGH_RECALL = "high_recall"


class RenderMode(str, Enum):
    """When to use browser rendering."""

    OFF = "off"
    AUTO = "auto"
    ALWAYS = "always"


class CompileConfig(BaseModel):
    """Configuration for a compilation run.

    All compilation behavior is controlled through this typed config.
    No hidden global state or undocumented environment variable magic.
    """

    mode: CompileMode = Field(
        CompileMode.BALANCED,
        description="Compilation mode: fast (minimal processing), balanced (default), high_recall (maximum extraction)",
    )
    render: RenderMode = Field(
        RenderMode.OFF,
        description="Browser rendering: off, auto (detect dynamic pages), always",
    )

    # Content options
    include_actions: bool = Field(True, description="Extract action affordances")
    include_provenance: bool = Field(True, description="Include provenance tracking")
    include_raw_html: bool = Field(
        False, description="Preserve raw HTML in block provenance"
    )

    # Filtering
    query: str | None = Field(
        None, description="Query for query-aware compilation — filters and re-ranks blocks by relevance"
    )
    min_importance: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Minimum importance threshold for blocks",
    )
    max_blocks: int | None = Field(
        None, description="Maximum number of blocks to emit"
    )

    # PDF options
    pdf_backend: str = Field(
        "auto",
        description="PDF backend: auto, pymupdf, docling",
    )

    # Network / pipeline timeout
    timeout_seconds: float = Field(
        30.0,
        description="Timeout in seconds for HTTP fetches and total pipeline compilation",
    )
    user_agent: str = Field(
        "agent-web-compiler/0.1.0",
        description="User-Agent header for HTTP requests",
    )

    # Cache
    cache_dir: str | None = Field(
        None, description="Cache directory. None disables caching."
    )
    cache_ttl: float = Field(3600.0, description="Cache TTL in seconds")

    # Token budget
    token_budget: int | None = Field(
        None,
        description="Target token count for output. None = unlimited.",
    )

    # Debug
    debug: bool = Field(False, description="Enable debug metadata in output")
