"""Agent Provenance / Citation Engine — verifiable evidence for agent decisions.

Makes every agent answer, retrieval, and action traceable back to
its exact source: block, DOM path, PDF bbox, screenshot region, or page snapshot.

High-level API:
- ProvenanceEngine: unified facade (engine.py) — uses its own lightweight models

Core objects (detailed modules):
- Evidence / EvidenceBuilder: verifiable source content with multi-level grounding (evidence.py)
- CitationObject / CitationBuilder: rendered references with render hints (citation.py)
- Snapshot / SnapshotStore: versioned page captures (snapshot.py)
- TraceStep / TraceSession / TraceRecorder: decision traces (tracer.py)
"""

from __future__ import annotations

# Detailed citation module
from agent_web_compiler.provenance.citation import CitationBuilder, CitationObject, RenderHint

# High-level unified API (has its own internal data classes)
from agent_web_compiler.provenance.engine import ProvenanceEngine

# Detailed evidence module
from agent_web_compiler.provenance.evidence import Evidence, EvidenceBuilder

# Detailed snapshot module
from agent_web_compiler.provenance.snapshot import Snapshot, SnapshotStore

# Detailed tracer module
from agent_web_compiler.provenance.tracer import TraceRecorder, TraceSession, TraceStep

__all__ = [
    # Engine facade
    "ProvenanceEngine",
    # Evidence
    "Evidence",
    "EvidenceBuilder",
    # Citations
    "CitationBuilder",
    "CitationObject",
    "RenderHint",
    # Snapshots
    "Snapshot",
    "SnapshotStore",
    # Traces
    "TraceRecorder",
    "TraceSession",
    "TraceStep",
]
