"""Example: End-to-end agent-search workflow.

Demonstrates the complete compile → index → search → answer → plan pipeline.
"""

# --- Setup ---
# from agent_web_compiler.search import AgentSearch
#
# search = AgentSearch()

# --- Step 1: Ingest Content ---
# Compile and index web pages, PDFs, or any document
# search.ingest_url("https://docs.example.com/api-reference")
# search.ingest_url("https://docs.example.com/authentication")
# search.ingest_url("https://docs.example.com/pricing")
# search.ingest_file("technical-report.pdf")

# --- Step 2: Fact Search ---
# Find specific information across all indexed content
# results = search.search("What is the rate limit for the API?")
# for r in results.results[:3]:
#     print(f"[{r.score:.2f}] {r.text[:100]}")
#     print(f"  Source: {r.section_path}")

# --- Step 3: Grounded Answering ---
# Get an answer backed by citations, not hallucinations
# answer = search.answer("What authentication methods are supported?")
# print(answer.to_markdown())
# Output:
#   **Answer**: The API supports API key authentication via Bearer token
#   and OAuth 2.0 for user-level access. [1][2]
#
#   **Evidence**:
#   [1] "Include your API key in the Authorization header..."
#       — API Reference > Authentication (docs.example.com/api-reference)
#   [2] "OAuth 2.0 flow requires client_id and client_secret..."
#       — Authentication > OAuth Setup (docs.example.com/authentication)

# --- Step 4: Action Search ---
# Find executable actions across indexed pages
# actions = search.search_actions("download pricing PDF")
# for a in actions[:3]:
#     print(f"[{a.score:.2f}] {a.text} -> {a.metadata.get('selector')}")

# --- Step 5: Task Planning ---
# Generate an execution plan for complex tasks
# plan = search.plan("Go to pricing page and download the enterprise PDF")
# print(plan.to_markdown())
# Output:
#   ## Execution Plan: Download enterprise pricing PDF
#   1. **Navigate** to https://docs.example.com/pricing
#   2. **Click** "Enterprise Plan" link (selector: a.enterprise-link)
#   3. **Click** "Download PDF" button (selector: button.download-pdf)

# --- Step 6: Save/Load Index ---
# Persist the index for reuse
# search.save("docs_index.json")
# Later: search.load("docs_index.json")

# --- Inline demo with real data ---
if __name__ == "__main__":
    from agent_web_compiler.search.agent_search import AgentSearch
    from pathlib import Path

    search = AgentSearch()

    # Ingest example HTML files
    examples_dir = Path(__file__).parent.parent / "web"
    for html_file in sorted(examples_dir.glob("*.html")):
        doc = search.ingest_file(str(html_file))
        print(f"Indexed: {doc.title} ({doc.block_count} blocks, {doc.action_count} actions)")

    print(f"\nIndex stats: {search.stats}")

    # Search for content
    print("\n--- Block Search: 'neural network architecture' ---")
    results = search.search_blocks("neural network architecture", top_k=3)
    for r in results:
        print(f"  [{r.score:.2f}] {r.text[:80]}...")

    # Search for actions
    print("\n--- Action Search: 'search' ---")
    actions = search.search_actions("search", top_k=3)
    for a in actions:
        print(f"  [{a.score:.2f}] {a.text} (selector: {a.metadata.get('selector', 'N/A')})")

    # Get a grounded answer
    print("\n--- Grounded Answer ---")
    answer = search.answer("What are the types of neural networks?")
    print(answer.to_markdown())

    # Plan a task
    print("\n--- Execution Plan ---")
    plan = search.plan("search for machine learning")
    print(plan.to_markdown())
