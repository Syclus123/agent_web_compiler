"""Example: Using agent-web-compiler with Claude Computer Use.

Shows how to provide structured page understanding instead of
raw screenshots, reducing token usage and improving accuracy.

Requirements:
    pip install agent-web-compiler anthropic
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 1. Compile a webpage into XML content for Claude
# ---------------------------------------------------------------------------

from agent_web_compiler import compile_url
from agent_web_compiler.core.config import CompileConfig

doc = compile_url(
    "https://dashboard.example.com",
    config=CompileConfig(include_actions=True, include_provenance=True),
)


# ---------------------------------------------------------------------------
# 2. Convert to XML content block for Claude messages
# ---------------------------------------------------------------------------

def to_xml_content(doc) -> str:
    """Convert an AgentDocument into XML that Claude can parse efficiently.

    XML is Claude's preferred structured format and uses fewer tokens
    than equivalent JSON for the same information.
    """
    parts = [f'<page url="{doc.source_url or ""}" title="{doc.title}">']

    # Semantic blocks
    parts.append("  <content>")
    for block in doc.get_main_content(min_importance=0.3):
        section = " > ".join(block.section_path) if block.section_path else ""
        parts.append(
            f'    <block type="{block.type.value}" section="{section}" '
            f'importance="{block.importance:.2f}">'
        )
        parts.append(f"      {block.text}")
        parts.append("    </block>")
    parts.append("  </content>")

    # Available actions
    parts.append("  <actions>")
    for action in doc.actions:
        parts.append(
            f'    <action id="{action.id}" type="{action.type.value}" '
            f'label="{action.label}" selector="{action.selector}" />'
        )
    parts.append("  </actions>")

    parts.append("</page>")
    return "\n".join(parts)


xml_content = to_xml_content(doc)

# Expected output (abbreviated):
# <page url="https://dashboard.example.com" title="Dashboard">
#   <content>
#     <block type="heading" section="" importance="0.95">
#       Dashboard Overview
#     </block>
#     <block type="paragraph" section="Metrics" importance="0.80">
#       Active users: 1,234 | Revenue: $56,789
#     </block>
#   </content>
#   <actions>
#     <action id="a_export" type="click" label="Export CSV" selector="button#export" />
#     <action id="a_filter" type="select" label="Date Range" selector="select#date-range" />
#   </actions>
# </page>


# ---------------------------------------------------------------------------
# 3. Convert to computer_use tool result format
# ---------------------------------------------------------------------------

def to_computer_use_result(doc) -> dict:
    """Format compiled page as a computer_use tool result.

    This can be sent alongside or instead of a screenshot to give
    Claude structured understanding of the page.
    """
    return {
        "type": "tool_result",
        "tool_use_id": "current_page",
        "content": [
            {
                "type": "text",
                "text": to_xml_content(doc),
            },
            # You can still include a screenshot for visual context:
            # {
            #     "type": "image",
            #     "source": {"type": "base64", "media_type": "image/png", "data": "..."},
            # },
        ],
    }


# ---------------------------------------------------------------------------
# 4. Middleware pattern for multi-page tasks
# ---------------------------------------------------------------------------

class CompiledPageMiddleware:
    """Middleware that compiles each page before sending to Claude.

    Sits between the browser automation layer and the Claude API,
    enriching each page observation with structured content.
    """

    def __init__(self, config: CompileConfig | None = None):
        self.config = config or CompileConfig(
            include_actions=True,
            include_provenance=True,
            min_importance=0.2,
        )
        self.page_history: list[dict] = []

    def on_page_load(self, url: str, page_html: str) -> dict:
        """Called when the browser navigates to a new page.

        Args:
            url: Current page URL.
            page_html: Raw HTML of the loaded page.

        Returns:
            A message dict ready to append to the Claude conversation.
        """
        from agent_web_compiler import compile_html

        doc = compile_html(page_html, source_url=url, config=self.config)

        page_context = {
            "url": url,
            "title": doc.title,
            "block_count": doc.block_count,
            "action_count": doc.action_count,
        }
        self.page_history.append(page_context)

        return {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Page loaded: {url}\n"
                        f"Title: {doc.title}\n"
                        f"Blocks: {doc.block_count}, Actions: {doc.action_count}\n\n"
                        f"{to_xml_content(doc)}"
                    ),
                },
            ],
        }

    def find_action(self, doc, intent: str) -> dict | None:
        """Find the best matching action for a given intent.

        Simple keyword matching; in production you might use embeddings.
        """
        intent_lower = intent.lower()
        for action in doc.actions:
            if intent_lower in (action.label or "").lower():
                return {
                    "type": action.type.value,
                    "selector": action.selector,
                    "label": action.label,
                }
            if action.role and intent_lower in action.role.lower():
                return {
                    "type": action.type.value,
                    "selector": action.selector,
                    "label": action.label,
                }
        return None


# ---------------------------------------------------------------------------
# 5. Full Claude Computer Use loop
# ---------------------------------------------------------------------------

def run_computer_use_task(task: str, start_url: str) -> str:
    """Run a Computer Use task with compiled page understanding.

    This is a simplified loop showing the pattern. In production,
    add error handling, retries, and navigation tracking.
    """
    # from anthropic import Anthropic
    # client = Anthropic()

    middleware = CompiledPageMiddleware()

    # Compile the starting page
    doc = compile_url(start_url, config=CompileConfig(include_actions=True))
    page_message = middleware.on_page_load(start_url, doc.canonical_markdown)

    messages = [
        {
            "role": "user",
            "content": (
                f"Task: {task}\n\n"
                "I'll provide you with compiled page content. "
                "Use the action selectors to interact with the page."
            ),
        },
        page_message,
    ]

    # response = client.messages.create(
    #     model="claude-sonnet-4-20250514",
    #     max_tokens=4096,
    #     messages=messages,
    #     tools=[{"type": "computer_20241022", "name": "computer", ...}],
    # )
    #
    # # Process tool use blocks
    # for block in response.content:
    #     if block.type == "tool_use":
    #         # Execute the action via browser automation
    #         print(f"Action: {block.input}")

    return "Task completed"


if __name__ == "__main__":
    print("=== Claude Computer Use Integration Example ===")
    print(f"Compiled {doc.block_count} blocks and {doc.action_count} actions")
    print(f"\nXML content preview ({len(xml_content)} chars):")
    print(xml_content[:500] + "...")
