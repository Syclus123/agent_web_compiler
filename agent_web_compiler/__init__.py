"""agent-web-compiler: Compile the Human Web into the Agent Web. Then search it.

Usage:
    # Compile
    from agent_web_compiler import compile_url, compile_html
    doc = compile_url("https://example.com")

    # Compile + Index + Search
    from agent_web_compiler import AgentSearch
    search = AgentSearch()
    search.ingest_url("https://example.com")
    answer = search.answer("What is the rate limit?")

    # Custom pipeline
    from agent_web_compiler import PipelineBuilder
    pipeline = PipelineBuilder().skip_actions().build()
    doc = pipeline.compile(html)

    # Publish agent-friendly site files
    from agent_web_compiler import SitePublisher
    publisher = SitePublisher(site_name="My Docs", site_url="https://docs.example.com")
    publisher.add_page(doc)
    publisher.generate_all("output/agent-publish/")
"""

from __future__ import annotations

__version__ = "0.7.0"

from agent_web_compiler.api.compile import (
    compile_batch,
    compile_html,
    compile_stream,
    compile_url,
)
from agent_web_compiler.memory.site_memory import SiteMemory
from agent_web_compiler.pipeline.builder import PipelineBuilder
from agent_web_compiler.provenance.engine import ProvenanceEngine
from agent_web_compiler.publisher.site_publisher import SitePublisher
from agent_web_compiler.search.agent_search import AgentSearch

__all__ = [
    # Compilation
    "compile_url",
    "compile_html",
    "compile_batch",
    "compile_stream",
    # Extensible pipeline
    "PipelineBuilder",
    # Search (primary entry point)
    "AgentSearch",
    # Site Memory
    "SiteMemory",
    # Provenance
    "ProvenanceEngine",
    # Publisher (site-level file generation)
    "SitePublisher",
    # Version
    "__version__",
]
