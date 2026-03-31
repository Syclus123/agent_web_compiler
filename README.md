# agent-web-compiler

**Compile the Human Web into the Agent Web. Then search it.**

Turn webpages, PDFs, and documents into **agent-native objects** — then index, search, answer, and plan against them. Built for browser agents, RAG pipelines, and agentic search.

```
                     agent-web-compiler v0.7

  Input Sources       Compile → Index → Search       Agent Consumers
 ┌────────────┐    ┌───────────────────────────┐    ┌──────────────────┐
 │  Webpages  │    │                           │    │                  │
 │  PDFs      │    │  Compile (8-stage)        │    │  OpenAI CUA      │
 │  DOCX      │───>│  Index   (BM25 + dense)   │───>│  Claude Computer │
 │  JSON APIs │    │  Search  (plan + answer)  │    │  Browser Use     │
 │            │    │                           │    │  LangChain / RAG │
 └────────────┘    │  → AgentDocument          │    │  MCP / REST API  │
                   │  → Grounded Answer        │    │                  │
                   │  → Execution Plan         │    └──────────────────┘
                   └───────────────────────────┘
```

> Across 15 diverse webpages: **27% fewer tokens** than raw HTML, **377 discovered actions** (vs 0 from naive extraction), **grounded answers with citations** — no LLM needed for answer composition.

## Quick Start

```bash
pip install agent-web-compiler
```

### The primary API: `AgentSearch`

```python
from agent_web_compiler import AgentSearch

search = AgentSearch()

# Compile and index content
search.ingest_url("https://docs.example.com/api")
search.ingest_file("report.pdf")

# Search for content blocks
results = search.search_blocks("What is the rate limit?", top_k=5)

# Get a grounded answer with citations (no LLM required)
answer = search.answer("What authentication methods are supported?")
print(answer.to_markdown())
#   **Answer**: The API supports Bearer token and OAuth 2.0. [1][2]
#   **Evidence**:
#   [1] "Include your API key in the Authorization header..."
#       — API Reference > Authentication
#   [2] "OAuth 2.0 flow requires client_id and client_secret..."
#       — Authentication > OAuth Setup

# Search for executable actions
actions = search.search_actions("download pricing PDF")

# Generate an execution plan for a task
plan = search.plan("search for wireless headphones")
print(plan.to_markdown())
#   1. **fill** `input[type="search"]` = `wireless headphones`
#   2. **click** `button[type="submit"]`

# Persist the index
search.save("my_index.json")
```

### With semantic search (optional embeddings)

```python
from agent_web_compiler import AgentSearch
from agent_web_compiler.index.embeddings import TFIDFEmbedder

# Built-in TF-IDF embeddings — no external dependencies
embedder = TFIDFEmbedder(max_features=300)
search = AgentSearch(embedder=embedder)

search.ingest_url("https://docs.example.com/api")
# Blocks and actions are automatically embedded during ingestion
# Queries are automatically embedded during search

# Or bring your own embeddings
from agent_web_compiler.index.embeddings import CallableEmbedder
search = AgentSearch(embedder=CallableEmbedder(
    lambda text: openai_client.embeddings.create(
        model="text-embedding-3-small", input=text
    ).data[0].embedding
))
```

### Compile only (no index/search needed)

```python
from agent_web_compiler import compile_url, compile_html

doc = compile_url("https://example.com")

for block in doc.blocks:
    print(f"[{block.type.value}] {block.text[:80]}")

for action in doc.actions:
    print(f"[{action.type.value}] {action.label} -> {action.selector}")

print(doc.canonical_markdown)
```

### CLI

```bash
# Compile
awc compile https://example.com -o output/
awc compile paper.pdf -o output/
awc compile url1 url2 url3 -o output/

# Index + Search
awc index add https://docs.example.com/api
awc index stats
awc search "What is the rate limit?"
awc answer "How to authenticate?"
awc plan "download the enterprise PDF"

# Interactive REPL (try it first!)
awc interactive

# Inspect compiled output
awc inspect output/agent_document.json

# Serve
awc serve --transport mcp          # MCP server (10 tools)
awc serve --transport rest         # REST API (7 endpoints)

# Benchmark
awc bench run
awc bench compare
awc bench search
```

## What Makes This Different

This is not a scraper, a markdown converter, or a RAG framework. It's a **three-layer stack** with clean separation:

```
Compile   compile_url() / compile_html() / compile_file()
  │       8-stage pipeline: ingest → render → normalize → segment
  │       → extract → align → validate → emit
  │       Output: AgentDocument (typed, versioned, with provenance)
  │
  ▼
Index     AgentSearch.ingest() / ingest_url() / ingest_file()
  │       4-level index: document, block, action, site
  │       Hybrid retrieval: BM25 + dense vectors + metadata filters
  │       Pluggable embeddings (TF-IDF built-in, OpenAI/custom optional)
  │
  ▼
Search    AgentSearch.search() / answer() / plan()
          Query planning: fact / evidence / navigation / task
          Grounded answering with citations (no LLM required)
          Execution planning → browser automation commands
```

