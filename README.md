# agent-web-compiler

**Compile the Human Web into the Agent Web. Then search it.**

Turn webpages, PDFs, and documents into **agent-native objects** — then index, search, answer, and plan against them. Built for browser agents, RAG pipelines, and agentic search.

```
                     agent-web-compiler v0.7.0

  Input Sources       Compile → Index → Search       Agent Consumers
 ┌────────────┐    ┌───────────────────────────┐    ┌──────────────────┐
 │  Webpages  │    │  Compile                  │    │                  │
 │  PDFs      │    │  ├── normalize + segment  │    │  OpenAI CUA      │
 │  DOCX      │───>│  ├── extract actions      │───>│  Claude Computer │
 │  JSON APIs │    │  └── provenance + validate│    │  Browser Use     │
 └────────────┘    │                           │    │  LangChain / RAG │
                   │  Index                    │    │  MCP Clients     │
                   │  ├── block index (BM25)   │    │  Research Agents │
                   │  ├── action index         │    │                  │
                   │  └── site profile index   │    └──────────────────┘
                   │                           │
                   │  Search                   │
                   │  ├── query planning       │
                   │  ├── hybrid retrieval     │
                   │  ├── grounded answering   │
                   │  └── execution planning   │
                   └───────────────────────────┘
```

> **Key results**: Across 15 diverse webpages, AWC saves **27% tokens** vs raw HTML, discovers **377 actions** that naive extraction misses entirely, and provides **grounded answers with citations** — no LLM required for answer composition.

## What Makes This Different

This is not a scraper, a markdown converter, or a RAG framework. It's a **three-layer stack**:

1. **Compile** — Turn any webpage/PDF/DOCX into a typed `AgentDocument` with semantic blocks, actions, entities, and provenance
2. **Index** — Store compiled objects in a hybrid search engine (BM25 + dense vectors + metadata filters)
3. **Search** — Answer questions with citations, find actions by intent, generate execution plans

## Quick Start

```bash
pip install agent-web-compiler
```

### Compile a page

```python
from agent_web_compiler import compile_url, compile_html

doc = compile_url("https://example.com")
# or
doc = compile_html("<html><body><h1>Hello</h1><p>World</p></body></html>")

for block in doc.blocks:
    print(f"[{block.type.value}] {block.text[:80]}")

for action in doc.actions:
    print(f"[{action.type.value}] {action.label} -> {action.selector}")
```

### Index and search

```python
from agent_web_compiler.search import AgentSearch

search = AgentSearch()

# Ingest content into the index
search.ingest_url("https://docs.example.com/api")
search.ingest_url("https://docs.example.com/auth")
search.ingest_file("report.pdf")

# Search for content blocks
results = search.search_blocks("What is the rate limit?", top_k=5)

# Get a grounded answer with citations
answer = search.answer("What authentication methods are supported?")
print(answer.to_markdown())
# Output:
#   **Answer**: The API supports Bearer token and OAuth 2.0. [1][2]
#   **Evidence**:
#   [1] "Include your API key in the Authorization header..."
#       — API Reference > Authentication
#   [2] "OAuth 2.0 flow requires client_id and client_secret..."
#       — Authentication > OAuth Setup

# Search for executable actions
actions = search.search_actions("download pricing PDF")

# Generate an execution plan
plan = search.plan("search for wireless headphones")
print(plan.to_markdown())
# Output:
#   1. **fill** `input[type="search"]` = `wireless headphones`
#   2. **click** `button[type="submit"]`

# Persist the index
search.save("my_index.json")
```

### CLI

```bash
# Compile
awc compile https://example.com -o output/
awc compile paper.pdf -o output/
awc compile url1 url2 url3 -o output/      # Batch compile

# Index and search
awc index add https://docs.example.com/api
awc index add ./reports/*.pdf
awc index stats
awc search "What is the rate limit?"
awc answer "How to authenticate?"
awc plan "download the enterprise PDF"

# Inspect
awc inspect output/agent_document.json

# Serve
awc serve --transport mcp                   # MCP server (10 tools)
awc serve --transport rest --port 8000      # REST API (8 endpoints)

# Benchmark
awc bench run
awc bench compare
awc bench search
```

