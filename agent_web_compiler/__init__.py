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

    # Publish a browser-harness domain-skill (requires `harness` extra)
    from agent_web_compiler import DomainSkillPublisher
    skill = DomainSkillPublisher().generate_from_document(doc, task="scraping")
    skill.write_to_repo("~/code/browser-harness")

    # Drive the user's real Chrome end-to-end (requires `harness` extra)
    from agent_web_compiler import LiveRuntime
    rt = LiveRuntime.from_url("https://github.com/browser-use/browser-harness")
    outcome = rt.run("star the repository", max_actions=1)
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
from agent_web_compiler.publisher.domain_skill import DomainSkill, DomainSkillPublisher
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
    # BH-compatible skill publishing (optional extra, safe to import without it)
    "DomainSkill",
    "DomainSkillPublisher",
    # Version
    "__version__",
]


def __getattr__(name: str):  # noqa: ANN202
    """Lazy loader for optional submodules.

    Exposing :class:`LiveRuntime` at the top level is very convenient for docs
    and README examples, but importing it eagerly would pull the
    ``runtime.browser_harness`` subpackage into every ``import
    agent_web_compiler`` — even when browser-harness itself is not installed.
    This indirection keeps the happy path dependency-free.
    """
    if name == "LiveRuntime":
        from agent_web_compiler.runtime.browser_harness import LiveRuntime

        return LiveRuntime
    if name == "LiveActionExecutor":
        from agent_web_compiler.runtime.browser_harness import LiveActionExecutor

        return LiveActionExecutor
    raise AttributeError(f"module 'agent_web_compiler' has no attribute {name!r}")