Each layer works independently — you can use just Compile, or Compile + Index, or the full stack.

## Features

### Compilation
- **14 semantic block types** — headings, paragraphs, tables, code, lists, quotes, figures, FAQs
- **8 action types** — click, input, submit, navigate, select, toggle, upload, download — with role inference, form field grouping, state effect prediction
- **Provenance tracking** — DOM path, character ranges, screenshot bounding boxes
- **Entity extraction** — dates, prices, emails, URLs, phones, percentages
- **Navigation graph** — page state transitions, form flows, pagination chains
- **5 input sources** — HTML, PDF, DOCX, JSON APIs, Playwright for JS pages
- **Hidden content filtering** — display:none, aria-hidden, hidden attribute

### Intelligence
- **10-feature salience scoring** — position, entity density, text length, link ratio, DOM depth
- **Query-aware compilation** — TF-IDF relevance filtering with section matching
- **6-level token budget** — progressive compression: truncation → compression → collapsing → dropping
- **Site profile learning** — cross-page template detection, shared boilerplate removal

### Search & Retrieval
- **Hybrid search** — BM25 sparse + dense vector + metadata filters, pure Python
- **Pluggable embeddings** — TF-IDF built-in, OpenAI/sentence-transformers/custom via `CallableEmbedder`
- **4-level indexing** — document, block, action, site
- **Query planning** — intent classification (fact / evidence / navigation / task)
- **Grounded answering** — evidence-backed answers with citations (no LLM required)
- **Execution planning** — task queries → browser automation steps
- **Incremental updates** — add/remove/update without full reindex

### Output Formats
- **5 LLM formatters** — AXTree (CUA), XML (Claude), function-call (OpenAI), compact, agent-prompt
- **Canonical markdown + JSON** — typed, versioned output
- **Streaming compilation** — yield blocks incrementally with token budget cutoff

### Ecosystem
- **Framework adapters** — OpenAI CUA, Claude Computer Use, Browser Use, LangChain (zero deps)
- **Browser middleware** — compiler-first + browser-fallback pattern
- **MCP server** — 10 tools (6 compile + 4 search)
- **REST API** — 7 FastAPI endpoints including SSE streaming
- **Interactive REPL** — `awc interactive` for instant exploration
- **Plugin system** — typed interfaces, capability-based registry
- **Batch compilation** — parallel multi-URL with shared site profiles
- **Disk cache** — ETag/Last-Modified support

## Framework Integration

### OpenAI CUA / Function Calling

```python
from agent_web_compiler.adapters.openai_adapter import OpenAIAdapter

adapter = OpenAIAdapter()
observation = adapter.to_cua_observation(doc)   # AXTree format
tools = adapter.to_tool_definitions(doc)        # Actions as tool definitions
```

### Claude Computer Use

```python
from agent_web_compiler.adapters.anthropic_adapter import AnthropicAdapter

adapter = AnthropicAdapter()
xml = adapter.to_xml_content(doc)               # XML (Claude-optimal)
result = adapter.to_computer_use_result(doc)    # Tool result format
```

### Browser Use — Compiler-First Pattern

```python
from agent_web_compiler.middleware.browser_middleware import BrowserMiddleware

middleware = BrowserMiddleware()
ctx = middleware.on_page_load(url, html)
llm_input = ctx.to_llm_prompt()                 # Structured, not raw screenshot
command = middleware.translate_action("a_001")   # → {"type": "click", "selector": "..."}
```

### LangChain / RAG

```python
from agent_web_compiler.adapters.langchain_adapter import AWCTool, AWCDocumentLoader

tool = AWCTool()                                # Agent tool
loader = AWCDocumentLoader()                    # RAG document loader
```

### LLM-Optimized Formats

```python
from agent_web_compiler.exporters.llm_formatters import format_for_llm

format_for_llm(doc, format="axtree")           # CUA agents
format_for_llm(doc, format="xml")              # Claude
format_for_llm(doc, format="function_call")    # OpenAI
format_for_llm(doc, format="compact")          # Token-constrained (<500 tokens)
format_for_llm(doc, format="agent_prompt")     # Full system prompt
```

### MCP Server

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

