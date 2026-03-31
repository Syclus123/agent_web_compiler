"""CLI entry point for agent-web-compiler.

Usage:
    awc compile https://example.com -o out/
    awc compile ./page.html -o out/
    awc compile ./paper.pdf -o out/
    awc inspect out/agent_document.json
    awc bench run --fixtures-dir bench/tasks
    awc bench run --fixtures-dir bench/tasks -o report.md
    awc bench inspect bench/tasks/blog_article.json
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
def interactive() -> None:
    """Start interactive search REPL."""
    from agent_web_compiler.cli.repl import InteractiveREPL

    repl = InteractiveREPL()
    repl.run()


@cli.command()
@click.argument("sources", nargs=-1, required=True)
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
    sources: tuple[str, ...],
    output: str | None,
    mode: str,
    render: str,
    actions: bool,
    provenance: bool,
    debug: bool,
    output_format: str,
    timeout: float,
) -> None:
    """Compile one or more URLs, HTML files, or PDFs into AgentDocuments.

    When multiple sources are given, batch compilation is used automatically.
    """
    from agent_web_compiler.core.config import CompileConfig, CompileMode, RenderMode

    config = CompileConfig(
        mode=CompileMode(mode),
        render=RenderMode(render),
        include_actions=actions,
        include_provenance=provenance,
        debug=debug,
        timeout_seconds=timeout,
    )

    # Batch mode: multiple sources
    if len(sources) > 1:
        _compile_batch_cli(sources, output, config, debug, output_format)
        return

    # Single source mode
    source = sources[0]
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
        _write_output(doc, output, output_format, debug)
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


@cli.command()
@click.option("--host", default="0.0.0.0", help="Bind host address")
@click.option("--port", default=8000, type=int, help="Bind port")
@click.option(
    "--transport",
    type=click.Choice(["rest", "mcp"]),
    default="rest",
    help="Server transport protocol",
)
def serve(host: str, port: int, transport: str) -> None:
    """Start the compilation server."""
    if transport == "rest":
        try:
            import uvicorn  # noqa: F401 — used below
        except ImportError:
            console.print(
                "[red]Error:[/red] REST server requires the 'serve' extra. "
                "Install with: pip install agent-web-compiler[serve]"
            )
            sys.exit(1)

        from agent_web_compiler.serving.rest_server import create_app

        app = create_app()
        console.print(
            f"\n[bold blue]Starting REST server[/bold blue] on {host}:{port}\n"
        )
        uvicorn.run(app, host=host, port=port)

    elif transport == "mcp":
        try:
            from agent_web_compiler.serving.mcp_server import main as run_mcp
        except ImportError:
            console.print(
                "[red]Error:[/red] MCP dependencies not installed. "
                "Install the required MCP dependencies first."
            )
            sys.exit(1)

        console.print(
            f"\n[bold blue]Starting MCP server[/bold blue] on {host}:{port}\n"
        )
        run_mcp()


@cli.group()
def bench() -> None:
    """Benchmark commands."""


@bench.command(name="run")
@click.option(
    "--fixtures-dir",
    default="bench/tasks",
    help="Path to fixtures directory",
    type=click.Path(exists=True),
)
@click.option("-o", "--output", default=None, help="Output report path (markdown file)")
def bench_run(fixtures_dir: str, output: str | None) -> None:
    """Run benchmarks against fixture files."""
    from bench.framework import BenchmarkRunner

    runner = BenchmarkRunner()
    console.print(f"\n[bold blue]Running benchmarks[/bold blue] from {fixtures_dir}\n")

    try:
        results = runner.run_all(fixtures_dir)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    report = runner.generate_report(results)

    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report)
        console.print(f"[green]Report written to {output_path}[/green]")
    else:
        console.print(report)

    # Print summary
    console.print(f"\n[bold green]Completed {len(results)} benchmarks[/bold green]")
    for r in results:
        status = "[green]PASS[/green]" if r.fidelity and r.fidelity.text_coverage >= 0.5 else "[yellow]WARN[/yellow]"
        console.print(
            f"  {status} {r.result.fixture_name}: "
            f"{r.result.compression_ratio:.1f}x compression, "
            f"{r.result.block_count} blocks, "
            f"{r.result.compile_time_ms:.0f}ms"
        )
    console.print()


@bench.command(name="compare")
@click.option(
    "--fixtures-dir",
    default="bench/tasks",
    help="Path to fixtures directory",
    type=click.Path(exists=True),
)
@click.option("-o", "--output", default=None, help="Output report path (markdown file)")
def bench_compare(fixtures_dir: str, output: str | None) -> None:
    """Compare AWC against raw HTML and naive markdown on fixtures."""
    from bench.comparison import ComparisonRunner

    runner = ComparisonRunner()
    console.print(f"\n[bold blue]Running comparison[/bold blue] from {fixtures_dir}\n")

    try:
        results = runner.compare_all(fixtures_dir)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    report = runner.generate_report(results)

    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report)
        console.print(f"[green]Report written to {output_path}[/green]")
    else:
        console.print(report)

    # Print summary
    console.print(f"\n[bold green]Compared {len(results)} fixtures[/bold green]")
    for r in results:
        console.print(
            f"  {r.fixture_name}: "
            f"HTML {r.raw_html.token_count:,} → MD {r.naive_markdown.token_count:,} → "
            f"AWC {r.awc.token_count:,} tokens "
            f"([green]{r.token_savings_vs_html:.0%}[/green] savings vs HTML)"
        )
    console.print()


@bench.command(name="qa")
@click.option(
    "--fixtures-dir",
    default="bench/tasks",
    help="Path to fixtures directory",
    type=click.Path(exists=True),
)
@click.option("-o", "--output", default=None, help="Output report path (markdown file)")
def bench_qa(fixtures_dir: str, output: str | None) -> None:
    """Run QA-based evaluation on fixtures with qa_items."""
    from bench.eval.qa_eval import QAEvaluator

    evaluator = QAEvaluator()
    console.print(f"\n[bold blue]Running QA evaluation[/bold blue] from {fixtures_dir}\n")

    try:
        results = evaluator.evaluate_all(fixtures_dir)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if not results:
        console.print("[yellow]No fixtures with qa_items found.[/yellow]")
        return

    report = evaluator.generate_report(results)

    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report)
        console.print(f"[green]Report written to {output_path}[/green]")
    else:
        console.print(report)

    # Print summary
    console.print(f"\n[bold green]Evaluated {len(results)} fixtures[/bold green]")
    for r in results:
        status = "[green]PASS[/green]" if r.answer_recall >= 0.5 else "[yellow]WARN[/yellow]"
        console.print(
            f"  {status} {r.fixture_name}: "
            f"{r.answers_found}/{r.total_questions} answered "
            f"({r.answer_recall:.0%} recall)"
        )
    console.print()


@bench.command(name="search")
@click.option(
    "--fixtures-dir",
    default="bench/tasks",
    help="Path to fixtures directory",
    type=click.Path(exists=True),
)
@click.option("-o", "--output", default=None, help="Output report path (markdown file)")
def bench_search(fixtures_dir: str, output: str | None) -> None:
    """Run search quality benchmarks on fixtures with search_qa items."""
    from bench.eval.search_quality import SearchQualityBenchmark

    benchmark = SearchQualityBenchmark()
    console.print(f"\n[bold blue]Running search quality benchmarks[/bold blue] from {fixtures_dir}\n")

    try:
        results = benchmark.evaluate_all(fixtures_dir)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if not results:
        console.print("[yellow]No fixtures with search_qa items found.[/yellow]")
        return

    report = benchmark.generate_report(results)

    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report)
        console.print(f"[green]Report written to {output_path}[/green]")
    else:
        console.print(report)

    # Print summary
    console.print(f"\n[bold green]Evaluated {len(results)} fixtures[/bold green]")
    for r in results:
        status = "[green]PASS[/green]" if r.avg_recall_at_5 >= 0.5 else "[yellow]WARN[/yellow]"
        console.print(
            f"  {status} {r.fixture_name}: "
            f"R@5={r.avg_recall_at_5:.0%} R@10={r.avg_recall_at_10:.0%} "
            f"MRR={r.avg_mrr:.2f} CitPrec={r.avg_citation_precision:.0%}"
        )
    console.print()


@bench.command(name="inspect")
@click.argument("path", type=click.Path(exists=True))
def bench_inspect(path: str) -> None:
    """Inspect a single benchmark fixture and show detailed results."""
    from bench.framework import BenchmarkRunner

    fixture_path = Path(path)

    # Determine if path is a JSON spec or HTML file
    if fixture_path.suffix == ".json":
        spec = json.loads(fixture_path.read_text())
        html_path = fixture_path.parent / spec["html_file"]
    elif fixture_path.suffix == ".html":
        json_path = fixture_path.with_suffix(".json")
        if not json_path.exists():
            console.print(f"[red]Error:[/red] No matching spec file: {json_path}")
            sys.exit(1)
        spec = json.loads(json_path.read_text())
        html_path = fixture_path
    else:
        console.print(f"[red]Error:[/red] Expected .json or .html file, got: {fixture_path.suffix}")
        sys.exit(1)

    if not html_path.exists():
        console.print(f"[red]Error:[/red] HTML file not found: {html_path}")
        sys.exit(1)

    runner = BenchmarkRunner()
    result = runner.run_fixture(str(html_path), spec)

    console.print(Panel(f"[bold]{result.result.fixture_name}[/bold]", title="Benchmark Result"))

    # Efficiency table
    eff_table = Table(title="Token Efficiency")
    eff_table.add_column("Metric", style="bold")
    eff_table.add_column("Value", justify="right")
    eff_table.add_row("Raw Tokens", f"{result.result.raw_tokens:,}")
    eff_table.add_row("Compiled Tokens", f"{result.result.compiled_tokens:,}")
    eff_table.add_row("Compression", f"{result.result.compression_ratio:.1f}x")
    eff_table.add_row("Compile Time", f"{result.result.compile_time_ms:.1f}ms")
    eff_table.add_row("Blocks", str(result.result.block_count))
    eff_table.add_row("Actions", str(result.result.action_count))
    console.print(eff_table)

    # Fidelity table
    if result.fidelity:
        fid_table = Table(title="Content Fidelity")
        fid_table.add_column("Dimension", style="bold")
        fid_table.add_column("Score", justify="right")
        fid_table.add_row("Headings", f"{result.fidelity.heading_fidelity:.0%}")
        fid_table.add_row("Tables", f"{result.fidelity.table_fidelity:.0%}")
        fid_table.add_row("Code", f"{result.fidelity.code_fidelity:.0%}")
        fid_table.add_row("Text Coverage", f"{result.fidelity.text_coverage:.0%}")
        fid_table.add_row("Structure", f"{result.fidelity.structure_score:.0%}")
        console.print(fid_table)

    # Action table
    if result.actions:
        act_table = Table(title="Action Quality")
        act_table.add_column("Metric", style="bold")
        act_table.add_column("Value", justify="right")
        act_table.add_row("Recall", f"{result.actions.action_recall:.0%}")
        act_table.add_row("Precision", f"{result.actions.action_precision:.0%}")
        main_icon = "[green]✓[/green]" if result.actions.main_action_found else "[red]✗[/red]"
        act_table.add_row("Main Action Found", main_icon)
        console.print(act_table)

    # Warnings
    if result.result.warnings:
        console.print(f"\n[yellow]Warnings ({len(result.result.warnings)}):[/yellow]")
        for w in result.result.warnings:
            console.print(f"  - {w}")

    console.print()


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


def _write_output(doc: object, output: str, output_format: str, debug: bool) -> None:
    """Write a compiled document to an output directory."""
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


def _compile_batch_cli(
    sources: tuple[str, ...],
    output: str | None,
    config: object,
    debug: bool,
    output_format: str,
) -> None:
    """Handle batch compilation from the CLI."""
    from agent_web_compiler.api.batch import BatchCompiler, BatchItem

    console.print(f"\n[bold blue]⚡ Batch compiling {len(sources)} sources[/bold blue]")
    start = time.perf_counter()

    items = [BatchItem(source=s) for s in sources]
    compiler = BatchCompiler()

    try:
        result = compiler.compile_batch(items, config=config)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        if debug:
            console.print_exception()
        sys.exit(1)

    elapsed = time.perf_counter() - start

    console.print(f"\n[bold green]✓ Batch compiled in {elapsed:.2f}s[/bold green]")
    console.print(f"  Successful: {len(result.items)}")
    if result.errors:
        console.print(f"  [red]Errors: {len(result.errors)}[/red]")
        for src, err in result.errors.items():
            console.print(f"    [red]✗[/red] {src}: {err}")
    if result.site_profile:
        console.print(f"  Site profile learned: {result.site_profile.site}")

    # Write output
    if output:
        for i, doc in enumerate(result.items):
            doc_output = str(Path(output) / f"doc_{i:03d}")
            _write_output(doc, doc_output, output_format, debug)
    else:
        for doc in result.items:
            if output_format == "json":
                from agent_web_compiler.exporters.json_exporter import to_json

                click.echo(to_json(doc))
            else:
                click.echo(doc.canonical_markdown)
            click.echo("---")

    console.print()


# ---------------------------------------------------------------------------
# Search / Index commands
# ---------------------------------------------------------------------------


@cli.group()
def index() -> None:
    """Index management commands."""


@index.command(name="add")
@click.argument("sources", nargs=-1, required=True)
@click.option("--index-path", default="awc_index.json", help="Index file path")
@click.option(
    "--mode",
    type=click.Choice(["fast", "balanced", "high_recall"]),
    default="balanced",
    help="Compilation mode",
)
def index_add(sources: tuple[str, ...], index_path: str, mode: str) -> None:
    """Add URLs or files to the search index."""
    from agent_web_compiler.core.config import CompileConfig, CompileMode
    from agent_web_compiler.search import AgentSearch

    config = CompileConfig(mode=CompileMode(mode))
    search = AgentSearch(config=config)

    # Load existing index if present
    index_file = Path(index_path)
    if index_file.exists():
        search.load(index_path)
        console.print(f"[dim]Loaded existing index from {index_path}[/dim]")

    for source in sources:
        console.print(f"[blue]Indexing:[/blue] {source}")
        try:
            source_path = Path(source)
            if source_path.exists():
                doc = search.ingest_file(source)
            elif source.startswith(("http://", "https://")):
                doc = search.ingest_url(source)
            else:
                console.print(f"  [red]Error:[/red] '{source}' is not a valid URL or file path")
                continue
            console.print(
                f"  [green]✓[/green] {doc.title or 'Untitled'} "
                f"({doc.block_count} blocks, {doc.action_count} actions)"
            )
        except Exception as e:
            console.print(f"  [red]Error:[/red] {e}")

    search.save(index_path)
    console.print(f"\n[green]Index saved to {index_path}[/green]")
    stats = search.stats
    console.print(
        f"  {stats['documents']} documents, {stats['blocks']} blocks, "
        f"{stats['actions']} actions"
    )
    console.print()


@index.command(name="crawl")
@click.argument("seed_url")
@click.option("--max-pages", default=50, type=int, help="Maximum pages to crawl")
@click.option("--delay", default=0.5, type=float, help="Politeness delay between requests (seconds)")
@click.option("--max-depth", default=3, type=int, help="Maximum link depth from seed URL")
@click.option("--index-path", default="awc_index.json", help="Index file path")
@click.option(
    "--mode",
    type=click.Choice(["fast", "balanced", "high_recall"]),
    default="balanced",
    help="Compilation mode",
)
def index_crawl(
    seed_url: str,
    max_pages: int,
    delay: float,
    max_depth: int,
    index_path: str,
    mode: str,
) -> None:
    """Crawl a site and add all discovered pages to the index."""
    from agent_web_compiler.core.config import CompileConfig, CompileMode
    from agent_web_compiler.search import AgentSearch

    config = CompileConfig(mode=CompileMode(mode))
    search = AgentSearch(config=config)

    # Load existing index if present
    index_file = Path(index_path)
    if index_file.exists():
        search.load(index_path)
        console.print(f"[dim]Loaded existing index from {index_path}[/dim]")

    console.print(f"\n[bold blue]🕷  Crawling:[/bold blue] {seed_url}")
    console.print(f"  max_pages={max_pages}, delay={delay}s, max_depth={max_depth}\n")

    result = search.crawl_site(
        seed_url,
        max_pages=max_pages,
        delay_seconds=delay,
        max_depth=max_depth,
    )

    console.print(f"\n[bold green]✓ Crawl complete in {result.elapsed_seconds:.1f}s[/bold green]")
    console.print(f"  Pages crawled: {result.pages_crawled}")
    console.print(f"  Pages failed:  {result.pages_failed}")
    console.print(f"  Total blocks:  {result.total_blocks}")
    console.print(f"  Total actions: {result.total_actions}")

    if result.errors:
        console.print(f"\n  [red]Errors ({len(result.errors)}):[/red]")
        for url, err in list(result.errors.items())[:10]:
            console.print(f"    [red]✗[/red] {url}: {err}")

    search.save(index_path)
    console.print(f"\n[green]Index saved to {index_path}[/green]")
    stats = search.stats
    console.print(
        f"  {stats['documents']} documents, {stats['blocks']} blocks, "
        f"{stats['actions']} actions"
    )
    console.print()


@index.command(name="stats")
@click.option("--index-path", default="awc_index.json", help="Index file path")
def index_stats(index_path: str) -> None:
    """Show index statistics."""
    from agent_web_compiler.search import AgentSearch

    search = AgentSearch()
    try:
        search.load(index_path)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] Index file not found: {index_path}")
        sys.exit(1)

    stats = search.stats
    table = Table(title=f"Index: {index_path}")
    table.add_column("Metric", style="bold")
    table.add_column("Count", justify="right")
    table.add_row("Documents", str(stats["documents"]))
    table.add_row("Blocks", str(stats["blocks"]))
    table.add_row("Actions", str(stats["actions"]))
    table.add_row("Sites", str(stats["sites"]))
    console.print(table)
    console.print()


@cli.command(name="search")
@click.argument("query")
@click.option("--index-path", default="awc_index.json", help="Index file path")
@click.option("--top-k", default=5, type=int, help="Number of results")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json", "markdown"]),
    default="markdown",
    help="Output format",
)
def search_cmd(query: str, index_path: str, top_k: int, fmt: str) -> None:
    """Search the index for relevant content."""
    from agent_web_compiler.search import AgentSearch

    search = AgentSearch()
    try:
        search.load(index_path)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] Index file not found: {index_path}")
        sys.exit(1)

    response = search.search(query, top_k=top_k)

    if fmt == "json":
        data = {
            "query": response.query,
            "intent": response.intent,
            "total_candidates": response.total_candidates,
            "retrieval_time_ms": response.retrieval_time_ms,
            "results": [
                {
                    "kind": r.kind,
                    "score": round(r.score, 4),
                    "doc_id": r.doc_id,
                    "block_id": r.block_id,
                    "action_id": r.action_id,
                    "text": r.text[:200],
                    "section_path": r.section_path,
                }
                for r in response.results
            ],
        }
        click.echo(json.dumps(data, indent=2))
    elif fmt == "text":
        click.echo(f"Query: {response.query}")
        click.echo(f"Intent: {response.intent}")
        click.echo(f"Results: {len(response.results)} (of {response.total_candidates} candidates)")
        click.echo(f"Time: {response.retrieval_time_ms:.1f}ms\n")
        for i, r in enumerate(response.results, 1):
            click.echo(f"{i}. [{r.kind}] (score={r.score:.3f}) {r.text[:120]}")
    else:
        # markdown
        console.print(f"\n[bold]Search: {query}[/bold]")
        console.print(f"[dim]Intent: {response.intent} | {len(response.results)} results | {response.retrieval_time_ms:.1f}ms[/dim]\n")
        for i, r in enumerate(response.results, 1):
            kind_style = "cyan" if r.kind == "block" else "yellow"
            console.print(f"  {i}. [{kind_style}][{r.kind}][/{kind_style}] (score={r.score:.3f})")
            console.print(f"     {r.text[:150]}")
            if r.section_path:
                console.print(f"     [dim]{' > '.join(r.section_path)}[/dim]")
        console.print()


@cli.command()
@click.argument("query")
@click.option("--index-path", default="awc_index.json", help="Index file path")
@click.option("--top-k", default=5, type=int, help="Number of evidence results")
def answer(query: str, index_path: str, top_k: int) -> None:
    """Get a grounded answer with citations."""
    from agent_web_compiler.search import AgentSearch

    search = AgentSearch()
    try:
        search.load(index_path)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] Index file not found: {index_path}")
        sys.exit(1)

    result = search.answer(query, top_k=top_k)
    console.print()
    console.print(result.to_markdown())
    console.print()


@cli.command()
@click.argument("query")
@click.option("--index-path", default="awc_index.json", help="Index file path")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["markdown", "json", "commands"]),
    default="markdown",
    help="Output format",
)
def plan(query: str, index_path: str, fmt: str) -> None:
    """Generate an execution plan for a task."""
    from agent_web_compiler.search import AgentSearch

    search = AgentSearch()
    try:
        search.load(index_path)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] Index file not found: {index_path}")
        sys.exit(1)

    result = search.plan(query)

    if fmt == "json":
        click.echo(json.dumps(result.to_dict(), indent=2))
    elif fmt == "commands":
        click.echo(json.dumps(result.to_browser_commands(), indent=2))
    else:
        console.print()
        console.print(result.to_markdown())
        console.print()


# ---------------------------------------------------------------------------
# Publish commands
# ---------------------------------------------------------------------------


@cli.group()
def publish() -> None:
    """Agent Publisher Toolkit — generate agent-friendly site files."""


@publish.command(name="site")
@click.argument("seed_url")
@click.option("--output", "-o", required=True, help="Output directory for generated files")
@click.option("--max-pages", default=50, type=int, help="Maximum pages to crawl")
@click.option("--site-name", default="", help="Site display name")
@click.option("--site-description", default="", help="Site description")
def publish_site(
    seed_url: str,
    output: str,
    max_pages: int,
    site_name: str,
    site_description: str,
) -> None:
    """Crawl a site and generate all agent-friendly files.

    Discovers pages starting from SEED_URL, compiles each page, then
    generates llms.txt, agent.json, content.json, actions.json, and
    agent-sitemap.xml in the output directory.
    """
    from agent_web_compiler.publisher import SitePublisher

    publisher = SitePublisher(
        site_name=site_name,
        site_url=seed_url,
        site_description=site_description,
    )

    console.print(f"\n[bold blue]🕷  Crawling:[/bold blue] {seed_url}")
    console.print(f"  max_pages={max_pages}\n")

    try:
        count = publisher.crawl_site(seed_url, max_pages=max_pages)
    except Exception as e:
        console.print(f"[red]Error during crawl:[/red] {e}")
        sys.exit(1)

    console.print(f"[green]✓ Crawled {count} pages[/green]\n")

    try:
        files = publisher.generate_all(output)
    except Exception as e:
        console.print(f"[red]Error during generation:[/red] {e}")
        sys.exit(1)

    console.print(f"[bold green]✓ Generated {len(files)} files in {output}/[/bold green]")
    for fname in sorted(files):
        console.print(f"  [green]✓[/green] {fname}")
    console.print()

    # Show summary
    summary = publisher.summary
    console.print(
        f"  Pages: {summary['page_count']} | "
        f"Blocks: {summary['total_blocks']} | "
        f"Actions: {summary['total_actions']}"
    )
    console.print()


@publish.command(name="files")
@click.argument("sources", nargs=-1, required=True)
@click.option("--output", "-o", required=True, help="Output directory for generated files")
@click.option("--site-name", default="", help="Site display name")
@click.option("--site-url", default="", help="Site base URL")
def publish_files(
    sources: tuple[str, ...],
    output: str,
    site_name: str,
    site_url: str,
) -> None:
    """Generate agent-friendly files from local HTML/PDF files.

    Compiles each source file, then generates all agent-friendly output
    files in the output directory.
    """
    from agent_web_compiler.api.compile import compile_file
    from agent_web_compiler.publisher import SitePublisher

    publisher = SitePublisher(
        site_name=site_name,
        site_url=site_url,
    )

    console.print(f"\n[bold blue]⚡ Compiling {len(sources)} source(s)[/bold blue]\n")

    for source in sources:
        source_path = Path(source)
        if not source_path.exists():
            console.print(f"  [red]✗[/red] Not found: {source}")
            continue
        try:
            doc = compile_file(source)
            publisher.add_page(doc)
            console.print(
                f"  [green]✓[/green] {source_path.name} "
                f"({doc.block_count} blocks, {doc.action_count} actions)"
            )
        except Exception as e:
            console.print(f"  [red]✗[/red] {source_path.name}: {e}")

    if publisher.page_count == 0:
        console.print("\n[yellow]No pages compiled. Nothing to generate.[/yellow]")
        sys.exit(1)

    try:
        files = publisher.generate_all(output)
    except Exception as e:
        console.print(f"\n[red]Error during generation:[/red] {e}")
        sys.exit(1)

    console.print(f"\n[bold green]✓ Generated {len(files)} files in {output}/[/bold green]")
    for fname in sorted(files):
        console.print(f"  [green]✓[/green] {fname}")
    console.print()


@publish.command(name="preview")
@click.argument("source")
def publish_preview(source: str) -> None:
    """Preview what would be published for a single page.

    Compiles SOURCE (URL or file path), then shows a summary of what
    each generated file would contain.
    """
    from agent_web_compiler.publisher import SitePublisher

    console.print(f"\n[bold blue]⚡ Preview:[/bold blue] {source}\n")

    try:
        source_path = Path(source)
        if source_path.exists():
            from agent_web_compiler.api.compile import compile_file

            doc = compile_file(source)
        elif source.startswith(("http://", "https://")):
            from agent_web_compiler.api.compile import compile_url as _compile_url

            doc = _compile_url(source)
        else:
            console.print(f"[red]Error:[/red] '{source}' is not a valid URL or file path")
            sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    publisher = SitePublisher()
    publisher.add_page(doc)
    summary = publisher.summary

    table = Table(title="Publish Preview")
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("Site Name", summary["site_name"] or "(auto)")
    table.add_row("Site URL", summary["site_url"] or "(auto)")
    table.add_row("Pages", str(summary["page_count"]))
    table.add_row("Total Blocks", str(summary["total_blocks"]))
    table.add_row("Total Actions", str(summary["total_actions"]))
    table.add_row("Files", ", ".join(summary["files"]))
    console.print(table)

    # Show document details
    console.print(f"\n  Title: [bold]{doc.title or 'Untitled'}[/bold]")
    console.print(f"  Blocks: {doc.block_count}")
    console.print(f"  Actions: {doc.action_count}")

    if doc.actions:
        console.print("\n  [bold]Top actions:[/bold]")
        for action in doc.actions[:5]:
            console.print(f"    - [{action.type.value}] {action.label}")

    console.print()


if __name__ == "__main__":
    cli()