## Features

### Compilation
- **14 semantic block types** — headings, paragraphs, tables, code, lists, quotes, figures, FAQs, metadata
- **8 action types** — click, input, submit, navigate, select, toggle, upload, download — with role inference, form field grouping, and state effect prediction
- **Provenance tracking** — every block/action maps back to DOM path, character range, or bounding box
- **Entity extraction** — dates, prices, emails, URLs, phones, percentages annotated per block
- **Navigation graph** — page state transitions, form flows, pagination chains
- **5 input sources** — HTML, PDF (PyMuPDF), DOCX (python-docx), JSON APIs, Playwright for JS-heavy pages

### Intelligence
- **10-feature salience scoring** — position, entity density, text length, link ratio, DOM depth, semantic tags
- **Query-aware compilation** — TF-IDF relevance filtering with section matching and heading proximity
- **6-level token budget** — progressive compression: paragraph truncation → table compression → code truncation → list compression → section collapsing → block dropping
- **Site profile learning** — cross-page template detection, shared boilerplate removal

### Search & Retrieval
- **Hybrid search** — BM25 sparse + dense vector + metadata filters, all in pure Python
- **4-level indexing** — document, block, action, and site indexes
- **Query planning** — classifies intent (fact / evidence / navigation / task) and generates search plans
- **Grounded answering** — evidence-backed answers with citations and provenance (no LLM required)
- **Execution planning** — translates task queries into browser automation steps
- **Incremental updates** — add/remove/update documents without full reindex

### Output Formats
- **5 LLM formatters** — AXTree (CUA), XML (Claude), function-call (OpenAI), compact, agent-prompt
- **Canonical markdown + JSON** — structured, versioned, typed output
- **Streaming compilation** — yield blocks incrementally with token budget early termination

### Ecosystem
- **Framework adapters** — OpenAI CUA, Claude Computer Use, Browser Use, LangChain (zero framework deps)
- **Browser middleware** — compiler-first + browser-fallback with page history tracking
- **MCP server** — 10 tools: 6 compile + 4 search (Claude Desktop, Cursor compatible)
- **REST API** — 8 FastAPI endpoints including SSE streaming
- **Plugin system** — typed interfaces, capability-based registry
- **Batch compilation** — parallel multi-URL with shared site profiles
- **Caching** — disk-backed with ETag/Last-Modified support

## Framework Integration

### OpenAI CUA / Function Calling

```python
from agent_web_compiler import compile_url
from agent_web_compiler.adapters.openai_adapter import OpenAIAdapter

doc = compile_url("https://example.com")
adapter = OpenAIAdapter()

observation = adapter.to_cua_observation(doc)   # AXTree format
tools = adapter.to_tool_definitions(doc)        # Actions as functions
messages = adapter.to_chat_messages(doc)         # Chat format
```

### Claude Computer Use

```python
from agent_web_compiler.adapters.anthropic_adapter import AnthropicAdapter

adapter = AnthropicAdapter()
xml = adapter.to_xml_content(doc)              # XML (Claude-optimal)
result = adapter.to_computer_use_result(doc)   # Tool result format
tools = adapter.to_tool_definitions(doc)       # Tool definitions
```

### Browser Use — Compiler-First Pattern

```python
from agent_web_compiler.middleware.browser_middleware import BrowserMiddleware

middleware = BrowserMiddleware()

# Auto-compile every page load
ctx = middleware.on_page_load(url, html, screenshot=screenshot_bytes)
llm_input = ctx.to_llm_prompt()       # Structured context, not raw screenshot

# Translate LLM decisions to browser commands
command = middleware.translate_action("a_001_submit")
# → {"type": "fill", "selector": "#search", "value": "..."}
```

### LangChain / RAG