10 tools: `compile_url`, `compile_html`, `compile_file`, `get_blocks`, `get_actions`, `get_markdown`, `ingest_url`, `search`, `answer`, `plan`.

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
├── blocks[]             14 semantic types
│   ├── type / text / section_path / importance
│   ├── metadata         {entities, language, headers, rows, ...}
│   └── provenance       {dom_path, page, bbox, char_range}
│
├── actions[]            8 interactive types
│   ├── type / label / selector / role
│   ├── required_fields / value_schema / confidence
│   └── state_effect / provenance
│
├── navigation_graph     Page state transitions
├── assets[]             Images, stylesheets, scripts
├── provenance_index     Section → block IDs
├── canonical_markdown
├── quality              {parse_confidence, warnings[]}
└── debug{}
```

## Comparison

Across 15 diverse webpages:

| Capability | Raw HTML | Markdown Scraper | **agent-web-compiler** |
|---|---|---|---|
| Token efficiency | Baseline | ~27% smaller | **27% smaller** + structured |
| Semantic blocks | ✗ | ✗ | **14 typed block types** |
| Actions discovered | 0 | 0 | **377 across 15 pages** |
| Grounded answers | ✗ | ✗ | **Citations + provenance** |
| Entity extraction | ✗ | ✗ | **Dates, prices, URLs, phones** |
| Tables | Raw tags | Lossy | **Structured (headers + rows)** |
| Navigation graph | ✗ | ✗ | **Reachable pages + flows** |
| Search / index | ✗ | ✗ | **BM25 + dense hybrid** |
| Execution planning | ✗ | ✗ | **Browser command generation** |
| Noise ratio | High | 5–35% | **~0%** |

## Architecture

**19 packages, 59 modules, 3 decoupled layers:**

```
agent_web_compiler/
├── core/           Schemas, interfaces, typed errors (7)
├── pipeline/       HTML, PDF, DOCX, API, streaming compilers + cache (7)
├── sources/        HTTP, Playwright, file reader (3)
├── normalizers/    Boilerplate removal, site profiles (2)
├── segmenters/     Blocking, salience, query filter (3)
├── extractors/     Actions, entities, assets, nav graph (4)
├── aligners/       DOM + screenshot provenance (2)
├── exporters/      JSON, markdown, token budget, LLM formatters (5)
├── index/          BM25 + dense + hybrid engine, embeddings (4)
├── search/         Planner, retriever, answerer, runtime, SDK (5)
├── adapters/       OpenAI, Anthropic, Browser Use, LangChain (4)
├── middleware/     Browser agent middleware (1)
├── plugins/        Registry + protocols (2)
├── standards/      agent.json spec (1)
├── serving/        MCP server, REST API (2)
├── cli/            CLI + interactive REPL (2)
└── utils/          Text, DOM, doc diff (3)
```

**Dependency flow** (no circular dependencies):
```
core  ←  pipeline  ←  index  ←  search
  ↑         ↑                      ↑
  └── sources, normalizers,   adapters, middleware,
      segmenters, extractors,  serving, cli
      aligners, exporters
```

## Demos

```bash
# Interactive REPL — the fastest way to explore
awc interactive

# Scripted demos
python examples/demos/docs_search_demo.py      # Documentation QA with citations
python examples/demos/web_task_demo.py          # Action search + execution plans
python examples/demos/comparison_demo.py        # AWC vs raw HTML vs naive markdown
```

## Installation

```bash
pip install agent-web-compiler                   # Core
pip install "agent-web-compiler[pdf]"            # + PDF (pymupdf)
pip install "agent-web-compiler[docx]"           # + DOCX (python-docx)
pip install "agent-web-compiler[browser]"        # + Playwright
pip install "agent-web-compiler[serve]"          # + REST + MCP servers
pip install "agent-web-compiler[all]"            # Everything
```

**Requirements:** Python 3.9+

### From source

```bash
git clone https://github.com/anthropics/agent-web-compiler.git
cd agent-web-compiler
pip install -e ".[dev]"
pytest                     # 967 tests, all offline
ruff check .               # Lint
awc bench run              # Benchmarks
```

## Configuration

```python
from agent_web_compiler.core.config import CompileConfig

config = CompileConfig(
    mode="high_recall",         # fast | balanced | high_recall
    render="auto",              # off | auto | always
    query="rate limits",        # Query-aware filtering
    token_budget=4000,          # Progressive compression
    cache_dir="/tmp/awc",       # Disk cache
)
```

## Contributing

See [docs/contributing.md](docs/contributing.md). Key: simple + typed + tested + offline.

## Roadmap

**v0.7.0** (current): Compile + Index + Search + Answer + Plan + Embeddings + REPL
**Next**: ML classifiers, multi-backend PDF, expanded benchmarks
**Future**: `agent.json` standard, distributed index, Docker

See [docs/roadmap.md](docs/roadmap.md).

## License

[MIT](LICENSE)

## Related Projects

| Project | Focus | How AWC differs |
|---|---|---|
| [Firecrawl](https://github.com/mendableai/firecrawl) | Web scraping | + actions, search, grounded answers |
| [Jina Reader](https://github.com/jina-ai/reader) | URL-to-markdown | + typed blocks, index, execution plans |
| [Crawl4AI](https://github.com/unclecode/crawl4ai) | Async crawling | AWC = compilation + search quality |
| [Docling](https://github.com/DS4SD/docling) | Document parsing | + web + search in one stack |
| [Browser Use](https://github.com/browser-use/browser-use) | Browser automation | + pre-compiled affordances + action search |
| [MCP](https://modelcontextprotocol.io/) | Model Context Protocol | AWC ships 10 MCP tools |

---

**agent-web-compiler** is a **compile → index → search** stack for the Agent Web.
