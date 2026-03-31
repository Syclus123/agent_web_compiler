# Provenance System

The provenance system makes every agent answer, retrieval, and action traceable
back to its exact source: block, DOM path, PDF bounding box, screenshot region,
or page snapshot.

## Overview

Traditional scrapers produce text without any link back to where it came from.
agent-web-compiler's provenance system ensures every piece of information carries
a chain of evidence from the original document to the final answer.

```
Document → Snapshot → Evidence → Citation → Traced Answer
```

## Core Concepts

### Evidence

An **Evidence** object is a verifiable piece of source content. Unlike a URL
citation, it points to a specific block, DOM path, PDF region, or screenshot
area — tied to a page snapshot.

```python
from agent_web_compiler.provenance import Evidence

ev = Evidence(
    evidence_id="ev_abc123",
    source_type="web_block",      # "web_block", "pdf_block", "action", "table_cell", "code_block"
    text="The rate limit is 100 requests per minute.",
    source_url="https://example.com/api",
    block_id="b_042",
    section_path=["API Reference", "Rate Limits"],
    dom_path="main > article > section:nth-child(3) > p:nth-child(2)",
    page=None,
    confidence=0.9,
)
```

Evidence can be created from compiled blocks, actions, or search results:

```python
from agent_web_compiler.provenance import EvidenceBuilder

builder = EvidenceBuilder()
evidence_list = builder.build_from_document(compiled_doc)
```

### Citation

A **CitationObject** is the user-facing reference linking an answer to its
evidence. It's what gets displayed as `[1]`, `[2]` in grounded answers. Each
citation includes rendering hints for highlighting in UIs.

```python
from agent_web_compiler.provenance import CitationBuilder

builder = CitationBuilder()
citations = builder.cite_answer(
    "The rate limit is 100 requests per minute.",
    evidence_list,
    max_citations=5,
)

# Render with inline markers
rendered = builder.render_answer_with_citations(answer_text, citations)
```

Output:
```
The rate limit is 100 requests per minute. [1]

---
[1] "The rate limit is 100 requests per minute."
    -- API Reference > Rate Limits (https://example.com/api)
```

### Snapshot

A **Snapshot** captures the state of a document at a point in time. This
ensures evidence references remain valid even if the source document changes.

```python
from agent_web_compiler.provenance import SnapshotStore

store = SnapshotStore()
snapshot = store.capture(compiled_doc)
# snapshot.snapshot_id -> "snap_a1b2c3d4e5f6"
# snapshot.content_hash -> SHA-256 of the canonical markdown
```

### Trace

A **TraceSession** records the full chain of decisions the agent makes:
which blocks were retrieved, which evidence was selected, which action was
chosen, and why.

```python
from agent_web_compiler.provenance import TraceRecorder

recorder = TraceRecorder()
session = recorder.start_session("What is the refund policy?")
recorder.record_step(session.session_id, "retrieve", input_data={"query": "refund policy"})
recorder.record_step(session.session_id, "select_evidence", evidence_ids=["ev_1", "ev_2"])
recorder.end_session(session.session_id, answer="Refunds are processed within 5 days.")

print(session.to_markdown())
```

## ProvenanceEngine — Unified API

The `ProvenanceEngine` is the high-level facade that ties everything together.
It delegates to `EvidenceBuilder`, `CitationBuilder`, `SnapshotStore`, and
`TraceRecorder` internally.

```python
from agent_web_compiler.provenance import ProvenanceEngine

engine = ProvenanceEngine()

# Capture a page snapshot
snapshot = engine.capture_snapshot(compiled_doc)

# Build evidence from a document
evidence_list = engine.build_evidence(compiled_doc, snapshot_id=snapshot.snapshot_id)

# Generate citations for an answer
citations = engine.cite_answer("The rate limit is 100/min.", evidence_list)

# Render the cited answer
print(engine.render_cited_answer("The rate limit is 100/min.", citations))

# Record a decision trace
session = engine.start_trace("What is the refund policy?")
engine.record_step(session.session_id, "retrieve", result_count=5)
engine.record_step(session.session_id, "answer", answer="Refunds take 5 days.")
trace = engine.end_trace(session.session_id, answer="Refunds take 5 days.")
print(trace.to_markdown())
```

### Full Pipeline: `answer_with_provenance`

