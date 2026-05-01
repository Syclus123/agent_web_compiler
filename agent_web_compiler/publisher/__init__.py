"""Publisher package — generate agent-friendly site files.

The primary entry point is :class:`SitePublisher`, which collects compiled
AgentDocuments and generates standardised files (llms.txt, agent.json,
content.json, actions.json, agent-sitemap.xml, agent-feed.json) for agent
consumption.

Individual generators are also available for direct use:

- :func:`generate_llms_txt` — LLM-friendly site overview
- :func:`generate_agent_json` — structured content + action manifest
- :func:`generate_content_json` — block-level content feed
- :func:`generate_actions_json` — interactive affordances
- :func:`generate_agent_sitemap` — agent-optimized sitemap
- :func:`generate_delta_feed` — delta feed for incremental updates
- :class:`DomainSkillPublisher` — emit a browser-harness-compatible
  ``agent-workspace/domain-skills/<site>/<task>.md`` from an
  :class:`AgentDocument` or a :class:`SiteInsight`.
"""

from __future__ import annotations

from agent_web_compiler.publisher.actions_json import generate_actions_json
from agent_web_compiler.publisher.agent_sitemap import generate_agent_sitemap
from agent_web_compiler.publisher.content_json import generate_agent_json, generate_content_json
from agent_web_compiler.publisher.delta_feed import generate_delta_feed
from agent_web_compiler.publisher.domain_skill import DomainSkill, DomainSkillPublisher
from agent_web_compiler.publisher.llms_txt import generate_llms_txt
from agent_web_compiler.publisher.site_publisher import SitePublisher

__all__ = [
    "DomainSkill",
    "DomainSkillPublisher",
    "SitePublisher",
    "generate_actions_json",
    "generate_agent_json",
    "generate_agent_sitemap",
    "generate_content_json",
    "generate_delta_feed",
    "generate_llms_txt",
]
