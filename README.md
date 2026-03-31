# agent-web-compiler

**Compile the Human Web into the Agent Web.**

Turn webpages, PDFs, and documents into **agent-native objects** with semantic blocks, action affordances, and grounded provenance. Built for the next generation of browser agents, RAG pipelines, and agentic search — not just another scraper or markdown converter.

```
                          agent-web-compiler

  Input Sources          Pipeline                    Agent Consumers
 ┌────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
 │  Webpages  │    │  Fetch & Render     │    │                     │
 │  PDFs      │───>│  Normalize & Clean  │    │  RAG / QA Agent     │
 │  HTML files│    │         │           │    │  Browser Agent      │
 │  Documents │    │    ┌────┴────┐      │───>│  Research Agent     │
 └────────────┘    │    │         │      │    │  Agent Search       │
                   │ Content  Action     │    │  MCP Server         │
                   │ Parser   Parser     │    │                     │
                   │    │         │      │    └─────────────────────┘
                   │    └────┬────┘      │
                   │   Provenance Map    │
                   │         │           │
                   │   AgentDocument     │
                   └─────────────────────┘
```

## Features

- **Semantic block extraction** — headings, paragraphs, tables, code, lists, quotes, figures, FAQs
- **Action affordance extraction** — buttons, links, forms, inputs with predicted side-effects
- **Provenance tracking** — DOM path, character ranges, bounding boxes back to source
- **Advanced salience scoring** — multi-feature importance ranking with configurable weights
- **Query-aware compilation** — TF-IDF relevance filtering, token budget control
- **Browser rendering** — Playwright integration for JavaScript-heavy pages (optional)
- **MCP server** — Model Context Protocol server for AI assistant integration
- **REST API** — FastAPI server with OpenAPI docs
- **Plugin system** — typed interfaces, capability-based registry, entry-point discovery
- **Canonical output** — structured JSON + clean markdown from a single compile call
- **Benchmark suite** — reproducible evaluation with token efficiency, content fidelity, action quality metrics
- **CLI + Python API** — one command or one function call to compile anything
- **PDF compilation** — native support via pymupdf, with optional Docling backend

## Quick Start

```bash
pip install agent-web-compiler
```

### Python API

```python
from agent_web_compiler import compile_url, compile_html

# Compile a URL
doc = compile_url("https://example.com")

# Compile raw HTML
doc = compile_html("<html><body><h1>Hello</h1><p>World</p></body></html>")

# Access semantic blocks
for block in doc.blocks:
    print(f"[{block.type}] {block.text[:80]}")

# Access actions
for action in doc.actions:
    print(f"[{action.type}] {action.label} -> {action.selector}")

# Get canonical markdown
print(doc.canonical_markdown)

# Filter by importance
main_content = doc.get_main_content(min_importance=0.5)

# Get a short summary
print(doc.summary_markdown(max_blocks=10))
```

### CLI

```bash
# Compile a webpage
awc compile https://example.com -o output/

# Compile a PDF
awc compile paper.pdf -o output/

# Compile with browser rendering for dynamic pages
awc compile https://spa-app.com --render auto -o output/

# Output JSON only
awc compile https://example.com --format json -o output/

# Inspect a compiled document
awc inspect output/agent_document.json
```

### Compile a local HTML file

```python
from agent_web_compiler.api.compile import compile_file

doc = compile_file("page.html")
print(f"Blocks: {doc.block_count}, Actions: {doc.action_count}")
```

### Query-Aware Compilation

Focus on what matters — filter and boost blocks by query relevance:

```python
from agent_web_compiler import compile_html
from agent_web_compiler.core.config import CompileConfig

doc = compile_html(html, config=CompileConfig(
    query="rate limits API",  # Boost relevant blocks
    max_blocks=20,            # Token budget control
    min_importance=0.3,       # Filter noise
))
```

### MCP Server

Integrate directly with Claude Desktop, Cursor, or any MCP-compatible client:

```bash
awc serve --transport stdio
```

Or add to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "web-compiler": {
      "command": "awc",
      "args": ["serve", "--transport", "stdio"]
    }
  }
}
```

Available MCP tools: `compile_url`, `compile_html`, `compile_file`, `get_blocks`, `get_actions`, `get_markdown`.

### REST API

```bash
# Start the server
awc serve --transport rest --port 8000