The `answer_with_provenance` method runs the complete pipeline in one call:

```python
from agent_web_compiler import AgentSearch, ProvenanceEngine

search = AgentSearch()
search.ingest_url("https://docs.example.com/api")

engine = ProvenanceEngine()
result = engine.answer_with_provenance(search, "What is the rate limit?")

print(result["cited_answer"])
# The rate limit is 100 requests per minute. [1][2]
#
# ---
# [1] "The rate limit is 100 requests per minute."
#     -- API Reference > Rate Limits (https://docs.example.com/api)
# [2] "All endpoints are rate-limited to prevent abuse."
#     -- API Reference > Overview (https://docs.example.com/api)
```

The returned dict contains:

| Key | Type | Description |
|-----|------|-------------|
| `answer` | `str` | Plain answer text |
| `cited_answer` | `str` | Answer with `[N]` markers and evidence section |
| `citations` | `list[dict]` | Serialized citation objects |
| `evidence` | `list[dict]` | Serialized evidence objects |
| `trace` | `dict` | Full decision trace |
| `snapshot_ids` | `list[str]` | IDs of any captured snapshots |

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                   ProvenanceEngine                       │
│                   (engine.py)                            │
│                                                          │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐ │
│  │ Evidence      │ │ Citation     │ │  Snapshot        │ │
│  │ Builder       │ │ Builder      │ │  Store           │ │
│  │ (evidence.py) │ │ (citation.py)│ │  (snapshot.py)   │ │
│  └──────────────┘ └──────────────┘ └──────────────────┘ │
│                                                          │
│  ┌──────────────────────────────────────────────────┐    │
│  │              Trace Recorder                      │    │
│  │              (tracer.py)                          │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
           │                    │
           ▼                    ▼
  ┌─────────────────┐  ┌──────────────────┐
  │  AgentDocument   │  │  AgentSearch     │
  │  (core)          │  │  (search)        │
  └─────────────────┘  └──────────────────┘
```

### Data Flow

1. **AgentDocument** is compiled from HTML/PDF/DOCX
2. **SnapshotStore** captures the document state
3. **EvidenceBuilder** extracts evidence from blocks and actions
4. **AgentSearch** retrieves relevant evidence for a query
5. **CitationBuilder** aligns answer text to evidence and produces citations
6. **TraceRecorder** logs every decision along the way
7. **ProvenanceEngine** orchestrates the entire flow

## CLI Commands

### `awc provenance cite`

Answer a query with full provenance citations:

```bash
awc provenance cite "What is the rate limit?" --index-path awc_index.json
```

Options:
- `--index-path`: Path to the search index (default: `awc_index.json`)
- `--format`: Output format, `markdown` or `json` (default: `markdown`)

### `awc provenance trace`

Show the full decision trace for answering a query:

```bash
awc provenance trace "What is the rate limit?" --index-path awc_index.json
```

## Integration with AgentSearch

The provenance system integrates with `AgentSearch` at two levels:

1. **Evidence from search results**: `build_evidence_from_search()` converts
   `SearchResult` objects into `Evidence` objects with preserved provenance.

2. **Full pipeline**: `answer_with_provenance()` uses `AgentSearch.search()`
   and `AgentSearch.answer()` internally, wrapping the entire flow in traces
   and citations.

```python
from agent_web_compiler import AgentSearch, ProvenanceEngine

# Build your search index
search = AgentSearch()
search.ingest_url("https://docs.example.com")

# Use provenance for traced, cited answers
engine = ProvenanceEngine()
result = engine.answer_with_provenance(search, "How do I authenticate?")

# Access individual components
print(result["answer"])          # Plain answer
print(result["cited_answer"])    # Answer with [1][2] markers
print(result["trace"])           # Full decision trace
```

## Design Principles

- **Composition over inheritance**: Each component (evidence, citation,
  snapshot, trace) is a standalone module. The engine composes them.
- **No hidden state**: All state is explicit and scoped to the engine instance.
- **Typed contracts**: Evidence, Citation, Snapshot, and Trace are typed
  dataclasses with `to_dict()` serialization.
- **Fail loudly**: Missing trace sessions raise `KeyError` with context.
- **Additive evolution**: New evidence types or citation formats can be added
  without breaking existing contracts.
