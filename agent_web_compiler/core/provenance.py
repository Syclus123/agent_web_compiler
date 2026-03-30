"""Provenance models — tracking where each block and action came from."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DOMProvenance(BaseModel):
    """Tracks origin in the DOM tree."""

    dom_path: str = Field(..., description="CSS-style path to the source element")
    element_tag: str | None = Field(None, description="HTML tag name")
    element_id: str | None = Field(None, description="HTML id attribute")
    element_classes: list[str] = Field(default_factory=list, description="HTML class list")


class PageProvenance(BaseModel):
    """Tracks origin on a page (PDF page or viewport region)."""

    page: int | None = Field(None, description="Page number (1-indexed, for PDFs)")
    bbox: list[float] | None = Field(
        None,
        description="Bounding box [x1, y1, x2, y2] in page coordinates",
        min_length=4,
        max_length=4,
    )
    char_range: list[int] | None = Field(
        None,
        description="Character offset range [start, end] in source text",
        min_length=2,
        max_length=2,
    )


class ScreenshotProvenance(BaseModel):
    """Tracks origin in a screenshot region."""

    screenshot_region_id: str | None = Field(None, description="Region identifier")
    screenshot_bbox: list[float] | None = Field(
        None,
        description="Bounding box in screenshot pixel coordinates [x1, y1, x2, y2]",
        min_length=4,
        max_length=4,
    )


class Provenance(BaseModel):
    """Combined provenance for a block or action.

    Links a compiled artifact back to its original source location(s).
    """

    dom: DOMProvenance | None = None
    page: PageProvenance | None = None
    screenshot: ScreenshotProvenance | None = None
    source_url: str | None = Field(None, description="URL of the source document")
    raw_html: str | None = Field(
        None, description="Original raw HTML snippet (for debug)"
    )
