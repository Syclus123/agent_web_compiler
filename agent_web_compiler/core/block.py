"""Block model — a semantic unit of content in an AgentDocument."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from agent_web_compiler.core.provenance import Provenance


class BlockType(str, Enum):
    """Semantic type of a content block."""

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST = "list"
    TABLE = "table"
    CODE = "code"
    QUOTE = "quote"
    FIGURE_CAPTION = "figure_caption"
    IMAGE = "image"
    PRODUCT_SPEC = "product_spec"
    REVIEW = "review"
    FAQ = "faq"
    FORM_HELP = "form_help"
    METADATA = "metadata"
    UNKNOWN = "unknown"


class Block(BaseModel):
    """A semantic content block extracted from a document.

    Each block represents a meaningful unit: a heading, paragraph, table, code block, etc.
    Blocks carry provenance (origin tracking) and importance scoring.
    """

    id: str = Field(..., description="Unique block identifier, e.g. 'b_001'")
    type: BlockType = Field(..., description="Semantic type of this block")
    text: str = Field(..., description="Plain text content of the block")
    html: str | None = Field(None, description="Original HTML content if available")
    section_path: list[str] = Field(
        default_factory=list,
        description="Heading hierarchy path, e.g. ['Methods', 'Training Setup']",
    )
    order: int = Field(0, description="Position in reading order (0-indexed)")
    importance: float = Field(
        0.5,
        ge=0.0,
        le=1.0,
        description="Salience score from 0 (noise) to 1 (critical)",
    )
    level: int | None = Field(
        None, description="Heading level (1-6) for heading blocks"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Type-specific metadata (e.g. row_count for tables)",
    )
    provenance: Provenance | None = Field(
        None, description="Origin tracking back to source"
    )
    children: list[Block] = Field(
        default_factory=list, description="Nested blocks (e.g. list items)"
    )
