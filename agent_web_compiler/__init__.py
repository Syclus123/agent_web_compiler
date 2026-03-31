"""agent-web-compiler: Compile the Human Web into the Agent Web."""

from __future__ import annotations

__version__ = "0.7.0"

from agent_web_compiler.api.compile import compile_batch, compile_html, compile_stream, compile_url

__all__ = ["compile_url", "compile_html", "compile_batch", "compile_stream", "__version__"]
