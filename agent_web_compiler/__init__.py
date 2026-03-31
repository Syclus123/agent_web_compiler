"""agent-web-compiler: Compile the Human Web into the Agent Web."""

__version__ = "0.3.0"

from agent_web_compiler.api.compile import compile_batch, compile_html, compile_url

__all__ = ["compile_url", "compile_html", "compile_batch", "__version__"]
