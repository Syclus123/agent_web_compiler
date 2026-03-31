"""Site Memory — long-term structural memory for visited websites.

Learns templates, noise patterns, entry points, navigation paths,
and action habits across multiple visits to the same domain.
"""

from agent_web_compiler.memory.site_memory import SiteInsight, SiteMemory

__all__ = [
    "SiteInsight",
    "SiteMemory",
]
