"""HTML normalizer: removes boilerplate, noise, and non-content elements."""

from __future__ import annotations

import re

import lxml.html
from lxml.html import HtmlElement, tostring

from agent_web_compiler.core.config import CompileConfig


class HTMLNormalizer:
    """Removes boilerplate, noise, and non-content elements from HTML.

    The normalizer operates in several passes:
    1. Strip tags that never contain useful content (script, style, etc.)
    2. Identify a main content area if one exists (main, article, etc.)
    3. Remove boilerplate structural tags with low content scores
    4. Remove elements whose class/id matches known noise patterns
    """

    # Tags to completely remove (content and all)
    REMOVE_TAGS: set[str] = {
        "script", "style", "noscript", "iframe", "svg", "math", "template", "head",
    }

    # Tags that are boilerplate indicators
    BOILERPLATE_TAGS: set[str] = {"header", "footer", "nav", "aside"}

    # Class/id patterns that indicate noise
    NOISE_PATTERNS: list[str] = [
        r"cookie", r"consent", r"banner", r"popup", r"modal", r"overlay",
        r"sidebar", r"widget", r"social", r"share", r"comment",
        r"subscribe", r"newsletter", r"advertisement", r"ad-", r"ads-",
        r"sponsor", r"promo", r"related", r"recommended",
        r"footer", r"header", r"nav", r"menu", r"breadcrumb",
    ]

    # Selectors for main content areas (checked in order)
    _MAIN_CONTENT_SELECTORS: list[str] = [
        "main",
        "article",
        ".//*[@role='main']",
        ".//*[@id='content']",
        ".//*[contains(@class, 'main-content')]",
        ".//*[contains(@class, 'post-content')]",
        ".//*[contains(@class, 'article-content')]",
        ".//*[contains(@class, 'entry-content')]",
    ]

    def __init__(self) -> None:
        self._noise_re = re.compile(
            "|".join(self.NOISE_PATTERNS), re.IGNORECASE,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def normalize(self, html: str, config: CompileConfig) -> str:
        """Clean HTML by removing boilerplate and noise.

        Args:
            html: Raw HTML string to normalize.
            config: Compilation config (reserved for future per-run tuning).

        Returns:
            Cleaned HTML string. Returns an empty string when the input is
            empty or cannot be parsed.
        """
        if not html or not html.strip():
            return ""

        tree = self._parse(html)
        if tree is None:
            return ""

        # Pass 1: strip always-remove tags
        self._remove_tags(tree)

        # Pass 2: locate main content area (used for score boosting)
        main_content = self._find_main_content(tree)

        # Pass 3: remove boilerplate structural tags with low scores
        self._remove_boilerplate(tree, main_content)

        # Pass 4: remove noise-patterned elements with low scores
        self._remove_noise(tree, main_content)

        return self._serialize(tree)

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse(html: str) -> HtmlElement | None:
        """Parse HTML string into an lxml tree, returning None on failure."""
        try:
            doc = lxml.html.fromstring(html)
            return doc
        except Exception:  # lxml can raise various errors on malformed input
            return None

    @staticmethod
    def _serialize(tree: HtmlElement) -> str:
        """Serialize an lxml tree back to an HTML string."""
        return tostring(tree, encoding="unicode", method="html")

    # ------------------------------------------------------------------
    # Pass 1: remove unwanted tags entirely
    # ------------------------------------------------------------------

    def _remove_tags(self, tree: HtmlElement) -> None:
        """Remove elements whose tag is in REMOVE_TAGS (including children)."""
        for tag in self.REMOVE_TAGS:
            for el in tree.iter(tag):
                parent = el.getparent()
                if parent is not None:
                    parent.remove(el)

    # ------------------------------------------------------------------
    # Pass 2: find main content area
    # ------------------------------------------------------------------

    def _find_main_content(self, tree: HtmlElement) -> HtmlElement | None:
        """Return the first element matching a main-content selector, or None."""
        for selector in self._MAIN_CONTENT_SELECTORS:
            # Simple tag names need to be turned into XPath
            if not selector.startswith("."):
                results = tree.iter(selector)
                first = next(results, None)
                if first is not None:
                    return first
            else:
                results = tree.xpath(selector)
                if results:
                    return results[0]
        return None

    # ------------------------------------------------------------------
    # Pass 3: boilerplate removal
    # ------------------------------------------------------------------

    def _remove_boilerplate(
        self, tree: HtmlElement, main_content: HtmlElement | None,
    ) -> None:
        """Remove BOILERPLATE_TAGS that have a low content score.

        When a main content area is detected, boilerplate elements outside it
        are removed more aggressively (higher score threshold).
        """
        for tag in self.BOILERPLATE_TAGS:
            for el in list(tree.iter(tag)):
                # If we found a main content area, remove boilerplate outside it
                # more aggressively
                if main_content is not None and not self._is_descendant_of(el, main_content):
                    parent = el.getparent()
                    if parent is not None:
                        parent.remove(el)
                    continue

                score = self._content_score(el, main_content)
                if score < 0.3:
                    parent = el.getparent()
                    if parent is not None:
                        parent.remove(el)

    # ------------------------------------------------------------------
    # Pass 4: noise pattern removal
    # ------------------------------------------------------------------

    def _remove_noise(
        self, tree: HtmlElement, main_content: HtmlElement | None,
    ) -> None:
        """Remove elements whose class/id matches noise patterns and have low content score."""
        for el in list(tree.iter()):
            if not isinstance(el, HtmlElement):
                continue
            if self._matches_noise(el):
                score = self._content_score(el, main_content)
                if score < 0.3:
                    parent = el.getparent()
                    if parent is not None:
                        parent.remove(el)

    def _matches_noise(self, el: HtmlElement) -> bool:
        """Return True if the element's class or id matches a noise pattern."""
        classes = el.get("class", "")
        el_id = el.get("id", "")
        combined = f"{classes} {el_id}"
        return bool(self._noise_re.search(combined))

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _content_score(
        self, el: HtmlElement, main_content: HtmlElement | None,
    ) -> float:
        """Compute a heuristic content score for an element.

        Score formula:
            text_density = len(text) / max(len(html_of_element), 1)
            link_density = count(<a>) / max(total_children, 1)
            content_score = text_density * (1 - link_density)

        Elements inside a detected main content area get a boost.
        Elements with fewer than 25 characters of text that are *not*
        inside main/article are penalized to zero.
        """
        text = el.text_content() or ""
        text_len = len(text.strip())

        # Short-text penalty: if < 25 chars and not inside main/article, score 0
        if text_len < 25 and not self._is_inside_main_or_article(el):
            return 0.0

        html_len = max(len(tostring(el, encoding="unicode", method="html")), 1)
        text_density = text_len / html_len

        child_elements = list(el)
        total_children = max(len(child_elements), 1)
        link_count = sum(1 for c in el.iter("a"))
        link_density = link_count / total_children

        score = text_density * (1.0 - link_density)

        # Boost if inside the identified main content area
        if main_content is not None and self._is_descendant_of(el, main_content):
            score = min(score * 1.5, 1.0)

        return score

    # ------------------------------------------------------------------
    # Tree-relationship helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_inside_main_or_article(el: HtmlElement) -> bool:
        """Return True if any ancestor of *el* is a <main> or <article> tag."""
        parent = el.getparent()
        while parent is not None:
            if isinstance(parent, HtmlElement) and parent.tag in ("main", "article"):
                return True
            parent = parent.getparent()
        return False

    @staticmethod
    def _is_descendant_of(el: HtmlElement, ancestor: HtmlElement) -> bool:
        """Return True if *el* is a descendant of *ancestor*."""
        parent = el.getparent()
        while parent is not None:
            if parent is ancestor:
                return True
            parent = parent.getparent()
        return False
