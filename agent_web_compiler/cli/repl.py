"""Interactive REPL -- the "5-minute wow experience" for new users.

Usage:
    awc interactive

Provides a loop where users can:
    /ingest <url_or_path>    -- Add content to the index
    /search <query>          -- Search for blocks
    /answer <query>          -- Get grounded answer
    /plan <query>            -- Get execution plan
    /actions <query>         -- Search for actions
    /stats                   -- Show index statistics
    /help                    -- Show available commands
    /quit                    -- Exit
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agent_web_compiler.search.agent_search import AgentSearch

_VERSION = "0.1.0"

_BANNER = rf"""
   ___  _      _______
  / _ || | /| / / ___/
 / __ || |/ |/ / /__
/_/ |_||__/|__/\___/   v{_VERSION}

Agent Web Compiler — Interactive REPL
"""

_HELP_TEXT = """\
[bold]Available commands:[/bold]

  [cyan]/ingest[/cyan] <url_or_path>    Add content to the index
  [cyan]/search[/cyan] <query>          Search for blocks
  [cyan]/answer[/cyan] <query>          Get grounded answer with citations
  [cyan]/plan[/cyan]   <query>          Get execution plan
  [cyan]/actions[/cyan] <query>         Search for actions
  [cyan]/stats[/cyan]                   Show index statistics
  [cyan]/help[/cyan]                    Show this help message
  [cyan]/quit[/cyan]                    Exit

Type a plain text query to get an answer (same as /answer).
"""

# Map of command names (without /) to handler method names
_COMMANDS = frozenset({
    "ingest", "search", "answer", "plan", "actions", "stats", "help", "quit",
})


def parse_command(line: str) -> tuple[str, str]:
    """Parse a user input line into (command, argument).

    Returns:
        A tuple of (command_name, argument_text).
        If the line is not a slash-command, returns ("answer", line).
    """
    stripped = line.strip()
    if not stripped:
        return ("", "")

    if stripped.startswith("/"):
        parts = stripped[1:].split(None, 1)
        cmd = parts[0].lower() if parts else ""
        arg = parts[1] if len(parts) > 1 else ""
        if cmd in _COMMANDS:
            return (cmd, arg)
        # Unknown /command — treat as answer
        return ("answer", stripped)

    # Plain text defaults to /answer
    return ("answer", stripped)


class InteractiveREPL:
    """Interactive search REPL with rich console output."""

    def __init__(self, search: AgentSearch | None = None) -> None:
        self.search = search or AgentSearch()
        self.console = Console()

    def run(self) -> None:
        """Run the interactive REPL loop."""
        self.console.print(Panel(_BANNER, style="bold blue"))
        self._cmd_help("")

        while True:
            try:
                line = input("\n[awc] > ")
            except (EOFError, KeyboardInterrupt):
                self.console.print("\n[dim]Goodbye![/dim]")
                break

            cmd, arg = parse_command(line)
            if not cmd:
                continue

            if cmd == "quit":
                self.console.print("[dim]Goodbye![/dim]")
                break

            handler = getattr(self, f"_cmd_{cmd}", None)
            if handler is None:
                self.console.print(f"[red]Unknown command:[/red] /{cmd}")
                continue

            try:
                handler(arg)
            except Exception as exc:
                self.console.print(f"[red]Error:[/red] {exc}")

    # --- Command handlers ---

    def _cmd_help(self, _arg: str) -> None:
        self.console.print(_HELP_TEXT)

    def _cmd_ingest(self, arg: str) -> None:
        if not arg:
            self.console.print("[red]Usage:[/red] /ingest <url_or_path>")
            return

        self.console.print(f"[blue]Ingesting:[/blue] {arg}")

        source_path = Path(arg)
        if source_path.exists():
            doc = self.search.ingest_file(arg)
        elif arg.startswith(("http://", "https://")):
            doc = self.search.ingest_url(arg)
        else:
            self.console.print(
                f"[red]Error:[/red] '{arg}' is not a valid URL or file path"
            )
            return

        self.console.print(
            f"[green]Indexed:[/green] {doc.title or 'Untitled'} "
            f"({len(doc.blocks)} blocks, {len(doc.actions)} actions)"
        )

    def _cmd_search(self, arg: str) -> None:
        if not arg:
            self.console.print("[red]Usage:[/red] /search <query>")
            return

        response = self.search.search(arg, top_k=5)

        if not response.results:
            self.console.print("[yellow]No results found.[/yellow]")
            return

        table = Table(title=f"Search: {arg}")
        table.add_column("#", style="dim", width=3)
        table.add_column("Type", style="cyan", width=8)
        table.add_column("Score", justify="right", width=7)
        table.add_column("Text", no_wrap=False)

        for i, r in enumerate(response.results, 1):
            table.add_row(
                str(i),
                r.kind,
                f"{r.score:.3f}",
                r.text[:120],
            )

        self.console.print(table)
        self.console.print(
            f"[dim]{len(response.results)} results "
            f"({response.total_candidates} candidates, "
            f"{response.retrieval_time_ms:.1f}ms)[/dim]"
        )

    def _cmd_answer(self, arg: str) -> None:
        if not arg:
            self.console.print("[red]Usage:[/red] /answer <query>")
            return

        result = self.search.answer(arg, top_k=5)
        self.console.print(
            Panel(result.to_markdown(), title="Answer", border_style="green")
        )

    def _cmd_plan(self, arg: str) -> None:
        if not arg:
            self.console.print("[red]Usage:[/red] /plan <query>")
            return

        result = self.search.plan(arg)
        self.console.print(
            Panel(result.to_markdown(), title="Execution Plan", border_style="blue")
        )

    def _cmd_actions(self, arg: str) -> None:
        if not arg:
            self.console.print("[red]Usage:[/red] /actions <query>")
            return

        results = self.search.search_actions(arg, top_k=5)

        if not results:
            self.console.print("[yellow]No actions found.[/yellow]")
            return

        table = Table(title=f"Actions: {arg}")
        table.add_column("#", style="dim", width=3)
        table.add_column("Score", justify="right", width=7)
        table.add_column("Label", no_wrap=False)
        table.add_column("Type", style="yellow", width=10)

        for i, r in enumerate(results, 1):
            table.add_row(
                str(i),
                f"{r.score:.3f}",
                r.text[:80],
                r.metadata.get("action_type", "?"),
            )

        self.console.print(table)

    def _cmd_stats(self, _arg: str) -> None:
        stats = self.search.stats

        table = Table(title="Index Statistics")
        table.add_column("Metric", style="bold")
        table.add_column("Count", justify="right")
        table.add_row("Documents", str(stats["documents"]))
        table.add_row("Blocks", str(stats["blocks"]))
        table.add_row("Actions", str(stats["actions"]))
        table.add_row("Sites", str(stats["sites"]))

        self.console.print(table)
