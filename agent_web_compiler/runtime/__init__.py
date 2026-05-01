"""Runtime subpackages — where AgentDocuments meet the real world.

``agent_web_compiler.runtime`` is the home of all "live" execution backends.
Unlike the rest of the package (which is purely transformational — HTML in,
``AgentDocument`` out), runtime backends produce side effects against an
actual browser / API / agent framework.

Submodules are **optional**. Each one gates its third-party dependency behind
a lazy import and a pyproject extra:

- :mod:`agent_web_compiler.runtime.browser_harness` — drive the user's real
  Chrome via `browser-harness <https://github.com/browser-use/browser-harness>`_.
  Install with ``pip install "agent-web-compiler[harness]"``.
"""