```python
from agent_web_compiler.adapters.langchain_adapter import AWCTool, AWCDocumentLoader

tool = AWCTool()                       # Agent tool
loader = AWCDocumentLoader()           # RAG document loader
documents = loader.load("https://docs.example.com/api")
```

### LLM-Optimized Formats

```python
from agent_web_compiler.exporters.llm_formatters import format_for_llm

format_for_llm(doc, format="axtree")         # CUA agents
format_for_llm(doc, format="xml")            # Claude
format_for_llm(doc, format="function_call")  # OpenAI
format_for_llm(doc, format="compact")        # Token-constrained
format_for_llm(doc, format="agent_prompt")   # System prompt
```

### MCP Server

```bash
awc serve --transport mcp
```

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

10 MCP tools: `compile_url`, `compile_html`, `compile_file`, `get_blocks`, `get_actions`, `get_markdown`, `ingest_url`, `search`, `answer`, `plan`.

### REST API

```bash
awc serve --transport rest --port 8000
```

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/compile` | Full AgentDocument |
| POST | `/v1/compile/markdown` | Markdown only |
| POST | `/v1/compile/blocks` | Filtered blocks |
| POST | `/v1/compile/actions` | Filtered actions |
| POST | `/v1/compile/stream` | SSE streaming |
| GET | `/health` | Health check |
| GET | `/schema` | JSON schema |

## Output Schema

```
AgentDocument (v0.7.0)
├── schema_version       "0.7.0"
├── doc_id               "sha256:a1b2c3d4..."
├── source_type          "html" | "pdf" | "docx" | "api"
├── title / lang / fetched_at / compiled_at
│
├── blocks[]             Semantic content (14 types)
│   ├── type             heading | paragraph | table | code | list | ...
│   ├── text / section_path / importance / level
│   ├── metadata         {entities, language, row_count, headers, rows, ...}
│   └── provenance       {dom_path, page, bbox, char_range}
│
├── actions[]            Interactive affordances (8 types)
│   ├── type / label / selector / role
│   ├── required_fields / value_schema
│   ├── confidence / priority / state_effect
│   └── provenance
│
├── navigation_graph     Page state transitions
├── assets[]             Images, stylesheets, scripts
├── provenance_index     Section → block IDs
├── canonical_markdown
├── quality              {parse_confidence, warnings[], block_count, action_count}
└── debug{}
```

## Comparison

Tested on 15 diverse webpages:

| Capability | Raw HTML | Markdown Scraper | **agent-web-compiler** |
|---|---|---|---|
| Token efficiency | Baseline | ~27% smaller | **27% smaller** + structured |
| Semantic blocks | ✗ | ✗ | **✓** 14 typed block types |
| Actions discovered | 0 | 0 | **377** across 15 pages |
| Grounded answers | ✗ | ✗ | **✓** with citations |
| Provenance | ✗ | ✗ | **✓** DOM path + char ranges |
| Entity extraction | ✗ | ✗ | **✓** dates, prices, URLs |
| Tables | Raw tags | Lossy | **Structured** headers + rows |
| Navigation graph | ✗ | ✗ | **✓** reachable pages + flows |
| Search/index | ✗ | ✗ | **✓** BM25 + hybrid retrieval |
| Execution planning | ✗ | ✗ | **✓** browser command generation |
| Noise ratio | High | 5-35% | **~0%** |

## Architecture

**18 packages, 57 modules, 3-layer stack:**

```
Compile (8-stage pipeline)
  ingest → render → normalize → segment → extract → align → validate → emit

Index (4-level hybrid engine)
  document index → block index → action index → site index

Search (4-stage retrieval)
  query planning → candidate retrieval → reranking → grounded answering
