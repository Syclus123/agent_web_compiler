"""Demo: Web Task Planning

Shows how agent-search can find actions and generate execution plans
for web tasks — like a compiler-first browser agent.

Run: python examples/demos/web_task_demo.py
"""

from __future__ import annotations

import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agent_web_compiler.search import AgentSearch

console = Console()

_EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "web"

TASKS = [
    "Search for wireless headphones",
    "Add the product to cart",
    "Go to the next search results page",
    "Download the API reference",
]


def main() -> None:
    console.print()
    console.print(
        Panel(
            "[bold cyan]Web Task Planning[/bold cyan]\n\n"
            "Compile pages → discover actions → generate execution plans\n"
            "Like a compiler-first browser agent.",
            title="agent-web-compiler demo",
            border_style="cyan",
        )
    )

    # ── 1. Ingest pages ─────────────────────────────────────────────────
    search = AgentSearch()

    pages = {
        "product_page.html": _EXAMPLES_DIR / "product_page.html",
        "search_results.html": _EXAMPLES_DIR / "search_results.html",
        "docs_page.html": _EXAMPLES_DIR / "docs_page.html",
    }

    console.print("\n[bold]Step 1: Compile and index pages[/bold]\n")
    for label, path in pages.items():
        html = path.read_text(encoding="utf-8")
        doc = search.ingest_html(html, source_url=f"file://{path}")
        console.print(
            f"  [green]✓[/green] {label}: "
            f"{doc.block_count} blocks, [bold]{doc.action_count} actions[/bold]"
        )

    stats = search.stats
    console.print(
        f"\n  [dim]Index: {stats['documents']} docs, "
        f"{stats['blocks']} blocks, {stats['actions']} actions[/dim]"
    )

    # ── 2. Action search and execution plans ────────────────────────────
    console.print("\n[bold]Step 2: Plan tasks from discovered actions[/bold]\n")

    for i, task in enumerate(TASKS, 1):
        console.print(f"  [bold yellow]Task {i}:[/bold yellow] {task}")

        # Show matching actions
        t0 = time.perf_counter()
        action_results = search.search_actions(task, top_k=5)
        elapsed_search = time.perf_counter() - t0

        if action_results:
            action_table = Table(
                title=f"Matching Actions ({len(action_results)} found in {elapsed_search * 1000:.1f}ms)",
                show_lines=False,
            )
            action_table.add_column("Action", style="cyan")
            action_table.add_column("Type", style="yellow")
            action_table.add_column("Selector")
            action_table.add_column("Score", justify="right")
            for r in action_results[:4]:
                action_table.add_row(
                    r.text[:50],
                    r.metadata.get("action_type", "?"),
                    r.metadata.get("selector", "—")[:40],
                    f"{r.score:.3f}",
                )
            console.print(action_table)

        # Generate execution plan
        t0 = time.perf_counter()
        plan = search.plan(task)
        elapsed_plan = time.perf_counter() - t0

        console.print(
            Panel(
                plan.to_markdown(),
                title=f"Execution Plan ({elapsed_plan * 1000:.1f}ms)",
                border_style="green" if plan.confidence > 0.5 else "yellow",
                padding=(0, 2),
            )
        )

        # Browser commands preview
        commands = plan.to_browser_commands()
        if commands:
            console.print("  [dim]Browser commands:[/dim]")
            for cmd in commands:
                console.print(f"    [dim]{cmd}[/dim]")
        console.print()

    console.print(
        "[bold green]✓ All task plans generated from compiled page structure — "
        "no LLM needed for action discovery.[/bold green]\n"
    )


if __name__ == "__main__":
    main()
