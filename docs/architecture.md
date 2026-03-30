# Architecture

This document describes the internal architecture of agent-web-compiler.

## Overview

agent-web-compiler is an **8-stage pipeline** that transforms web content into typed, agent-native objects. Each stage has a small typed interface (a Python `Protocol`) and can be extended or replaced independently.

```
┌──────────┐   ┌──────────┐   ┌───────────┐   ┌──────────┐
│  Ingest  │──>│  Render  │──>│ Normalize │──>│ Segment  │
└──────────┘   └──────────┘   └───────────┘   └──────────┘
                                                     │
                                                     v
┌──────────┐   ┌──────────┐   ┌───────────┐   ┌──────────┐
│   Emit   │<──│ Validate │<──│   Align   │<──│ Extract  │
└──────────┘   └──────────┘   └───────────┘   └──────────┘
```

## Directory Structure

```
agent_web_compiler/
├── core/                 # Schemas, domain models, interfaces, errors
│   ├── document.py       # AgentDocument — the top-level output object
│   ├── block.py          # Block — semantic content unit
│   ├── action.py         # Action — interactive affordance
│   ├── provenance.py     # Provenance — origin tracking
│   ├── config.py         # CompileConfig — typed configuration
│   ├── interfaces.py     # Protocol definitions for each stage
│   └── errors.py         # Typed error hierarchy
│
├── api/                  # Public entry points
│   └── compile.py        # compile_url(), compile_html(), compile_file()
│
├── pipeline/             # Orchestration
│   ├── compiler.py       # HTMLCompiler — main HTML pipeline
│   └── pdf_compiler.py   # PDFCompiler — PDF pipeline
│
├── sources/              # Input adapters
│   ├── http_fetcher.py   # HTTP/HTTPS fetching via httpx
│   └── file_reader.py    # Local file reading (HTML, PDF)
│
├── normalizers/          # Cleanup and canonicalization
│   └── html_normalizer.py # Strip scripts, fix encoding, remove boilerplate
│
├── segmenters/           # Structural parsing and block creation
│
├── extractors/           # Metadata, actions, tables, links, entities
│   └── action_extractor.py # Action affordance extraction
│
├── aligners/             # Source/visual/provenance mapping
│   └── dom_aligner.py    # DOM path and char range alignment
│
├── exporters/            # Output format adapters
│   ├── json_exporter.py  # JSON serialization
│   ├── markdown_exporter.py # Canonical markdown generation
│   └── debug_exporter.py # Debug bundle generation
│
├── plugins/              # Extension registration and discovery
│
├── utils/                # Internal utilities
│   ├── text.py           # Text processing helpers
│   └── dom.py            # DOM manipulation helpers
│
└── cli/                  # User-facing commands
    └── main.py           # Click CLI (awc compile, awc inspect)
```

### Supporting directories

```
tests/                    # Unit, integration, golden, failure-path tests
bench/                    # Reproducible benchmark code
docs/                     # Documentation
examples/                 # Example scripts and usage
```

## Pipeline Stages

### 1. Ingest

**Purpose:** Acquire raw content from the source.

**Interfaces:** `Fetcher` protocol (for URLs), `FileReader` (for local files).

**Implementations:**
- `HTTPFetcher` — fetches URLs via httpx with configurable timeout and user-agent
- `FileReader` — reads local HTML and PDF files, detects content type

**Input:** URL string, file path, or raw HTML
**Output:** `FetchResult` (content bytes/string, content type, headers, metadata)

### 2. Render

**Purpose:** Execute JavaScript and render dynamic pages when needed.

**Trigger:** Controlled by `CompileConfig.render` — `off` (default), `auto` (detect dynamic pages), or `always`.

**Implementation:** Uses Playwright (optional dependency) for headless browser rendering.

**Input:** `FetchResult` with static HTML
**Output:** `FetchResult` with rendered HTML

### 3. Normalize

**Purpose:** Clean and canonicalize HTML for reliable downstream parsing.

**Interface:** `Normalizer` protocol.

**Operations:**
- Strip `<script>`, `<style>`, `<noscript>` elements
- Fix character encoding issues
- Normalize whitespace
- Remove invisible/hidden elements
- Strip tracking pixels and ad containers
- Detect and mark boilerplate regions (headers, footers, sidebars)

**Input:** Raw HTML string
**Output:** Cleaned HTML string

### 4. Segment

**Purpose:** Split normalized content into typed semantic blocks.

**Interface:** `Segmenter` protocol.

**Block types:** `heading`, `paragraph`, `list`, `table`, `code`, `quote`, `figure_caption`, `image`, `product_spec`, `review`, `faq`, `form_help`, `metadata`, `unknown`.

**Operations:**
- Identify content boundaries using DOM structure and visual cues
- Assign block types based on element semantics
- Build section hierarchy from heading levels
- Compute reading order
- Assign importance scores

**Input:** Cleaned HTML string
**Output:** `list[Block]` with type, text, section path, order, and importance

### 5. Extract

**Purpose:** Pull out action affordances, metadata, and structured content.

**Interface:** `Extractor` protocol.

**Action types:** `click`, `input`, `select`, `toggle`, `upload`, `download`, `navigate`, `submit`.

**Operations:**
- Identify interactive elements (buttons, links, inputs, forms)
- Compute CSS selectors for targeting
- Assign semantic roles (e.g., `submit_search`, `next_page`, `login`)
- Predict state effects (navigation, modals, downloads)
- Score confidence and priority

**Input:** Cleaned HTML string
**Output:** `list[Action]` with type, label, selector, role, and state effects

