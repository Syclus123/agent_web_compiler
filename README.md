# agent-web-compiler

**Compile the Human Web into the Agent Web. Search it. Publish it.**

Turn webpages, PDFs, and documents into **agent-native objects** — then index, search, answer, and plan against them. Help websites **publish agent-friendly content** with standardized files.

```
                        agent-web-compiler

  ┌──── Consume Side ────────────────────── Supply Side ────┐
  │                                                         │
  │  Compile → Index → Search              Publish          │
  │  ┌─────────────────────────┐    ┌────────────────────┐  │
  │  │ 8-stage pipeline        │    │ llms.txt           │  │
  │  │ BM25 + dense index      │    │ agent.json         │  │
  │  │ Query planning          │    │ content.json       │  │
  │  │ Grounded answering      │───>│ actions.json       │  │
  │  │ Execution planning      │    │ agent-sitemap.xml  │  │
  │  │ → AgentDocument         │    │ agent-feed.json    │  │
  │  └─────────────────────────┘    └────────────────────┘  │
  │                                                         │
  │  Agents consume ◄──────────────────► Websites publish   │
  └─────────────────────────────────────────────────────────┘
```

> Across 15 diverse webpages: **27% fewer tokens** than raw HTML, **377 discovered actions**, **grounded answers with citations** — no LLM needed.

## Quick Start

```bash
pip install agent-web-compiler
```

### Search: `AgentSearch`

```python
from agent_web_compiler import AgentSearch

search = AgentSearch()
search.ingest_url("https://docs.example.com/api")
search.ingest_file("report.pdf")

# Grounded answer with citations
answer = search.answer("What authentication methods are supported?")
print(answer.to_markdown())
#   **Answer**: The API supports Bearer token and OAuth 2.0. [1][2]
#   **Evidence**:
#   [1] "Include your API key in the Authorization header..."
#   [2] "OAuth 2.0 flow requires client_id and client_secret..."

# Search blocks / actions
results = search.search_blocks("rate limit", top_k=5)
actions = search.search_actions("download pricing PDF")

# Execution plan
plan = search.plan("search for wireless headphones")
#   1. fill `input[type="search"]` = `wireless headphones`
#   2. click `button[type="submit"]`
```

### Publish: `SitePublisher`

```python
from agent_web_compiler import SitePublisher

publisher = SitePublisher(
    site_name="My Documentation",
    site_url="https://docs.example.com",
)
publisher.crawl_site("https://docs.example.com/", max_pages=50)
publisher.generate_all("output/agent-publish/")
# Creates: llms.txt, agent.json, content.json, actions.json,
#          agent-sitemap.xml, agent-feed.json
```

### Compile only

```python
from agent_web_compiler import compile_url
doc = compile_url("https://example.com")
print(doc.canonical_markdown)
```

### Custom pipeline

```python
from agent_web_compiler import PipelineBuilder
pipeline = PipelineBuilder().skip_actions().skip_salience().build()
doc = pipeline.compile(html)  # 0.45ms — 93x faster than full pipeline
```

### CLI

```bash
# Compile
awc compile https://example.com -o output/

# Index + Search
awc index add https://docs.example.com/api
awc index crawl https://docs.example.com/ --max-pages 50
awc search "What is the rate limit?"
awc answer "How to authenticate?"
awc plan "download the enterprise PDF"

# Publish agent-friendly files
awc publish site https://docs.example.com/ -o output/ --max-pages 50
awc publish files ./docs/*.html -o output/ --site-name "My Docs"
awc publish preview https://example.com/api

# Interactive REPL
awc interactive

# Serve
awc serve --transport mcp          # 10 MCP tools
awc serve --transport rest         # 7 REST endpoints

# Benchmark
awc bench run && awc bench compare && awc bench search
```

## Agent Publisher Toolkit

Help websites shift from "agents scrape me" to **"I publish for agents."**

