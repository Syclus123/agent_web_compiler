"""Plugin registration and discovery.

Public API:
    from agent_web_compiler.plugins import registry, PluginManifest
    from agent_web_compiler.plugins.base import SourcePlugin, NormalizerPlugin, ExtractorPlugin
"""

from __future__ import annotations

from agent_web_compiler.plugins.registry import (
    PluginManifest,
    PluginRegistry,
    load_entry_point_plugins,
    registry,
)

__all__ = [
    "PluginManifest",
    "PluginRegistry",
    "load_entry_point_plugins",
    "registry",
]
