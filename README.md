# agent-web-compiler

**Compile the Human Web into the Agent Web.**

Turn webpages, PDFs, and documents into **agent-native objects** with semantic blocks, action affordances, and grounded provenance. Built for browser agents, RAG pipelines, and agentic search — not just another scraper or markdown converter.

```
                          agent-web-compiler

  Input Sources          Pipeline                    Agent Consumers
 ┌────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
 │  Webpages  │    │  Fetch & Render     │    │                     │
 │  PDFs      │───>│  Normalize & Clean  │    │  OpenAI CUA         │
 │  DOCX      │    │         │           │    │  Claude Computer Use│
 │  JSON APIs │    │    ┌────┴────┐      │───>│  Browser Use        │
 └────────────┘    │    │         │      │    │  LangChain / RAG    │
                   │ Content  Action     │    │  MCP Clients        │
                   │ Parser   Parser     │    │  Research Agents    │
                   │    │         │      │    │                     │
                   │    └────┬────┘      │    └─────────────────────┘
                   │   Provenance Map    │
                   │   + Validate        │
                   │         │           │
                   │   AgentDocument     │
                   └─────────────────────┘
```

> **Benchmark result**: On 15 diverse webpages, AWC saves **27% tokens** vs raw HTML, discovers **377 actions** that naive markdown extraction misses entirely, and reduces noise ratio to near 0%.

## Features

**Core Compilation**
- **Semantic block extraction** — 14 block types: headings, paragraphs, tables, code, lists, quotes, figures, FAQs, metadata
- **Action affordance extraction** — buttons, links, forms, inputs with role inference, state effect prediction, and form field grouping
- **Provenance tracking** — DOM path, character ranges, screenshot bounding boxes back to source
- **Entity extraction** — dates, prices, emails, URLs, phone numbers, percentages annotated per block
- **Navigation graph** — page state transitions, form flows, pagination chains modeled from actions

**Intelligence**
- **Advanced salience scoring** — 10-feature importance model with configurable weights
- **Query-aware compilation** — TF-IDF relevance filtering with section matching and heading proximity
- **Intelligent token budget** — 6-level progressive compression (paragraph truncation → table compression → code truncation → list compression → section collapsing → block dropping)
- **Site profile learning** — cross-page template detection, shared boilerplate removal, persistent profiles

**Output Formats**
- **5 LLM-optimized formatters** — AXTree (for CUA), XML (for Claude), function-call (for OpenAI), compact, agent-prompt
- **Canonical markdown + JSON** — structured, versioned, typed output from a single compile call
- **Streaming compilation** — yield blocks incrementally with early termination on token budget

**Ecosystem Integration**
- **Framework adapters** — OpenAI CUA, Claude Computer Use, Browser Use, LangChain (zero framework dependencies)
- **Browser agent middleware** — compiler-first + browser-fallback pattern with page history tracking
- **MCP server** — 6 tools for Claude Desktop, Cursor, and MCP-compatible clients
- **REST API** — FastAPI with 7 endpoints including SSE streaming
- **Plugin system** — typed interfaces, capability-based registry, entry-point discovery
- **Batch compilation** — parallel multi-URL compilation with shared site profiles

**Input Sources**
- HTML (static + JavaScript-rendered via Playwright)
- PDF (via PyMuPDF, with optional Docling backend)
- DOCX (via python-docx)
- JSON API responses
- Local files

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
    print(f"[{block.type.value}] {block.text[:80]}")

# Access actions
for action in doc.actions:
    print(f"[{action.type.value}] {action.label} -> {action.selector}")

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

# Batch compile multiple URLs
awc compile url1 url2 url3 -o output/

# Inspect a compiled document
awc inspect output/agent_document.json

# Start MCP server
awc serve --transport mcp

# Start REST API
awc serve --transport rest --port 8000

# Run benchmarks
awc bench run
awc bench compare
```

### Query-Aware Compilation

Focus on what matters — filter and boost blocks by query relevance:

```python
from agent_web_compiler import compile_html
from agent_web_compiler.core.config import CompileConfig

doc = compile_html(html, config=CompileConfig(
    query="rate limits API",   # Boost relevant blocks
    max_blocks=20,             # Token budget control
    min_importance=0.3,        # Filter noise
    token_budget=4000,         # Intelligent progressive compression
))
```

### Streaming Compilation

```python
from agent_web_compiler import compile_stream

