"""agent-web-compiler: Compile the Human Web into the Agent Web."""

__version__ = "0.1.0"

from agent_web_compiler.api.compile import compile_html, compile_url

__all__ = ["compile_url", "compile_html", "__version__"]
