"""End-to-end integration test: PipelineBuilder.with_skill_hints.

Verifies the ``AWC → BH → AWC`` round-trip without touching the network or
any real BH daemon:

1. :class:`DomainSkillPublisher` writes a skill to a temp dir.
2. :meth:`PipelineBuilder.with_skill_hints` reads it back.
3. The compiled document's matching blocks get their importance boosted.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_web_compiler import PipelineBuilder
from agent_web_compiler.core.action import Action, ActionType
from agent_web_compiler.core.document import AgentDocument, SourceType
from agent_web_compiler.publisher import DomainSkillPublisher

_DEMO_HTML = """\
<!DOCTYPE html>
<html><head><title>Example</title></head>
<body>
<main>
    <article class="Box-row">
        <p>Inner boosted paragraph</p>
    </article>
    <footer class="site-footer">
        <p>A regular footer paragraph</p>
    </footer>
</main>
</body></html>
"""


def test_with_skill_hints_noop_when_skills_dir_missing(tmp_path: Path) -> None:
    """No skills on disk → the builder stays unchanged."""
    pipeline = (
        PipelineBuilder()
        .with_skill_hints("https://example.com/", skills_dir=str(tmp_path))
        .build()
    )
    # Compile anything — should work unchanged.
    doc = pipeline.compile(_DEMO_HTML, source_url="https://example.com/")
    assert doc.title == "Example"


def test_with_skill_hints_boosts_matching_blocks(tmp_path: Path) -> None:
    """AWC → BH → AWC round-trip via PipelineBuilder.with_skill_hints."""
    # Step 1: fabricate a doc that has a selector pointing into `article.Box-row`.
    seed_doc = AgentDocument(
        doc_id="seed",
        source_type=SourceType.HTML,
        source_url="https://github.com/browser-use/browser-harness",
        title="Seed",
        blocks=[],
        actions=[
            Action(
                id="a_row",
                type=ActionType.CLICK,
                label="row",
                selector="main article.Box-row",
                priority=0.9,
            ),
        ],
    )
    skill = DomainSkillPublisher().generate_from_document(seed_doc, task="scraping")
    skill.write_to_repo(tmp_path, overwrite=True)

    # Step 2: build a pipeline that reads that same skill back and apply
    # the hook to a page that contains an `.Box-row` block.
    pipeline_without = PipelineBuilder().build()
    baseline_doc = pipeline_without.compile(
        _DEMO_HTML, source_url="https://github.com/browser-use/anything"
    )

    pipeline_with_hints = (
        PipelineBuilder()
        .with_skill_hints(
            "https://github.com/browser-use/anything", skills_dir=str(tmp_path),
        )
        .build()
    )
    boosted_doc = pipeline_with_hints.compile(
        _DEMO_HTML, source_url="https://github.com/browser-use/anything"
    )

    # Step 3: find the block whose DOM path matches `Box-row`.
    def _find_box_row_importance(doc: AgentDocument) -> float | None:
        for b in doc.blocks:
            prov = b.provenance
            dom = getattr(prov, "dom", None) if prov else None
            dp = getattr(dom, "dom_path", "") if dom else ""
            if "box-row" in (dp or "").lower():
                return b.importance
        return None

    base_imp = _find_box_row_importance(baseline_doc)
    boosted_imp = _find_box_row_importance(boosted_doc)

    assert base_imp is not None, "baseline must produce a block under Box-row"
    assert boosted_imp is not None, "boosted must produce a block under Box-row"
    assert boosted_imp > base_imp, (
        f"skill-hint boost failed: baseline={base_imp}, boosted={boosted_imp}"
    )


def test_with_skill_hints_env_var_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``AWC_BH_SKILLS_DIR`` env var is honoured when skills_dir is omitted."""
    seed_doc = AgentDocument(
        doc_id="s",
        source_type=SourceType.HTML,
        source_url="https://example.com/page",
        title="s",
        blocks=[],
        actions=[
            Action(
                id="a",
                type=ActionType.CLICK,
                label="x",
                selector="main article.foo",
                priority=0.9,
            ),
        ],
    )
    skill = DomainSkillPublisher().generate_from_document(seed_doc, task="scraping")
    skill.write_to_repo(tmp_path, overwrite=True)

    monkeypatch.setenv("AWC_BH_SKILLS_DIR", str(tmp_path))
    # No explicit skills_dir — should pick up env var.
    builder = PipelineBuilder().with_skill_hints("https://example.com/page")
    # One hook should be registered — we use after_compile so the boost
    # survives the salience pass.
    assert len(builder._hooks.after_compile) == 1  # noqa: SLF001
