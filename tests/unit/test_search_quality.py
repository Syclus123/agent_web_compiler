"""Unit tests for search quality benchmarks."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_web_compiler.search.retriever import SearchResult
from bench.eval.search_quality import (
    SearchQAItem,
    SearchQualityBenchmark,
    SearchQualityResult,
    _compute_recall_at_k,
    _compute_reciprocal_rank,
    _is_relevant,
)

# --- Helpers ---


def _make_result(
    text: str,
    score: float = 0.5,
    block_type: str = "paragraph",
    section_path: list[str] | None = None,
) -> SearchResult:
    """Create a minimal SearchResult for testing."""
    return SearchResult(
        kind="block",
        score=score,
        doc_id="doc-1",
        block_id="blk-1",
        text=text,
        section_path=section_path or [],
        metadata={"block_type": block_type},
    )


# --- _is_relevant ---


class TestIsRelevant:
    def test_all_keywords_present(self) -> None:
        result = _make_result("The price is $549.00 with free shipping")
        item = SearchQAItem(query="price", relevant_keywords=["549", "price"])
        assert _is_relevant(result, item) is True

    def test_missing_keyword(self) -> None:
        result = _make_result("Free shipping available")
        item = SearchQAItem(query="price", relevant_keywords=["549", "price"])
        assert _is_relevant(result, item) is False

    def test_case_insensitive(self) -> None:
        result = _make_result("The VORTEX_ prefix is used for env vars")
        item = SearchQAItem(query="env prefix", relevant_keywords=["vortex_"])
        assert _is_relevant(result, item) is True

    def test_block_type_filter_match(self) -> None:
        result = _make_result("Price: $549", block_type="paragraph")
        item = SearchQAItem(
            query="price",
            relevant_keywords=["549"],
            expected_block_type="paragraph",
        )
        assert _is_relevant(result, item) is True

    def test_block_type_filter_mismatch(self) -> None:
        result = _make_result("Price: $549", block_type="table")
        item = SearchQAItem(
            query="price",
            relevant_keywords=["549"],
            expected_block_type="paragraph",
        )
        assert _is_relevant(result, item) is False

    def test_section_filter_match(self) -> None:
        result = _make_result(
            "Price: $549",
            section_path=["Product", "Pricing"],
        )
        item = SearchQAItem(
            query="price",
            relevant_keywords=["549"],
            expected_section="Pricing",
        )
        assert _is_relevant(result, item) is True

    def test_section_filter_mismatch(self) -> None:
        result = _make_result(
            "Price: $549",
            section_path=["Product", "Overview"],
        )
        item = SearchQAItem(
            query="price",
            relevant_keywords=["549"],
            expected_section="Pricing",
        )
        assert _is_relevant(result, item) is False


# --- recall@K ---


class TestRecallAtK:
    def test_relevant_in_top_5(self) -> None:
        results = [
            _make_result("irrelevant"),
            _make_result("irrelevant"),
            _make_result("price is $549"),
        ]
        item = SearchQAItem(query="price", relevant_keywords=["549"])
        assert _compute_recall_at_k(results, item, k=5) == 1.0

    def test_relevant_outside_k(self) -> None:
        results = [_make_result("irrelevant")] * 5 + [_make_result("price is $549")]
        item = SearchQAItem(query="price", relevant_keywords=["549"])
        assert _compute_recall_at_k(results, item, k=5) == 0.0
        assert _compute_recall_at_k(results, item, k=10) == 1.0

    def test_no_relevant(self) -> None:
        results = [_make_result("irrelevant")] * 10
        item = SearchQAItem(query="price", relevant_keywords=["549"])
        assert _compute_recall_at_k(results, item, k=10) == 0.0

    def test_empty_results(self) -> None:
        item = SearchQAItem(query="price", relevant_keywords=["549"])
        assert _compute_recall_at_k([], item, k=5) == 0.0


# --- MRR ---


class TestReciprocalRank:
    def test_first_result_relevant(self) -> None:
        results = [_make_result("price is $549")]
        item = SearchQAItem(query="price", relevant_keywords=["549"])
        assert _compute_reciprocal_rank(results, item) == 1.0

    def test_third_result_relevant(self) -> None:
        results = [
            _make_result("irrelevant"),
            _make_result("also irrelevant"),
            _make_result("price is $549"),
        ]
        item = SearchQAItem(query="price", relevant_keywords=["549"])
        assert _compute_reciprocal_rank(results, item) == pytest.approx(1 / 3)

    def test_no_relevant(self) -> None:
        results = [_make_result("irrelevant")] * 5
        item = SearchQAItem(query="price", relevant_keywords=["549"])
        assert _compute_reciprocal_rank(results, item) == 0.0


# --- SearchQualityBenchmark ---


class TestSearchQualityBenchmark:
    def test_evaluate_with_engine(self) -> None:
        """Test evaluation with a real compiled document and index engine."""

        from agent_web_compiler.api.compile import compile_html
        from agent_web_compiler.index import IndexEngine

        # Minimal HTML with known content
        html = """
        <html>
        <body>
            <h1>Product Info</h1>
            <p>The price is $549.00 for the standing desk.</p>
            <p>Includes a 5-year warranty with free returns.</p>
            <p>Weight capacity: 350 lbs maximum load.</p>
        </body>
        </html>
        """

        doc = compile_html(html, source_url="test://product")
        engine = IndexEngine()
        engine.ingest(doc)

        items = [
            SearchQAItem(query="What is the price?", relevant_keywords=["549"]),
            SearchQAItem(query="What is the warranty?", relevant_keywords=["5-year", "warranty"]),
        ]

        benchmark = SearchQualityBenchmark()
        result = benchmark.evaluate(engine, items, fixture_name="test_product")

        assert result.fixture_name == "test_product"
        assert result.total_queries == 2
        assert 0.0 <= result.avg_recall_at_5 <= 1.0
        assert 0.0 <= result.avg_recall_at_10 <= 1.0
        assert 0.0 <= result.avg_mrr <= 1.0
        assert 0.0 <= result.avg_citation_precision <= 1.0
        assert len(result.item_results) == 2

    def test_generate_report(self) -> None:
        """Test that report generation produces valid markdown."""
        results = [
            SearchQualityResult(
                fixture_name="test_fixture",
                total_queries=3,
                avg_recall_at_5=0.67,
                avg_recall_at_10=1.0,
                avg_mrr=0.72,
                avg_citation_precision=0.5,
                item_results=[],
            ),
        ]
        benchmark = SearchQualityBenchmark()
        report = benchmark.generate_report(results)

        assert "# Search Quality Report" in report
        assert "test_fixture" in report
        assert "67%" in report
        assert "100%" in report

    def test_evaluate_all_skips_without_search_qa(self, tmp_path: Path) -> None:
        """Test that evaluate_all skips fixtures without search_qa."""
        import json

        # Create a fixture without search_qa
        html = "<html><body><p>Hello</p></body></html>"
        (tmp_path / "test.html").write_text(html)
        spec = {"name": "no_qa", "html_file": "test.html", "expected": {}}
        (tmp_path / "test.json").write_text(json.dumps(spec))

        benchmark = SearchQualityBenchmark()
        results = benchmark.evaluate_all(str(tmp_path))
        assert results == []

    def test_evaluate_all_with_search_qa(self, tmp_path: Path) -> None:
        """Test evaluate_all processes fixtures with search_qa items."""
        import json

        html = """
        <html><body>
            <h1>Test</h1>
            <p>The price is $99 for this item.</p>
        </body></html>
        """
        (tmp_path / "test.html").write_text(html)
        spec = {
            "name": "with_qa",
            "html_file": "test.html",
            "expected": {},
            "search_qa": [
                {"query": "What is the price?", "relevant_keywords": ["99", "price"]},
            ],
        }
        (tmp_path / "test.json").write_text(json.dumps(spec))

        benchmark = SearchQualityBenchmark()
        results = benchmark.evaluate_all(str(tmp_path))
        assert len(results) == 1
        assert results[0].fixture_name == "with_qa"
        assert results[0].total_queries == 1
