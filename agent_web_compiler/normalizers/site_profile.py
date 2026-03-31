"""Site profile learning -- detects shared templates across pages from the same domain."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import lxml.html
from lxml.html import HtmlElement

from agent_web_compiler.core.document import SiteProfile


@dataclass
class _ElementSignature:
    """Signature of a top-level body child for template detection."""

    tag: str
    classes: frozenset[str]
    child_count: int

    @property
    def key(self) -> str:
        """Hashable key for comparison across pages."""
        sorted_classes = ",".join(sorted(self.classes)) if self.classes else ""
        return f"{self.tag}|{sorted_classes}"


@dataclass
class _DomainObservations:
    """Accumulated observations for a single domain."""

    page_count: int = 0
    # key -> list of child counts per observation
    element_counts: dict[str, list[int]] = field(default_factory=lambda: defaultdict(list))
    # key -> set of classes seen
    element_classes: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    # key -> tag
    element_tags: dict[str, str] = field(default_factory=dict)
    # Track all class names for noise detection
    all_class_names: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    # Track text variance per top-level element across pages (hash of text content)
    text_hashes: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))


class SiteProfileLearner:
    """Learns noise patterns and template structure from multiple pages of the same site.

    Usage:
        learner = SiteProfileLearner()
        learner.observe("example.com", html_page_1)
        learner.observe("example.com", html_page_2)
        profile = learner.build_profile("example.com")
        # Use profile to improve normalization
    """

    # Threshold: elements appearing in this fraction of pages are template
    TEMPLATE_THRESHOLD = 0.7

    def __init__(self) -> None:
        self._domains: dict[str, _DomainObservations] = {}
        self._profiles: dict[str, SiteProfile] = {}

    def observe(self, domain: str, html: str) -> None:
        """Feed a page's HTML to learn template patterns.

        Args:
            domain: The domain name (e.g. "example.com").
            html: Raw HTML string of the page.
        """
        if not html or not html.strip():
            return

        try:
            doc = lxml.html.fromstring(html)
        except Exception:
            return

        if domain not in self._domains:
            self._domains[domain] = _DomainObservations()

        obs = self._domains[domain]
        obs.page_count += 1

        # Find body element
        body = self._find_body(doc)
        if body is None:
            return

        # Track which keys we saw on this page
        seen_keys: set[str] = set()

        for child in body:
            if not isinstance(child, HtmlElement):
                continue

            sig = self._compute_signature(child)
            key = sig.key
            seen_keys.add(key)

            obs.element_counts[key].append(sig.child_count)
            obs.element_classes[key].update(sig.classes)
            obs.element_tags[key] = sig.tag

            # Track text content hash for variance detection
            text = (child.text_content() or "").strip()
            text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()[:8]
            obs.text_hashes[key].append(text_hash)

        # For keys NOT seen on this page, record absence (empty child count)
        for key in obs.element_counts:
            if key not in seen_keys:
                # Don't add — absence is captured by len(counts) < page_count
                pass

        # Track class names across the page for noise detection
        for el in doc.iter():
            if not isinstance(el, HtmlElement):
                continue
            classes_str = el.get("class", "")
            if classes_str:
                for cls in classes_str.split():
                    obs.all_class_names[cls] += 1

    def build_profile(self, domain: str) -> SiteProfile:
        """Build a SiteProfile from observed pages.

        Args:
            domain: The domain to build a profile for.

        Returns:
            A SiteProfile with detected template selectors and noise patterns.

        Raises:
            ValueError: If no observations exist for the domain.
        """
        if domain not in self._domains:
            raise ValueError(f"No observations for domain: {domain}")

        obs = self._domains[domain]
        if obs.page_count == 0:
            raise ValueError(f"No valid pages observed for domain: {domain}")

        header_selectors: list[str] = []
        footer_selectors: list[str] = []
        sidebar_selectors: list[str] = []
        main_content_selectors: list[str] = []

        # Identify template elements (appear in >70% of pages)
        template_keys: set[str] = set()
        for key, counts in obs.element_counts.items():
            frequency = len(counts) / obs.page_count
            if frequency >= self.TEMPLATE_THRESHOLD:
                template_keys.add(key)

        # Classify template elements by tag and classes
        for key in template_keys:
            tag = obs.element_tags.get(key, "div")
            classes = obs.element_classes.get(key, set())
            selector = self._build_selector(tag, classes)

            if tag in ("header", "nav") or self._matches_any(classes, {"header", "nav", "navbar", "top-bar"}):
                header_selectors.append(selector)
            elif tag == "footer" or self._matches_any(classes, {"footer", "bottom"}):
                footer_selectors.append(selector)
            elif tag == "aside" or self._matches_any(classes, {"sidebar", "side-nav", "aside"}):
                sidebar_selectors.append(selector)

        # Identify main content area: the template element with MOST text variance
        if obs.page_count >= 2:
            best_variance_key: str | None = None
            best_variance: float = -1.0

            for key in obs.element_counts:
                hashes = obs.text_hashes.get(key, [])
                if len(hashes) < 2:
                    continue
                unique_ratio = len(set(hashes)) / len(hashes)
                if unique_ratio > best_variance:
                    best_variance = unique_ratio
                    best_variance_key = key

            if best_variance_key is not None and best_variance > 0.5:
                tag = obs.element_tags.get(best_variance_key, "div")
                classes = obs.element_classes.get(best_variance_key, set())
                main_content_selectors.append(self._build_selector(tag, classes))

        # Detect noise patterns from common class names
        noise_patterns: list[str] = []
        noise_keywords = {
            "cookie", "consent", "banner", "popup", "modal", "overlay",
            "widget", "social", "share", "subscribe", "newsletter",
            "advertisement", "ad-", "ads-", "sponsor", "promo",
        }
        for cls in obs.all_class_names:
            cls_lower = cls.lower()
            for keyword in noise_keywords:
                if keyword in cls_lower:
                    noise_patterns.append(re.escape(cls))
                    break

        # Compute template signature hash
        sig_parts = sorted(template_keys)
        template_signature = hashlib.sha256(
            "|".join(sig_parts).encode("utf-8"),
        ).hexdigest()[:16]

        profile = SiteProfile(
            site=domain,
            template_signature=template_signature,
            header_selectors=header_selectors,
            footer_selectors=footer_selectors,
            sidebar_selectors=sidebar_selectors,
            main_content_selectors=main_content_selectors,
            noise_patterns=noise_patterns,
        )

        self._profiles[domain] = profile
        return profile

    def save(self, path: str) -> None:
        """Persist learned profiles to disk (JSON).

        Args:
            path: File path to write JSON profiles to.
        """
        data = {
            domain: profile.model_dump()
            for domain, profile in self._profiles.items()
        }
        Path(path).write_text(json.dumps(data, indent=2))

    def load(self, path: str) -> None:
        """Load profiles from disk.

        Args:
            path: File path to read JSON profiles from.

        Raises:
            FileNotFoundError: If the path does not exist.
        """
        raw = json.loads(Path(path).read_text())
        for domain, profile_data in raw.items():
            self._profiles[domain] = SiteProfile(**profile_data)

    def get_profile(self, domain: str) -> SiteProfile | None:
        """Return a previously built or loaded profile, or None."""
        return self._profiles.get(domain)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_body(doc: HtmlElement) -> HtmlElement | None:
        """Find the <body> element in the document."""
        if doc.tag == "body":
            return doc
        bodies = doc.findall(".//body")
        if bodies:
            return bodies[0]
        # lxml sometimes wraps content without explicit body
        return doc

    @staticmethod
    def _compute_signature(el: HtmlElement) -> _ElementSignature:
        """Compute a structural signature for a top-level element."""
        tag = el.tag if isinstance(el.tag, str) else "unknown"
        classes_str = el.get("class", "")
        classes = frozenset(classes_str.split()) if classes_str else frozenset()
        child_count = sum(1 for c in el if isinstance(c, HtmlElement))
        return _ElementSignature(tag=tag, classes=classes, child_count=child_count)

    @staticmethod
    def _build_selector(tag: str, classes: set[str]) -> str:
        """Build a CSS-like selector from tag and classes."""
        if not classes:
            return tag
        # Use the most specific class (longest) to avoid overly broad selectors
        sorted_classes = sorted(classes, key=len, reverse=True)
        primary_class = sorted_classes[0]
        return f"{tag}.{primary_class}"

    @staticmethod
    def _matches_any(classes: set[str], keywords: set[str]) -> bool:
        """Check if any class name contains any keyword."""
        for cls in classes:
            cls_lower = cls.lower()
            for kw in keywords:
                if kw in cls_lower:
                    return True
        return False
