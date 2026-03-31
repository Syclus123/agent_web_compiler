"""Demo: AWC vs Traditional Approaches — Side-by-Side Comparison

Shows a concrete comparison of what an LLM sees when consuming:
1. Raw HTML
2. Naive text extraction
3. agent-web-compiler output

Run: python examples/demos/comparison_demo.py
"""

from __future__ import annotations

from pathlib import Path

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from agent_web_compiler.api.compile import compile_html
from agent_web_compiler.utils.text import count_tokens_approx, extract_text_from_html

console = Console()

_EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "web"


def main() -> None:
    console.print()
    console.print(
        Panel(
            "[bold cyan]AWC vs Traditional Approaches[/bold cyan]\n\n"
            "What does an LLM actually see? Raw HTML, stripped text, or\n"
            "structured semantic objects with actions and provenance?",
            title="agent-web-compiler demo",
            border_style="cyan",
        )
    )

    # ── Load the product page ───────────────────────────────────────────
    html_path = _EXAMPLES_DIR / "product_page.html"
    html = html_path.read_text(encoding="utf-8")

    console.print(f"\n[bold]Input:[/bold] {html_path.name} ({len(html):,} chars)\n")

    # ── Approach 1: Raw HTML ────────────────────────────────────────────
    raw_tokens = count_tokens_approx(html)
    raw_preview = html[:500].replace("\n", "↵\n")

    # ── Approach 2: Naive text extraction ───────────────────────────────
    naive_text = extract_text_from_html(html)
    naive_tokens = count_tokens_approx(naive_text)
    naive_preview = naive_text[:500]

    # ── Approach 3: AWC compilation ─────────────────────────────────────
    doc = compile_html(
        html,
        source_url="demo://product_page",
        mode="balanced",
        include_actions=True,
        include_provenance=True,
    )
    awc_markdown = doc.canonical_markdown
    awc_tokens = count_tokens_approx(awc_markdown)
    awc_preview = awc_markdown[:500]

    # ── Side-by-side panels ─────────────────────────────────────────────
    console.print("[bold]Side-by-side: first 500 characters of each approach[/bold]\n")

    panels = Columns(
        [
            Panel(
                Text(raw_preview, style="dim"),
                title="[red]Raw HTML[/red]",
                width=40,
                border_style="red",
            ),
            Panel(
                Text(naive_preview, style="dim"),
                title="[yellow]Naive Text[/yellow]",
                width=40,
                border_style="yellow",
            ),
            Panel(
                Text(awc_preview),
                title="[green]AWC Output[/green]",
                width=40,
                border_style="green",
            ),
        ],
        equal=True,
        expand=True,
    )
    console.print(panels)
    console.print()

    # ── Comparison table ────────────────────────────────────────────────
    table = Table(title="Comparison: What the LLM Gets", show_lines=True)
    table.add_column("Metric", style="bold")
    table.add_column("Raw HTML", style="red", justify="right")
    table.add_column("Naive Text", style="yellow", justify="right")
    table.add_column("AWC", style="green", justify="right")

    table.add_row("Tokens", f"{raw_tokens:,}", f"{naive_tokens:,}", f"{awc_tokens:,}")
    table.add_row("Characters", f"{len(html):,}", f"{len(naive_text):,}", f"{len(awc_markdown):,}")

    # Structure
    from agent_web_compiler.core.block import BlockType

    heading_count = len(doc.get_blocks_by_type(BlockType.HEADING))
    table_count = len(doc.get_blocks_by_type(BlockType.TABLE))
    code_count = len(doc.get_blocks_by_type(BlockType.CODE))
    list_count = len(doc.get_blocks_by_type(BlockType.LIST))

    table.add_row("Semantic blocks", "0", "0", str(doc.block_count))
    table.add_row("Headings preserved", "?", "0", str(heading_count))
    table.add_row("Tables preserved", "?", "0", str(table_count))
    table.add_row("Code blocks", "?", "0", str(code_count))
    table.add_row("Lists", "?", "0", str(list_count))

    # Actions
    table.add_row(
        "Actions discovered",
        "[red]0[/red]",
        "[red]0[/red]",
        f"[bold green]{doc.action_count}[/bold green]",
    )

    # Entities
    entity_count = sum(len(b.entities) for b in doc.blocks if hasattr(b, "entities") and b.entities)
    table.add_row(
        "Entities extracted",
        "[red]0[/red]",
        "[red]0[/red]",
        f"[bold green]{entity_count}[/bold green]",
    )

    # Provenance
    has_provenance = any(
        b.provenance is not None for b in doc.blocks if hasattr(b, "provenance")
    )
    table.add_row(
        "Provenance/traceability",
        "[red]No[/red]",
        "[red]No[/red]",
        "[bold green]Yes[/bold green]" if has_provenance else "[yellow]Partial[/yellow]",
    )

    # Token savings
    savings_vs_html = (1.0 - awc_tokens / raw_tokens) if raw_tokens else 0
    savings_vs_naive = (1.0 - awc_tokens / naive_tokens) if naive_tokens else 0
    table.add_row("Token savings vs HTML", "—", "—", f"[bold green]{savings_vs_html:.0%}[/bold green]")
    table.add_row("Token savings vs naive", "—", "—", f"[bold green]{savings_vs_naive:.0%}[/bold green]")

    console.print(table)

    # ── Highlight ───────────────────────────────────────────────────────
    console.print()
    console.print(
        Panel(
            f"[bold green]AWC found {doc.action_count} actions and "
            f"{entity_count} entities. Naive markdown found 0.[/bold green]\n\n"
            f"Token savings: [bold]{savings_vs_html:.0%}[/bold] vs raw HTML, "
            f"[bold]{savings_vs_naive:.0%}[/bold] vs naive text.\n"
            f"Blocks: {doc.block_count} semantic blocks with hierarchy, "
            f"provenance, and type information.",
            title="The Bottom Line",
            border_style="green",
        )
    )
    console.print()

    # ── Action details ──────────────────────────────────────────────────
    if doc.actions:
        action_table = Table(title=f"Discovered Actions ({doc.action_count})")
        action_table.add_column("#", justify="right")
        action_table.add_column("Type", style="yellow")
        action_table.add_column("Label")
        action_table.add_column("Selector", style="dim")
        action_table.add_column("Priority", justify="right")
        for i, a in enumerate(doc.actions[:15], 1):
            action_table.add_row(
                str(i),
                a.type,
                (a.label or "—")[:40],
                (a.selector or "—")[:35],
                f"{a.priority:.2f}",
            )
        console.print(action_table)
        console.print()


if __name__ == "__main__":
    main()
