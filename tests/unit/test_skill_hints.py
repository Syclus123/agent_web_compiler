"""Tests for skill_hints — reverse adapter from BH domain-skills to AWC."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_web_compiler.runtime.browser_harness.skill_hints import (
    SkillHints,
    load_skill_hints,
    parse_skill_markdown,
    skill_hints_hook,
)

# A realistic skill sample modelled on real BH domain-skill files
# (e.g. github/scraping.md). Covers both code fences and inline URLs.
_GITHUB_SKILL_MD = """\
# GitHub — Scraping & Data Extraction

`https://github.com` — public data.

## Do this first

```python
import json
data = json.loads(http_get("https://api.github.com/repos/owner/repo"))
```

## Selectors that work

```js
document.querySelectorAll('article.Box-row')
document.querySelectorAll('#repo-content-pjax-container .Box')
[data-testid="repo-card"]
```

See https://raw.githubusercontent.com/owner/repo/main/README.md for raw files.
"""


# ---------------------------------------------------------------------------
# parse_skill_markdown
# ---------------------------------------------------------------------------


def test_parse_extracts_selectors() -> None:
    hints = parse_skill_markdown(_GITHUB_SKILL_MD, domain="github.com")
    assert "article.Box-row" in hints.stable_selectors
    assert any(s.startswith("#repo-content-pjax-container") for s in hints.stable_selectors)
    assert any('data-testid="repo-card"' in s for s in hints.stable_selectors)


def test_parse_classifies_api_endpoints() -> None:
    hints = parse_skill_markdown(_GITHUB_SKILL_MD, domain="github.com")
    # api.github.com path should be classified as API.
    assert any("api.github.com" in u for u in hints.api_endpoints)
    # raw.githubusercontent.com is not an API → should be in url_patterns
    assert any("raw.githubusercontent.com" in u for u in hints.url_patterns)


def test_parse_empty_input_returns_empty_hints() -> None:
    hints = parse_skill_markdown("", domain="x")
    assert hints.is_empty()
    assert hints.to_dict()["stable_selectors"] == []


def test_parse_handles_markdown_without_code_blocks() -> None:
    text = "Just prose. See https://example.com/page for more."
    hints = parse_skill_markdown(text, domain="example.com")
    # No selectors.
    assert hints.stable_selectors == []
    # URL is in url_patterns (no /api/, no api.host).
    assert any("example.com" in u for u in hints.url_patterns)


def test_parse_is_deterministic() -> None:
    a = parse_skill_markdown(_GITHUB_SKILL_MD, domain="github.com")
    b = parse_skill_markdown(_GITHUB_SKILL_MD, domain="github.com")
    assert a.to_dict() == b.to_dict()


# ---------------------------------------------------------------------------
# load_skill_hints — disk-backed
# ---------------------------------------------------------------------------


def _write_skills_tree(root: Path, *, slug: str, files: dict[str, str]) -> None:
    site = root / slug
    site.mkdir(parents=True, exist_ok=True)
    for fname, content in files.items():
        (site / fname).write_text(content, encoding="utf-8")


def test_load_skill_hints_missing_dir_returns_empty(tmp_path: Path) -> None:
    hints = load_skill_hints("https://github.com/foo", skills_dir=tmp_path / "does-not-exist")
    assert hints.is_empty()
    assert hints.domain == "github.com"


def test_load_skill_hints_slug_matches_domain_skill(tmp_path: Path) -> None:
    """The slug used for loading must match the one used by DomainSkill._slug."""
    _write_skills_tree(
        tmp_path,
        slug="github",  # produced from github.com
        files={"scraping.md": _GITHUB_SKILL_MD},
    )
    hints = load_skill_hints("https://github.com/browser-use/foo", skills_dir=tmp_path)
    assert hints.domain == "github.com"
    assert len(hints.source_paths) == 1
    assert hints.source_paths[0].name == "scraping.md"
    assert "article.Box-row" in hints.stable_selectors


def test_load_skill_hints_merges_multiple_files(tmp_path: Path) -> None:
    _write_skills_tree(
        tmp_path,
        slug="github",
        files={
            "scraping.md": _GITHUB_SKILL_MD,
            "repo-actions.md": "```js\nconst btn = document.querySelector('.js-star-button');\n```",
        },
    )
    hints = load_skill_hints("github.com", skills_dir=tmp_path)
    assert len(hints.source_paths) == 2
    assert ".js-star-button" in hints.stable_selectors
    assert "article.Box-row" in hints.stable_selectors


def test_load_skill_hints_accepts_bare_domain_and_full_domain_folder(tmp_path: Path) -> None:
    """If slug dir doesn't exist, fall back to trying the raw domain."""
    _write_skills_tree(
        tmp_path,
        slug="github.com",  # unusual but observed in some forks
        files={"scraping.md": _GITHUB_SKILL_MD},
    )
    hints = load_skill_hints("github.com", skills_dir=tmp_path)
    assert not hints.is_empty()