# Stream blocks as they're extracted — ideal for large documents
for event in compile_stream(html, token_budget=4000):
    if event.event_type == "block":
        process_block(event.data)
    elif event.event_type == "budget_reached":
        break  # Stop early when token budget is reached
    elif event.event_type == "complete":
        final_doc = event.data
```

### Batch Compilation

```python
from agent_web_compiler import compile_batch

# Compile multiple URLs with shared site profiles
results = compile_batch([
    {"source": "https://example.com/page1"},
    {"source": "https://example.com/page2"},
    {"source": "https://example.com/page3"},
])
# Same-domain pages share learned site profiles for better denoising
for doc in results.items:
    print(f"{doc.title}: {doc.block_count} blocks")
```

## Framework Integration

agent-web-compiler provides zero-friction adapters for popular agent frameworks — no framework dependencies required.

### OpenAI CUA / Function Calling

```python
from agent_web_compiler import compile_url
from agent_web_compiler.adapters.openai_adapter import OpenAIAdapter

doc = compile_url("https://example.com")
adapter = OpenAIAdapter()

# Get accessibility tree observation for CUA
observation = adapter.to_cua_observation(doc)

# Convert actions to OpenAI tool definitions
tools = adapter.to_tool_definitions(doc)

# Format as chat messages
messages = adapter.to_chat_messages(doc)
```

### Claude Computer Use

```python
from agent_web_compiler import compile_html
from agent_web_compiler.adapters.anthropic_adapter import AnthropicAdapter

doc = compile_html(page_html, source_url=url)
adapter = AnthropicAdapter()

# Get XML content (Claude's optimal structured format)
xml_content = adapter.to_xml_content(doc)

# Get computer_use tool result format
result = adapter.to_computer_use_result(doc)

# Get Anthropic tool definitions
tools = adapter.to_tool_definitions(doc)
```

### Browser Use

```python
from agent_web_compiler import compile_html
from agent_web_compiler.adapters.browser_use_adapter import BrowserUseAdapter

doc = compile_html(page_html, source_url=url)
adapter = BrowserUseAdapter()

# Get structured page context
context = adapter.get_page_context(doc)

# Get action plan for a task
plan = adapter.get_action_plan(doc, task="search for headphones")

# Get form filling guidance
form_guide = adapter.get_form_fill_guide(doc)
```

### Browser Agent Middleware

```python
from agent_web_compiler.middleware.browser_middleware import BrowserMiddleware

middleware = BrowserMiddleware()

# On every page load: auto-compile and provide structured context
ctx = middleware.on_page_load(url, html, screenshot=screenshot_bytes)
llm_input = ctx.to_llm_prompt()  # Replace raw screenshot with structured representation

# When LLM decides to act: translate to browser command
command = middleware.translate_action("a_001_submit")
# → {"type": "fill", "selector": "#search", "value": "..."}

# Track history across page visits
summary = middleware.get_history_summary()

# Only fall back to screenshot when compilation confidence is low
if middleware.needs_screenshot_fallback():
    use_screenshot_instead()
```

### LangChain / LlamaIndex

```python
from agent_web_compiler.adapters.langchain_adapter import AWCTool, AWCDocumentLoader

# As an agent tool
tool = AWCTool()
result = tool._run("https://docs.example.com/api")  # Returns structured summary

# As a document loader for RAG
loader = AWCDocumentLoader()
documents = loader.load("https://docs.example.com/api")
# Each block → Document with metadata: type, section_path, importance, provenance
```

### LLM-Optimized Output Formats

```python
from agent_web_compiler.exporters.llm_formatters import format_for_llm

doc = compile_url("https://example.com")

# Accessibility tree (for CUA agents)
print(format_for_llm(doc, format="axtree"))

# XML (optimal for Claude)
print(format_for_llm(doc, format="xml"))

# OpenAI function-calling schema
print(format_for_llm(doc, format="function_call"))

# Ultra-compact (< 500 tokens)
print(format_for_llm(doc, format="compact"))

# Full agent system prompt
print(format_for_llm(doc, format="agent_prompt"))
```

See [examples/integrations/](examples/integrations/) for complete examples.

### MCP Server

Integrate directly with Claude Desktop, Cursor, or any MCP-compatible client:

```bash
awc serve --transport mcp
```

Add to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "web-compiler": {
      "command": "awc",
      "args": ["serve", "--transport", "mcp"]
    }
  }
}
```

