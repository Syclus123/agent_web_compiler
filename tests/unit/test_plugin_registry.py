"""Tests for the plugin registry system."""

from __future__ import annotations

import threading

import pytest

from agent_web_compiler.plugins.registry import PluginManifest, PluginRegistry, registry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakePlugin:
    """Minimal fake plugin for testing."""

    def __init__(self, name: str = "fake") -> None:
        self.name = name
        self.initialized = False
        self.shut_down = False

    def initialize(self, config: dict) -> None:
        self.initialized = True

    def shutdown(self) -> None:
        self.shut_down = True


class BrokenShutdownPlugin:
    """Plugin whose shutdown raises an exception."""

    def shutdown(self) -> None:
        raise RuntimeError("shutdown failed!")


# ---------------------------------------------------------------------------
# PluginManifest
# ---------------------------------------------------------------------------


class TestPluginManifest:
    def test_create_manifest(self) -> None:
        m = PluginManifest(
            name="test-plugin",
            version="1.0.0",
            capabilities=["source:docx"],
            description="A test plugin",
        )
        assert m.name == "test-plugin"
        assert m.version == "1.0.0"
        assert m.capabilities == ["source:docx"]
        assert m.config_schema is None
        assert m.description == "A test plugin"

    def test_manifest_defaults(self) -> None:
        m = PluginManifest(name="minimal", version="0.1.0")
        assert m.capabilities == []
        assert m.config_schema is None
        assert m.description == ""

    def test_manifest_is_frozen(self) -> None:
        m = PluginManifest(name="frozen", version="1.0.0")
        with pytest.raises(AttributeError):
            m.name = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PluginRegistry — basic operations
# ---------------------------------------------------------------------------


class TestPluginRegistry:
    def setup_method(self) -> None:
        self.reg = PluginRegistry()

    def test_register_and_get(self) -> None:
        plugin = FakePlugin()
        manifest = PluginManifest(name="p1", version="1.0.0")
        self.reg.register(manifest, plugin)
        assert self.reg.get("p1") is plugin

    def test_get_missing_returns_none(self) -> None:
        assert self.reg.get("nonexistent") is None

    def test_register_duplicate_raises(self) -> None:
        manifest = PluginManifest(name="dup", version="1.0.0")
        self.reg.register(manifest, FakePlugin())
        with pytest.raises(ValueError, match="already registered"):
            self.reg.register(manifest, FakePlugin())

    def test_unregister(self) -> None:
        plugin = FakePlugin()
        manifest = PluginManifest(name="rm", version="1.0.0")
        self.reg.register(manifest, plugin)
        self.reg.unregister("rm")
        assert self.reg.get("rm") is None
        assert plugin.shut_down is True

    def test_unregister_missing_raises(self) -> None:
        with pytest.raises(KeyError, match="not registered"):
            self.reg.unregister("ghost")

    def test_unregister_broken_shutdown_does_not_raise(self) -> None:
        """Plugin shutdown failure must not corrupt global state."""
        manifest = PluginManifest(name="broken", version="1.0.0")
        self.reg.register(manifest, BrokenShutdownPlugin())
        # Should not raise even though shutdown() throws
        self.reg.unregister("broken")
        assert self.reg.get("broken") is None

    def test_list_plugins(self) -> None:
        m1 = PluginManifest(name="a", version="1.0.0")
        m2 = PluginManifest(name="b", version="2.0.0")
        self.reg.register(m1, FakePlugin())
        self.reg.register(m2, FakePlugin())
        manifests = self.reg.list_plugins()
        names = {m.name for m in manifests}
        assert names == {"a", "b"}

    def test_clear(self) -> None:
        p1 = FakePlugin("p1")
        p2 = FakePlugin("p2")
        self.reg.register(PluginManifest(name="p1", version="1.0.0"), p1)
        self.reg.register(PluginManifest(name="p2", version="1.0.0"), p2)
        self.reg.clear()
        assert self.reg.list_plugins() == []
        assert p1.shut_down is True
        assert p2.shut_down is True


# ---------------------------------------------------------------------------
# Capability-based discovery
# ---------------------------------------------------------------------------


class TestPluginDiscovery:
    def setup_method(self) -> None:
        self.reg = PluginRegistry()

    def test_discover_single_capability(self) -> None:
        plugin = FakePlugin()
        manifest = PluginManifest(
            name="docx-src", version="1.0.0", capabilities=["source:docx"]
        )
        self.reg.register(manifest, plugin)
        found = self.reg.discover("source:docx")
        assert found == [plugin]

    def test_discover_no_match(self) -> None:
        manifest = PluginManifest(
            name="html-src", version="1.0.0", capabilities=["source:html"]
        )
        self.reg.register(manifest, FakePlugin())
        assert self.reg.discover("source:docx") == []

    def test_discover_multiple_plugins(self) -> None:
        p1 = FakePlugin("p1")
        p2 = FakePlugin("p2")
        self.reg.register(
            PluginManifest(name="a", version="1.0.0", capabilities=["normalizer:clean"]),
            p1,
        )
        self.reg.register(
            PluginManifest(name="b", version="1.0.0", capabilities=["normalizer:clean", "extractor:ner"]),
            p2,
        )
        found = self.reg.discover("normalizer:clean")
        assert set(id(p) for p in found) == {id(p1), id(p2)}

    def test_discover_specific_capability(self) -> None:
        p1 = FakePlugin("p1")
        p2 = FakePlugin("p2")
        self.reg.register(
            PluginManifest(name="a", version="1.0.0", capabilities=["source:docx"]),
            p1,
        )
        self.reg.register(
            PluginManifest(name="b", version="1.0.0", capabilities=["extractor:ner"]),
            p2,
        )
        assert self.reg.discover("extractor:ner") == [p2]
        assert self.reg.discover("source:docx") == [p1]


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestPluginRegistryThreadSafety:
    def test_concurrent_register(self) -> None:
        """Registering many plugins concurrently should not lose any."""
        reg = PluginRegistry()
        errors: list[Exception] = []

        def register_one(i: int) -> None:
            try:
                m = PluginManifest(name=f"plugin-{i}", version="1.0.0", capabilities=["test"])
                reg.register(m, FakePlugin(f"p{i}"))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=register_one, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(reg.list_plugins()) == 50


# ---------------------------------------------------------------------------
# Global registry singleton
# ---------------------------------------------------------------------------


class TestGlobalRegistry:
    def setup_method(self) -> None:
        # Clean global registry before each test
        registry.clear()

    def test_global_registry_is_plugin_registry(self) -> None:
        assert isinstance(registry, PluginRegistry)

    def test_global_register_and_discover(self) -> None:
        m = PluginManifest(name="global-test", version="0.1.0", capabilities=["test:cap"])
        plugin = FakePlugin()
        registry.register(m, plugin)
        assert registry.discover("test:cap") == [plugin]
        registry.clear()
