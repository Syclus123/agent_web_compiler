"""Tests for QA-based evaluation framework."""

from __future__ import annotations

from agent_web_compiler.core.block import Block, BlockType
from agent_web_compiler.core.document import AgentDocument, SourceType
from agent_web_compiler.core.provenance import DOMProvenance, Provenance
from bench.eval.qa_eval import QAEvalResult, QAEvaluator, QAItem, QAResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc(
    blocks: list[Block] | None = None,
    title: str = "Test Page",
) -> AgentDocument:
    return AgentDocument(
        doc_id="sha256:test123",
        source_type=SourceType.HTML,
        title=title,
        blocks=blocks or [],
    )


def _block(
    id: str,
    btype: BlockType,
    text: str,
    order: int = 0,
    section_path: list[str] | None = None,
    provenance: Provenance | None = None,
) -> Block:
    return Block(
        id=id,
        type=btype,
        text=text,
        order=order,
        section_path=section_path or [],
        provenance=provenance,
    )


# ---------------------------------------------------------------------------
# QAEvaluator.evaluate
# ---------------------------------------------------------------------------


class TestQAEvaluator:
    def test_empty_qa_items(self):
        doc = _make_doc()
        evaluator = QAEvaluator()
        result = evaluator.evaluate(doc, [])
        assert result.total_questions == 0
        assert result.answer_recall == 1.0

    def test_answer_found_by_keywords(self):
        doc = _make_doc(
            blocks=[
                _block("b1", BlockType.PARAGRAPH, "The price is $299.99 today."),
            ]
        )
        qa = [
            QAItem(
                question="What is the price?",
                expected_answer="$299.99",
                answer_keywords=["299", "price"],
                answer_in_block_type="paragraph",
            )
        ]
        evaluator = QAEvaluator()
        result = evaluator.evaluate(doc, qa)
        assert result.answers_found == 1
        assert result.answer_recall == 1.0
        assert result.correct_block_type == 1

    def test_answer_not_found(self):
        doc = _make_doc(
            blocks=[
                _block("b1", BlockType.PARAGRAPH, "Hello world"),
            ]
        )
        qa = [
            QAItem(
                question="What is the price?",
                expected_answer="$299.99",
                answer_keywords=["299", "price"],
            )
        ]
        evaluator = QAEvaluator()
        result = evaluator.evaluate(doc, qa)
        assert result.answers_found == 0
        assert result.answer_recall == 0.0

    def test_wrong_block_type(self):
        doc = _make_doc(
            blocks=[
                _block("b1", BlockType.HEADING, "Price: $299.99"),
            ]
        )
        qa = [
            QAItem(
                question="What is the price?",
                expected_answer="$299.99",
                answer_keywords=["299", "price"],
                answer_in_block_type="paragraph",
            )
        ]
        evaluator = QAEvaluator()
        result = evaluator.evaluate(doc, qa)
        assert result.answers_found == 1
        assert result.correct_block_type == 0  # wrong block type

    def test_no_block_type_specified_counts_as_correct(self):
        doc = _make_doc(
            blocks=[
                _block("b1", BlockType.HEADING, "Price: $299.99"),
            ]
        )
        qa = [
            QAItem(
                question="What is the price?",
                expected_answer="$299.99",
                answer_keywords=["299", "price"],
                # answer_in_block_type not set
            )
        ]
        evaluator = QAEvaluator()
        result = evaluator.evaluate(doc, qa)
        assert result.correct_block_type == 1

    def test_provenance_detected_via_section_path(self):
        doc = _make_doc(
            blocks=[
                _block(
                    "b1",
                    BlockType.PARAGRAPH,
                    "Price is $299.99",
                    section_path=["Products", "Pricing"],
                ),
            ]
        )
        qa = [
            QAItem(
                question="What is the price?",
                expected_answer="$299.99",
                answer_keywords=["299"],
            )
        ]
        evaluator = QAEvaluator()
        result = evaluator.evaluate(doc, qa)
        assert result.provenance_accurate == 1
        assert result.per_question[0].source_section == "Products > Pricing"

    def test_provenance_detected_via_provenance_object(self):
        prov = Provenance(
            dom=DOMProvenance(dom_path="div.price", element_tag="span")
        )
        doc = _make_doc(
            blocks=[
                _block(
                    "b1", BlockType.PARAGRAPH, "Price is $299.99", provenance=prov
                ),
            ]
        )
        qa = [
            QAItem(
                question="What is the price?",
                expected_answer="$299.99",
                answer_keywords=["299"],
            )
        ]
        evaluator = QAEvaluator()
        result = evaluator.evaluate(doc, qa)
        assert result.provenance_accurate == 1

    def test_multiple_questions(self):
        doc = _make_doc(
            blocks=[
                _block("b1", BlockType.PARAGRAPH, "Author: Jane Doe"),
                _block("b2", BlockType.PARAGRAPH, "Published: March 2026"),
                _block("b3", BlockType.CODE, "def hello(): pass  # Python"),
            ]
        )
        qa = [
            QAItem(
                question="Who wrote this?",
                expected_answer="Jane Doe",
                answer_keywords=["Jane", "Doe"],
                answer_in_block_type="paragraph",
            ),
            QAItem(
                question="When was it published?",
                expected_answer="March 2026",
                answer_keywords=["March", "2026"],
                answer_in_block_type="paragraph",
            ),
            QAItem(
                question="What language?",
                expected_answer="Python",
                answer_keywords=["Python"],
                answer_in_block_type="code",
            ),
        ]
        evaluator = QAEvaluator()
        result = evaluator.evaluate(doc, qa)
        assert result.total_questions == 3
        assert result.answers_found == 3
        assert result.answer_recall == 1.0
        assert result.correct_block_type == 3

    def test_token_savings_calculated(self):
        doc = _make_doc(
            blocks=[
                _block("b1", BlockType.PARAGRAPH, "Price $100"),
            ]
        )
        qa = [
            QAItem(
                question="What is the price?",
                expected_answer="$100",
                answer_keywords=["100"],
            )
        ]
        raw_html = "x " * 1000  # large HTML
        evaluator = QAEvaluator()
        result = evaluator.evaluate(doc, qa, raw_html=raw_html)
        assert result.per_question[0].token_savings_vs_full > 0.0

    def test_fallback_to_expected_answer_when_no_keywords(self):
        doc = _make_doc(
            blocks=[
                _block("b1", BlockType.PARAGRAPH, "The answer is 42."),
            ]
        )
        qa = [
            QAItem(
                question="What is the answer?",
                expected_answer="42",
                # No answer_keywords — should fall back to expected_answer
            )
        ]
        evaluator = QAEvaluator()
        result = evaluator.evaluate(doc, qa)
        assert result.answers_found == 1


class TestQAEvalReport:
    def test_generate_report_empty(self):
        evaluator = QAEvaluator()
        report = evaluator.generate_report([])
        assert "No fixtures" in report

    def test_generate_report_with_results(self):
        result = QAEvalResult(
            fixture_name="test",
            total_questions=2,
            answers_found=1,
            correct_block_type=1,
            provenance_accurate=0,
            answer_recall=0.5,
            avg_token_savings=0.8,
            per_question=[
                QAResult(
                    question="Q1?",
                    answer_found=True,
                    answer_in_correct_block=True,
                    provenance_points_to_answer=False,
                    source_section="Section A",
                ),
                QAResult(
                    question="Q2?",
                    answer_found=False,
                    answer_in_correct_block=False,
                    provenance_points_to_answer=False,
                ),
            ],
        )
        evaluator = QAEvaluator()
        report = evaluator.generate_report([result])
        assert "QA Evaluation Report" in report
        assert "test" in report
        assert "Q1?" in report
        assert "Q2?" in report
        assert "50%" in report
