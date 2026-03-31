# agent-web-compiler

**Compile the Human Web into the Agent Web. Search it. Prove it. Act on it. Publish it.**

Turn webpages, PDFs, and documents into **agent-native objects** — then index, search, answer with verifiable citations, synthesize callable APIs from UI actions, and help websites publish agent-friendly content.

```
                        agent-web-compiler

  Compile ──► Index ──► Search ──► Prove ──► Act ──► Publish
  ┌────────┐ ┌───────┐ ┌────────┐ ┌───────┐ ┌─────┐ ┌────────┐
  │8-stage │ │BM25 + │ │Query   │ │Block  │ │State│ │llms.txt│
  │pipeline│ │dense  │ │planning│ │level  │ │graph│ │agent   │
  │14 block│ │hybrid │ │Grounded│ │cites +│ │API  │ │content │
  │8 action│ │4-level│ │answers │ │traces │ │synth│ │actions │
  │types   │ │index  │ │Exec    │ │snaps  │ │exec │ │sitemap │
  └────────┘ └───────┘ │plans   │ └───────┘ └─────┘ └────────┘
                       └────────┘
```

> **1,279 tests** · **77 modules** · **40K LOC** · Across 15 webpages: **27% fewer tokens**, **377 actions discovered**, **block-level citations** — no LLM needed.

## Quick Start

```bash
pip install agent-web-compiler
```

### Search with grounded answers

```python
from agent_web_compiler import AgentSearch

search = AgentSearch()
search.ingest_url("https://docs.example.com/api")

answer = search.answer("What authentication methods are supported?")
print(answer.to_markdown())
#   **Answer**: Bearer token and OAuth 2.0. [1][2]
#   [1] "Include your API key in the Authorization header..."
#   [2] "OAuth 2.0 flow requires client_id and client_secret..."
```

### Verifiable provenance

```python
from agent_web_compiler import ProvenanceEngine

provenance = ProvenanceEngine()
result = provenance.answer_with_provenance(search, "What is the rate limit?")
# → answer + citations (block + DOM + bbox) + evidence + decision trace + snapshots
```

### Action graph & API synthesis

```python
from agent_web_compiler.actiongraph import ActionGraphBuilder, APISynthesizer, HybridExecutor

doc = search.ingest_url("https://example.com/products")
graph = ActionGraphBuilder().build_from_document(doc)      # page state machine
apis = APISynthesizer().synthesize_from_document(doc)      # pseudo-API candidates
decisions = HybridExecutor().decide_all(doc, apis)         # API-first, browser-fallback
```

### Site memory

```python
from agent_web_compiler import SiteMemory

memory = SiteMemory()
memory.observe(doc1); memory.observe(doc2); memory.observe(doc3)
insight = memory.get_insight("example.com")
# → templates, noise selectors, entry points, common actions, nav patterns
```

### Publish for agents

```python
from agent_web_compiler import SitePublisher

publisher = SitePublisher(site_name="My Docs", site_url="https://docs.example.com")
publisher.crawl_site("https://docs.example.com/", max_pages=50)
publisher.generate_all("output/")
# → llms.txt, agent.json, content.json, actions.json, agent-sitemap.xml, agent-feed.json
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
doc = pipeline.compile(html)  # 0.45ms — 93x faster
```

### CLI

```bash
# Compile
awc compile https://example.com -o output/

# Index + Search
awc index crawl https://docs.example.com/ --max-pages 50
awc search "rate limit" && awc answer "How to auth?" && awc plan "download PDF"

# Provenance
awc provenance cite "What is the refund policy?"

# Publish
awc publish site https://docs.example.com/ -o output/

# Memory
awc memory show example.com

# Interactive
awc interactive

# Serve
awc serve --transport mcp     # 10 MCP tools
awc serve --transport rest    # 7 REST endpoints
```

## Seven Capabilities

### 1. Compile
14 block types · 8 action types · provenance · entities · nav graph · 17 extension points via `PipelineBuilder` · HTML/PDF/DOCX/JSON/Playwright

### 2. Index & Search
BM25 + dense hybrid · pluggable embeddings (TF-IDF built-in, OpenAI optional) · 4-level indexing · query planning (fact/evidence/navigation/task) · grounded answering · execution planning · site crawling

### 3. Prove
Evidence objects (block/action/DOM/bbox/screenshot) · citations with answer-span alignment · page snapshots (version-bound) · decision traces (query→retrieve→rerank→answer) · reproducibility

