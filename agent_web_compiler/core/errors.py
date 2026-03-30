"""Typed errors for the compilation pipeline."""

from __future__ import annotations

from typing import Any


class CompilerError(Exception):
    """Base error for all compilation failures."""

    def __init__(
        self,
        message: str,
        *,
        stage: str | None = None,
        cause: Exception | None = None,
        context: dict[str, Any] | None = None,
    ):
        self.stage = stage
        self.cause = cause
        self.context = context or {}
        super().__init__(message)
        if cause:
            self.__cause__ = cause


class FetchError(CompilerError):
    """Failed to fetch the source content."""

    def __init__(self, message: str, **kwargs: Any):
        super().__init__(message, stage="fetch", **kwargs)


class RenderError(CompilerError):
    """Failed to render dynamic content."""

    def __init__(self, message: str, **kwargs: Any):
        super().__init__(message, stage="render", **kwargs)


class ParseError(CompilerError):
    """Failed to parse source content."""

    def __init__(self, message: str, **kwargs: Any):
        super().__init__(message, stage="parse", **kwargs)


class NormalizeError(CompilerError):
    """Failed during normalization."""

    def __init__(self, message: str, **kwargs: Any):
        super().__init__(message, stage="normalize", **kwargs)


class SegmentError(CompilerError):
    """Failed during segmentation."""

    def __init__(self, message: str, **kwargs: Any):
        super().__init__(message, stage="segment", **kwargs)


class ExtractError(CompilerError):
    """Failed during extraction."""

    def __init__(self, message: str, **kwargs: Any):
        super().__init__(message, stage="extract", **kwargs)


class AlignError(CompilerError):
    """Failed during provenance alignment."""

    def __init__(self, message: str, **kwargs: Any):
        super().__init__(message, stage="align", **kwargs)


class ExportError(CompilerError):
    """Failed during export."""

    def __init__(self, message: str, **kwargs: Any):
        super().__init__(message, stage="export", **kwargs)