Available MCP tools: `compile_url`, `compile_html`, `compile_file`, `get_blocks`, `get_actions`, `get_markdown`.

### REST API

```bash
awc serve --transport rest --port 8000
```

Endpoints:
| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/compile` | Full AgentDocument |
| POST | `/v1/compile/markdown` | Markdown only |
| POST | `/v1/compile/blocks` | Filtered blocks |
| POST | `/v1/compile/actions` | Filtered actions |
| POST | `/v1/compile/stream` | SSE streaming |
| GET | `/health` | Health check |
| GET | `/schema` | AgentDocument JSON schema |

## Output Schema

Every compilation produces an `AgentDocument` — a typed, versioned object:

```
AgentDocument (v0.4.0)
├── schema_version       "0.4.0"
├── doc_id               "sha256:a1b2c3d4..."
├── source_type          "html" | "pdf" | "docx" | "api"
├── source_url           "https://..."
├── title                "Page Title"
├── lang                 "en"
├── fetched_at / compiled_at
│
├── blocks[]             Semantic content blocks
│   ├── id               "b_001"
│   ├── type             heading | paragraph | table | code | list | quote | ...
│   ├── text             "Plain text content"
│   ├── section_path     ["Methods", "Training Setup"]
│   ├── importance       0.85
│   ├── metadata         {entities: [...], language: "python", row_count: 5, ...}
│   ├── provenance       {dom, page, screenshot}
│   └── children[]
│
├── actions[]            Interactive affordances
│   ├── type             click | input | submit | navigate | select | toggle | ...
│   ├── label            "Search"
│   ├── selector         "#search-btn"
│   ├── role             "submit_search"
│   ├── required_fields  ["q"]
│   ├── value_schema     {"q": "text"}
│   ├── confidence       0.92
│   ├── priority         0.9
│   ├── state_effect     {may_navigate, may_open_modal, target_url}
│   └── provenance       {dom}
│
├── navigation_graph     Page state transitions (nodes + edges)
├── assets[]             Referenced images, stylesheets, scripts
├── provenance_index     Section path → block IDs reverse lookup
├── canonical_markdown   Clean markdown rendering
├── quality              {parse_confidence, warnings[], block_count, action_count}
└── debug{}              Timings, intermediates (when enabled)
```

See [docs/schema.md](docs/schema.md) for the full reference.

## Comparison

Tested on 15 diverse webpages (articles, product pages, search results, dashboards, forms, docs, forums):

| Feature | Raw HTML | Markdown Scraper | agent-web-compiler |
|---|---|---|---|
| Avg token count | 948 | 692 | **692** (27% savings vs HTML) |
| Semantic blocks | ✗ | ✗ | **✓** (typed with hierarchy) |
| Action discovery | ✗ | ✗ | **377 actions** across 15 pages |
| Provenance | ✗ | ✗ | **✓** (DOM path, char ranges, bbox) |
| Entity extraction | ✗ | ✗ | **✓** (dates, prices, URLs, phones) |
| Tables | Raw `<table>` tags | Lossy text | **Structured** (headers + rows) |
| Code detection | ✗ | Basic | **✓** (language-tagged) |
| Importance scoring | ✗ | ✗ | **✓** (10-feature salience model) |
| Navigation graph | ✗ | ✗ | **✓** (reachable pages, form flows) |
| Noise ratio | High | 5-35% | **~0%** |
| CUA/Agent format | ✗ | ✗ | **5 LLM formats** (AXTree, XML, function-call, compact, prompt) |

## Architecture

agent-web-compiler uses an **8-stage pipeline**. Each stage has a typed interface and can be extended or replaced independently.

```
ingest → render → normalize → segment → extract → align → validate → emit
```

| Stage | What it does |
|---|---|
| **Ingest** | Fetch content from URL, file, or raw input (HTTP, Playwright, local file) |
| **Render** | Optionally render JS-heavy pages via Playwright (auto-detects SPAs) |
| **Normalize** | Strip scripts, remove boilerplate, apply site profile templates |
| **Segment** | Split into typed semantic blocks with salience scoring and entity extraction |
| **Extract** | Pull out actions (with form grouping), assets, navigation graph |
| **Align** | Map blocks/actions back to source with DOM + screenshot provenance |
| **Validate** | Check quality, detect duplicates, compute confidence, generate warnings |
| **Emit** | AgentDocument, JSON, markdown, LLM formats, debug bundles, SSE stream |

```
agent_web_compiler/
├── core/           Schemas, domain models, interfaces, typed errors
├── pipeline/       Orchestration: HTML, PDF, DOCX, API, streaming compilers + cache
├── sources/        HTTP fetcher, Playwright fetcher, file reader
├── normalizers/    Boilerplate removal, site profile learning
├── segmenters/     Semantic blocking, salience scoring, query filtering
├── extractors/     Actions, entities, assets, navigation graph
├── aligners/       DOM provenance, screenshot alignment
├── exporters/      JSON, markdown, debug bundles, token budget, LLM formatters
├── adapters/       OpenAI, Anthropic, Browser Use, LangChain adapters
├── middleware/     Browser agent middleware (compiler-first, browser-fallback)
├── plugins/        Plugin registry, protocol base classes
├── serving/        MCP server, REST API
└── cli/            Command-line interface
```

See [docs/architecture.md](docs/architecture.md) for details.

## Installation

```bash
# Core (HTML compilation, CLI)
pip install agent-web-compiler

