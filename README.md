# agent-web-compiler

**Compile the Human Web into the Agent Web. Search it. Prove it. Publish it.**

Turn webpages, PDFs, and documents into **agent-native objects** — then index, search, answer with verifiable citations, and help websites publish agent-friendly content.

```
                        agent-web-compiler

  ┌─── Consume ──────────────── Verify ────────── Supply ───┐
  │                                                         │
  │  Compile → Index → Search   Provenance     Publish      │
  │  ┌──────────────────────┐  ┌───────────┐  ┌──────────┐ │
  │  │ 8-stage pipeline     │  │ Evidence   │  │ llms.txt │ │
  │  │ BM25 + dense index   │  │ Citations  │  │ agent.json│ │
  │  │ Query planning       │──│ Snapshots  │──│ content  │ │
  │  │ Grounded answers     │  │ Traces     │  │ actions  │ │
  │  │ Execution plans      │  │            │  │ sitemap  │ │
  │  └──────────────────────┘  └───────────┘  └──────────┘ │
  │                                                         │
  │  Agents consume    Decisions verified    Sites publish   │
  └─────────────────────────────────────────────────────────┘
```

> Across 15 webpages: **27% fewer tokens**, **377 discovered actions**, **grounded answers with block-level citations** — no LLM needed for answer composition.

## Quick Start

```bash
pip install agent-web-compiler
```

### Search with citations

```python
from agent_web_compiler import AgentSearch

search = AgentSearch()
search.ingest_url("https://docs.example.com/api")
search.ingest_file("report.pdf")

answer = search.answer("What authentication methods are supported?")
print(answer.to_markdown())
#   **Answer**: The API supports Bearer token and OAuth 2.0. [1][2]
#   **Evidence**:
#   [1] "Include your API key in the Authorization header..."
#       — API Reference > Authentication
#   [2] "OAuth 2.0 flow requires client_id and client_secret..."
#       — Authentication > OAuth Setup
```

### Provenance: verify every answer

```python
from agent_web_compiler import AgentSearch, ProvenanceEngine

search = AgentSearch()
search.ingest_url("https://docs.example.com/api")

provenance = ProvenanceEngine()
result = provenance.answer_with_provenance(search, "What is the rate limit?")

# result contains:
#   answer     — text with [N] citation markers
#   citations  — block-level refs with DOM path, bbox, screenshot region
#   evidence   — verifiable source objects tied to page snapshots
#   trace      — full decision chain: query → retrieve → rerank → answer
```

### Publish for agents

```python
from agent_web_compiler import SitePublisher

publisher = SitePublisher(site_name="My Docs", site_url="https://docs.example.com")
publisher.crawl_site("https://docs.example.com/", max_pages=50)
publisher.generate_all("output/")
# Creates: llms.txt, agent.json, content.json, actions.json,
#          agent-sitemap.xml, agent-feed.json
```

### Compile only

```python
from agent_web_compiler import compile_url
doc = compile_url("https://example.com")
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

# Provenance
awc provenance cite "What is the refund policy?"
awc provenance trace "Find the download link"

# Publish
awc publish site https://docs.example.com/ -o output/ --max-pages 50
awc publish preview https://example.com/api

# Interactive REPL
awc interactive

# Serve
awc serve --transport mcp          # 10 MCP tools
awc serve --transport rest         # 7 REST endpoints
```

## Five Capabilities

### 1. Compile

Turn any webpage/PDF/DOCX into a typed `AgentDocument`:
- **14 block types** — headings, paragraphs, tables, code, lists, quotes, FAQs
- **8 action types** — click, submit, navigate, download, with role inference + form grouping
- **Provenance** — DOM path, char ranges, bbox, screenshot regions
- **Entities** — dates, prices, emails, URLs, phones per block
- **17 extension points** — replace any stage via `PipelineBuilder`

### 2. Index & Search

Hybrid retrieval over compiled content:
- **BM25 + dense vectors** — pluggable embeddings (TF-IDF built-in, OpenAI optional)
- **4-level indexing** — document, block, action, site
- **Query planning** — fact / evidence / navigation / task intent
- **Grounded answering** — citations + provenance, no LLM required
- **Execution planning** — task queries → browser automation steps
- **Site crawling** — `crawl_site()` for bounded domain indexing

### 3. Prove

Verifiable evidence for every agent decision:
- **Evidence objects** — block/action-level with DOM path, bbox, screenshot region
- **Citations** — answer-span aligned, renderable as markdown/HTML with highlight hints
- **Snapshots** — version-bound page captures (content hash + timestamp)
- **Decision traces** — step-by-step: query → retrieve → rerank → select → answer
- **Replay** — tied to specific page versions for reproducibility

### 4. Publish

