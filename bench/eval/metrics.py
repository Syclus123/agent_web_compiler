"""Benchmark evaluation metrics — token efficiency, content fidelity, and action quality."""

from __future__ import annotations

from agent_web_compiler.core.block import BlockType
from agent_web_compiler.core.document import AgentDocument
from agent_web_compiler.utils.text import count_tokens_approx


def compute_token_efficiency(raw_html: str, compiled_markdown: str) -> dict[str, int | float]:
    """Compute token efficiency metrics.

    Args:
        raw_html: The raw HTML input.
        compiled_markdown: The compiled markdown output.

    Returns:
        Dictionary with raw_tokens, compiled_tokens, and compression_ratio.
    """
    raw_tokens = count_tokens_approx(raw_html)
    compiled_tokens = count_tokens_approx(compiled_markdown)
    compression_ratio = raw_tokens / compiled_tokens if compiled_tokens > 0 else float("inf")
    return {
        "raw_tokens": raw_tokens,
        "compiled_tokens": compiled_tokens,
        "compression_ratio": round(compression_ratio, 2),
    }


def _heading_texts(doc: AgentDocument) -> list[str]:
    """Extract lowercase heading texts from document blocks."""
    return [
        b.text.strip().lower()
        for b in doc.blocks
        if b.type == BlockType.HEADING
    ]


def compute_content_fidelity(
    doc: AgentDocument,
    expected_headings: list[str],
    expected_tables: int,
    expected_code: int,
    key_phrases: list[str],
) -> dict[str, float]:
    """Evaluate content fidelity against expected outputs.

    All scores are floats in [0.0, 1.0].

    Args:
        doc: The compiled AgentDocument.
        expected_headings: Headings that should appear in the output.
        expected_tables: Minimum expected table block count.
        expected_code: Minimum expected code block count.
        key_phrases: Phrases that must appear somewhere in the output text.

    Returns:
        Dictionary with heading_fidelity, table_fidelity, code_fidelity,
        text_coverage, and structure_score.
    """
    # Heading fidelity: fraction of expected headings found (case-insensitive substring match)
    found_headings = _heading_texts(doc)
    if expected_headings:
        matches = sum(
            1
            for eh in expected_headings
            if any(eh.lower() in fh for fh in found_headings)
        )
        heading_fidelity = matches / len(expected_headings)
    else:
        heading_fidelity = 1.0

    # Table fidelity
    table_count = len(doc.get_blocks_by_type(BlockType.TABLE))
    if expected_tables > 0:
        table_fidelity = min(1.0, table_count / expected_tables)
    else:
        table_fidelity = 1.0

    # Code fidelity
    code_count = len(doc.get_blocks_by_type(BlockType.CODE))
    if expected_code > 0:
        code_fidelity = min(1.0, code_count / expected_code)
    else:
        code_fidelity = 1.0

    # Text coverage: fraction of key phrases found in canonical markdown
    markdown_lower = doc.canonical_markdown.lower()
    if key_phrases:
        phrase_hits = sum(1 for kp in key_phrases if kp.lower() in markdown_lower)
        text_coverage = phrase_hits / len(key_phrases)
    else:
        text_coverage = 1.0

    # Structure score: check that headings appear in correct order and sections exist
    if expected_headings and found_headings:
        # Order preservation: for each pair of expected headings that both appear,
        # check that they appear in the correct relative order.
        found_indices: list[int | None] = []
        for eh in expected_headings:
            idx = next(
                (i for i, fh in enumerate(found_headings) if eh.lower() in fh),
                None,
            )
            found_indices.append(idx)

        present = [i for i in found_indices if i is not None]
        if len(present) >= 2:
            ordered_pairs = sum(
                1 for a, b in zip(present, present[1:]) if a < b
            )
            structure_score = ordered_pairs / (len(present) - 1)
        else:
            structure_score = 1.0 if present else 0.0
    else:
        structure_score = 1.0

    return {
        "heading_fidelity": round(heading_fidelity, 3),
        "table_fidelity": round(table_fidelity, 3),
        "code_fidelity": round(code_fidelity, 3),
        "text_coverage": round(text_coverage, 3),
        "structure_score": round(structure_score, 3),
    }


def compute_action_recall(
    doc: AgentDocument,
    expected_actions: list[dict[str, str]],
    main_action_label: str | None = None,
) -> dict[str, float | bool]:
    """Evaluate action extraction quality.

    Each expected action is a dict with 'type' and 'label_contains'.

    Args:
        doc: The compiled AgentDocument.
        expected_actions: List of expected action specifications.
        main_action_label: Label substring of the primary/main action.

    Returns:
        Dictionary with action_recall, action_precision, and main_action_found.
    """
    found_actions = doc.actions

    if not expected_actions:
        return {
            "action_recall": 1.0,
            "action_precision": 1.0 if not found_actions else 0.0,
            "main_action_found": main_action_label is None,
        }

    # Recall: fraction of expected actions matched
    matched_expected = 0
    matched_found_ids: set[str] = set()

    for ea in expected_actions:
        ea_type = ea.get("type", "").lower()
        ea_label = ea.get("label_contains", "").lower()

        for fa in found_actions:
            if fa.id in matched_found_ids:
                continue
            type_match = (not ea_type) or (fa.type.value.lower() == ea_type)
            label_match = (not ea_label) or (ea_label in fa.label.lower())
            if type_match and label_match:
                matched_expected += 1
                matched_found_ids.add(fa.id)
                break

    action_recall = matched_expected / len(expected_actions)

    # Precision: fraction of found actions that matched an expected action
    action_precision = (
        len(matched_found_ids) / len(found_actions) if found_actions else 1.0
    )

    # Main action
    main_action_found = False
    if main_action_label:
        main_lower = main_action_label.lower()
        main_action_found = any(main_lower in a.label.lower() for a in found_actions)
    else:
        main_action_found = True

    return {
        "action_recall": round(action_recall, 3),
        "action_precision": round(action_precision, 3),
        "main_action_found": main_action_found,
    }
