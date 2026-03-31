"""Demo: Documentation Search with Grounded Answers

Shows how agent-web-compiler + agent-search turns HTML documentation
into a searchable knowledge base with cited, grounded answers.

Run: python examples/demos/docs_search_demo.py
"""

from __future__ import annotations

import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agent_web_compiler.search import AgentSearch
from agent_web_compiler.utils.text import count_tokens_approx

console = Console()

# Resolve example HTML files relative to this script
_EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "web"

QUESTIONS = [
    "What is the API authentication method?",
    "What are the rate limits?",
    "What types of neural networks exist?",
    "How to create a resource?",
    "What error codes are returned?",
]


def main() -> None:
    console.print()
    console.print(
        Panel(
            "[bold cyan]Documentation Search with Grounded Answers[/bold cyan]\n\n"
            "Compile HTML docs → index → search → grounded answers with citations",
            title="agent-web-compiler demo",
            border_style="cyan",
        )
    )

    # ── 1. Load and ingest ──────────────────────────────────────────────
    search = AgentSearch()

    files = {
        "docs_page.html": _EXAMPLES_DIR / "docs_page.html",
        "article.html": _EXAMPLES_DIR / "article.html",
    }

    raw_html_tokens = 0
    compiled_tokens = 0
    total_blocks = 0

    console.print("\n[bold]Step 1: Ingest documentation[/bold]\n")
    for label, path in files.items():
        html = path.read_text(encoding="utf-8")
        raw_tokens = count_tokens_approx(html)
        raw_html_tokens += raw_tokens

        doc = search.ingest_html(html, source_url=f"file://{path}")
        doc_tokens = count_tokens_approx(doc.canonical_markdown)
        compiled_tokens += doc_tokens
        total_blocks += doc.block_count

        console.print(
            f"  [green]✓[/green] {label}: "
            f"{raw_tokens:,} raw tokens → {doc_tokens:,} compiled tokens "
            f"({doc.block_count} blocks, {doc.action_count} actions)"
        )

    # ── 2. Before/after summary ─────────────────────────────────────────
    stats = search.stats
    summary_table = Table(title="Index Summary", show_header=True)
    summary_table.add_column("Metric", style="bold")
    summary_table.add_column("Value", justify="right")
    summary_table.add_row("Documents indexed", str(stats["documents"]))
    summary_table.add_row("Searchable blocks", str(stats["blocks"]))
    summary_table.add_row("Discovered actions", str(stats["actions"]))
    summary_table.add_row("Raw HTML tokens", f"{raw_html_tokens:,}")
    summary_table.add_row("Compiled tokens", f"{compiled_tokens:,}")
    savings = 1.0 - compiled_tokens / raw_html_tokens if raw_html_tokens else 0
    summary_table.add_row("Token savings", f"{savings:.0%}")
    console.print()
    console.print(summary_table)

    # ── 3. Ask questions ────────────────────────────────────────────────
    console.print("\n[bold]Step 2: Ask questions and get grounded answers[/bold]\n")

    timing_table = Table(title="Query Performance")
    timing_table.add_column("#", justify="right")
    timing_table.add_column("Question")
    timing_table.add_column("Time", justify="right")
    timing_table.add_column("Citations", justify="right")
    timing_table.add_column("Confidence", justify="right")

    for i, question in enumerate(QUESTIONS, 1):
        console.print(f"  [bold yellow]Q{i}:[/bold yellow] {question}")

        t0 = time.perf_counter()
        answer = search.answer(question, top_k=5)
        elapsed = time.perf_counter() - t0

        console.print(
            Panel(
                answer.to_markdown(),
                border_style="green" if answer.evidence_sufficient else "yellow",
                padding=(0, 2),
            )
        )

        timing_table.add_row(
            str(i),
            question,
            f"{elapsed * 1000:.1f}ms",
            str(len(answer.citations)),
            f"{answer.confidence:.0%}",
        )

    # ── 4. Timing summary ──────────────────────────────────────────────
    console.print(timing_table)
    console.print(
        "\n[bold green]✓ All queries answered from compiled documentation — "
        "zero network calls, full provenance.[/bold green]\n"
    )


if __name__ == "__main__":
    main()
