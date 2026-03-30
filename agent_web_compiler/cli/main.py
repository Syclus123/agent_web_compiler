"""CLI entry point for agent-web-compiler.

Usage:
    awc compile https://example.com -o out/
    awc compile ./page.html -o out/
    awc compile ./paper.pdf -o out/
    awc inspect out/agent_document.json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


@click.group()
@click.version_option(package_name="agent-web-compiler")
def cli() -> None:
    """agent-web-compiler — Compile the Human Web into the Agent Web."""


@cli.command()
@click.argument("source")
@click.option("-o", "--output", type=click.Path(), default=None, help="Output directory or file")
@click.option(
    "--mode",
    type=click.Choice(["fast", "balanced", "high_recall"]),
    default="balanced",
    help="Compilation mode",
)
@click.option(
    "--render",
    type=click.Choice(["off", "auto", "always"]),
    default="off",
    help="Browser rendering mode",
)
@click.option("--actions/--no-actions", default=True, help="Extract actions")
@click.option("--provenance/--no-provenance", default=True, help="Include provenance")
@click.option("--debug/--no-debug", default=False, help="Include debug metadata")
@click.option("--format", "output_format", type=click.Choice(["json", "markdown", "both"]), default="both")
@click.option("--timeout", type=float, default=30.0, help="HTTP timeout in seconds")
def compile(
    source: str,
    output: str | None,
    mode: str,
    render: str,
    actions: bool,
    provenance: bool,
    debug: bool,
    output_format: str,
    timeout: float,
) -> None:
    """Compile a URL, HTML file, or PDF into an AgentDocument."""
    from agent_web_compiler.core.config import CompileConfig, CompileMode, RenderMode

    config = CompileConfig(
        mode=CompileMode(mode),
        render=RenderMode(render),
        include_actions=actions,
        include_provenance=provenance,
        debug=debug,
        timeout_seconds=timeout,
    )

    console.print(f"\n[bold blue]⚡ Compiling:[/bold blue] {source}")
    start = time.perf_counter()

    try:
        source_path = Path(source)
        if source_path.exists():
            from agent_web_compiler.api.compile import compile_file

            doc = compile_file(source, config=config)
        elif source.startswith(("http://", "https://")):
            from agent_web_compiler.api.compile import compile_url

            doc = compile_url(source, config=config)
        else:
            console.print(f"[red]Error:[/red] '{source}' is not a valid URL or file path")
            sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        if debug:
            console.print_exception()
        sys.exit(1)

    elapsed = time.perf_counter() - start

    # Display summary
    _print_summary(doc, elapsed)

    # Write output
    if output:
        output_path = Path(output)
        output_path.mkdir(parents=True, exist_ok=True)

        if output_format in ("json", "both"):
            json_path = output_path / "agent_document.json"
            from agent_web_compiler.exporters.json_exporter import to_json

            json_path.write_text(to_json(doc))
            console.print(f"  [green]✓[/green] JSON: {json_path}")

        if output_format in ("markdown", "both"):
            md_path = output_path / "document.md"
            md_path.write_text(doc.canonical_markdown)
            console.print(f"  [green]✓[/green] Markdown: {md_path}")

        if debug:
            debug_path = output_path / "debug_bundle.json"
            from agent_web_compiler.exporters.debug_exporter import to_debug_bundle

            debug_path.write_text(json.dumps(to_debug_bundle(doc), indent=2, default=str))
            console.print(f"  [green]✓[/green] Debug: {debug_path}")
    else:
        # Print to stdout
        if output_format == "json":
            from agent_web_compiler.exporters.json_exporter import to_json

            click.echo(to_json(doc))
        elif output_format == "markdown":
            click.echo(doc.canonical_markdown)
        else:
            click.echo(doc.canonical_markdown)

    console.print()


@cli.command()
@click.argument("path", type=click.Path(exists=True))
def inspect(path: str) -> None:
    """Inspect an AgentDocument JSON file."""
    data = json.loads(Path(path).read_text())

    console.print(Panel(f"[bold]{data.get('title', 'Untitled')}[/bold]", title="AgentDocument"))

    table = Table(show_header=False)
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("Schema Version", data.get("schema_version", "?"))
    table.add_row("Source Type", data.get("source_type", "?"))
    table.add_row("Source URL", data.get("source_url", "N/A") or "N/A")
    table.add_row("Language", data.get("lang", "?") or "?")
    table.add_row("Blocks", str(data.get("block_count", len(data.get("blocks", [])))))
    table.add_row("Actions", str(data.get("action_count", len(data.get("actions", [])))))

    quality = data.get("quality", {})
    table.add_row("Parse Confidence", f"{quality.get('parse_confidence', 0):.0%}")
    table.add_row("Warnings", str(len(quality.get("warnings", []))))

    console.print(table)

    # Show block type distribution
    blocks = data.get("blocks", [])
    if blocks:
        type_counts: dict[str, int] = {}
        for b in blocks:
            t = b.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1

        block_table = Table(title="Block Types")
        block_table.add_column("Type", style="cyan")
        block_table.add_column("Count", justify="right")
        for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
            block_table.add_row(t, str(c))
        console.print(block_table)

    # Show top actions
    actions_data = data.get("actions", [])
    if actions_data:
        action_table = Table(title=f"Actions (top 10 of {len(actions_data)})")
        action_table.add_column("Type", style="yellow")
        action_table.add_column("Label")
        action_table.add_column("Priority", justify="right")
        for a in actions_data[:10]:
            action_table.add_row(
                a.get("type", "?"),
                a.get("label", "?")[:50],
                f"{a.get('priority', 0):.2f}",
            )
        console.print(action_table)


def _print_summary(doc: object, elapsed: float) -> None:
    """Print a compilation summary."""
    from agent_web_compiler.utils.text import count_tokens_approx

    tokens = count_tokens_approx(doc.canonical_markdown)

    console.print(f"\n[bold green]✓ Compiled in {elapsed:.2f}s[/bold green]")
    console.print(f"  Title: [bold]{doc.title or 'Untitled'}[/bold]")
    console.print(f"  Blocks: {len(doc.blocks)}")
    console.print(f"  Actions: {len(doc.actions)}")
    console.print(f"  Markdown tokens: ~{tokens:,}")

    if doc.quality.warnings:
        console.print(f"  [yellow]Warnings: {len(doc.quality.warnings)}[/yellow]")
        for w in doc.quality.warnings[:5]:
            console.print(f"    ⚠ {w}")


if __name__ == "__main__":
    cli()