# With PDF support
pip install "agent-web-compiler[pdf]"

# With DOCX support
pip install "agent-web-compiler[docx]"

# With browser rendering (Playwright)
pip install "agent-web-compiler[browser]"

# With API server (REST + MCP)
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

# Run tests (637 tests, ~2s, all offline)
pytest

# Run linter
ruff check .

# Run benchmarks
awc bench run
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
    query="search query",            # Query-aware filtering
    min_importance=0.1,
    max_blocks=200,
    token_budget=4000,               # Progressive compression target
    timeout_seconds=30.0,
    cache_dir="/tmp/awc-cache",      # Disk-backed caching
    debug=True,
)

doc = compile_url("https://example.com", config=config)
```

## Contributing

We welcome contributions! See [docs/contributing.md](docs/contributing.md) for the full guide.

```bash
git clone https://github.com/anthropics/agent-web-compiler.git
cd agent-web-compiler
pip install -e ".[dev]"
pytest                    # Run all tests
ruff check .              # Lint
awc bench run             # Benchmarks
```

**Key principles** (from [CLAUDE.md](CLAUDE.md)):
- Keep code simple, explicit, and typed
- Prefer composition over inheritance
- Tests run offline by default
- Every bug fix adds a regression test
- Schema changes require migration notes
- Prefer clearer over fancier

## Roadmap

See [docs/roadmap.md](docs/roadmap.md) for the full roadmap.

**Current (v0.4.0):** Core compilation + intelligence + ecosystem integration complete
**Next (v0.5):** ML-based classifiers, multi-backend PDF fusion, expanded benchmarks
**Future:** `agent.json` specification, agent-native search index, Docker deployment

## License

[MIT](LICENSE)

## Related Projects

| Project | Focus | How AWC differs |
|---|---|---|
| [Firecrawl](https://github.com/mendableai/firecrawl) | Web scraping for LLMs | AWC adds actions, provenance, entity extraction |
| [Jina Reader](https://github.com/jina-ai/reader) | URL-to-markdown | AWC adds typed blocks, importance scoring, navigation graph |
| [Crawl4AI](https://github.com/unclecode/crawl4ai) | Async web crawling | AWC focuses on compilation quality, not crawling scale |
| [Docling](https://github.com/DS4SD/docling) | Document parsing | AWC unifies web + doc + API into one schema |
| [MinerU](https://github.com/opendatalab/MinerU) | PDF extraction | AWC can use MinerU as a backend, adds agent-native output |
| [Browser Use](https://github.com/browser-use/browser-use) | LLM browser automation | AWC provides pre-compiled affordances, reducing DOM analysis |
| [MCP](https://modelcontextprotocol.io/) | Model Context Protocol | AWC ships a built-in MCP server |

**agent-web-compiler** sits between content sources and agent frameworks as a **universal compilation layer** — producing a single typed object with semantic blocks, action affordances, provenance tracking, and importance scoring that any agent can consume.