Help websites declare content for agents:
- **llms.txt** — LLM-friendly overview ([llmstxt.org](https://llmstxt.org/) format)
- **agent.json** — content structure + action manifest
- **content.json** — block-level content feed
- **actions.json** — interactive capabilities
- **agent-sitemap.xml** — agent-optimized sitemap
- **agent-feed.json** — delta feed for incremental updates

### 5. Integrate

Zero-friction adapters for agent frameworks:
- **OpenAI CUA** — AXTree format, tool definitions
- **Claude Computer Use** — XML content, tool results
- **Browser Use** — compiler-first middleware
- **LangChain** — Tool + DocumentLoader
- **5 LLM formatters** — AXTree, XML, function-call, compact, agent-prompt
- **MCP server** — 10 tools · **REST API** — 7 endpoints + SSE

## Framework Integration

```python
# OpenAI CUA
from agent_web_compiler.adapters.openai_adapter import OpenAIAdapter
OpenAIAdapter().to_cua_observation(doc)

# Claude Computer Use
from agent_web_compiler.adapters.anthropic_adapter import AnthropicAdapter
AnthropicAdapter().to_xml_content(doc)

# Browser middleware
from agent_web_compiler.middleware.browser_middleware import BrowserMiddleware
ctx = BrowserMiddleware().on_page_load(url, html)

# LLM formats
from agent_web_compiler.exporters.llm_formatters import format_for_llm
format_for_llm(doc, format="axtree")   # or: xml, function_call, compact, agent_prompt
```

### MCP Server

```json
{"mcpServers": {"awc": {"command": "awc", "args": ["serve", "--transport", "mcp"]}}}
```

10 tools: `compile_url`, `compile_html`, `compile_file`, `get_blocks`, `get_actions`, `get_markdown`, `ingest_url`, `search`, `answer`, `plan`.

## Comparison

| Capability | Raw HTML | MD Scraper | **agent-web-compiler** |
|---|---|---|---|
| Tokens | Baseline | -27% | **-27%** + structured |
| Semantic blocks | ✗ | ✗ | **14 types** |
| Actions | 0 | 0 | **377 across 15 pages** |
| Grounded answers | ✗ | ✗ | **Block-level citations** |
| Evidence chain | ✗ | ✗ | **DOM + bbox + snapshot + trace** |
| Search / index | ✗ | ✗ | **BM25 + dense hybrid** |
| Publish for agents | ✗ | ✗ | **6 standardized files** |
| Decision replay | ✗ | ✗ | **Step-level traces** |

## Architecture

**21 packages, 72 modules, 5 capabilities:**

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
├── provenance/     Evidence, citations, snapshots, traces, engine (5)
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
awc interactive                                # REPL
awc provenance cite "What is the rate limit?"  # Provenance demo
awc publish preview https://example.com        # Publisher preview
python examples/demos/docs_search_demo.py      # Search + citations
python examples/demos/web_task_demo.py         # Action planning
python examples/demos/comparison_demo.py       # AWC vs baselines
```

## Installation

```bash
pip install agent-web-compiler                 # Core
pip install "agent-web-compiler[pdf]"          # + PDF
pip install "agent-web-compiler[browser]"      # + Playwright
pip install "agent-web-compiler[serve]"        # + MCP + REST
pip install "agent-web-compiler[all]"          # Everything
```

Python 3.9+ · From source: `pip install -e ".[dev]" && pytest` (1,190 tests, ~4s, offline)

## Documentation

| Doc | Content |
|-----|---------|
| [Architecture](docs/architecture.md) | Pipeline stages, module boundaries |
| [Schema](docs/schema.md) | AgentDocument field reference |
| [Provenance](docs/provenance.md) | Evidence, citations, snapshots, traces |
| [Publisher](docs/publisher.md) | Agent-friendly file generation |
| [Contributing](docs/contributing.md) | Setup, style, testing |
| [Roadmap](docs/roadmap.md) | What's done, what's next |
| [Changelog](CHANGELOG.md) | Version history |

## License

[MIT](LICENSE)

## Related Projects

| Project | Focus | AWC adds |
|---|---|---|
| [Firecrawl](https://github.com/mendableai/firecrawl) | Web scraping | Search, provenance, publish |
| [Jina Reader](https://github.com/jina-ai/reader) | URL → markdown | Typed blocks, evidence chains |
| [Docling](https://github.com/DS4SD/docling) | Document parsing | Web + search + provenance + publish |
| [Browser Use](https://github.com/browser-use/browser-use) | Browser automation | Pre-compiled affordances, decision traces |
| [llms.txt](https://llmstxt.org/) | LLM overview | Full agent manifest + delta feeds |

---

**agent-web-compiler** — compile → index → search → prove → publish — for the Agent Web.
