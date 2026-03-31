# Roadmap

## Status: v0.4.0 (current)

### Completed ✅

**Phase 0: Foundation**
- Core schemas (AgentDocument, Block, Action, Provenance)
- 8-stage pipeline architecture
- Typed configuration and error handling

**Phase 1: Core Compilation**
- HTML boilerplate removal (text density + noise patterns)
- Semantic block segmentation (14 block types)
- Action affordance extraction (8 action types with role inference)
- DOM provenance alignment
- CLI (`awc compile`, `awc inspect`, `awc serve`, `awc bench`)
- Python API (`compile_url`, `compile_html`, `compile_file`, `compile_batch`)
- JSON / Markdown / Debug exporters

**Phase 2: Dynamic Pages + Serving**
- Playwright browser rendering (auto-detect SPA)
- MCP server (6 tools, stdio transport)
- REST API (FastAPI, 6 endpoints + SSE streaming)
- Plugin system (typed registry, capability discovery)
- Screenshot + accessibility tree alignment

**Phase 3: Intelligence + Quality**
- Query-aware compilation (TF-IDF relevance filtering)
- Advanced salience scoring (10-feature model)
- Intelligent token budget (6-level progressive compression)
- Validation stage (quality metrics, warnings)
- Form field grouping (composite form actions)
- Table colspan/rowspan handling
- Definition list (dt/dd) support
- DOCX compilation (python-docx)
- API response compilation (JSON → blocks)
- Compilation cache (disk-backed, ETag support)
- Entity extraction (dates, prices, emails, URLs, phones)
- Site profile learning (cross-page template detection)
- Navigation graph (page state transitions)
- Batch/parallel compilation with shared context
- Comparison framework (AWC vs Raw HTML vs Naive MD)
- Benchmark suite (15 fixtures, 4 dimensions)

**Phase 4: Ecosystem Integration** ← NEW
- LLM-optimized output formatters (AXTree, XML, function-call, compact, agent-prompt)
- Framework adapters (OpenAI CUA, Claude Computer Use, Browser Use, LangChain)
- Browser agent middleware (compiler-first, browser-fallback pattern)
- Streaming compilation pipeline (Generator + SSE)
- Integration examples for all major frameworks

### In Progress 🚧

**Phase 5: Learning + Scale**
- [ ] ML-based content classifier (GBDT on DOM features)
- [ ] ML-based action priority model
- [ ] Multi-backend PDF fusion (Docling + MinerU)
- [ ] Expanded benchmark suite with LLM-graded evaluation
- [ ] CI/CD pipeline with benchmark regression

### Planned 📋

**Phase 6: Standards + Infrastructure**
- [ ] `agent.json` / `content.json` specification draft
- [ ] Interoperability with Firecrawl, Crawl4AI, Docling
- [ ] MCP resource provider (not just tools)
- [ ] Agent-native search index (block-level)
- [ ] Visual diff tool for golden test comparison
- [ ] Docker image for self-hosted deployment
- [ ] PyPI package release workflow

## Design Principles (Permanent)

1. **Semantic fidelity** over token compression
2. **Simplicity** over cleverness
3. **Extensibility** over completeness
4. **Clearer** over fancier
5. **Better contracts** over more features
6. **Framework-agnostic** — adapt to any agent framework via typed interfaces
