"""Benchmark framework — runner, result types, and evaluation harness."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from agent_web_compiler.api.compile import compile_html
from agent_web_compiler.core.block import BlockType
from agent_web_compiler.core.document import AgentDocument
from bench.eval.metrics import (
    compute_action_recall,
    compute_content_fidelity,
    compute_token_efficiency,
)


@dataclass
class BenchmarkResult:
    """Result from a single benchmark run."""

    fixture_name: str
    source_type: str
    raw_tokens: int
    compiled_tokens: int
    compression_ratio: float
    compile_time_ms: float
    block_count: int
    action_count: int
    heading_count: int
    table_count: int
    code_count: int
    has_provenance: bool
    warnings: list[str] = field(default_factory=list)


@dataclass
class ContentFidelityScore:
    """Measures how well content is preserved."""

    heading_fidelity: float
    table_fidelity: float
    code_fidelity: float
    text_coverage: float
    structure_score: float


@dataclass
class ActionScore:
    """Measures action extraction quality."""

    action_recall: float
    action_precision: float
    main_action_found: bool


@dataclass
class FullBenchmarkResult:
    """Complete result including scores."""

    result: BenchmarkResult
    fidelity: ContentFidelityScore | None = None
    actions: ActionScore | None = None


class BenchmarkRunner:
    """Runs benchmarks against fixture files with expected outputs.

    Fixture directory layout::

        tasks/
            blog_article.json    # spec with expected outputs
            blog_article.html    # raw HTML fixture

    Each JSON spec references its HTML file via the ``html_file`` key.
    """

    def run_all(self, fixtures_dir: str) -> list[FullBenchmarkResult]:
        """Run all fixtures in a directory.

        Args:
            fixtures_dir: Path to directory containing .json spec files and .html fixtures.

        Returns:
            List of benchmark results, one per fixture.
        """
        fixtures_path = Path(fixtures_dir)
        if not fixtures_path.is_dir():
            raise FileNotFoundError(f"Fixtures directory not found: {fixtures_dir}")

        results: list[FullBenchmarkResult] = []
        for spec_file in sorted(fixtures_path.glob("*.json")):
            spec = json.loads(spec_file.read_text())
            html_file = fixtures_path / spec["html_file"]
            if not html_file.exists():
                raise FileNotFoundError(
                    f"HTML fixture not found: {html_file} (referenced by {spec_file.name})"
                )
            full_result = self.run_fixture(str(html_file), spec)
            results.append(full_result)

        return results

    def run_fixture(self, fixture_path: str, spec: dict) -> FullBenchmarkResult:
        """Run a single fixture and evaluate it.

        Args:
            fixture_path: Path to the HTML file.
            spec: The JSON spec with expected outputs.

        Returns:
            Full benchmark result with metrics and scores.
        """
        html = Path(fixture_path).read_text(encoding="utf-8")
        expected = spec.get("expected", {})

        # Compile
        start = time.perf_counter()
        doc = compile_html(
            html,
            source_url=f"bench://fixture/{spec.get('name', 'unknown')}",
            mode="balanced",
            include_actions=True,
            include_provenance=True,
            debug=False,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        # Token efficiency
        efficiency = compute_token_efficiency(html, doc.canonical_markdown)

        # Block counts
        heading_count = len(doc.get_blocks_by_type(BlockType.HEADING))
        table_count = len(doc.get_blocks_by_type(BlockType.TABLE))
        code_count = len(doc.get_blocks_by_type(BlockType.CODE))

        has_provenance = any(b.provenance is not None for b in doc.blocks)

        result = BenchmarkResult(
            fixture_name=spec.get("name", Path(fixture_path).stem),
            source_type=spec.get("source_type", "html"),
            raw_tokens=efficiency["raw_tokens"],
            compiled_tokens=efficiency["compiled_tokens"],
            compression_ratio=efficiency["compression_ratio"],
            compile_time_ms=round(elapsed_ms, 1),
            block_count=doc.block_count,
            action_count=doc.action_count,
            heading_count=heading_count,
            table_count=table_count,
            code_count=code_count,
            has_provenance=has_provenance,
            warnings=doc.quality.warnings[:],
        )

        # Fidelity
        fidelity_score = self.evaluate_fidelity(doc, expected)
        action_score = self.evaluate_actions(doc, expected)

        return FullBenchmarkResult(
            result=result,
            fidelity=fidelity_score,
            actions=action_score,
        )

    def evaluate_fidelity(
        self, doc: AgentDocument, expected: dict
    ) -> ContentFidelityScore:
        """Evaluate content fidelity against expected outputs.

        Args:
            doc: The compiled document.
            expected: Expected output spec.

        Returns:
            ContentFidelityScore with per-dimension scores.
        """
        scores = compute_content_fidelity(
            doc,
            expected_headings=expected.get("headings", []),
            expected_tables=expected.get("min_tables", 0),
            expected_code=expected.get("min_code_blocks", 0),
            key_phrases=expected.get("key_phrases", []),
        )
        return ContentFidelityScore(
            heading_fidelity=scores["heading_fidelity"],
            table_fidelity=scores["table_fidelity"],
            code_fidelity=scores["code_fidelity"],
            text_coverage=scores["text_coverage"],
            structure_score=scores["structure_score"],
        )

    def evaluate_actions(self, doc: AgentDocument, expected: dict) -> ActionScore:
        """Evaluate action extraction quality.

        Args:
            doc: The compiled document.
            expected: Expected output spec.

        Returns:
            ActionScore with recall, precision, and main action flag.
        """
        scores = compute_action_recall(
            doc,
            expected_actions=expected.get("expected_actions", []),
            main_action_label=expected.get("main_action_label"),
        )
        return ActionScore(
            action_recall=scores["action_recall"],
            action_precision=scores["action_precision"],
            main_action_found=bool(scores["main_action_found"]),
        )

    def generate_report(self, results: list[FullBenchmarkResult]) -> str:
        """Generate a markdown report from benchmark results.

        Args:
            results: List of full benchmark results.

        Returns:
            Markdown-formatted report string.
        """
        from bench.scripts.report import generate_markdown_report

        return generate_markdown_report(results)