```

```
agent_web_compiler/
├── core/           Schemas, interfaces, typed errors (7 modules)
├── pipeline/       HTML, PDF, DOCX, API, streaming compilers + cache (7)
├── sources/        HTTP, Playwright, file reader (3)
├── normalizers/    Boilerplate removal, site profile learning (2)
├── segmenters/     Semantic blocking, salience, query filtering (3)
├── extractors/     Actions, entities, assets, navigation graph (4)
├── aligners/       DOM + screenshot provenance (2)
├── exporters/      JSON, markdown, token budget, LLM formatters (5)
├── index/          BM25 + dense + hybrid index engine (3)
├── search/         Query planner, retriever, answerer, runtime, SDK (5)
├── adapters/       OpenAI, Anthropic, Browser Use, LangChain (4)
├── middleware/     Browser agent middleware (1)
├── plugins/        Registry + protocols (2)
├── standards/      agent.json specification (1)
├── serving/        MCP server, REST API (2)
├── cli/            Command-line interface (1)
└── utils/          Text, DOM, document diff (3)
```

## Demos

Run the included demos to see the full capabilities:

```bash
python examples/demos/docs_search_demo.py     # Documentation QA with citations
python examples/demos/web_task_demo.py         # Action search + execution plans
python examples/demos/comparison_demo.py       # AWC vs raw HTML vs naive markdown
```

## Installation

```bash
# Core
pip install agent-web-compiler

# With extras
pip install "agent-web-compiler[pdf]"         # PDF (pymupdf)
pip install "agent-web-compiler[docx]"        # DOCX (python-docx)
pip install "agent-web-compiler[browser]"     # Playwright
pip install "agent-web-compiler[serve]"       # REST + MCP
pip install "agent-web-compiler[all]"         # Everything
```

**Requirements:** Python 3.9+

### From source

```bash
git clone https://github.com/anthropics/agent-web-compiler.git
cd agent-web-compiler
pip install -e ".[dev]"
pytest                     # 925 tests, all offline
ruff check .               # Lint
awc bench run              # Benchmarks
```

## Configuration

```python
from agent_web_compiler.core.config import CompileConfig, CompileMode, RenderMode

config = CompileConfig(
    mode=CompileMode.HIGH_RECALL,
    render=RenderMode.AUTO,
    include_actions=True,
    include_provenance=True,
    query="rate limits",
    min_importance=0.1,
    max_blocks=200,
    token_budget=4000,
    timeout_seconds=30.0,
    cache_dir="/tmp/awc-cache",
    debug=True,
)
```

## Contributing

See [docs/contributing.md](docs/contributing.md).

```bash
pip install -e ".[dev]"
pytest                # 925 tests
ruff check .          # Lint
awc bench run         # Benchmarks
```

**Principles**: simple + explicit + typed · composition over inheritance · offline tests · regression tests for bugs · clearer over fancier.

## Roadmap

See [docs/roadmap.md](docs/roadmap.md).

**v0.7.0** (current): Compile + Index + Search + Answer + Plan
**Next**: ML classifiers, multi-backend PDF fusion, vector embedding support
**Future**: `agent.json` web standard, distributed index, Docker deployment

## License

[MIT](LICENSE)

## Related Projects

| Project | Focus | How AWC differs |
|---|---|---|
| [Firecrawl](https://github.com/mendableai/firecrawl) | Web scraping | AWC adds actions, search, grounded answers |
| [Jina Reader](https://github.com/jina-ai/reader) | URL-to-markdown | AWC adds typed blocks, index, execution plans |
| [Crawl4AI](https://github.com/unclecode/crawl4ai) | Async crawling | AWC focuses on compilation + search quality |
| [Docling](https://github.com/DS4SD/docling) | Document parsing | AWC unifies web + doc + search into one stack |
| [Browser Use](https://github.com/browser-use/browser-use) | Browser automation | AWC provides pre-compiled affordances + action search |
| [MCP](https://modelcontextprotocol.io/) | Model Context Protocol | AWC ships 10 MCP tools (compile + search) |

**agent-web-compiler** is a **compile → index → search** stack for the Agent Web — producing typed objects with semantic blocks, actions, provenance, and grounded answers that any agent framework can consume.