### 4. Act — Action Graph & API Synthesis ← NEW
**Page state machine** — model pages as states with typed transitions (navigate/expand/filter/submit/download)
**API candidate synthesis** — find machine-callable endpoints behind UI actions (search forms→GET API, pagination→parameterized URLs)
**Hybrid execution** — API-first when safe and confident, browser-fallback otherwise
**Risk assessment** — read_only/write/auth_required safety levels

### 5. Remember — Site Memory ← NEW
**Cross-page learning** — templates, noise selectors, entry points, hub pages, action habits
**Navigation patterns** — frequently-traversed URL sequences
**Persistent** — save/load site insights across sessions
**Improves over time** — 3+ pages triggers pattern detection

### 6. Publish
llms.txt · agent.json · content.json · actions.json · agent-sitemap.xml · agent-feed.json (delta) · auto-generated from existing content

### 7. Integrate
OpenAI CUA · Claude Computer Use · Browser Use · LangChain · 5 LLM formatters · MCP (10 tools) · REST (7 endpoints) · REPL · browser middleware

## Framework Integration

```python
from agent_web_compiler.adapters.openai_adapter import OpenAIAdapter     # CUA
from agent_web_compiler.adapters.anthropic_adapter import AnthropicAdapter # Claude
from agent_web_compiler.middleware.browser_middleware import BrowserMiddleware
from agent_web_compiler.exporters.llm_formatters import format_for_llm    # 5 formats
```

MCP: `compile_url` `compile_html` `compile_file` `get_blocks` `get_actions` `get_markdown` `ingest_url` `search` `answer` `plan`

## Comparison

| Capability | Raw HTML | MD Scraper | **agent-web-compiler** |
|---|---|---|---|
| Tokens | Baseline | -27% | **-27%** + structured |
| Semantic blocks | ✗ | ✗ | **14 types** |
| Actions | 0 | 0 | **377 across 15 pages** |
| Grounded answers | ✗ | ✗ | **Block-level citations** |
| Evidence chain | ✗ | ✗ | **DOM + bbox + snapshot + trace** |
| API synthesis | ✗ | ✗ | **Pseudo-API from UI actions** |
| Site memory | ✗ | ✗ | **Cross-page pattern learning** |
| Publish for agents | ✗ | ✗ | **6 standardized files** |

## Architecture

**23 packages · 77 modules:**

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
├── actiongraph/    State machine, API synthesis, hybrid executor (4)
├── memory/         Site-level learning across visits (1)
├── publisher/      llms.txt, agent/content/actions.json, sitemap, feed (6)
├── adapters/       OpenAI, Anthropic, Browser Use, LangChain (4)
├── middleware/     Browser agent middleware (1)
├── plugins/        Registry + protocols (2)
├── standards/      agent.json spec (1)
├── serving/        MCP server, REST API (2)
├── cli/            CLI + REPL (2)
└── utils/          Text, DOM, doc diff (3)
```

## Installation

```bash
pip install agent-web-compiler                 # Core
pip install "agent-web-compiler[pdf]"          # + PDF
pip install "agent-web-compiler[browser]"      # + Playwright
pip install "agent-web-compiler[serve]"        # + MCP + REST
pip install "agent-web-compiler[all]"          # Everything
```

Python 3.9+ · From source: `pip install -e ".[dev]" && pytest` (1,279 tests, ~4s, offline)

## Documentation

[Architecture](docs/architecture.md) · [Schema](docs/schema.md) · [Provenance](docs/provenance.md) · [Publisher](docs/publisher.md) · [Contributing](docs/contributing.md) · [Roadmap](docs/roadmap.md) · [Changelog](CHANGELOG.md)

## License

[MIT](LICENSE)

## Related Projects

| Project | AWC adds |
|---|---|
| [Firecrawl](https://github.com/mendableai/firecrawl) | Search, provenance, API synthesis, publish |
| [Jina Reader](https://github.com/jina-ai/reader) | Typed blocks, action graph, evidence chains |
| [Docling](https://github.com/DS4SD/docling) | Web + search + provenance + publish in one stack |
| [Browser Use](https://github.com/browser-use/browser-use) | Pre-compiled affordances, API-first execution, site memory |
| [llms.txt](https://llmstxt.org/) | Full agent manifest + actions + delta feeds |

---

**agent-web-compiler** — compile → index → search → prove → act → publish — for the Agent Web.
