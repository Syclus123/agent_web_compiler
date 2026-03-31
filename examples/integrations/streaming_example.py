"""Example: Streaming compilation for real-time processing.

Shows how to use the streaming API for large documents
with early termination and progressive rendering.

Requirements:
    pip install agent-web-compiler
    pip install httpx-sse  # For SSE client example
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 1. Basic streaming compilation with token budget
# ---------------------------------------------------------------------------

from agent_web_compiler import compile_stream
from agent_web_compiler.core.config import CompileConfig


def stream_with_budget(html: str, token_budget: int = 2000) -> None:
    """Stream compilation with a token budget.

    Blocks are yielded one at a time. When the token budget is reached,
    the stream emits a "budget_reached" event and stops producing blocks.
    The "complete" event still contains a valid AgentDocument with all
    blocks emitted up to that point.

    Args:
        html: Raw HTML to compile.
        token_budget: Maximum tokens to emit before stopping.
    """
    config = CompileConfig(
        token_budget=token_budget,
        include_actions=True,
        debug=True,
    )

    blocks_received = 0
    actions_received = 0

    for event in compile_stream(html, config=config):
        if event.event_type == "progress":
            print(f"  [progress] {event.data['stage']}")

        elif event.event_type == "block":
            blocks_received += 1
            block_type = event.data["type"]
            text_preview = event.data["text"][:60]
            print(f"  [block {blocks_received}] ({block_type}) {text_preview}...")

        elif event.event_type == "action":
            actions_received += 1
            print(f"  [action] {event.data['type']}: {event.data.get('label', '')}")

        elif event.event_type == "budget_reached":
            print(f"  [budget] {event.data['reason']}")
            print(f"  [budget] Blocks emitted: {event.data['blocks_emitted']}")

        elif event.event_type == "complete":
            doc_title = event.data.get("title", "(untitled)")
            block_count = event.data.get("block_count", 0)
            print(f"  [complete] '{doc_title}' — {block_count} blocks")

        elif event.event_type == "error":
            print(f"  [error] {event.data['message']}")

    print(f"\nTotal: {blocks_received} blocks, {actions_received} actions")


# ---------------------------------------------------------------------------
# 2. Progressive rendering pattern
# ---------------------------------------------------------------------------

def progressive_render(html: str) -> list[str]:
    """Progressively render blocks as they arrive.

    Useful for showing a loading indicator that fills in with
    real content as the compilation progresses.

    Args:
        html: Raw HTML to compile.

    Returns:
        List of rendered markdown sections.
    """
    sections: list[str] = []

    for event in compile_stream(html):
        if event.event_type == "block":
            block_type = event.data["type"]
            text = event.data["text"]

            # Render different block types appropriately
            if block_type == "heading":
                level = event.data.get("level", 2)
                sections.append(f"{'#' * level} {text}")
            elif block_type == "code":
                lang = event.data.get("metadata", {}).get("language", "")
                sections.append(f"```{lang}\n{text}\n```")
            elif block_type == "table":
                sections.append(text)  # Already formatted
            else:
                sections.append(text)

            # In a real UI, you could update the display here:
            # ui.update_content("\n\n".join(sections))

    return sections


# ---------------------------------------------------------------------------
# 3. SSE client for the REST API streaming endpoint
# ---------------------------------------------------------------------------

def consume_sse_stream(server_url: str, html: str) -> None:
    """Consume streaming compilation from the REST API.

    The /v1/compile/stream endpoint returns Server-Sent Events.
    Each event has a type and JSON data payload.

    Args:
        server_url: Base URL of the agent-web-compiler server.
        html: Raw HTML to compile.
    """
    # import httpx
    # import json
    #
    # with httpx.stream(
    #     "POST",
    #     f"{server_url}/v1/compile/stream",
    #     json={"html": html, "mode": "balanced"},
    #     headers={"Accept": "text/event-stream"},
    # ) as response:
    #     for line in response.iter_lines():
    #         if line.startswith("data: "):
    #             event = json.loads(line[6:])
    #             event_type = event["event_type"]
    #             data = event["data"]
    #
    #             if event_type == "block":
    #                 print(f"Block: [{data['type']}] {data['text'][:80]}")
    #             elif event_type == "action":
    #                 print(f"Action: {data['type']} - {data.get('label', '')}")
    #             elif event_type == "progress":
    #                 print(f"Stage: {data['stage']}")
    #             elif event_type == "complete":
    #                 print(f"Done! {data['block_count']} blocks")
    #             elif event_type == "error":
    #                 print(f"Error: {data['message']}")

    print(f"Would connect to {server_url}/v1/compile/stream")
    print("SSE events would stream in real-time")


# ---------------------------------------------------------------------------
# 4. Async streaming
# ---------------------------------------------------------------------------

async def async_stream_example(html: str) -> None:
    """Async streaming compilation example.

    Uses the async generator for integration with async frameworks
    like FastAPI, aiohttp, or asyncio-based agents.
    """
    from agent_web_compiler.pipeline.stream_compiler import StreamCompiler

    compiler = StreamCompiler()

    async for event in compiler.compile_stream_async(html):
        if event.event_type == "block":
            # Process blocks as they arrive
            print(f"  Async block: {event.data['type']}")
        elif event.event_type == "complete":
            print(f"  Async complete: {event.data.get('block_count', 0)} blocks")


# ---------------------------------------------------------------------------
# 5. Early termination pattern
# ---------------------------------------------------------------------------

def find_first_match(html: str, target_type: str) -> dict | None:
    """Find the first block of a given type and stop.

    Demonstrates early termination — useful when you only need
    a specific piece of information from a large document.

    Args:
        html: Raw HTML to compile.
        target_type: Block type to search for (e.g., "table", "code").

    Returns:
        The first matching block dict, or None if not found.
    """
    for event in compile_stream(html):
        if event.event_type == "block" and event.data["type"] == target_type:
            return event.data
        # Note: in a generator, breaking out stops processing
        # but the "complete" event won't be yielded
    return None


if __name__ == "__main__":
    print("=== Streaming Compilation Example ===\n")

    sample_html = """
    <html><head><title>Streaming Demo</title></head>
    <body>
        <h1>Large Document</h1>
        <p>First paragraph with important information.</p>
        <p>Second paragraph with more details about the topic.</p>
        <table><tr><th>Name</th><th>Value</th></tr>
        <tr><td>Alpha</td><td>100</td></tr></table>
        <pre><code>print("hello world")</code></pre>
        <p>Third paragraph wrapping up the discussion.</p>
        <button>Submit</button>
        <a href="/next">Next Page</a>
    </body></html>
    """

    print("--- Basic streaming ---")
    stream_with_budget(sample_html, token_budget=500)

    print("\n--- Progressive render ---")
    sections = progressive_render(sample_html)
    print(f"Rendered {len(sections)} sections")

    print("\n--- Early termination (find first table) ---")
    table = find_first_match(sample_html, "table")
    if table:
        print(f"Found table: {table['text'][:80]}...")
    else:
        print("No table found")
