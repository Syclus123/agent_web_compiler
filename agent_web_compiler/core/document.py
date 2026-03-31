"""AgentDocument — the top-level compiled output object."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, computed_field

from agent_web_compiler.core.action import Action
from agent_web_compiler.core.block import Block

# Schema version — bump on breaking changes
SCHEMA_VERSION = "0.5.0"


class SourceType(str, Enum):
    """Type of input source."""

    HTML = "html"
    PDF = "pdf"
    DOCX = "docx"
    API = "api"
    IMAGE_PDF = "image_pdf"


class Quality(BaseModel):
    """Quality indicators for the compilation."""

    parse_confidence: float = Field(
        1.0,
        ge=0.0,
        le=1.0,
        description="Overall confidence in the parse quality",
    )
    ocr_used: bool = Field(False, description="Whether OCR was used")
    dynamic_rendered: bool = Field(
        False, description="Whether browser rendering was used"
    )
    block_count: int = Field(0, description="Total number of blocks")
    action_count: int = Field(0, description="Total number of actions")
    warnings: list[str] = Field(
        default_factory=list, description="Machine-readable warning messages"
    )


class SiteProfile(BaseModel):
    """Site-level template metadata for boilerplate detection."""

    site: str = Field(..., description="Domain name")
    template_signature: str | None = Field(
        None, description="Hash of template structure"
    )
    header_selectors: list[str] = Field(default_factory=list)
    footer_selectors: list[str] = Field(default_factory=list)
    sidebar_selectors: list[str] = Field(default_factory=list)
    main_content_selectors: list[str] = Field(default_factory=list)
    noise_patterns: list[str] = Field(
        default_factory=list,
        description="Known noise block patterns (cookie, subscribe, share, etc.)",
    )


class Asset(BaseModel):
    """A referenced asset in the document (image, stylesheet, script, font, etc.)."""

    id: str = Field(..., description="Unique asset identifier, e.g. 'asset_001'")
    type: str = Field(..., description="Asset type: 'image', 'stylesheet', 'script', 'font'")
    url: str | None = Field(None, description="URL or path of the asset")
    alt: str | None = Field(None, description="Alt text (for images)")
    mime_type: str | None = Field(None, description="MIME type if known")


class AgentDocument(BaseModel):
    """The canonical compiled output — an agent-native representation of a document.

    Contains semantic blocks, action affordances, provenance tracking,
    and quality metadata. This is the primary output of the compilation pipeline.
    """

    schema_version: str = Field(
        SCHEMA_VERSION, description="Schema version for compatibility"
    )
    doc_id: str = Field(..., description="Unique document identifier (sha256 of source)")
    source_type: SourceType = Field(..., description="Type of source document")
    source_url: str | None = Field(None, description="Source URL if applicable")
    source_file: str | None = Field(None, description="Source file path if applicable")
    title: str = Field("", description="Document title")
    lang: str | None = Field(None, description="Detected language code")
    fetched_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the source was fetched",
    )
    compiled_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When compilation completed",
    )

    # Core content
    blocks: list[Block] = Field(default_factory=list, description="Semantic content blocks")
    canonical_markdown: str = Field(
        "", description="Canonical markdown representation of content"
    )

    # Actions
    actions: list[Action] = Field(
        default_factory=list, description="Interactive affordances"
    )
    navigation_graph: dict | None = Field(
        None,
        description="Navigation graph modeling reachable states from actions (serialized)",
    )

    # Assets
    assets: list[Asset] = Field(
        default_factory=list,
        description="Referenced assets (images, stylesheets, scripts, fonts)",
    )

    # Provenance index
    provenance_index: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Reverse lookup: source region (e.g. section path) -> block IDs",
    )

    # Metadata
    site_profile: SiteProfile | None = Field(
        None, description="Site template metadata"
    )
    quality: Quality = Field(
        default_factory=Quality, description="Quality indicators"
    )

    # Debug
    debug: dict[str, Any] = Field(
        default_factory=dict,
        description="Debug metadata (timings, intermediate artifacts, etc.)",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def block_count(self) -> int:
        """Total number of content blocks."""
        return len(self.blocks)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def action_count(self) -> int:
        """Total number of actions."""
        return len(self.actions)

    @staticmethod
    def make_doc_id(content: str | bytes) -> str:
        """Generate a deterministic document ID from content."""
        if isinstance(content, str):
            content = content.encode("utf-8")
        return f"sha256:{hashlib.sha256(content).hexdigest()[:16]}"

    def get_blocks_by_type(self, block_type: str) -> list[Block]:
        """Return all blocks of a given type."""
        return [b for b in self.blocks if b.type == block_type]

    def get_main_content(self, min_importance: float = 0.3) -> list[Block]:
        """Return blocks above a minimum importance threshold."""
        return [b for b in self.blocks if b.importance >= min_importance]

    def summary_markdown(self, max_blocks: int = 20) -> str:
        """Generate a short markdown summary using top blocks by importance."""
        top_blocks = sorted(self.blocks, key=lambda b: b.importance, reverse=True)[
            :max_blocks
        ]
        top_blocks.sort(key=lambda b: b.order)
        parts: list[str] = []
        if self.title:
            parts.append(f"# {self.title}\n")
        for block in top_blocks:
            parts.append(block.text)
        return "\n\n".join(parts)
