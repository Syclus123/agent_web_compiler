"""Report generator — produces markdown benchmark reports."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bench.framework import FullBenchmarkResult


def generate_markdown_report(results: list[FullBenchmarkResult]) -> str:
    """Generate a markdown report table from benchmark results.

    Args:
        results: List of full benchmark results from BenchmarkRunner.

    Returns:
        Markdown-formatted report string.
    """
    lines: list[str] = []
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines.append("# Benchmark Report\n")
    lines.append(f"Generated: {timestamp}\n")

    # --- Token Efficiency ---
    lines.append("## Token Efficiency\n")
    lines.append(
        "| Fixture | Raw Tokens | Compiled Tokens | Compression | Blocks | Actions | Time (ms) |"
    )
    lines.append(
        "|---------|-----------|----------------|-------------|--------|---------|-----------|"
    )
    for r in results:
        br = r.result
        lines.append(
            f"| {br.fixture_name} "
            f"| {br.raw_tokens:,} "
            f"| {br.compiled_tokens:,} "
            f"| {br.compression_ratio:.1f}x "
            f"| {br.block_count} "
            f"| {br.action_count} "
            f"| {br.compile_time_ms:.0f} |"
        )

    # --- Content Fidelity ---
    lines.append("\n## Content Fidelity\n")
    lines.append(
        "| Fixture | Headings | Tables | Code | Text Coverage | Structure |"
    )
    lines.append(
        "|---------|----------|--------|------|---------------|-----------|"
    )
    for r in results:
        if r.fidelity:
            f = r.fidelity
            lines.append(
                f"| {r.result.fixture_name} "
                f"| {f.heading_fidelity:.0%} "
                f"| {f.table_fidelity:.0%} "
                f"| {f.code_fidelity:.0%} "
                f"| {f.text_coverage:.0%} "
                f"| {f.structure_score:.0%} |"
            )

    # --- Action Quality ---
    lines.append("\n## Action Quality\n")
    lines.append("| Fixture | Recall | Precision | Main Action |")
    lines.append("|---------|--------|-----------|-------------|")
    for r in results:
        if r.actions:
            a = r.actions
            main = "✓" if a.main_action_found else "✗"
            lines.append(
                f"| {r.result.fixture_name} "
                f"| {a.action_recall:.0%} "
                f"| {a.action_precision:.0%} "
                f"| {main} |"
            )

    # --- Block Details ---
    lines.append("\n## Block Details\n")
    lines.append(
        "| Fixture | Headings | Tables | Code | Provenance | Warnings |"
    )
    lines.append(
        "|---------|----------|--------|------|------------|----------|"
    )
    for r in results:
        br = r.result
        prov = "✓" if br.has_provenance else "✗"
        lines.append(
            f"| {br.fixture_name} "
            f"| {br.heading_count} "
            f"| {br.table_count} "
            f"| {br.code_count} "
            f"| {prov} "
            f"| {len(br.warnings)} |"
        )

    # --- Summary ---
    lines.append("\n## Summary\n")
    if results:
        avg_compression = sum(r.result.compression_ratio for r in results) / len(results)
        avg_time = sum(r.result.compile_time_ms for r in results) / len(results)
        fidelity_results = [r for r in results if r.fidelity]
        if fidelity_results:
            avg_text_coverage = (
                sum(r.fidelity.text_coverage for r in fidelity_results) / len(fidelity_results)
            )
        else:
            avg_text_coverage = 0.0
        lines.append(f"- **Fixtures**: {len(results)}")
        lines.append(f"- **Avg compression**: {avg_compression:.1f}x")
        lines.append(f"- **Avg compile time**: {avg_time:.0f}ms")
        lines.append(f"- **Avg text coverage**: {avg_text_coverage:.0%}")

    lines.append("")
    return "\n".join(lines)
