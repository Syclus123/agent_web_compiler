"""Comparison framework — measures agent-web-compiler against baseline approaches.

Compares three approaches on the same input:
1. Raw HTML (just the full HTML string)
2. Naive markdown (strip tags, basic text extraction)
3. agent-web-compiler (full pipeline)

Metrics compared:
- Token count
- Information density (unique entities / tokens)
- Structure preservation (heading count, table presence, code blocks)
- Action discoverability (action count, main action)
- Noise ratio (boilerplate text / total text)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from agent_web_compiler.api.compile import compile_html
from agent_web_compiler.core.block import BlockType
from agent_web_compiler.utils.text import (
    count_tokens_approx,
    extract_text_from_html,
)

# Patterns for entity detection
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PRICE_RE = re.compile(r"\$[\d,]+(?:\.\d{2})?")
_DATE_RE = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|(?:January|February|March|April|May|June|July|August"
    r"|September|October|November|December)\s+\d{1,2},?\s+\d{4})\b",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"https?://[^\s<>\"']+")

# Common boilerplate phrases (case-insensitive matching)
_BOILERPLATE_PHRASES = [
    "cookie", "privacy policy", "terms of service", "all rights reserved",
    "subscribe to our newsletter", "follow us on", "powered by",
    "advertisement", "loading...", "please enable javascript",
    "copyright ©", "cookie policy", "accept cookies", "analytics",
    "tracking pixel", "promo banner", "sign up for",
]


@dataclass
class ApproachResult:
    """Metrics for a single compilation approach."""

    name: str  # "raw_html", "naive_markdown", "agent_web_compiler"
    token_count: int
    char_count: int
    heading_count: int
    table_count: int
    code_block_count: int
    list_count: int
    action_count: int
    has_main_action: bool
    noise_ratio: float  # estimated boilerplate / total
    unique_entities: int  # dates, prices, emails found
    output_preview: str  # first 500 chars


@dataclass
class ComparisonResult:
    """Side-by-side comparison of all three approaches on one fixture."""

    fixture_name: str
    raw_html: ApproachResult
    naive_markdown: ApproachResult
    awc: ApproachResult

    @property
    def token_savings_vs_html(self) -> float:
        """Fraction of tokens saved by AWC compared to raw HTML."""
        if self.raw_html.token_count == 0:
            return 0.0
        return 1.0 - self.awc.token_count / self.raw_html.token_count

    @property
    def token_savings_vs_markdown(self) -> float:
        """Fraction of tokens saved by AWC compared to naive markdown."""
        if self.naive_markdown.token_count == 0:
            return 0.0
        return 1.0 - self.awc.token_count / self.naive_markdown.token_count


def _count_entities(text: str) -> int:
    """Count unique entities (emails, prices, dates, URLs) in text."""
    entities: set[str] = set()
    entities.update(_EMAIL_RE.findall(text))
    entities.update(_PRICE_RE.findall(text))
    entities.update(_DATE_RE.findall(text))
    # Limit URL matches to avoid counting every href in raw HTML
    for url in _URL_RE.findall(text)[:50]:
        entities.add(url)
    return len(entities)


def _estimate_noise_ratio(text: str) -> float:
    """Estimate boilerplate noise ratio based on known boilerplate phrases.

    Returns a float in [0.0, 1.0] representing the fraction of the text
    that appears to be boilerplate.
    """
    if not text.strip():
        return 0.0

    text_lower = text.lower()
    total_chars = len(text_lower)
    noise_chars = 0

    for phrase in _BOILERPLATE_PHRASES:
        start = 0
        while True:
            idx = text_lower.find(phrase, start)
            if idx == -1:
                break
            # Count a window around each boilerplate phrase
            window_start = max(0, idx - 20)
            window_end = min(total_chars, idx + len(phrase) + 20)
            noise_chars += window_end - window_start
            start = idx + len(phrase)

    return min(1.0, noise_chars / total_chars) if total_chars > 0 else 0.0


def _count_html_headings(html: str) -> int:
    """Count heading tags in raw HTML."""
    return len(re.findall(r"<h[1-6][^>]*>", html, re.IGNORECASE))


def _count_html_tables(html: str) -> int:
    """Count table tags in raw HTML."""
    return len(re.findall(r"<table[^>]*>", html, re.IGNORECASE))


def _count_html_code_blocks(html: str) -> int:
    """Count pre/code blocks in raw HTML."""
    return len(re.findall(r"<(?:pre|code)[^>]*>", html, re.IGNORECASE))


def _count_html_lists(html: str) -> int:
    """Count list containers in raw HTML."""
    return len(re.findall(r"<(?:ul|ol)[^>]*>", html, re.IGNORECASE))


def _count_markdown_headings(md: str) -> int:
    """Count markdown headings (lines starting with #)."""
    return len(re.findall(r"^#{1,6}\s", md, re.MULTILINE))


def _count_markdown_tables(md: str) -> int:
    """Count markdown tables (lines with | separators following a header row)."""
    return len(re.findall(r"^\|[-:| ]+\|$", md, re.MULTILINE))


def _count_markdown_code_blocks(md: str) -> int:
    """Count fenced code blocks in markdown."""
    return len(re.findall(r"^```", md, re.MULTILINE)) // 2


def _count_markdown_lists(md: str) -> int:
    """Count list items in markdown (rough count of list groups)."""
    items = re.findall(r"^[\s]*[-*+]\s|^\s*\d+\.\s", md, re.MULTILINE)
    return len(items)


class ComparisonRunner:
    """Runs side-by-side comparison of compilation approaches."""

    def compare(self, html: str, fixture_name: str = "unnamed") -> ComparisonResult:
        """Compare all three approaches on a single HTML input.

        Args:
            html: Raw HTML string.
            fixture_name: Human-readable name for this fixture.

        Returns:
            ComparisonResult with metrics for each approach.
        """
        raw_result = self._analyze_raw_html(html)
        md_result = self._analyze_naive_markdown(html)
        awc_result = self._analyze_awc(html, fixture_name)

        return ComparisonResult(
            fixture_name=fixture_name,
            raw_html=raw_result,
            naive_markdown=md_result,
            awc=awc_result,
        )

    def compare_all(self, fixtures_dir: str) -> list[ComparisonResult]:
        """Run comparison on all fixtures in a directory.

        Args:
            fixtures_dir: Path to directory containing .json spec files and .html fixtures.

        Returns:
            List of ComparisonResult, one per fixture.
        """
        fixtures_path = Path(fixtures_dir)
        if not fixtures_path.is_dir():
            raise FileNotFoundError(f"Fixtures directory not found: {fixtures_dir}")

        results: list[ComparisonResult] = []
        for spec_file in sorted(fixtures_path.glob("*.json")):
            spec = json.loads(spec_file.read_text(encoding="utf-8"))
            html_file = fixtures_path / spec["html_file"]
            if not html_file.exists():
                raise FileNotFoundError(
                    f"HTML fixture not found: {html_file} (referenced by {spec_file.name})"
                )
            html = html_file.read_text(encoding="utf-8")
            name = spec.get("name", html_file.stem)
            results.append(self.compare(html, fixture_name=name))

        return results

    def generate_report(self, results: list[ComparisonResult]) -> str:
        """Generate a markdown comparison report.

        Args:
            results: List of comparison results from compare_all or individual compares.

        Returns:
            Markdown-formatted report string.
        """
        lines: list[str] = []
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        lines.append("# Compilation Comparison Report\n")
        lines.append(f"Generated: {timestamp}\n")
        lines.append(
            "Compares three approaches: Raw HTML → LLM vs Naive Markdown → LLM "
            "vs agent-web-compiler → LLM\n"
        )

        # --- Token Efficiency ---
        lines.append("## Token Efficiency\n")
        lines.append(
            "| Fixture | Raw HTML | Naive MD | AWC | Savings vs HTML | Savings vs MD |"
        )
        lines.append(
            "|---------|----------|----------|-----|-----------------|---------------|"
        )
        for r in results:
            lines.append(
                f"| {r.fixture_name} "
                f"| {r.raw_html.token_count:,} "
                f"| {r.naive_markdown.token_count:,} "
                f"| {r.awc.token_count:,} "
                f"| {r.token_savings_vs_html:.0%} "
                f"| {r.token_savings_vs_markdown:.0%} |"
            )

        # Averages
        if results:
            avg_html = sum(r.raw_html.token_count for r in results) / len(results)
            avg_md = sum(r.naive_markdown.token_count for r in results) / len(results)
            avg_awc = sum(r.awc.token_count for r in results) / len(results)
            avg_save_html = (
                sum(r.token_savings_vs_html for r in results) / len(results)
            )
            avg_save_md = (
                sum(r.token_savings_vs_markdown for r in results) / len(results)
            )
            lines.append(
                f"| **Average** "
                f"| **{avg_html:,.0f}** "
                f"| **{avg_md:,.0f}** "
                f"| **{avg_awc:,.0f}** "
                f"| **{avg_save_html:.0%}** "
                f"| **{avg_save_md:.0%}** |"
            )

        # --- Structure Preservation ---
        lines.append("\n## Structure Preservation\n")
        lines.append(
            "| Fixture | Approach | Headings | Tables | Code | Lists | Actions |"
        )
        lines.append(
            "|---------|----------|----------|--------|------|-------|---------|"
        )
        for r in results:
            for approach in [r.raw_html, r.naive_markdown, r.awc]:
                lines.append(
                    f"| {r.fixture_name} "
                    f"| {approach.name} "
                    f"| {approach.heading_count} "
                    f"| {approach.table_count} "
                    f"| {approach.code_block_count} "
                    f"| {approach.list_count} "
                    f"| {approach.action_count} |"
                )

        # --- Information Density ---
        lines.append("\n## Information Density\n")
        lines.append("| Fixture | Approach | Tokens | Entities | Entities/1K Tokens | Noise Ratio |")
        lines.append("|---------|----------|--------|----------|--------------------|-------------|")
        for r in results:
            for approach in [r.raw_html, r.naive_markdown, r.awc]:
                density = (
                    (approach.unique_entities / approach.token_count * 1000)
                    if approach.token_count > 0
                    else 0.0
                )
                lines.append(
                    f"| {r.fixture_name} "
                    f"| {approach.name} "
                    f"| {approach.token_count:,} "
                    f"| {approach.unique_entities} "
                    f"| {density:.1f} "
                    f"| {approach.noise_ratio:.0%} |"
                )

        # --- Summary ---
        lines.append("\n## Summary\n")
        if results:
            lines.append(f"- **Fixtures evaluated**: {len(results)}")
            lines.append(f"- **Avg token savings vs raw HTML**: {avg_save_html:.0%}")
            lines.append(f"- **Avg token savings vs naive markdown**: {avg_save_md:.0%}")

            # Structure preservation summary
            awc_actions = sum(r.awc.action_count for r in results)
            md_actions = sum(r.naive_markdown.action_count for r in results)
            lines.append(f"- **Total AWC actions discovered**: {awc_actions}")
            lines.append(f"- **Total naive markdown actions discovered**: {md_actions}")

        lines.append("")
        return "\n".join(lines)

    # ---- Internal analysis methods ----

    def _analyze_raw_html(self, html: str) -> ApproachResult:
        """Analyze raw HTML as-is (no processing)."""
        token_count = count_tokens_approx(html)
        return ApproachResult(
            name="raw_html",
            token_count=token_count,
            char_count=len(html),
            heading_count=_count_html_headings(html),
            table_count=_count_html_tables(html),
            code_block_count=_count_html_code_blocks(html),
            list_count=_count_html_lists(html),
            action_count=0,  # raw HTML has no structured actions
            has_main_action=False,
            noise_ratio=_estimate_noise_ratio(html),
            unique_entities=_count_entities(html),
            output_preview=html[:500],
        )

    def _analyze_naive_markdown(self, html: str) -> ApproachResult:
        """Analyze naive text extraction (strip tags, collapse whitespace)."""
        plain_text = extract_text_from_html(html)
        token_count = count_tokens_approx(plain_text)
        return ApproachResult(
            name="naive_markdown",
            token_count=token_count,
            char_count=len(plain_text),
            heading_count=0,  # naive extraction loses all structure
            table_count=0,
            code_block_count=0,
            list_count=0,
            action_count=0,  # no action discovery
            has_main_action=False,
            noise_ratio=_estimate_noise_ratio(plain_text),
            unique_entities=_count_entities(plain_text),
            output_preview=plain_text[:500],
        )

    def _analyze_awc(self, html: str, fixture_name: str) -> ApproachResult:
        """Analyze agent-web-compiler output."""
        doc = compile_html(
            html,
            source_url=f"bench://comparison/{fixture_name}",
            mode="balanced",
            include_actions=True,
            include_provenance=True,
            debug=False,
        )

        markdown = doc.canonical_markdown
        token_count = count_tokens_approx(markdown)

        heading_count = len(doc.get_blocks_by_type(BlockType.HEADING))
        table_count = len(doc.get_blocks_by_type(BlockType.TABLE))
        code_count = len(doc.get_blocks_by_type(BlockType.CODE))
        list_count = len(doc.get_blocks_by_type(BlockType.LIST))

        has_main = doc.action_count > 0 and any(
            a.priority >= 0.7 for a in doc.actions
        )

        return ApproachResult(
            name="agent_web_compiler",
            token_count=token_count,
            char_count=len(markdown),
            heading_count=heading_count,
            table_count=table_count,
            code_block_count=code_count,
            list_count=list_count,
            action_count=doc.action_count,
            has_main_action=has_main,
            noise_ratio=_estimate_noise_ratio(markdown),
            unique_entities=_count_entities(markdown),
            output_preview=markdown[:500],
        )
