"""Example: Using agent-web-compiler with browser-use framework.

Shows compiler-first + browser-fallback pattern that reduces
the need for repeated DOM/screenshot analysis.

Requirements:
    pip install agent-web-compiler browser-use
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 1. Compiler-first page context
# ---------------------------------------------------------------------------

from agent_web_compiler import compile_html
from agent_web_compiler.core.config import CompileConfig


def get_page_context(page_html: str, url: str) -> dict:
    """Compile a page into a structured context for the agent.

    The browser-use framework typically sends raw DOM or screenshots
    to the LLM. This function pre-compiles the page into a compact
    structured representation, saving tokens and improving accuracy.

    Args:
        page_html: Raw HTML from the browser page.
        url: Current page URL.

    Returns:
        A context dict with semantic content and available actions.
    """
    doc = compile_html(
        page_html,
        source_url=url,
        config=CompileConfig(
            include_actions=True,
            min_importance=0.2,
            max_blocks=50,  # Keep context manageable
        ),
    )

    return {
        "url": url,
        "title": doc.title,
        "summary": doc.summary_markdown(max_blocks=10),
        "blocks": [
            {
                "type": block.type.value,
                "text": block.text[:300],
                "section": " > ".join(block.section_path),
            }
            for block in doc.get_main_content(min_importance=0.3)
        ],
        "actions": [
            {
                "id": action.id,
                "type": action.type.value,
                "label": action.label,
                "selector": action.selector,
                "group": action.group,
            }
            for action in doc.actions
        ],
    }


# Expected output:
# {
#     "url": "https://example.com/search",
#     "title": "Search Results",
#     "summary": "# Search Results\n\nFound 42 results for 'agent frameworks'...",
#     "blocks": [...],
#     "actions": [
#         {"id": "a_next", "type": "click", "label": "Next Page", ...},
#         {"id": "a_filter", "type": "select", "label": "Sort By", ...},
#     ]
# }


# ---------------------------------------------------------------------------
# 2. Action translation for browser-use commands
# ---------------------------------------------------------------------------

def translate_action(action: dict, value: str | None = None) -> dict:
    """Translate a compiled action into a browser-use command.

    Maps the generic action format from agent-web-compiler to the
    specific command format expected by browser-use.

    Args:
        action: An action dict from get_page_context().
        value: Optional value for input/select actions.

    Returns:
        A browser-use compatible command dict.
    """
    action_type = action["type"]
    selector = action["selector"]

    if action_type in ("click", "submit"):
        return {"action": "click", "selector": selector}
    elif action_type == "input":
        return {
            "action": "type",
            "selector": selector,
            "text": value or "",
        }
    elif action_type == "select":
        return {
            "action": "select",
            "selector": selector,
            "value": value or "",
        }
    elif action_type == "navigate":
        return {"action": "goto", "url": action.get("target_url", "")}
    else:
        return {"action": "click", "selector": selector}


# ---------------------------------------------------------------------------
# 3. Browser-use integration with compiler-first pattern
# ---------------------------------------------------------------------------

class CompilerFirstAgent:
    """Agent wrapper that compiles pages before processing.

    Pattern: On each page load, compile first, then let the LLM
    decide actions based on structured content. Fall back to raw
    browser interaction only when needed.

    This reduces the need for repeated DOM/screenshot analysis
    across navigation steps.
    """

    def __init__(self):
        self.compiled_pages: dict[str, dict] = {}  # URL -> context cache

    def on_page_load(self, page_html: str, url: str) -> dict:
        """Called by browser-use when a page loads.

        Compiles the page and caches the result. The compiled context
        is much smaller than raw HTML, so caching is cheap.
        """
        context = get_page_context(page_html, url)
        self.compiled_pages[url] = context
        return context

    def get_action_for_intent(self, url: str, intent: str) -> dict | None:
        """Find and translate an action matching the agent's intent.

        Args:
            url: Current page URL (to look up cached context).
            intent: What the agent wants to do, e.g. "click next page".

        Returns:
            A browser-use command dict, or None if no match found.
        """
        context = self.compiled_pages.get(url)
        if context is None:
            return None

        intent_lower = intent.lower()
        for action in context["actions"]:
            label = (action.get("label") or "").lower()
            if intent_lower in label or label in intent_lower:
                return translate_action(action)
        return None

    def get_page_summary(self, url: str) -> str:
        """Get a concise markdown summary of a previously compiled page."""
        context = self.compiled_pages.get(url)
        if context is None:
            return f"Page {url} not yet compiled."
        return context["summary"]


# ---------------------------------------------------------------------------
# 4. Usage with browser-use (pseudo-code showing integration points)
# ---------------------------------------------------------------------------

def run_browser_use_task(task: str, start_url: str):
    """Run a browser-use task with compiler-first page understanding.

    Pseudo-code showing where agent-web-compiler integrates with
    the browser-use framework.
    """
    agent = CompilerFirstAgent()

    # from browser_use import Browser, Agent
    # browser = Browser()
    # page = browser.goto(start_url)
    # page_html = page.content()

    # # Compile on load — this is the key integration point
    # context = agent.on_page_load(page_html, start_url)
    #
    # # Feed compiled context to the LLM instead of raw DOM
    # llm_prompt = f"""
    # Task: {task}
    #
    # Current page ({context['title']}):
    # {context['summary']}
    #
    # Available actions:
    # {json.dumps(context['actions'], indent=2)}
    #
    # Which action should I take?
    # """
    #
    # # LLM decides on an intent
    # intent = llm.complete(llm_prompt)  # e.g., "click Add to Cart"
    #
    # # Translate intent to browser command
    # command = agent.get_action_for_intent(start_url, intent)
    # if command:
    #     browser.execute(command)
    # else:
    #     # Fallback to raw browser interaction
    #     browser.screenshot_and_act(intent)

    print(f"Would execute task: {task}")
    print(f"Starting at: {start_url}")


if __name__ == "__main__":
    print("=== Browser-Use Integration Example ===")

    # Demo with sample HTML
    sample_html = """
    <html><head><title>Product Page</title></head>
    <body>
        <h1>Premium Widget</h1>
        <p>$29.99 - In Stock</p>
        <button id="add-cart">Add to Cart</button>
        <button id="buy-now">Buy Now</button>
        <a href="/products">Back to Products</a>
    </body></html>
    """

    context = get_page_context(sample_html, "https://example.com/product/1")
    print(f"Title: {context['title']}")
    print(f"Blocks: {len(context['blocks'])}")
    print(f"Actions: {len(context['actions'])}")

    for action in context["actions"]:
        cmd = translate_action(action)
        print(f"  {action['label']} -> {cmd}")
