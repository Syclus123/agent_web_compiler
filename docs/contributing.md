# Contributing to agent-web-compiler

Thank you for considering contributing to agent-web-compiler! This guide will help you get started.

## Development Setup

```bash
git clone https://github.com/anthropics/agent-web-compiler.git
cd agent-web-compiler
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Optional extras

```bash
pip install -e ".[pdf]"       # PDF support (pymupdf)
pip install -e ".[browser]"   # Playwright rendering
pip install -e ".[serve]"     # REST + MCP servers
pip install -e ".[all]"       # Everything
```

## Running Tests

```bash
# All tests (fast, offline)
pytest

# Specific module
pytest tests/unit/test_segmenter.py -v

# Skip integration tests
pytest -m "not integration"

# With coverage
pytest --cov=agent_web_compiler
```

## Running Linter

```bash
ruff check agent_web_compiler/ tests/ bench/
ruff check --fix  # Auto-fix
```

## Running Benchmarks

```bash
awc bench run --fixtures-dir bench/tasks/
```

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full overview. Key principles:

### Pipeline Shape (8 stages)
```
ingest → render → normalize → segment → extract → align → validate → emit
```

### Module Boundaries
```
core/           Domain models, typed errors, interfaces
pipeline/       Orchestration (HTML, PDF, DOCX, API compilers)
sources/        HTTP fetcher, file reader, Playwright
normalizers/    Boilerplate removal
segmenters/     Semantic block splitting, salience scoring, query filtering
extractors/     Action affordance extraction
aligners/       DOM + screenshot provenance mapping
exporters/      JSON, markdown, debug bundles
plugins/        Plugin registry, protocol base classes
serving/        REST API, MCP server
cli/            Command-line interface
```

### Key Design Rules

1. **Typed contracts** — All schemas are Pydantic models with explicit versioning
2. **Composition over inheritance** — Pipeline stages are independent, composable functions
3. **Fail loudly** — Typed errors with context, never silent failures
4. **Extension via plugins** — New sources/normalizers/extractors implement small protocols
5. **Optional heavy deps** — Playwright, PDF backends, ML models behind extras

## Writing a Plugin

```python
from agent_web_compiler.plugins.base import SourcePlugin
from agent_web_compiler.plugins.registry import PluginManifest, registry

class MyPlugin:
    manifest = PluginManifest(
        name="my-source",
        version="0.1.0",
        capabilities=["source:custom"],
        description="My custom source plugin",
    )

    def initialize(self, config): pass
    def shutdown(self): pass
    def can_handle(self, source): return source.startswith("custom://")
    def fetch(self, source, config): ...

# Register
registry.register(plugin.manifest, plugin)
```

## Submitting Changes

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Add/update tests
5. Run `pytest` and `ruff check`
6. Submit a pull request

### Commit Messages

- Use imperative mood: "Add X" not "Added X"
- First line: concise summary (< 72 chars)
- Body: explain why, not just what

### Definition of Done

- [ ] Code is correct and clear
- [ ] Tests cover intended and regression behavior
- [ ] Docs updated if behavior changed
- [ ] Config is typed and validated
- [ ] No unnecessary dependency introduced
- [ ] Lint passes (`ruff check`)

## Code Style

- Use `from __future__ import annotations` in all files
- Prefer pure functions over hidden state
- Use Pydantic for data structures, dataclass for internal-only types
- Avoid broad catch-all exceptions
- Add comments only for intent, invariants, or non-obvious trade-offs

## Questions?

Open an issue or start a discussion. We're happy to help!
