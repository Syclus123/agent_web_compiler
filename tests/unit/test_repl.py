"""Tests for the interactive REPL."""

from __future__ import annotations

import pytest

from agent_web_compiler.cli.repl import InteractiveREPL, parse_command

# ---------------------------------------------------------------------------
# parse_command
# ---------------------------------------------------------------------------


class TestParseCommand:
    """Tests for the command parser."""

    def test_empty_input(self) -> None:
        assert parse_command("") == ("", "")
        assert parse_command("   ") == ("", "")

    def test_slash_commands(self) -> None:
        assert parse_command("/help") == ("help", "")
        assert parse_command("/quit") == ("quit", "")
        assert parse_command("/stats") == ("stats", "")

    def test_slash_command_with_arg(self) -> None:
        assert parse_command("/search hello world") == ("search", "hello world")
        assert parse_command("/ingest https://example.com") == (
            "ingest",
            "https://example.com",
        )

    def test_slash_command_case_insensitive(self) -> None:
        assert parse_command("/HELP") == ("help", "")
        assert parse_command("/Search query") == ("search", "query")

    def test_unknown_slash_command_defaults_to_answer(self) -> None:
        cmd, arg = parse_command("/unknown some text")
        assert cmd == "answer"

    def test_plain_text_defaults_to_answer(self) -> None:
        cmd, arg = parse_command("what is the meaning of life")
        assert cmd == "answer"
        assert arg == "what is the meaning of life"

    def test_whitespace_handling(self) -> None:
        assert parse_command("  /search   spaced query  ") == ("search", "spaced query")

    def test_all_known_commands(self) -> None:
        for cmd in ("ingest", "search", "answer", "plan", "actions", "stats", "help", "quit"):
            result_cmd, _ = parse_command(f"/{cmd}")
            assert result_cmd == cmd

    def test_slash_only(self) -> None:
        # "/" alone — empty command name, defaults to answer
        cmd, arg = parse_command("/")
        assert cmd == "answer"


# ---------------------------------------------------------------------------
# InteractiveREPL
# ---------------------------------------------------------------------------


class TestInteractiveREPL:
    """Tests for the InteractiveREPL class."""

    def test_construction_default(self) -> None:
        repl = InteractiveREPL()
        assert repl.search is not None
        assert repl.console is not None

    def test_construction_with_search(self) -> None:
        from agent_web_compiler.search.agent_search import AgentSearch

        search = AgentSearch()
        repl = InteractiveREPL(search=search)
        assert repl.search is search

    def test_help_handler_runs(self, capsys: pytest.CaptureFixture[str]) -> None:
        """The help handler should not raise."""
        repl = InteractiveREPL()
        repl._cmd_help("")
        # Should have printed something (rich output goes to console)

    def test_stats_handler_runs(self) -> None:
        """The stats handler should not raise on an empty index."""
        repl = InteractiveREPL()
        repl._cmd_stats("")

    def test_ingest_no_arg_prints_usage(self, capsys: pytest.CaptureFixture[str]) -> None:
        repl = InteractiveREPL()
        repl._cmd_ingest("")
        # Should not raise

    def test_search_no_arg_prints_usage(self) -> None:
        repl = InteractiveREPL()
        repl._cmd_search("")

    def test_answer_no_arg_prints_usage(self) -> None:
        repl = InteractiveREPL()
        repl._cmd_answer("")

    def test_plan_no_arg_prints_usage(self) -> None:
        repl = InteractiveREPL()
        repl._cmd_plan("")

    def test_actions_no_arg_prints_usage(self) -> None:
        repl = InteractiveREPL()
        repl._cmd_actions("")
