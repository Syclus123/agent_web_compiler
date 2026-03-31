"""Example: Using agent-web-compiler as a LangChain Tool.

Shows how to add web compilation as a tool for LangChain agents
and how to use AWCDocumentLoader for RAG pipelines.

Requirements:
    pip install agent-web-compiler langchain langchain-openai
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 1. AWCTool — a LangChain tool for web compilation
# ---------------------------------------------------------------------------

# from langchain.tools import BaseTool
# from langchain.pydantic_v1 import BaseModel as LCBaseModel, Field as LCField

from agent_web_compiler import compile_html, compile_url
from agent_web_compiler.core.config import CompileConfig


class AWCTool:
    """LangChain-compatible tool that compiles web pages.

    To use as a real LangChain tool, subclass BaseTool:

        class AWCTool(BaseTool):
            name = "web_compiler"
            description = "..."
            def _run(self, url: str) -> str: ...
    """

    name = "web_compiler"
    description = (
        "Compiles a web page URL into structured semantic content. "
        "Returns a compact markdown summary with key information extracted. "
        "Use this instead of raw web scraping for better accuracy."
    )

    def __init__(self, config: CompileConfig | None = None):
        self.config = config or CompileConfig(
            include_actions=True,
            min_importance=0.2,
            max_blocks=30,  # Keep output manageable for LLM context
        )

    def run(self, url: str) -> str:
        """Compile a URL and return a structured summary.

        Args:
            url: The web page URL to compile.

        Returns:
            A markdown summary with semantic blocks and metadata.
        """
        doc = compile_url(url, config=self.config)

        parts = [
            f"# {doc.title}",
            f"Source: {doc.source_url}",
            f"Blocks: {doc.block_count} | Actions: {doc.action_count}",
            "",
            doc.summary_markdown(max_blocks=20),
        ]

        # Append action summary if present
        if doc.actions:
            parts.append("\n## Available Actions")
            for action in doc.actions[:10]:
                parts.append(f"- [{action.type.value}] {action.label}")

        return "\n".join(parts)


# Usage in an agent:
#
# from langchain.agents import initialize_agent, AgentType
# from langchain_openai import ChatOpenAI
#
# llm = ChatOpenAI(model="gpt-4o")
# tools = [AWCTool()]
# agent = initialize_agent(tools, llm, agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION)
#
# result = agent.run("What are the pricing tiers on example.com?")


# ---------------------------------------------------------------------------
# 2. AWCDocumentLoader — a LangChain document loader for RAG
# ---------------------------------------------------------------------------

# from langchain.document_loaders.base import BaseLoader
# from langchain.schema import Document as LCDocument


class AWCDocumentLoader:
    """LangChain-compatible document loader using agent-web-compiler.

    Compiles web pages into semantic blocks, where each block becomes
    a LangChain Document with rich metadata for better retrieval.

    To use as a real LangChain loader, subclass BaseLoader:

        class AWCDocumentLoader(BaseLoader):
            def load(self) -> list[Document]: ...
    """

    def __init__(
        self,
        urls: list[str],
        config: CompileConfig | None = None,
    ):
        self.urls = urls
        self.config = config or CompileConfig(
            include_provenance=True,
            min_importance=0.2,
        )

    def load(self) -> list[dict]:
        """Load and compile all URLs into LangChain-style documents.

        Each semantic block becomes a separate document with metadata
        for filtering, section-based retrieval, and provenance tracking.

        Returns:
            List of document dicts (page_content + metadata).
            In production, these would be LangChain Document objects.
        """
        documents = []

        for url in self.urls:
            doc = compile_url(url, config=self.config)

            for block in doc.get_main_content(min_importance=0.3):
                documents.append({
                    "page_content": block.text,
                    "metadata": {
                        "source": url,
                        "title": doc.title,
                        "block_type": block.type.value,
                        "section_path": " > ".join(block.section_path),
                        "importance": block.importance,
                        "block_id": block.id,
                        "doc_id": doc.doc_id,
                    },
                })

        return documents


# Usage in a RAG pipeline:
#
# from langchain_openai import OpenAIEmbeddings
# from langchain.vectorstores import Chroma
#
# # Load and compile docs
# loader = AWCDocumentLoader(urls=[
#     "https://docs.example.com/api-reference",
#     "https://docs.example.com/quickstart",
#     "https://docs.example.com/faq",
# ])
# documents = loader.load()  # Returns LangChain Document objects
#
# # Index into vector store
# vectorstore = Chroma.from_documents(documents, OpenAIEmbeddings())
#
# # Query with section-aware retrieval
# results = vectorstore.similarity_search(
#     "How do I authenticate API requests?",
#     filter={"block_type": "paragraph"},  # Filter by block type
# )


# ---------------------------------------------------------------------------
# 3. Query-aware compilation for focused RAG ingestion
# ---------------------------------------------------------------------------

def compile_for_rag(url: str, topic: str) -> list[dict]:
    """Compile a URL with query-aware filtering for focused RAG ingestion.

    Uses the query parameter to boost relevant blocks, producing
    smaller and more relevant chunks for the vector store.

    Args:
        url: Web page URL.
        topic: The topic to focus on during compilation.

    Returns:
        List of document dicts focused on the given topic.
    """
    config = CompileConfig(
        query=topic,
        max_blocks=30,
        min_importance=0.3,
        include_provenance=True,
    )

    doc = compile_url(url, config=config)

    return [
        {
            "page_content": block.text,
            "metadata": {
                "source": url,
                "topic": topic,
                "block_type": block.type.value,
                "section_path": " > ".join(block.section_path),
                "importance": block.importance,
                "relevance": block.metadata.get("query_score", 0.0),
            },
        }
        for block in doc.blocks
    ]


# Expected output:
# [
#     {
#         "page_content": "To authenticate, include your API key in the...",
#         "metadata": {
#             "source": "https://docs.example.com/api-reference",
#             "topic": "authentication",
#             "block_type": "paragraph",
#             "section_path": "Authentication > API Keys",
#             "importance": 0.92,
#             "relevance": 0.88,
#         }
#     },
#     ...
# ]


if __name__ == "__main__":
    print("=== LangChain Integration Example ===")

    # Demo with the AWCTool
    tool = AWCTool()
    print(f"Tool: {tool.name}")
    print(f"Description: {tool.description}")

    # Demo the loader (would need network access for real URLs)
    # loader = AWCDocumentLoader(urls=["https://example.com"])
    # docs = loader.load()
    # print(f"Loaded {len(docs)} document chunks")
