"""Plugin registry — thread-safe registration and capability-based discovery.

Usage:
    from agent_web_compiler.plugins.registry import registry, PluginManifest

    manifest = PluginManifest(
        name="my-source",
        version="1.0.0",
        capabilities=["source:docx"],
        description="DOCX source plugin",
    )
    registry.register(manifest, my_plugin_instance)

    # Discover by capability
    docx_plugins = registry.discover("source:docx")
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PluginManifest:
    """Declarative metadata for a plugin.

    Attributes:
        name: Unique plugin name (e.g. "docx-source").
        version: Semver version string.
        capabilities: List of capability strings the plugin provides
            (e.g. ["source:docx", "normalizer:academic"]).
        config_schema: Optional JSON-Schema dict describing accepted config.
        description: Human-readable description.
    """

    name: str
    version: str
    capabilities: list[str] = field(default_factory=list)
    config_schema: dict[str, Any] | None = None
    description: str = ""


class PluginRegistry:
    """Thread-safe plugin registry with capability-based discovery.

    Plugins are stored by name. Each plugin is associated with a
    ``PluginManifest`` that declares its capabilities. Discovery queries
    scan manifests for matching capability strings.

    Thread safety is ensured via a ``threading.Lock`` around all
    mutating operations and reads that must be consistent.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._plugins: dict[str, object] = {}
        self._manifests: dict[str, PluginManifest] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, manifest: PluginManifest, plugin: object) -> None:
        """Register a plugin.

        Args:
            manifest: The plugin's manifest with name, version, and capabilities.
            plugin: The plugin instance.

        Raises:
            ValueError: If a plugin with the same name is already registered.
        """
        with self._lock:
            if manifest.name in self._plugins:
                raise ValueError(
                    f"Plugin '{manifest.name}' is already registered. "
                    "Unregister it first if you want to replace it."
                )
            self._plugins[manifest.name] = plugin
            self._manifests[manifest.name] = manifest
            logger.info(
                "Registered plugin '%s' v%s with capabilities %s",
                manifest.name,
                manifest.version,
                manifest.capabilities,
            )

    def unregister(self, name: str) -> None:
        """Unregister a plugin by name.

        Calls ``shutdown()`` on the plugin if available. Shutdown errors
        are logged but do not propagate — plugin failure must not corrupt
        global state.

        Args:
            name: The plugin name to remove.

        Raises:
            KeyError: If no plugin with this name is registered.
        """
        with self._lock:
            if name not in self._plugins:
                raise KeyError(f"Plugin '{name}' is not registered.")
            plugin = self._plugins.pop(name)
            self._manifests.pop(name)

        # Call shutdown outside the lock to avoid holding it during I/O.
        _safe_shutdown(plugin, name)
        logger.info("Unregistered plugin '%s'", name)

    def get(self, name: str) -> object | None:
        """Retrieve a plugin by name, or ``None`` if not found."""
        with self._lock:
            return self._plugins.get(name)

    def discover(self, capability: str) -> list[object]:
        """Return all plugins that declare the given capability.

        Args:
            capability: A capability string (e.g. "source:docx").

        Returns:
            List of plugin instances whose manifests include the capability.
        """
        with self._lock:
            return [
                self._plugins[name]
                for name, manifest in self._manifests.items()
                if capability in manifest.capabilities
            ]

    def list_plugins(self) -> list[PluginManifest]:
        """Return manifests for all registered plugins."""
        with self._lock:
            return list(self._manifests.values())

    def clear(self) -> None:
        """Unregister all plugins. Useful for testing."""
        with self._lock:
            names = list(self._plugins.keys())
            plugins = dict(self._plugins)
            self._plugins.clear()
            self._manifests.clear()

        for name in names:
            _safe_shutdown(plugins[name], name)

        logger.info("Cleared all plugins from registry")


# ---------------------------------------------------------------------------
# Entry-point discovery
# ---------------------------------------------------------------------------


def load_entry_point_plugins(group: str = "agent_web_compiler.plugins") -> None:
    """Discover and register plugins from installed entry points.

    Scans the given entry-point group for plugins. Each entry point
    must resolve to a callable that returns ``(PluginManifest, plugin_instance)``.

    Errors during loading are logged and skipped — a broken plugin must
    not prevent the application from starting.

    Args:
        group: The entry-point group name to scan.
    """
    try:
        from importlib.metadata import entry_points
    except ImportError:
        logger.debug("importlib.metadata not available; skipping entry-point discovery")
        return

    eps = entry_points()

    # Python 3.9/3.10 returns a dict; 3.12+ returns a SelectableGroups
    if isinstance(eps, dict):
        plugin_eps = eps.get(group, [])
    else:
        plugin_eps = eps.select(group=group)

    for ep in plugin_eps:
        try:
            factory = ep.load()
            manifest, plugin = factory()
            registry.register(manifest, plugin)
            logger.info("Loaded entry-point plugin '%s' from %s", manifest.name, ep.value)
        except Exception:
            logger.exception("Failed to load plugin entry point '%s'", ep.name)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_shutdown(plugin: object, name: str) -> None:
    """Call shutdown() on a plugin, swallowing any errors."""
    shutdown_fn = getattr(plugin, "shutdown", None)
    if callable(shutdown_fn):
        try:
            shutdown_fn()
        except Exception:
            logger.exception("Error shutting down plugin '%s'", name)


# ---------------------------------------------------------------------------
# Global registry instance
# ---------------------------------------------------------------------------

registry = PluginRegistry()
