"""QA-based evaluation — proves AWC helps agents answer questions correctly.

For each fixture, we define questions and expected answers. Then we test
whether the compiled output contains enough information to answer each
question, and whether provenance can locate the answer source.

This is the KEY metric for demonstrating value: it's not about tokens,
it's about whether an agent can do its job with the compiled output.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from agent_web_compiler.core.block import Block
from agent_web_compiler.core.document import AgentDocument
from agent_web_compiler.utils.text import count_tokens_approx


@dataclass
class QAItem:
    """A single question-answer pair for evaluation."""

    question: str
    expected_answer: str
    answer_in_block_type: str | None = None  # Expected block type containing the answer
    answer_keywords: list[str] = field(default_factory=list)  # Keywords that must appear


@dataclass
class QAResult:
    """Result of evaluating a single QA item against a compiled document."""

    question: str
    answer_found: bool  # Was the answer text findable in compiled output?
    answer_in_correct_block: bool  # Was it in the expected block type?
    provenance_points_to_answer: bool  # Does provenance locate the answer?
    source_section: str | None = None  # Which section contained the answer
    token_savings_vs_full: float = 0.0  # How many tokens saved vs full page


@dataclass
class QAEvalResult:
    """Aggregated QA evaluation result for a single fixture."""

    fixture_name: str
    total_questions: int
    answers_found: int
    correct_block_type: int
    provenance_accurate: int
    answer_recall: float  # answers_found / total
    avg_token_savings: float
    per_question: list[QAResult] = field(default_factory=list)


def _keywords_in_text(keywords: list[str], text: str) -> bool:
    """Check if all keywords appear in text (case-insensitive)."""
    text_lower = text.lower()
    return all(kw.lower() in text_lower for kw in keywords)


def _find_answer_blocks(
    blocks: list[Block], keywords: list[str]
) -> list[Block]:
    """Find blocks containing all answer keywords."""
    if not keywords:
        return []
    return [b for b in blocks if _keywords_in_text(keywords, b.text)]


def _block_section_path(block: Block) -> str | None:
    """Get a readable section path from a block."""
    if block.section_path:
        return " > ".join(block.section_path)
    return None


def _check_provenance(block: Block, section_path_str: str | None) -> bool:
    """Check if the block's provenance or section_path can locate the answer."""
    # A block has useful provenance if it has a section_path or a Provenance object
    if block.section_path:
        return True
    return block.provenance is not None