# Compile a URL
curl -X POST http://localhost:8000/v1/compile \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "mode": "balanced"}'
```

### Benchmark Suite

```bash
# Run benchmarks against built-in fixtures
awc bench run --fixtures-dir bench/tasks/
```

## Output Schema

Every compilation produces an `AgentDocument` — a typed, versioned object:

```
AgentDocument
├── schema_version    "0.1.0"
├── doc_id            "sha256:a1b2c3d4..."
├── source_type       "html" | "pdf" | "docx" | "api" | "image_pdf"
├── source_url        "https://..."
├── title             "Page Title"
├── lang              "en"
├── fetched_at        "2026-03-30T12:00:00Z"
├── compiled_at       "2026-03-30T12:00:01Z"
│
├── blocks[]          Semantic content blocks
│   ├── id            "b_001"
│   ├── type          "heading" | "paragraph" | "table" | "code" | ...
│   ├── text          "Plain text content"
│   ├── section_path  ["Methods", "Training Setup"]
│   ├── importance    0.85
│   ├── provenance    { dom, page, screenshot }
│   └── children[]    Nested blocks
│
├── actions[]         Interactive affordances
│   ├── id            "a_search_submit"
│   ├── type          "click" | "input" | "submit" | "navigate" | ...
│   ├── label         "Search"
│   ├── selector      "button#search-btn"
│   ├── role          "submit_search"
│   ├── confidence    0.92
│   ├── state_effect  { may_navigate, may_open_modal, target_url }
│   └── provenance    { dom }
│
├── canonical_markdown   Clean markdown rendering
├── quality
│   ├── parse_confidence  0.95
│   ├── block_count       42
│   ├── action_count      7
│   └── warnings[]        ["table_parse_degraded", ...]
│
└── debug{}           Timings, intermediates (when enabled)
```

See [docs/schema.md](docs/schema.md) for the full schema reference.

## Comparison

| Feature | Raw HTML | Markdown Scraper | agent-web-compiler |
|---|---|---|---|
| Token efficiency | Poor (tags, scripts, styles) | Good | Good (canonical markdown) |
| Semantic blocks | None | Flat text | Typed blocks with hierarchy |
| Action extraction | None | None | Buttons, forms, links, inputs |
| Provenance | N/A | None | DOM path, char ranges, bbox |
| Tables | Raw `<table>` tags | Lossy conversion | Structured with metadata |
| Code detection | None | Basic | Language-tagged blocks |
| Importance scoring | None | None | Per-block salience [0, 1] |
| Schema versioned | No | No | Yes |

## Architecture

agent-web-compiler uses an **8-stage pipeline**. Each stage has a typed interface and can be extended or replaced independently.

```
ingest → render → normalize → segment → extract → align → validate → emit
```

| Stage | What it does |
|---|---|
| **Ingest** | Fetch content from URL, file, or raw input |
| **Render** | Optionally render dynamic pages via browser (Playwright) |
| **Normalize** | Clean HTML: strip scripts, fix encoding, remove boilerplate |
| **Segment** | Split content into typed semantic blocks |
| **Extract** | Pull out actions, metadata, tables, code, links |
| **Align** | Map blocks/actions back to source with provenance |
| **Validate** | Check output quality, flag warnings, compute confidence |
| **Emit** | Produce AgentDocument, JSON, markdown, debug bundles |

See [docs/architecture.md](docs/architecture.md) for details.

## For Agent Developers

### Browser Agents

Feed your agent structured actions instead of raw DOM:

```python
doc = compile_url("https://shopping-site.com", render="auto")

for action in doc.actions:
    if action.role == "add_to_cart":
        agent.click(action.selector)
```

### RAG Pipelines

Index semantic blocks with provenance for grounded retrieval:

```python
doc = compile_url("https://docs.example.com/api-reference")

for block in doc.get_main_content(min_importance=0.3):
    vector_store.add(
        text=block.text,
        metadata={
            "type": block.type,
            "section": block.section_path,
            "source": doc.source_url,
            "dom_path": block.provenance.dom.dom_path if block.provenance else None,
        },
    )
```

### Research Agents

Compile papers and reports, preserving structure:

```python
from agent_web_compiler.api.compile import compile_file

doc = compile_file("paper.pdf")

tables = doc.get_blocks_by_type("table")
headings = doc.get_blocks_by_type("heading")
```

### Agent Search

Compile search result pages into structured, actionable data:

```python
doc = compile_url("https://search-engine.com/search?q=agent+frameworks")

results = doc.get_blocks_by_type("paragraph")
next_page = [a for a in doc.actions if a.role == "next_page"]
```

## Installation

```bash
# Core (HTML compilation, CLI)
pip install agent-web-compiler

# With PDF support
pip install "agent-web-compiler[pdf]"

# With browser rendering (Playwright)
pip install "agent-web-compiler[browser]"

# With Docling PDF backend
pip install "agent-web-compiler[docling]"

# With API server
pip install "agent-web-compiler[serve]"

# Everything
pip install "agent-web-compiler[all]"
```

**Requirements:** Python 3.9+

### From source

```bash
git clone https://github.com/anthropics/agent-web-compiler.git
cd agent-web-compiler
pip install -e ".[dev]"
```

## Configuration

All compilation behavior is controlled through typed config — no hidden globals or magic environment variables.

```python
from agent_web_compiler.core.config import CompileConfig, CompileMode, RenderMode

config = CompileConfig(
    mode=CompileMode.HIGH_RECALL,    # fast | balanced | high_recall
    render=RenderMode.AUTO,          # off | auto | always
    include_actions=True,
    include_provenance=True,
    min_importance=0.1,
    max_blocks=200,
    timeout_seconds=30.0,
    debug=True,
)

doc = compile_url("https://example.com", config=config)
```

## Contributing

We welcome contributions. It is required to adhere to the architectural principles and coding standards.


```bash
# Setup
git clone https://github.com/anthropics/agent-web-compiler.git
cd agent-web-compiler
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check .

# Run type checker
mypy agent_web_compiler/
```

**Key principles:**
- Keep code simple, explicit, and typed
- Prefer composition over inheritance
- Tests run offline by default
- Every bug fix adds a regression test
- Schema changes require migration notes

## License

[MIT](LICENSE)

## Related Projects

| Project | Focus |
|---|---|
| [Firecrawl](https://github.com/mendableai/firecrawl) | Web scraping for LLMs |
| [Jina Reader](https://github.com/jina-ai/reader) | URL-to-markdown for LLMs |
| [Crawl4AI](https://github.com/unclecode/crawl4ai) | Async web crawling for AI |
| [Docling](https://github.com/DS4SD/docling) | Document parsing |
| [MinerU](https://github.com/opendatalab/MinerU) | PDF extraction |
| [Browser Use](https://github.com/browser-use/browser-use) | LLM browser automation |
| [MCP](https://modelcontextprotocol.io/) | Model Context Protocol |

**agent-web-compiler** differs from these by producing a **single typed object** with semantic blocks, action affordances, provenance tracking, and importance scoring — designed as a compiler, not a scraper.
