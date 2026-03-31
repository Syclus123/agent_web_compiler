"""agent-index: Multi-granularity indexing for compiled Agent Web objects.

Indexes documents, blocks, actions, and sites for hybrid retrieval.
No external database required — runs embedded with optional persistence.
"""

from agent_web_compiler.index.embeddings import (
    CallableEmbedder,
    Embedder,
    TFIDFEmbedder,
)
from agent_web_compiler.index.engine import IndexEngine
from agent_web_compiler.index.schema import (
    ActionRecord,
    BlockRecord,
    DocumentRecord,
    SiteRecord,
)

__all__ = [
    "ActionRecord",
    "BlockRecord",
    "CallableEmbedder",
    "DocumentRecord",
    "Embedder",
    "IndexEngine",
    "SiteRecord",
    "TFIDFEmbedder",
]