### 6. Align

**Purpose:** Map blocks and actions back to their source locations.

**Interface:** `Aligner` protocol.

**Provenance types:**
- `DOMProvenance` — CSS path, element tag/id/classes
- `PageProvenance` — page number, bounding box, character range
- `ScreenshotProvenance` — pixel-space region reference

**Operations:**
- Compute DOM paths for each block and action
- Map character ranges in source text
- Compute bounding boxes for PDF content
- Cross-reference blocks with their source elements

**Input:** blocks, actions, source HTML/PDF
**Output:** blocks and actions with `Provenance` attached

### 7. Validate

**Purpose:** Check output quality, flag warnings, and compute confidence.

**Operations:**
- Count blocks and actions
- Compute overall parse confidence
- Detect quality issues (e.g., empty blocks, low-confidence actions)
- Generate machine-readable warnings
- Populate the `Quality` object

**Input:** AgentDocument draft
**Output:** AgentDocument with `quality` field populated

### 8. Emit

**Purpose:** Produce final outputs in requested formats.

**Formats:**
- `AgentDocument` — typed Pydantic model (always produced)
- JSON — via `json_exporter.to_json()`
- Canonical markdown — stored in `AgentDocument.canonical_markdown`
- Debug bundle — timings, intermediates, provenance samples

**Input:** Validated AgentDocument
**Output:** Serialized JSON, markdown, or debug bundle files

## Data Flow

```
URL / file / raw HTML
        │
        v
   ┌─────────┐
   │  Ingest  │  → FetchResult { content, content_type, url, headers }
   └────┬─────┘
        │
        v
   ┌─────────┐
   │  Render  │  → FetchResult { rendered HTML }  (optional)
   └────┬─────┘
        │
        v
   ┌───────────┐
   │ Normalize │  → cleaned HTML string
   └─────┬─────┘
        │
   ┌────┴────┐
   │         │
   v         v
┌─────────┐ ┌──────────┐
│ Segment │ │ Extract  │  → list[Block], list[Action]
└────┬────┘ └────┬─────┘
     │           │
     └─────┬─────┘
           v
      ┌─────────┐
      │  Align  │  → blocks + actions with Provenance
      └────┬────┘
           v
      ┌──────────┐
      │ Validate │  → Quality { confidence, warnings }
      └────┬─────┘
           v
      ┌─────────┐
      │  Emit   │  → AgentDocument, JSON, markdown
      └─────────┘
```

## Extension Points

### Adding a New Source Type

Implement the `Fetcher` protocol:

```python
from agent_web_compiler.core.interfaces import Fetcher, FetchResult
from agent_web_compiler.core.config import CompileConfig

class MyFetcher:
    async def fetch(self, source: str, config: CompileConfig) -> FetchResult:
        content = ...  # fetch your content
        return FetchResult(
            content=content,
            content_type="text/html",
            url=source,
        )
```

### Adding a New Normalizer

Implement the `Normalizer` protocol:

```python
from agent_web_compiler.core.interfaces import Normalizer
from agent_web_compiler.core.config import CompileConfig

class MyNormalizer:
    def normalize(self, html: str, config: CompileConfig) -> str:
        # clean and transform the HTML
        return cleaned_html
```

### Adding a New Extractor

Implement the `Extractor` protocol:

```python
from agent_web_compiler.core.interfaces import Extractor
from agent_web_compiler.core.action import Action
from agent_web_compiler.core.config import CompileConfig

class MyExtractor:
    def extract(self, html: str, config: CompileConfig) -> list[Action]:
        # extract actions from the HTML
        return actions
```

### Adding a New Exporter

Export functions take an `AgentDocument` and produce output:

```python
from agent_web_compiler.core.document import AgentDocument

def to_my_format(doc: AgentDocument) -> str:
    # serialize the document
    return output
```

## Configuration

All behavior is controlled through `CompileConfig`:

| Field | Type | Default | Description |
|---|---|---|---|
| `mode` | `CompileMode` | `balanced` | `fast`, `balanced`, or `high_recall` |
| `render` | `RenderMode` | `off` | `off`, `auto`, or `always` |
| `include_actions` | `bool` | `True` | Extract action affordances |
| `include_provenance` | `bool` | `True` | Include provenance tracking |
| `include_raw_html` | `bool` | `False` | Preserve raw HTML in block provenance |
| `query` | `str?` | `None` | Query for query-aware compilation |
| `min_importance` | `float` | `0.0` | Minimum importance threshold for blocks |
| `max_blocks` | `int?` | `None` | Maximum number of blocks to emit |
| `pdf_backend` | `str` | `auto` | PDF backend: `auto`, `pymupdf`, `docling` |
| `timeout_seconds` | `float` | `30.0` | HTTP fetch timeout |
| `user_agent` | `str` | `agent-web-compiler/0.1.0` | User-Agent header |
| `debug` | `bool` | `False` | Enable debug metadata |

No hidden global state. No undocumented environment variable magic.

## Error Handling

All pipeline errors inherit from `CompilerError`:

```
CompilerError
├── FetchError        (stage: "fetch")
├── RenderError       (stage: "render")
├── ParseError        (stage: "parse")
├── NormalizeError    (stage: "normalize")
├── SegmentError      (stage: "segment")
├── ExtractError      (stage: "extract")
├── AlignError        (stage: "align")
└── ExportError       (stage: "export")
```

Every error carries:
- `stage` — which pipeline stage failed
- `cause` — original exception (preserved via `__cause__`)
- `context` — dict with debug information