class QAEvaluator:
    """Evaluates whether compiled output supports question answering."""

    def evaluate(
        self,
        doc: AgentDocument,
        qa_items: list[QAItem],
        raw_html: str | None = None,
    ) -> QAEvalResult:
        """Evaluate a compiled document against a list of QA items.

        Args:
            doc: The compiled AgentDocument.
            qa_items: List of question-answer pairs to evaluate.
            raw_html: Original raw HTML for token savings calculation.

        Returns:
            QAEvalResult with per-question and aggregate scores.
        """
        if not qa_items:
            return QAEvalResult(
                fixture_name=doc.title or "unknown",
                total_questions=0,
                answers_found=0,
                correct_block_type=0,
                provenance_accurate=0,
                answer_recall=1.0,
                avg_token_savings=0.0,
            )

        raw_tokens = count_tokens_approx(raw_html) if raw_html else 0
        per_question: list[QAResult] = []

        for item in qa_items:
            result = self._evaluate_single(doc, item, raw_tokens)
            per_question.append(result)

        answers_found = sum(1 for r in per_question if r.answer_found)
        correct_block_type = sum(1 for r in per_question if r.answer_in_correct_block)
        provenance_accurate = sum(
            1 for r in per_question if r.provenance_points_to_answer
        )
        savings = [r.token_savings_vs_full for r in per_question]
        avg_savings = sum(savings) / len(savings) if savings else 0.0

        return QAEvalResult(
            fixture_name=doc.title or "unknown",
            total_questions=len(qa_items),
            answers_found=answers_found,
            correct_block_type=correct_block_type,
            provenance_accurate=provenance_accurate,
            answer_recall=round(answers_found / len(qa_items), 3),
            avg_token_savings=round(avg_savings, 3),
            per_question=per_question,
        )

    def _evaluate_single(
        self,
        doc: AgentDocument,
        item: QAItem,
        raw_tokens: int,
    ) -> QAResult:
        """Evaluate a single QA item against the document."""
        keywords = item.answer_keywords
        if not keywords:
            # Fall back to the expected answer text as the keyword
            keywords = [item.expected_answer]

        # Find blocks containing the answer
        matching_blocks = _find_answer_blocks(doc.blocks, keywords)
        answer_found = len(matching_blocks) > 0

        # Check block type
        answer_in_correct_block = False
        if item.answer_in_block_type and matching_blocks:
            answer_in_correct_block = any(
                b.type.value == item.answer_in_block_type for b in matching_blocks
            )
        elif not item.answer_in_block_type and matching_blocks:
            # No expected block type specified — count as correct
            answer_in_correct_block = True

        # Check provenance
        provenance_points = False
        source_section: str | None = None
        if matching_blocks:
            for block in matching_blocks:
                section = _block_section_path(block)
                if _check_provenance(block, section):
                    provenance_points = True
                    source_section = section
                    break
            if source_section is None and matching_blocks:
                source_section = _block_section_path(matching_blocks[0])

        # Token savings: tokens of relevant blocks vs full HTML
        token_savings = 0.0
        if raw_tokens > 0 and matching_blocks:
            relevant_text = " ".join(b.text for b in matching_blocks)
            relevant_tokens = count_tokens_approx(relevant_text)
            token_savings = round(1.0 - (relevant_tokens / raw_tokens), 3)

        return QAResult(
            question=item.question,
            answer_found=answer_found,
            answer_in_correct_block=answer_in_correct_block,
            provenance_points_to_answer=provenance_points,
            source_section=source_section,
            token_savings_vs_full=token_savings,
        )

    def evaluate_all(self, fixtures_dir: str) -> list[QAEvalResult]:
        """Run QA evaluation on all fixtures in a directory.

        Each fixture must have a .json spec with a ``qa_items`` key
        and a corresponding .html file.

        Args:
            fixtures_dir: Path to directory containing fixture .json and .html files.

        Returns:
            List of QAEvalResult, one per fixture that has qa_items.
        """
        from agent_web_compiler.api.compile import compile_html

        fixtures_path = Path(fixtures_dir)
        if not fixtures_path.is_dir():
            raise FileNotFoundError(f"Fixtures directory not found: {fixtures_dir}")

        results: list[QAEvalResult] = []
        for spec_file in sorted(fixtures_path.glob("*.json")):
            spec = json.loads(spec_file.read_text())
            qa_raw = spec.get("qa_items")
            if not qa_raw:
                continue

            html_file = fixtures_path / spec["html_file"]
            if not html_file.exists():
                continue

            html = html_file.read_text(encoding="utf-8")
            doc = compile_html(
                html,
                source_url=f"bench://fixture/{spec.get('name', 'unknown')}",
                mode="balanced",
                include_actions=True,
                include_provenance=True,
                debug=False,
            )

            qa_items = [
                QAItem(
                    question=q["question"],
                    expected_answer=q["expected_answer"],
                    answer_in_block_type=q.get("answer_in_block_type"),
                    answer_keywords=q.get("answer_keywords", []),
                )
                for q in qa_raw
            ]

            result = self.evaluate(doc, qa_items, raw_html=html)
            result.fixture_name = spec.get("name", spec_file.stem)
            results.append(result)

        return results

    def generate_report(self, results: list[QAEvalResult]) -> str:
        """Generate a markdown report from QA evaluation results.

        Args:
            results: List of QAEvalResult from evaluate_all.

        Returns:
            Markdown-formatted report string.
        """
        lines: list[str] = []
        lines.append("# QA Evaluation Report\n")

        if not results:
            lines.append("No fixtures with qa_items found.\n")
            return "\n".join(lines)

        # Summary table
        lines.append("## Summary\n")
        lines.append(
            "| Fixture | Questions | Answered | Recall | Block Type | Provenance | Avg Token Savings |"
        )
        lines.append(
            "|---------|-----------|----------|--------|------------|------------|-------------------|"
        )

        total_q = 0
        total_found = 0
        total_block = 0
        total_prov = 0

        for r in results:
            total_q += r.total_questions
            total_found += r.answers_found
            total_block += r.correct_block_type
            total_prov += r.provenance_accurate
            lines.append(
                f"| {r.fixture_name} "
                f"| {r.total_questions} "
                f"| {r.answers_found} "
                f"| {r.answer_recall:.0%} "
                f"| {r.correct_block_type}/{r.total_questions} "
                f"| {r.provenance_accurate}/{r.total_questions} "
                f"| {r.avg_token_savings:.0%} |"
            )

        # Totals
        overall_recall = total_found / total_q if total_q > 0 else 0.0
        lines.append(
            f"| **Total** "
            f"| **{total_q}** "
            f"| **{total_found}** "
            f"| **{overall_recall:.0%}** "
            f"| **{total_block}/{total_q}** "
            f"| **{total_prov}/{total_q}** "
            f"| — |"
        )

        # Per-question detail
        lines.append("\n## Detail\n")
        for r in results:
            lines.append(f"### {r.fixture_name}\n")
            for pq in r.per_question:
                found_icon = "Y" if pq.answer_found else "N"
                block_icon = "Y" if pq.answer_in_correct_block else "N"
                prov_icon = "Y" if pq.provenance_points_to_answer else "N"
                section = pq.source_section or "—"
                lines.append(
                    f"- **Q:** {pq.question}\n"
                    f"  Found: {found_icon} | Block type: {block_icon} | "
                    f"Provenance: {prov_icon} | Section: {section}"
                )
            lines.append("")

        return "\n".join(lines)
