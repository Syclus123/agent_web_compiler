"""Example: browser-harness integration end-to-end.

Prerequisites:
    pip install "agent-web-compiler[harness]"
    # Follow the BH setup prompt to connect to your Chrome:
    # https://github.com/browser-use/browser-harness#setup-prompt

Three self-contained demos:

    1. Fetch a page from the user's real Chrome and compile it.
    2. Run a task against that compiled page (click the best-match action).
    3. Generate a BH domain-skill PR-ready markdown.
"""

from __future__ import annotations

from pathlib import Path


def demo_1_fetch_with_bh() -> None:
    """AWC compile using the user's real Chrome as the rendering source."""
    from agent_web_compiler import compile_url

    doc = compile_url(
        "https://github.com/browser-use/browser-harness",
        fetcher="browser_harness",  # ← the one line that changes everything
    )
    print(f"Title: {doc.title}")
    print(f"Blocks: {doc.block_count} · Actions: {doc.action_count}")
    print(f"Parse confidence: {doc.quality.parse_confidence:.0%}")


def demo_2_live_act() -> None:
    """Compile + plan + execute a task against the live page."""
    from agent_web_compiler import LiveRuntime

    rt = LiveRuntime.from_url(
        "https://github.com/browser-use/browser-harness",
        fetcher="browser_harness",
    )
    outcome = rt.run("star the repository", max_actions=1)

    print(f"Success: {outcome.success}")
    for r in outcome.results:
        label = next((a.label for a in outcome.actions if a.id == r.action_id), r.action_id)
        print(f"  [{r.mode_used}] {label} → {'OK' if r.success else r.error}")
        if r.transition:
            print(f"    effect={r.transition.effect_type}, "
                  f"url_changed={r.transition.url_changed}, "
                  f"dom_changed={r.transition.dom_changed}")
        if r.screenshot_path:
            print(f"    screenshot: {r.screenshot_path}")

    for ev in outcome.evidence:
        print(f"  evidence: {ev.evidence_id} ({ev.source_type})")


def demo_3_generate_bh_skill(bh_repo: str) -> None:
    """Generate a browser-harness domain-skill from a compiled page.

    Args:
        bh_repo: path to a local clone of browser-use/browser-harness.
    """
    from agent_web_compiler import DomainSkillPublisher, compile_url

    doc = compile_url(
        "https://github.com/browser-use/browser-harness",
        fetcher="http",  # HTTP is enough for this page — no login needed
    )
    skill = DomainSkillPublisher().generate_from_document(doc, task="scraping")

    target = skill.write_to_repo(bh_repo, overwrite=True)
    print(f"Wrote {target}")
    print(skill.markdown)


if __name__ == "__main__":
    import sys

    demos = {
        "fetch": demo_1_fetch_with_bh,
        "live": demo_2_live_act,
        "skill": lambda: demo_3_generate_bh_skill(
            sys.argv[2] if len(sys.argv) > 2 else str(Path.home() / "code" / "browser-harness")
        ),
    }
    if len(sys.argv) < 2 or sys.argv[1] not in demos:
        print("Usage: python browser_harness_integration.py {fetch|live|skill [bh_repo_path]}")
        sys.exit(1)
    demos[sys.argv[1]]()
