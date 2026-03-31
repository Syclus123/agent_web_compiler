# Roadmap

## Status: v0.2.0 (current)

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
- CLI (`awc compile`, `awc inspect`)
- Python API (`compile_url`, `compile_html`, `compile_file`)
- JSON / Markdown / Debug exporters

**Phase 2: Dynamic Pages + Serving**
- Playwright browser rendering (auto-detect SPA)
- MCP server (6 tools, stdio transport)
- REST API (FastAPI, 6 endpoints)
- Plugin system (typed registry, capability discovery)
- Screenshot + accessibility tree alignment

**Phase 3: Intelligence + Quality**
- Query-aware compilation (TF-IDF relevance filtering)
- Advanced salience scoring (10-feature model)
- Token budget control (max_blocks, min_importance)
- Validation stage (quality metrics, warnings)
- Form field grouping (composite form actions)
- Table colspan/rowspan handling
- Definition list (dt/dd) support
- DOCX compilation (python-docx)
- API response compilation (JSON → blocks)
- Compilation cache (disk-backed, ETag support)
- Benchmark suite (5 fixtures, 3 dimensions)

### In Progress 🚧

**Phase 4: Learning + Scale**
- [ ] Site profile learning (cross-page template detection)
- [ ] ML-based content classifier (GBDT on DOM features)
- [ ] ML-based action priority model
- [ ] Multi-backend PDF fusion (Docling + MinerU)
- [ ] Expanded benchmark suite (20+ fixtures)

### Planned 📋

**Phase 5: Ecosystem**
- [ ] SSE/WebSocket streaming for large documents
- [ ] Batch compilation API
- [ ] Agent-native search index (block-level)
- [ ] `agent.json` publisher specification
- [ ] Visual diff tool for golden test comparison
- [ ] CI/CD pipeline with benchmark regression

**Phase 6: Standards**
- [ ] `agent.json` / `content.json` specification draft
- [ ] Interoperability with Firecrawl, Crawl4AI, Docling
- [ ] MCP resource provider (not just tools)
- [ ] OpenAPI schema for REST API

## Design Principles (Permanent)

1. **Semantic fidelity** over token compression
2. **Simplicity** over cleverness
3. **Extensibility** over completeness
4. **Clearer** over fancier
5. **Better contracts** over more features