| File | Purpose |
|------|---------|
| **`llms.txt`** | LLM-friendly site overview ([llmstxt.org](https://llmstxt.org/) format) |
| **`agent.json`** | Content structure + action manifest |
| **`content.json`** | Block-level content feed (structured, not HTML) |
| **`actions.json`** | Interactive capabilities: forms, buttons, downloads |
| **`agent-sitemap.xml`** | Agent-optimized sitemap with content metadata |
| **`agent-feed.json`** | Delta feed — what changed since last visit |

```bash
# One command to publish a site for agents
awc publish site https://docs.example.com/ -o output/ --max-pages 50
```

The compiler auto-generates these from existing content — website owners don't need to author them manually.

> `robots.txt` says what NOT to do. `llms.txt` says what a site IS. **Agent Publisher says what agents CAN DO.**

See [docs/publisher.md](docs/publisher.md) for the full specification.

## What Makes This Different

Not a scraper. Not a markdown converter. A **four-capability stack**:

```
Compile     compile_url() → AgentDocument
  │         8-stage pipeline, 17 extension points (PipelineBuilder)
  ▼
Index       AgentSearch.ingest() → hybrid search engine
  │         BM25 + dense vectors, pluggable embeddings
  ▼
Search      AgentSearch.search() / answer() / plan()
  │         Query planning, grounded answers, execution plans
  ▼
Publish     SitePublisher.generate_all()
            llms.txt + agent.json + content.json + actions.json + sitemap + feed
```

Each layer works independently. Use just Compile, or Compile + Index, or the full stack.

## Features

### Compilation
- **14 semantic block types** — headings, paragraphs, tables, code, lists, quotes, figures, FAQs
- **8 action types** — click, input, submit, navigate, select, toggle, upload, download
- **Provenance tracking** — DOM path, char ranges, bounding boxes
- **Entity extraction** — dates, prices, emails, URLs, phones, percentages
- **Navigation graph** — page transitions, form flows, pagination chains
- **5 input sources** — HTML, PDF, DOCX, JSON APIs, Playwright (JS pages)
- **17 extension points** — replace any stage, add hooks, skip stages via `PipelineBuilder`

### Search & Retrieval
- **Hybrid search** — BM25 + dense vector + metadata filters, pure Python
- **Pluggable embeddings** — TF-IDF built-in, OpenAI/custom via `CallableEmbedder`
- **Query planning** — fact / evidence / navigation / task intent classification
- **Grounded answering** — citations + provenance (no LLM required)
- **Execution planning** — task → browser automation commands
- **Site crawling** — `crawl_site()` for bounded domain-level indexing

### Publishing
- **6 output files** — llms.txt, agent.json, content.json, actions.json, sitemap, delta feed
- **Auto-generation** — compiler reverse-engineers existing sites into publishable formats
- **Delta feeds** — track what changed between snapshots for incremental agent updates

### Intelligence
- **10-feature salience scoring** — position, entity density, text length, link ratio, DOM depth
- **Query-aware compilation** — TF-IDF relevance filtering with section matching
- **6-level token budget** — progressive compression (truncation → collapsing → dropping)
- **Site profile learning** — cross-page template detection, boilerplate removal

### Ecosystem
- **Framework adapters** — OpenAI CUA, Claude Computer Use, Browser Use, LangChain
- **5 LLM formatters** — AXTree, XML, function-call, compact, agent-prompt
- **MCP server** — 10 tools (compile + search)
- **REST API** — 7 endpoints + SSE streaming
- **Interactive REPL** — `awc interactive`
- **Browser middleware** — compiler-first + browser-fallback
- **Disk cache** — ETag/Last-Modified support

## Framework Integration

```python
# OpenAI CUA
from agent_web_compiler.adapters.openai_adapter import OpenAIAdapter
adapter = OpenAIAdapter()
observation = adapter.to_cua_observation(doc)

# Claude Computer Use
from agent_web_compiler.adapters.anthropic_adapter import AnthropicAdapter
xml = AnthropicAdapter().to_xml_content(doc)

# Browser Use middleware
from agent_web_compiler.middleware.browser_middleware import BrowserMiddleware
ctx = BrowserMiddleware().on_page_load(url, html)
llm_input = ctx.to_llm_prompt()

# LangChain
from agent_web_compiler.adapters.langchain_adapter import AWCTool
tool = AWCTool()

# LLM-optimized formats
from agent_web_compiler.exporters.llm_formatters import format_for_llm
format_for_llm(doc, format="axtree")    # CUA
format_for_llm(doc, format="xml")       # Claude
format_for_llm(doc, format="compact")   # Token-constrained
```

### MCP Server

```json
{"mcpServers": {"web-compiler": {"command": "awc", "args": ["serve", "--transport", "mcp"]}}}
```

10 tools: `compile_url`, `compile_html`, `compile_file`, `get_blocks`, `get_actions`, `get_markdown`, `ingest_url`, `search`, `answer`, `plan`.

## Output Schema

```
AgentDocument (v0.7.0)
├── blocks[]          14 semantic types (heading, paragraph, table, code, ...)
├── actions[]         8 interactive types (click, submit, navigate, ...)
├── navigation_graph  Page state transitions
├── assets[]          Images, stylesheets, scripts
├── provenance_index  Section → block IDs
├── canonical_markdown
├── quality           {parse_confidence, warnings[]}
└── entities          Per-block: dates, prices, URLs, phones
```

## Comparison

| Capability | Raw HTML | MD Scraper | **agent-web-compiler** |
|---|---|---|---|
| Tokens | Baseline | -27% | **-27%** + structured |
| Semantic blocks | ✗ | ✗ | **14 typed types** |
| Actions | 0 | 0 | **377 across 15 pages** |
| Grounded answers | ✗ | ✗ | **Citations + provenance** |
| Search / index | ✗ | ✗ | **BM25 + dense hybrid** |
| Execution plans | ✗ | ✗ | **Browser commands** |
| Publish for agents | ✗ | ✗ | **6 standardized files** |
| Noise ratio | High | 5–35% | **~0%** |

## Architecture

**20 packages, 67 modules:**

```
agent_web_compiler/
├── core/           Schemas, interfaces, errors (7)
├── pipeline/       Compilers + cache + extensible builder (8)
├── sources/        HTTP, Playwright, file reader, crawler (4)
├── normalizers/    Boilerplate removal, site profiles (2)
├── segmenters/     Blocking, salience, query filter (3)
├── extractors/     Actions, entities, assets, nav graph (4)
├── aligners/       DOM + screenshot provenance (2)
├── exporters/      JSON, markdown, token budget, LLM formatters (5)
├── index/          BM25 + dense engine, embeddings (4)
├── search/         Planner, retriever, answerer, runtime, SDK (5)
├── publisher/      llms.txt, agent/content/actions.json, sitemap, feed (6)
├── adapters/       OpenAI, Anthropic, Browser Use, LangChain (4)
├── middleware/     Browser agent middleware (1)
├── plugins/        Registry + protocols (2)
├── standards/      agent.json spec (1)
├── serving/        MCP server, REST API (2)
├── cli/            CLI + REPL (2)
└── utils/          Text, DOM, doc diff (3)
```

## Demos

```bash
awc interactive                                    # REPL
awc publish preview https://example.com            # Publisher preview
python examples/demos/docs_search_demo.py          # Search + citations
python examples/demos/web_task_demo.py             # Action planning
python examples/demos/comparison_demo.py           # AWC vs baselines
```

## Installation

```bash
pip install agent-web-compiler                     # Core
pip install "agent-web-compiler[pdf]"              # + PDF
pip install "agent-web-compiler[browser]"          # + Playwright
pip install "agent-web-compiler[serve]"            # + MCP + REST
pip install "agent-web-compiler[all]"              # Everything
```

Python 3.9+ · [From source](docs/contributing.md): `pip install -e ".[dev]" && pytest` (1,081 tests, ~3s, offline)

## Contributing

See [docs/contributing.md](docs/contributing.md). Principles: simple + typed + tested + offline + clearer over fancier.

## Roadmap

See [docs/roadmap.md](docs/roadmap.md). Current: v0.7.0 (Compile + Index + Search + Publish). Next: ML classifiers, multi-backend PDF, distributed index.

## License

[MIT](LICENSE) · [Changelog](CHANGELOG.md)

## Related Projects

| Project | Focus | AWC adds |
|---|---|---|
| [Firecrawl](https://github.com/mendableai/firecrawl) | Web scraping | Search, publish, grounded answers |
| [Jina Reader](https://github.com/jina-ai/reader) | URL → markdown | Typed blocks, index, execution plans |
| [Crawl4AI](https://github.com/unclecode/crawl4ai) | Async crawling | Compilation + search quality |
| [Docling](https://github.com/DS4SD/docling) | Document parsing | Web + search + publish in one stack |
| [Browser Use](https://github.com/browser-use/browser-use) | Browser automation | Pre-compiled affordances + action search |
| [llms.txt](https://llmstxt.org/) | LLM site overview | Full agent manifest (actions + content + delta) |

---

**agent-web-compiler** is a **compile → index → search → publish** stack for the Agent Web.
