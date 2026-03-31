"""Example: Using agent-web-compiler with OpenAI CUA (Computer Use Agent).

Shows how to compile web pages into accessibility-tree-like format
that CUA agents can consume directly, and how to expose actions
as OpenAI function-calling tool definitions.

Requirements:
    pip install agent-web-compiler openai
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 1. Compile a webpage into structured content
# ---------------------------------------------------------------------------

from agent_web_compiler import compile_url
from agent_web_compiler.core.config import CompileConfig

doc = compile_url(
    "https://shopping-site.com/product/12345",
    config=CompileConfig(include_actions=True, include_provenance=True),
)


# ---------------------------------------------------------------------------
# 2. Convert to CUA observation format
# ---------------------------------------------------------------------------

def to_cua_observation(doc) -> dict:
    """Convert an AgentDocument into a CUA-style observation.

    Returns a compact dict that the CUA agent can use in place of
    (or alongside) a screenshot-based observation.
    """
    return {
        "type": "compiled_page",
        "url": doc.source_url,
        "title": doc.title,
        # Semantic blocks as an accessibility-tree-like structure
        "content": [
            {
                "role": block.type.value,
                "text": block.text[:500],  # Truncate for token efficiency
                "section": " > ".join(block.section_path),
                "importance": block.importance,
            }
            for block in doc.get_main_content(min_importance=0.3)
        ],
        # Actions the agent can take
        "available_actions": [
            {
                "id": action.id,
                "type": action.type.value,
                "label": action.label,
                "selector": action.selector,
                "role": action.role,
            }
            for action in doc.actions
        ],
    }


observation = to_cua_observation(doc)

# Expected output (abbreviated):
# {
#     "type": "compiled_page",
#     "url": "https://shopping-site.com/product/12345",
#     "title": "Premium Widget - Shopping Site",
#     "content": [
#         {"role": "heading", "text": "Premium Widget", "section": "", "importance": 0.95},
#         {"role": "paragraph", "text": "$29.99 - In Stock", "section": "Product Info", ...},
#         ...
#     ],
#     "available_actions": [
#         {"id": "a_add_cart", "type": "click", "label": "Add to Cart", ...},
#         {"id": "a_buy_now", "type": "click", "label": "Buy Now", ...},
#     ]
# }


# ---------------------------------------------------------------------------
# 3. Convert actions to OpenAI function-calling tool definitions
# ---------------------------------------------------------------------------

def to_tool_definitions(doc) -> list[dict]:
    """Convert extracted actions into OpenAI function tool definitions.

    Each action becomes a tool the agent can call via function calling.
    """
    tools = []
    for action in doc.actions:
        tool = {
            "type": "function",
            "function": {
                "name": f"page_action_{action.id}",
                "description": f"{action.type.value}: {action.label}",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }
        # For input actions, add a value parameter
        if action.type.value in ("input", "select"):
            tool["function"]["parameters"]["properties"]["value"] = {
                "type": "string",
                "description": f"Value to enter into '{action.label}'",
            }
            tool["function"]["parameters"]["required"].append("value")

        tools.append(tool)
    return tools


tools = to_tool_definitions(doc)


# ---------------------------------------------------------------------------
# 4. Full CUA loop with OpenAI
# ---------------------------------------------------------------------------

def run_cua_task(task: str, start_url: str) -> str:
    """Run a CUA task using compiled page understanding.

    This is a simplified loop showing the pattern. In production,
    you would handle navigation, errors, and multi-step flows.
    """
    # from openai import OpenAI
    # client = OpenAI()

    doc = compile_url(start_url, config=CompileConfig(include_actions=True))
    observation = to_cua_observation(doc)
    tools = to_tool_definitions(doc)

    messages = [
        {
            "role": "system",
            "content": (
                "You are a web agent. Use the compiled page observation "
                "and available tools to complete tasks. "
                "Prefer structured actions over raw browser commands."
            ),
        },
        {
            "role": "user",
            "content": f"Task: {task}\n\nCurrent page:\n{observation}",
        },
    ]

    # response = client.chat.completions.create(
    #     model="gpt-4o",
    #     messages=messages,
    #     tools=tools,
    # )
    #
    # # Process tool calls — each maps back to a page action
    # for tool_call in response.choices[0].message.tool_calls:
    #     action_id = tool_call.function.name.replace("page_action_", "")
    #     action = next(a for a in doc.actions if a.id == action_id)
    #     print(f"Executing: {action.type} on {action.selector}")
    #     # Execute action via browser automation...

    return "Task completed"


if __name__ == "__main__":
    print("=== OpenAI CUA Integration Example ===")
    print(f"Compiled {doc.block_count} blocks and {doc.action_count} actions")
    print(f"Tools generated: {len(tools)}")
    print(f"\nObservation preview:")
    for item in observation["content"][:3]:
        print(f"  [{item['role']}] {item['text'][:60]}...")
