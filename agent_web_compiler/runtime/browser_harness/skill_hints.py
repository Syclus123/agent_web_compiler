"""SkillHints — read browser-harness domain-skills and feed them back into AWC.

This closes the loop of the AWC × browser-harness integration in both
directions:

- **AWC → BH**: :class:`DomainSkillPublisher` emits markdown BH can consume.
- **BH → AWC** *(this module)*: when AWC compiles a page for a domain that
  already has a BH skill on disk, we parse that skill to extract
  *high-signal* hints — stable selectors, private APIs, "do not touch"
  patterns — and surface them to the pipeline.

Why this matters:

1. A site like ``github.com`` has a hand-tuned ``domain-skills/github/`` with
   selectors that took real agents real tries to discover. AWC's
   :class:`ActionExtractor` shouldn't re-learn them; it should treat them as
   **whitelisted affordances**.
2. The BH skill ecosystem is the only curated, community-maintained corpus
   of "what actually works on every site" — AWC that ignores it throws away
   free supervision.

Design:

- Parsing is **grammar-free**. We don't try to understand the markdown
  structure — we scan for fenced code blocks containing CSS selectors
  (``.foo``, ``#bar``, ``[data-*]``) and URLs. This keeps us robust to
  arbitrary authoring styles across the 80+ real skill files.
- The returned :class:`SkillHints` is a **pure data** object. How the
  pipeline uses it (boost salience, whitelist selectors, bias action
  extraction) is up to the caller — this module does not reach into the
  compilation code.
- All I/O is guarded so a malformed or missing skill dir degrades to
  *empty hints*, never an exception.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

# Matches any fenced code block. (?s) makes . match newlines.
_FENCED_CODE_RE = re.compile(r"```(?:[a-zA-Z0-9_+-]*)?\n(.*?)\n```", re.DOTALL)

# Matches inline code spans: `foo`. Used so we can pick up selectors listed
# in bullet lists (e.g. "- **main content**: `main#repo ...`"), which is the
# format that :class:`DomainSkillPublisher` emits.
_INLINE_CODE_RE = re.compile(r"`([^`\n]{1,120})`")

# We extract selectors from **string literals** inside code fences. BH
# skills consistently call `document.querySelector('...')`, `querySelectorAll('...')`,
# or write attribute-style selectors `[data-*="..."]` on their own line.
# This is far more precise than trying to grammar-parse CSS out of raw prose,
# and it avoids false positives from domain names (`.github.com`) and URL
# substrings.
_QS_CALL_RE = re.compile(
    r"""(?xs)
    (?:querySelector(?:All)?|closest|matches)
    \s* \( \s*
    (['"])                                   # opening quote
    (?P<sel>.+?)                             # selector body
    \1                                       # matching closing quote
    """,
)

# Attribute-style or tag.class selectors that occur on their own line:
# ``[data-*="x"]``, ``#root``, ``main.content``, ``article.Box-row``,
# ``button[aria-label="Close"]``.
# The line must START with ``#/./[`` or an alpha character (tag); the rest
# of the line (up to trailing punctuation) becomes the candidate selector.
# ``_is_plausible_selector`` filters obviously bogus matches.
_BARE_SELECTOR_LINE_RE = re.compile(
    r"^\s*(?P<sel>[\[#.a-zA-Z][^\n`]{1,119}?)\s*[;,)]?\s*$",
    re.MULTILINE,
)

# Matches http(s) URLs inside markdown.
_URL_RE = re.compile(r"https?://[^\s<>()\"'`]+")

# API hosts worth surfacing as "known private APIs". We match these against
# the hostnames we find in the skill's code fences.
_API_PATH_PATTERN = re.compile(r"/(?:api|v\d+|graphql|rest|json)(?:/|$)", re.IGNORECASE)


@dataclass
class SkillHints:
    """Structured hints extracted from a browser-harness domain-skill.

    Attributes:
        domain:             Target domain this skill is about.
        source_paths:       Files on disk that contributed to these hints.
        stable_selectors:   CSS selectors observed inside ``python`` / ``js``
                            code fences — presumed stable enough to be
                            whitelisted.
        api_endpoints:      URLs whose path looks like an API (``/api/``,
                            ``/v1/``, ``/graphql``, ``api.<host>``, …).
        url_patterns:       Other http(s) URLs found — useful as entry-point
                            candidates.
        raw:                Concatenated markdown bodies. Callers that want
                            richer parsing can work from this.
    """

    domain: str
    source_paths: list[Path] = field(default_factory=list)
    stable_selectors: list[str] = field(default_factory=list)
    api_endpoints: list[str] = field(default_factory=list)
    url_patterns: list[str] = field(default_factory=list)
    raw: str = ""

    def is_empty(self) -> bool:
        return not (self.stable_selectors or self.api_endpoints or self.url_patterns)

    def to_dict(self) -> dict[str, object]:
        return {
            "domain": self.domain,
            "source_paths": [str(p) for p in self.source_paths],
            "stable_selectors": list(self.stable_selectors),
            "api_endpoints": list(self.api_endpoints),
            "url_patterns": list(self.url_patterns),
        }


# ---------------------------------------------------------------------------
# Parsing surface
# ---------------------------------------------------------------------------


def parse_skill_markdown(text: str, *, domain: str = "") -> SkillHints:
    """Extract hints from one BH skill markdown body.

    Args:
        text: The full ``.md`` file contents.
        domain: Optional — recorded on the returned object for traceability.

    Returns:
        A :class:`SkillHints` instance. Never raises.
    """
    hints = SkillHints(domain=domain, raw=text)
    if not text:
        return hints

    selectors: set[str] = set()
    api_urls: set[str] = set()
    all_urls: set[str] = set()

    def _is_plausible_selector(s: str) -> bool:
        """Guard against obvious false positives.

        Accepted forms:
          * starts with ``#``, ``.``, or ``[`` (ID / class / attribute) — but
            ``#`` followed by whitespace is a comment, not an ID selector.
          * starts with an HTML tag and contains at least one ``#/./[`` modifier
            (e.g. ``article.Box-row``, ``button[aria-label=...]``)

        Rejected:
          * lines containing ``()``                 — JS method calls
          * lines containing ``==`` / ``!=`` / ``:`` — expressions
          * lines containing ``=`` outside ``[...]`` — assignments
          * ends with common file extensions
          * hostname / URL-like strings
          * TLD-leading
          * comments / shebangs
          * curly braces (`{`, `}`) — JS/JSON literals
        """
        s = s.strip()
        if not s or len(s) > 120:
            return False
        if "(" in s or ")" in s:
            return False
        if "==" in s or "!=" in s:
            return False
        if "{" in s or "}" in s:
            return False
        # ``:`` only appears in CSS selectors as pseudo-classes (``:hover``)
        # or namespaces (``svg|circle``). A bare ``:`` followed by space is
        # always python/YAML. Apply only to the first 3 chars to stay
        # conservative.
        if " : " in s or s.endswith(":"):
            return False
        # Assignment guard: a raw ``= `` (equals + space) is python/JS
        # assignment — never appears in a valid CSS selector.
        if "= " in s or " =" in s:
            return False
        lower = s.lower()
        if lower.endswith((".md", ".py", ".js", ".ts", ".html", ".json", ".txt")):
            return False
        if s.startswith((".com", ".org", ".net", ".io", ".dev")):
            return False
        if len(s) < 2:
            return False

        if s.startswith("#"):
            return s[1] not in " \t!"
        if s[0] in ".[":
            return True
        if s[0].isalpha():
            # Tag-led: must contain a CSS structural modifier (`#`, `[`, or
            # `.` followed by an identifier that is NOT a TLD).
            if re.search(r"[#\[]", s):
                return True
            if re.search(
                r"\.(com|org|net|io|dev|gov|edu|co|ai)(/|$)",
                s,
                re.IGNORECASE,
            ):
                return False
            # Any ``.classname`` where classname is not a TLD. This matches
            # ``article.Box-row``, ``main article.Box-row`` (with descendant
            # combinator), ``div.foo > span.bar``, etc.
            for m in re.finditer(r"\.([a-zA-Z][\w-]*)", s):
                if m.group(1).lower() not in {
                    "com", "org", "net", "io", "dev", "gov", "edu", "md", "py",
                    "js", "ts", "html", "json", "txt", "co", "ai",
                }:
                    return True
        return False

    for m in _FENCED_CODE_RE.finditer(text):
        body = m.group(1)

        # 1. Selectors inside querySelector / querySelectorAll calls.
        for qs in _QS_CALL_RE.finditer(body):
            sel = qs.group("sel").strip()
            if _is_plausible_selector(sel):
                selectors.add(sel)

        # 2. Bare selector lines (e.g. `[data-testid="..."]` on its own line).
        for bare in _BARE_SELECTOR_LINE_RE.finditer(body):
            sel = bare.group("sel").strip().rstrip(",;")
            if _is_plausible_selector(sel):
                selectors.add(sel)

        # 3. URLs — classify each.
        for url in _URL_RE.findall(body):
            url = url.rstrip(").,;\"'`")
            all_urls.add(url)
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
            if _API_PATH_PATTERN.search(parsed.path) or host.startswith("api."):
                api_urls.add(url)

    # Also scan prose for URLs — BH skills often cite APIs inline.
    for url in _URL_RE.findall(text):
        url = url.rstrip(").,;\"'`")
        all_urls.add(url)
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if _API_PATH_PATTERN.search(parsed.path) or host.startswith("api."):
            api_urls.add(url)

    # 4. Inline code spans — DomainSkillPublisher puts selectors here.
    # Limit to prose *outside* fenced blocks (otherwise we'd double-count
    # the bodies we already scanned). We strip fences from ``text`` first.
    text_outside_fences = _FENCED_CODE_RE.sub("", text)
    for m in _INLINE_CODE_RE.finditer(text_outside_fences):
        candidate = m.group(1).strip()
        # Skip obvious non-selector spans (URLs, python identifiers).
        if candidate.startswith(("http://", "https://")):
            continue
        if _is_plausible_selector(candidate):
            selectors.add(candidate)

    hints.stable_selectors = sorted(selectors)
    hints.api_endpoints = sorted(api_urls)
    hints.url_patterns = sorted(all_urls - api_urls)
    return hints


def load_skill_hints(
    url_or_domain: str,
    *,
    skills_dir: str | Path,
) -> SkillHints:
    """Load and merge every skill under ``<skills_dir>/<slug>/*.md``.

    ``url_or_domain`` may be a full URL or a bare domain. The slug rule
    mirrors :meth:`DomainSkill._slug` (``www.`` stripped, TLD dropped,
    dots → hyphens) so that skill folders written by AWC can also be read
    back.

    ``skills_dir`` may be either:

    - the ``agent-workspace/domain-skills/`` directory itself, or
    - a browser-harness repo root (we will look for
      ``<skills_dir>/agent-workspace/domain-skills/``), or
    - an agent-workspace dir (we will look for ``<skills_dir>/domain-skills/``).

    Returns an empty :class:`SkillHints` if nothing is found.
    """
    domain = _extract_domain(url_or_domain)
    slug = _slug(domain)
    root = Path(skills_dir).expanduser()
    if not root.is_dir():
        return SkillHints(domain=domain)

    # Try each plausible layout. First hit wins.
    candidates: list[Path] = [
        root,
        root / "agent-workspace" / "domain-skills",
        root / "domain-skills",
    ]
    resolved_root: Path | None = None
    for cand in candidates:
        if (cand / slug).is_dir() or (cand / domain).is_dir():
            resolved_root = cand
            break
    if resolved_root is None:
        return SkillHints(domain=domain)

    site_dir = resolved_root / slug
    if not site_dir.is_dir():
        site_dir = resolved_root / domain
        if not site_dir.is_dir():
            return SkillHints(domain=domain)

    merged = SkillHints(domain=domain)
    for md in sorted(site_dir.glob("*.md")):
        try:
            text = md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        partial = parse_skill_markdown(text, domain=domain)
        merged.source_paths.append(md)
        merged.stable_selectors.extend(partial.stable_selectors)
        merged.api_endpoints.extend(partial.api_endpoints)
        merged.url_patterns.extend(partial.url_patterns)
        merged.raw = (merged.raw + "\n\n" + partial.raw) if merged.raw else partial.raw

    merged.stable_selectors = sorted(set(merged.stable_selectors))
    merged.api_endpoints = sorted(set(merged.api_endpoints))
    merged.url_patterns = sorted(set(merged.url_patterns))
    return merged


# ---------------------------------------------------------------------------
# Pipeline hook
# ---------------------------------------------------------------------------


def skill_hints_hook(
    hints: SkillHints,
    *,
    boost: float = 0.25,
):
    """Return a function that boosts block importance.

    The returned callable accepts **either** a :class:`Block` (for use as an
    ``on_block_created`` hook) **or** an :class:`AgentDocument` (for use as
    an ``after_compile`` hook that survives the downstream salience pass).
    Use the document form with :meth:`PipelineBuilder.on_after_compile` when
    you want the boost to persist after ``Salience`` scoring.

    Args:
        hints: The hints to apply.
        boost: Amount to add to ``block.importance`` on a match (clamped to [0, 1]).
    """
    # Pre-compute per-selector tokens. A "token" is a selector chunk between
    # whitespace or a ``>`` / ``+`` / ``~`` combinator. For matching against a
    # DOM path, we require *every* token of a selector to appear somewhere in
    # the DOM path (in any order). This makes the match robust to the
    # space-vs-`` > `` combinator mismatch between BH skill markdown (which
    # uses descendant combinators) and AWC's DOM path notation (which uses
    # child combinators).
    combinator_re = re.compile(r"[\s>+~]+")
    selector_tokens = []
    for sel in hints.stable_selectors:
        tokens = [t for t in combinator_re.split(sel.strip().lower()) if t]
        if tokens:
            selector_tokens.append(tokens)

    def _boost_block(block) -> bool:  # noqa: ANN001 — dynamic Block
        if not selector_tokens:
            return False
        prov = getattr(block, "provenance", None)
        dom_path: str | None = None
        if prov is not None:
            dom_obj = getattr(prov, "dom", None)
            if dom_obj is not None:
                dom_path = getattr(dom_obj, "dom_path", None)
            if dom_path is None:
                dom_path = getattr(prov, "dom_path", None)
        if not dom_path:
            return False
        dp_low = dom_path.lower()
        for tokens in selector_tokens:
            if all(tok in dp_low for tok in tokens):
                block.importance = min(1.0, float(block.importance) + boost)
                return True
        return False

    def _hook(target):  # noqa: ANN001
        # AgentDocument path (after_compile): iterate blocks and return doc
        if hasattr(target, "blocks") and isinstance(target.blocks, list):
            for b in target.blocks:
                _boost_block(b)
            return target
        # Single block path (on_block_created)
        _boost_block(target)
        return target

    return _hook


# ---------------------------------------------------------------------------
# Slug / domain helpers (mirror DomainSkill._slug so roundtrips work)
# ---------------------------------------------------------------------------


def _extract_domain(url_or_domain: str) -> str:
    """Accept a URL *or* a bare hostname and return the hostname."""
    if "://" in url_or_domain:
        parsed = urlparse(url_or_domain)
        return (parsed.hostname or parsed.netloc or "").lower()
    return url_or_domain.strip().lower()


def _slug(domain: str) -> str:
    """Mirror of :meth:`DomainSkill._slug`.

    Rules: strip ``www.``, drop the TLD (everything after the last dot),
    then replace any remaining dots / underscores with hyphens.
    """
    d = domain.lower().removeprefix("www.")
    if "." in d:
        d = d.rsplit(".", 1)[0]
    return d.replace(".", "-").replace("_", "-")
