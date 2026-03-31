"""Search quality benchmarks — measures retrieval accuracy and answer quality.

Metrics:
- Recall@K: fraction of relevant blocks found in top-K results
- MRR: Mean Reciprocal Rank of the first relevant result
- Citation Precision: fraction of citations that point to correct evidence
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from agent_web_compiler.api.compile import compile_html
from agent_web_compiler.index import IndexEngine
from agent_web_compiler.search.grounded_answer import GroundedAnswerer
from agent_web_compiler.search.retriever import Retriever, SearchResult


@dataclass
class SearchQAItem:
    """A single search quality evaluation item."""

    query: str
    relevant_keywords: list[str]  # Keywords that MUST appear in a correct result
    expected_block_type: str | None = None
    expected_section: str | None = None  # Section path substring


@dataclass
class SearchQAItemResult:
    """Result of evaluating a single search QA item."""

    query: str
    recall_at_5: float
    recall_at_10: float
    reciprocal_rank: float  # 1/rank of first relevant result, 0 if not found
    citation_precision: float  # fraction of citations pointing to relevant evidence
    top_result_relevant: bool
    relevant_results_count: int


@dataclass
class SearchQualityResult:
    """Aggregated search quality metrics for one fixture."""

    fixture_name: str
    total_queries: int
    avg_recall_at_5: float
    avg_recall_at_10: float
    avg_mrr: float
    avg_citation_precision: float
    item_results: list[SearchQAItemResult] = field(default_factory=list)


def _is_relevant(result: SearchResult, item: SearchQAItem) -> bool:
    """Check if a search result is relevant to the QA item.

    A result is relevant if:
    1. Its text contains ALL required keywords (case-insensitive), AND
    2. If expected_block_type is set, the result's block_type matches, AND
    3. If expected_section is set, the section path contains the substring.
    """
    text_lower = result.text.lower()

    # All keywords must appear
    for kw in item.relevant_keywords:
        if kw.lower() not in text_lower:
            return False

    # Block type check (optional)
    if item.expected_block_type is not None:
        block_type = result.metadata.get("block_type", "")
        if block_type != item.expected_block_type:
            return False

    # Section check (optional)
    if item.expected_section is not None:
        section_str = " > ".join(result.section_path).lower()
        if item.expected_section.lower() not in section_str:
            return False

    return True


def _compute_recall_at_k(
    results: list[SearchResult], item: SearchQAItem, k: int
) -> float:
    """Compute recall@K: did we find at least one relevant result in top-K?

    Since each query has a single information need, recall@K is binary:
    1.0 if any result in top-K is relevant, 0.0 otherwise.
    """
    for r in results[:k]:
        if _is_relevant(r, item):
            return 1.0
    return 0.0


def _compute_reciprocal_rank(
    results: list[SearchResult], item: SearchQAItem
) -> float:
    """Compute reciprocal rank of the first relevant result."""
    for i, r in enumerate(results):
        if _is_relevant(r, item):
            return 1.0 / (i + 1)
    return 0.0


def _compute_citation_precision(
    answerer: GroundedAnswerer, retriever: Retriever, item: SearchQAItem
) -> float:
    """Compute citation precision: fraction of citations pointing to relevant evidence."""
    answer = answerer.answer(item.query, top_k=5)
    if not answer.citations:
        return 0.0

    relevant_count = 0
    for cit in answer.citations:
        cit_text = cit.text_snippet.lower()
        if all(kw.lower() in cit_text for kw in item.relevant_keywords):
            relevant_count += 1

    return relevant_count / len(answer.citations)


class SearchQualityBenchmark:
    """Evaluates search retrieval quality on benchmark fixtures."""

    def evaluate(
        self,
        engine: IndexEngine,
        items: list[SearchQAItem],
        fixture_name: str = "unnamed",
    ) -> SearchQualityResult:
        """Evaluate search quality on a set of QA items against an indexed engine.

        Args:
            engine: An IndexEngine with documents already ingested.
            items: List of SearchQAItem queries to evaluate.
            fixture_name: Human-readable fixture name.

        Returns:
            SearchQualityResult with aggregated metrics.
        """
        retriever = Retriever(engine)
        answerer = GroundedAnswerer(retriever)

        item_results: list[SearchQAItemResult] = []

        for item in items:
            response = retriever.search(item.query, top_k=10)
            results = response.results

            recall_5 = _compute_recall_at_k(results, item, k=5)
            recall_10 = _compute_recall_at_k(results, item, k=10)
            rr = _compute_reciprocal_rank(results, item)
            cit_prec = _compute_citation_precision(answerer, retriever, item)

            relevant_count = sum(1 for r in results if _is_relevant(r, item))

            item_results.append(
                SearchQAItemResult(
                    query=item.query,
                    recall_at_5=recall_5,
                    recall_at_10=recall_10,
                    reciprocal_rank=rr,
                    citation_precision=cit_prec,
                    top_result_relevant=recall_5 > 0 and rr == 1.0,
                    relevant_results_count=relevant_count,
                )
            )

        total = len(items)
        avg_r5 = sum(r.recall_at_5 for r in item_results) / total if total else 0.0
        avg_r10 = sum(r.recall_at_10 for r in item_results) / total if total else 0.0
        avg_mrr = sum(r.reciprocal_rank for r in item_results) / total if total else 0.0
        avg_cit = sum(r.citation_precision for r in item_results) / total if total else 0.0

        return SearchQualityResult(
            fixture_name=fixture_name,
            total_queries=total,
            avg_recall_at_5=round(avg_r5, 4),
            avg_recall_at_10=round(avg_r10, 4),
            avg_mrr=round(avg_mrr, 4),
            avg_citation_precision=round(avg_cit, 4),
            item_results=item_results,
        )

    def evaluate_all(self, fixtures_dir: str) -> list[SearchQualityResult]:
        """Run search quality evaluation on all fixtures with search_qa items.

        Args:
            fixtures_dir: Path to directory containing .json spec files and .html fixtures.

        Returns:
            List of SearchQualityResult, one per fixture with search_qa data.
        """
        fixtures_path = Path(fixtures_dir)
        if not fixtures_path.is_dir():
            raise FileNotFoundError(f"Fixtures directory not found: {fixtures_dir}")

        results: list[SearchQualityResult] = []

        for spec_file in sorted(fixtures_path.glob("*.json")):
            spec = json.loads(spec_file.read_text(encoding="utf-8"))

            search_qa = spec.get("search_qa")
            if not search_qa:
                continue

            html_file = fixtures_path / spec["html_file"]
            if not html_file.exists():
                raise FileNotFoundError(
                    f"HTML fixture not found: {html_file} (referenced by {spec_file.name})"
                )

            html = html_file.read_text(encoding="utf-8")
            name = spec.get("name", html_file.stem)

            # Compile and index
            engine = IndexEngine()
            doc = compile_html(
                html,
                source_url=f"bench://search_quality/{name}",
                mode="balanced",
                include_actions=True,
                include_provenance=True,
            )
            engine.ingest(doc)

            # Parse QA items
            items = [
                SearchQAItem(
                    query=qa["query"],
                    relevant_keywords=qa["relevant_keywords"],
                    expected_block_type=qa.get("expected_block_type"),
                    expected_section=qa.get("expected_section"),
                )
                for qa in search_qa
            ]

            result = self.evaluate(engine, items, fixture_name=name)
            results.append(result)

        return results

    def generate_report(self, results: list[SearchQualityResult]) -> str:
        """Generate a markdown report of search quality results.

        Args:
            results: List of SearchQualityResult from evaluate_all.

        Returns:
            Markdown-formatted report string.
        """
        lines: list[str] = []
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        lines.append("# Search Quality Report\n")
        lines.append(f"Generated: {timestamp}\n")

        # Summary table
        lines.append("## Summary\n")
        lines.append(
            "| Fixture | Queries | Recall@5 | Recall@10 | MRR | Citation Precision |"
        )
        lines.append(
            "|---------|---------|----------|-----------|-----|--------------------|"
        )
        for r in results:
            lines.append(
                f"| {r.fixture_name} "
                f"| {r.total_queries} "
                f"| {r.avg_recall_at_5:.0%} "
                f"| {r.avg_recall_at_10:.0%} "
                f"| {r.avg_mrr:.2f} "
                f"| {r.avg_citation_precision:.0%} |"
            )

        # Averages
        if results:
            n = len(results)
            avg_r5 = sum(r.avg_recall_at_5 for r in results) / n
            avg_r10 = sum(r.avg_recall_at_10 for r in results) / n
            avg_mrr = sum(r.avg_mrr for r in results) / n
            avg_cit = sum(r.avg_citation_precision for r in results) / n
            total_q = sum(r.total_queries for r in results)
            lines.append(
                f"| **Average** "
                f"| **{total_q}** "
                f"| **{avg_r5:.0%}** "
                f"| **{avg_r10:.0%}** "
                f"| **{avg_mrr:.2f}** "
                f"| **{avg_cit:.0%}** |"
            )

        # Per-query detail
        lines.append("\n## Per-Query Details\n")
        for r in results:
            lines.append(f"### {r.fixture_name}\n")
            lines.append("| Query | R@5 | R@10 | RR | Cit. Prec. | Relevant |")
            lines.append("|-------|-----|------|----|------------|----------|")
            for ir in r.item_results:
                lines.append(
                    f"| {ir.query} "
                    f"| {ir.recall_at_5:.0%} "
                    f"| {ir.recall_at_10:.0%} "
                    f"| {ir.reciprocal_rank:.2f} "
                    f"| {ir.citation_precision:.0%} "
                    f"| {ir.relevant_results_count} |"
                )
            lines.append("")

        lines.append("")
        return "\n".join(lines)
