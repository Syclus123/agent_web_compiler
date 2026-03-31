"""Base protocols for plugins.

Plugins implement one or more of these protocols to extend the pipeline
with new source types, normalizers, or extractors.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.core.interfaces import FetchResult
from agent_web_compiler.plugins.registry import PluginManifest


@runtime_checkable
class Plugin(Protocol):
    """Base protocol for all plugins."""

    manifest: PluginManifest

    def initialize(self, config: dict[str, Any]) -> None:
        """Initialize the plugin with the given configuration.

        Called once after registration. Plugins should validate their
        config and acquire any resources here.
        """
        ...

    def shutdown(self) -> None:
        """Release any resources held by the plugin.

        Called when the plugin is unregistered or the application shuts down.
        """
        ...


@runtime_checkable
class SourcePlugin(Plugin, Protocol):
    """Plugin that provides a new source type (e.g. DOCX, API).

    Capabilities should be declared as ``source:<type>`` in the manifest.
    """

    def can_handle(self, source: str) -> bool:
        """Return True if this plugin can handle the given source identifier."""
        ...

    def fetch(self, source: str, config: CompileConfig) -> FetchResult:
        """Fetch content from the source.

        Args:
            source: A URL, file path, or other identifier.
            config: The compilation configuration.

        Returns:
            A FetchResult with the raw content.

        Raises:
            FetchError: If the source cannot be fetched.
        """
        ...


@runtime_checkable
class NormalizerPlugin(Plugin, Protocol):
    """Plugin that provides custom normalization logic.

    Capabilities should be declared as ``normalizer:<domain>`` in the manifest.
    """

    def normalize(self, html: str, config: CompileConfig) -> str:
        """Normalize HTML content.

        Args:
            html: Raw or partially-normalized HTML.
            config: The compilation configuration.

        Returns:
            Normalized HTML string.
        """
        ...


@runtime_checkable
class ExtractorPlugin(Plugin, Protocol):
    """Plugin that provides custom extraction logic.

    Capabilities should be declared as ``extractor:<type>`` in the manifest.
    """

    def extract(self, html: str, config: CompileConfig) -> list[Any]:
        """Extract structured data from HTML.

        Args:
            html: Normalized HTML content.
            config: The compilation configuration.

        Returns:
            A list of extracted items (blocks, actions, entities, etc.).
        """
        ...
