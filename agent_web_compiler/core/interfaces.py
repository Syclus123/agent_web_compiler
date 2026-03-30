"""Interfaces (protocols) for pipeline stages.

Each stage in the pipeline implements a small typed protocol.
New source types and stages register by implementing these interfaces.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from agent_web_compiler.core.action import Action
from agent_web_compiler.core.block import Block
from agent_web_compiler.core.config import CompileConfig


class FetchResult:
    """Result from a fetch operation."""

    __slots__ = ("content", "content_type", "url", "status_code", "headers", "metadata")

    def __init__(
        self,
        content: str | bytes,
        content_type: str = "text/html",
        url: str = "",
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.content = content
        self.content_type = content_type
        self.url = url
        self.status_code = status_code
        self.headers = headers or {}
        self.metadata = metadata or {}


@runtime_checkable
class Fetcher(Protocol):
    """Fetches raw content from a URL or file."""

    async def fetch(self, source: str, config: CompileConfig) -> FetchResult: ...


@runtime_checkable
class Normalizer(Protocol):
    """Cleans and normalizes raw content."""

    def normalize(self, html: str, config: CompileConfig) -> str: ...


@runtime_checkable
class Segmenter(Protocol):
    """Segments normalized content into typed blocks."""

    def segment(self, html: str, config: CompileConfig) -> list[Block]: ...


@runtime_checkable
class Extractor(Protocol):
    """Extracts actions/affordances from content."""

    def extract(self, html: str, config: CompileConfig) -> list[Action]: ...


@runtime_checkable
class Aligner(Protocol):
    """Aligns blocks and actions with provenance data."""

    def align(
        self, blocks: list[Block], actions: list[Action], html: str, config: CompileConfig
    ) -> tuple[list[Block], list[Action]]: ...
