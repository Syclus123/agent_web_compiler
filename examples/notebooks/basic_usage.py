"""Example: Compile a local HTML file and display results."""

from agent_web_compiler import compile_html
from agent_web_compiler.exporters.json_exporter import to_json
from pathlib import Path

# Read the sample article
html = Path(__file__).parent.parent / "web" / "article.html"
html_content = html.read_text()

# Compile with debug mode
doc = compile_html(html_content, debug=True)

# Print summary
print(f"Title: {doc.title}")
print(f"Blocks: {doc.block_count}")
print(f"Actions: {doc.action_count}")
print(f"Schema: v{doc.schema_version}")
print()

# Print blocks
print("=== Semantic Blocks ===")
for block in doc.blocks:
    importance = "█" * int(block.importance * 10)
    section = " > ".join(block.section_path) if block.section_path else "(root)"
    print(f"  [{block.type.value:15s}] {importance:10s} | {section}")
    print(f"    {block.text[:100]}")
    print()

# Print actions
print("=== Actions ===")
for action in doc.actions:
    print(f"  [{action.type.value:10s}] p={action.priority:.1f} | {action.label:30s} | {action.role or '-':20s} | {action.selector}")
print()

# Print markdown
print("=== Canonical Markdown (first 1000 chars) ===")
print(doc.canonical_markdown[:1000])
print()

# Print JSON (first 500 chars)
print("=== JSON (first 500 chars) ===")
print(to_json(doc)[:500])