# ---------------------------------------------------------------------------
# skill_hints_hook — importance boosting
# ---------------------------------------------------------------------------


def test_skill_hints_hook_boosts_matching_blocks() -> None:
    from agent_web_compiler.core.block import Block, BlockType
    from agent_web_compiler.core.provenance import DOMProvenance, Provenance

    hints = SkillHints(domain="github.com", stable_selectors=["article.Box-row"])
    hook = skill_hints_hook(hints, boost=0.3)

    matching = Block(
        id="b_match",
        type=BlockType.PARAGRAPH,
        text="hello",
        importance=0.4,
        provenance=Provenance(
            dom=DOMProvenance(dom_path="main > article.Box-row > p"),
        ),
    )
    non_matching = Block(
        id="b_miss",
        type=BlockType.PARAGRAPH,
        text="world",
        importance=0.4,
        provenance=Provenance(dom=DOMProvenance(dom_path="footer > nav > a")),
    )
    hook(matching)
    hook(non_matching)
    assert matching.importance == pytest.approx(0.7)
    assert non_matching.importance == pytest.approx(0.4)


def test_skill_hints_hook_clamps_to_one() -> None:
    from agent_web_compiler.core.block import Block, BlockType
    from agent_web_compiler.core.provenance import DOMProvenance, Provenance

    hints = SkillHints(domain="x", stable_selectors=[".foo"])
    hook = skill_hints_hook(hints, boost=0.9)
    b = Block(
        id="b",
        type=BlockType.PARAGRAPH,
        text="",
        importance=0.5,
        provenance=Provenance(dom=DOMProvenance(dom_path="div.foo")),
    )
    hook(b)
    assert b.importance == pytest.approx(1.0)


def test_skill_hints_hook_noop_when_no_selectors() -> None:
    from agent_web_compiler.core.block import Block, BlockType

    hints = SkillHints(domain="x")  # empty
    hook = skill_hints_hook(hints)
    b = Block(id="b", type=BlockType.PARAGRAPH, text="", importance=0.5)
    hook(b)
    assert b.importance == 0.5  # unchanged


# ---------------------------------------------------------------------------
# Round-trip: DomainSkillPublisher writes → load_skill_hints reads
# ---------------------------------------------------------------------------


def test_publisher_output_can_be_reloaded(tmp_path: Path) -> None:
    """The slug used by DomainSkill.write_to_repo must align with load_skill_hints."""
    from agent_web_compiler.core.action import Action, ActionType
    from agent_web_compiler.core.document import AgentDocument, SourceType
    from agent_web_compiler.publisher import DomainSkillPublisher

    doc = AgentDocument(
        doc_id="d",
        source_type=SourceType.HTML,
        source_url="https://github.com/browser-use/browser-harness",
        title="t",
        blocks=[],
        actions=[
            Action(
                id="a",
                type=ActionType.CLICK,
                label="Star",
                selector="main#repo-content article.Box-row",
                priority=0.9,
            ),
        ],
    )
    skill = DomainSkillPublisher().generate_from_document(doc, task="scraping")
    # Write under <tmp>/agent-workspace/domain-skills/github/scraping.md
    written = skill.write_to_repo(tmp_path)
    skills_dir = written.parent.parent  # .../domain-skills

    # Now read it back.
    hints = load_skill_hints("https://github.com/", skills_dir=skills_dir)
    assert not hints.is_empty()
    # The main selector we fed in should come back as a stable selector.
    assert any("article.Box-row" in s for s in hints.stable_selectors)
