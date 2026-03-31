"""Example: Using agent-web-compiler for RAG ingestion.

Shows how to compile web pages into semantically-rich chunks
for vector store indexing with provenance tracking.

Requirements:
    pip install agent-web-compiler chromadb sentence-transformers
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 1. Compile web pages into semantic blocks with provenance
# ---------------------------------------------------------------------------

from agent_web_compiler import compile_url
from agent_web_compiler.core.config import CompileConfig


def compile_for_indexing(urls: list[str]) -> list[dict]:
    """Compile multiple URLs into indexable chunks.

    Each semantic block becomes a chunk with rich metadata.
    Unlike naive text splitting, blocks respect document structure:
    headings, paragraphs, tables, and code stay intact.

    Args:
        urls: List of web page URLs to compile.

    Returns:
        List of chunk dicts ready for embedding and indexing.
    """
    config = CompileConfig(
        include_provenance=True,
        min_importance=0.2,
    )

    chunks = []
    for url in urls:
        doc = compile_url(url, config=config)

        for block in doc.get_main_content(min_importance=0.3):
            # Skip very short blocks (navigation noise, etc.)
            if len(block.text.strip()) < 20:
                continue

            chunk = {
                "id": f"{doc.doc_id}:{block.id}",
                "text": block.text,
                "metadata": {
                    # Source tracking
                    "source_url": url,
                    "doc_id": doc.doc_id,
                    "block_id": block.id,
                    "title": doc.title,
                    # Structural metadata
                    "block_type": block.type.value,
                    "section_path": " > ".join(block.section_path),
                    "importance": block.importance,
                    "order": block.order,
                    # Provenance for grounded citations
                    "dom_path": (
                        block.provenance.dom.dom_path
                        if block.provenance and block.provenance.dom
                        else None
                    ),
                },
            }
            chunks.append(chunk)

    return chunks


# Expected output:
# [
#     {
#         "id": "sha256:a1b2c3d4:b_003",
#         "text": "Rate limits are enforced per API key. The default...",
#         "metadata": {
#             "source_url": "https://docs.example.com/api",
#             "doc_id": "sha256:a1b2c3d4",
#             "block_id": "b_003",
#             "title": "API Reference",
#             "block_type": "paragraph",
#             "section_path": "Rate Limits > Default Quotas",
#             "importance": 0.85,
#             "order": 3,
#             "dom_path": "html > body > main > section:nth-child(2) > p",
#         }
#     },
#     ...
# ]


# ---------------------------------------------------------------------------
# 2. Index into ChromaDB with semantic embeddings
# ---------------------------------------------------------------------------

def index_to_chromadb(chunks: list[dict], collection_name: str = "web_docs"):
    """Index compiled chunks into ChromaDB.

    ChromaDB handles embedding automatically. The rich metadata
    enables filtered retrieval by section, block type, or source.

    Args:
        chunks: Chunk dicts from compile_for_indexing().
        collection_name: ChromaDB collection name.
    """
    # import chromadb
    # client = chromadb.Client()
    # collection = client.get_or_create_collection(
    #     name=collection_name,
    #     metadata={"hnsw:space": "cosine"},
    # )
    #
    # collection.add(
    #     ids=[c["id"] for c in chunks],
    #     documents=[c["text"] for c in chunks],
    #     metadatas=[c["metadata"] for c in chunks],
    # )
    #
    # print(f"Indexed {len(chunks)} chunks into '{collection_name}'")

    print(f"Would index {len(chunks)} chunks into '{collection_name}'")


# ---------------------------------------------------------------------------
# 3. Query with provenance-grounded retrieval
# ---------------------------------------------------------------------------

def query_with_provenance(
    query: str,
    collection_name: str = "web_docs",
    n_results: int = 5,
) -> list[dict]:
    """Query the vector store and return results with provenance.

    Results include the original source URL, section path, and DOM path
    so the agent can cite its sources precisely.

    Args:
        query: Natural language query.
        collection_name: ChromaDB collection name.
        n_results: Number of results to return.

    Returns:
        List of result dicts with text and provenance metadata.
    """
    # import chromadb
    # client = chromadb.Client()
    # collection = client.get_collection(collection_name)
    #
    # results = collection.query(
    #     query_texts=[query],
    #     n_results=n_results,
    #     # Filter to specific block types for focused retrieval
    #     where={"block_type": {"$in": ["paragraph", "table", "code"]}},
    # )
    #
    # return [
    #     {
    #         "text": doc,
    #         "source_url": meta["source_url"],
    #         "section": meta["section_path"],
    #         "dom_path": meta.get("dom_path"),
    #         "importance": meta["importance"],
    #     }
    #     for doc, meta in zip(results["documents"][0], results["metadatas"][0])
    # ]

    # Simulated output for demonstration
    return [
        {
            "text": "Rate limits are enforced per API key...",
            "source_url": "https://docs.example.com/api",
            "section": "Rate Limits > Default Quotas",
            "dom_path": "html > body > main > section:nth-child(2) > p",
            "importance": 0.85,
        }
    ]


# ---------------------------------------------------------------------------
# 4. Query-aware compilation for focused ingestion
# ---------------------------------------------------------------------------

def focused_ingest(url: str, topics: list[str]) -> list[dict]:
    """Compile a URL multiple times with different topic filters.

    This produces topic-specific chunks that are more relevant
    for retrieval within each topic domain.

    Args:
        url: Web page URL.
        topics: List of topics to focus compilation on.

    Returns:
        All topic-filtered chunks combined.
    """
    all_chunks = []

    for topic in topics:
        config = CompileConfig(
            query=topic,
            max_blocks=20,
            min_importance=0.3,
            include_provenance=True,
        )

        doc = compile_url(url, config=config)

        for block in doc.blocks:
            all_chunks.append({
                "id": f"{doc.doc_id}:{block.id}:{topic}",
                "text": block.text,
                "metadata": {
                    "source_url": url,
                    "topic": topic,
                    "block_type": block.type.value,
                    "section_path": " > ".join(block.section_path),
                    "importance": block.importance,
                },
            })

    return all_chunks


if __name__ == "__main__":
    print("=== RAG Pipeline Integration Example ===")

    # Demo: compile and show chunk structure
    # In production, replace with real URLs
    # chunks = compile_for_indexing(["https://docs.example.com/api"])
    # index_to_chromadb(chunks)
    # results = query_with_provenance("What are the rate limits?")
    # for r in results:
    #     print(f"  [{r['section']}] {r['text'][:60]}...")
    #     print(f"  Source: {r['source_url']}")
    #     print(f"  DOM: {r['dom_path']}")

    print("Run with real URLs to see full output.")
    print("Key benefits over naive text splitting:")
    print("  - Blocks respect document structure (no mid-sentence splits)")
    print("  - Rich metadata enables filtered retrieval")
    print("  - Provenance tracking for grounded citations")
    print("  - Importance scoring pre-filters noise")
