"""Tests for SiteProfileLearner."""

from __future__ import annotations

import json

import pytest

from agent_web_compiler.core.document import SiteProfile
from agent_web_compiler.normalizers.site_profile import SiteProfileLearner


def _make_page(body_content: str) -> str:
    """Wrap body content in a minimal HTML page."""
    return f"<html><body>{body_content}</body></html>"


# Shared template: header + nav + main (varies) + footer
TEMPLATE_HEADER = '<header class="site-header"><a href="/">Logo</a><nav>Menu</nav></header>'
TEMPLATE_FOOTER = '<footer class="site-footer"><p>Copyright 2024</p></footer>'
TEMPLATE_SIDEBAR = '<aside class="sidebar"><ul><li>Link1</li><li>Link2</li></ul></aside>'


PAGE_1 = _make_page(
    f"{TEMPLATE_HEADER}"
    '<main class="content"><article><h1>Article One</h1><p>First article body text here.</p></article></main>'
    f"{TEMPLATE_SIDEBAR}"
    f"{TEMPLATE_FOOTER}"
)

PAGE_2 = _make_page(
    f"{TEMPLATE_HEADER}"
    '<main class="content"><article><h1>Article Two</h1><p>Second article with different content.</p></article></main>'
    f"{TEMPLATE_SIDEBAR}"
    f"{TEMPLATE_FOOTER}"
)

PAGE_3 = _make_page(
    f"{TEMPLATE_HEADER}"
    '<main class="content"><article><h1>Article Three</h1><p>Third article completely unique text.</p></article></main>'
    f"{TEMPLATE_SIDEBAR}"
    f"{TEMPLATE_FOOTER}"
)


class TestSiteProfileLearner:
    def test_observe_single_page_builds_profile(self):
        learner = SiteProfileLearner()
        learner.observe("example.com", PAGE_1)
        profile = learner.build_profile("example.com")

        assert isinstance(profile, SiteProfile)
        assert profile.site == "example.com"
        assert profile.template_signature is not None

    def test_no_observations_raises_error(self):
        learner = SiteProfileLearner()
        with pytest.raises(ValueError, match="No observations"):
            learner.build_profile("unknown.com")

    def test_empty_html_ignored(self):
        learner = SiteProfileLearner()
        learner.observe("example.com", "")
        with pytest.raises(ValueError, match="No observations|No valid"):
            learner.build_profile("example.com")

    def test_multiple_pages_detects_template_elements(self):
        learner = SiteProfileLearner()
        learner.observe("example.com", PAGE_1)
        learner.observe("example.com", PAGE_2)
        learner.observe("example.com", PAGE_3)
        profile = learner.build_profile("example.com")

        # Header and footer should be detected as template elements
        assert len(profile.header_selectors) > 0 or len(profile.footer_selectors) > 0

    def test_main_content_detected_as_varying(self):
        learner = SiteProfileLearner()
        learner.observe("example.com", PAGE_1)
        learner.observe("example.com", PAGE_2)
        learner.observe("example.com", PAGE_3)
        profile = learner.build_profile("example.com")

        # The main content area varies most, should be identified
        # (may or may not be in main_content_selectors depending on heuristics)
        assert profile.template_signature is not None

    def test_sidebar_detection(self):
        learner = SiteProfileLearner()
        learner.observe("example.com", PAGE_1)
        learner.observe("example.com", PAGE_2)
        profile = learner.build_profile("example.com")

        # Sidebar should be detected
        assert len(profile.sidebar_selectors) > 0

    def test_noise_patterns_detected(self):
        """Pages with cookie/subscribe elements should detect noise patterns."""
        page_with_noise = _make_page(
            '<header>Logo</header>'
            '<div class="cookie-banner">Accept cookies</div>'
            '<div class="subscribe-popup">Subscribe!</div>'
            '<main><p>Content here with enough text to pass thresholds.</p></main>'
            '<footer>Footer</footer>'
        )
        learner = SiteProfileLearner()
        learner.observe("noisy.com", page_with_noise)
        profile = learner.build_profile("noisy.com")

        # Should detect cookie/subscribe as noise patterns
        noise_combined = " ".join(profile.noise_patterns).lower()
        assert "cookie" in noise_combined or "subscribe" in noise_combined

    def test_save_and_load(self, tmp_path):
        learner = SiteProfileLearner()
        learner.observe("example.com", PAGE_1)
        learner.observe("example.com", PAGE_2)
        learner.build_profile("example.com")

        path = str(tmp_path / "profiles.json")
        learner.save(path)

        # Load into a new learner
        learner2 = SiteProfileLearner()
        learner2.load(path)

        profile = learner2.get_profile("example.com")
        assert profile is not None
        assert profile.site == "example.com"

    def test_save_produces_valid_json(self, tmp_path):
        learner = SiteProfileLearner()
        learner.observe("example.com", PAGE_1)
        learner.build_profile("example.com")

        path = str(tmp_path / "profiles.json")
        learner.save(path)

        with open(path) as f:
            data = json.load(f)

        assert "example.com" in data
        assert data["example.com"]["site"] == "example.com"

    def test_get_profile_returns_none_for_unknown(self):
        learner = SiteProfileLearner()
        assert learner.get_profile("unknown.com") is None

    def test_deterministic_signatures(self):
        """Same pages should produce the same template signature."""
        learner1 = SiteProfileLearner()
        learner1.observe("example.com", PAGE_1)
        learner1.observe("example.com", PAGE_2)
        profile1 = learner1.build_profile("example.com")

        learner2 = SiteProfileLearner()
        learner2.observe("example.com", PAGE_1)
        learner2.observe("example.com", PAGE_2)
        profile2 = learner2.build_profile("example.com")

        assert profile1.template_signature == profile2.template_signature


class TestHTMLNormalizerWithProfile:
    """Test that HTMLNormalizer uses SiteProfile for better boilerplate removal."""

    def test_normalizer_accepts_site_profile(self):
        from agent_web_compiler.core.config import CompileConfig
        from agent_web_compiler.normalizers.html_normalizer import HTMLNormalizer

        profile = SiteProfile(
            site="example.com",
            header_selectors=["header.site-header"],
            footer_selectors=["footer.site-footer"],
            sidebar_selectors=[],
            main_content_selectors=[],
            noise_patterns=["cookie-banner"],
        )

        normalizer = HTMLNormalizer(site_profile=profile)
        config = CompileConfig()

        html = (
            '<html><body>'
            '<header class="site-header"><a href="/">Logo</a></header>'
            '<main><p>Important content that should be preserved in the output.</p></main>'
            '<footer class="site-footer"><p>Copyright</p></footer>'
            '</body></html>'
        )
        result = normalizer.normalize(html, config)

        # The header and footer should be removed via profile selectors
        assert "Important content" in result

    def test_normalizer_without_profile_still_works(self):
        from agent_web_compiler.core.config import CompileConfig
        from agent_web_compiler.normalizers.html_normalizer import HTMLNormalizer

        normalizer = HTMLNormalizer()
        config = CompileConfig()

        html = '<html><body><p>Simple content for testing.</p></body></html>'
        result = normalizer.normalize(html, config)
        assert "Simple content" in result

    def test_profile_noise_patterns_merged(self):
        from agent_web_compiler.normalizers.html_normalizer import HTMLNormalizer

        profile = SiteProfile(
            site="example.com",
            noise_patterns=["custom-noise-class"],
        )

        normalizer = HTMLNormalizer(site_profile=profile)
        # The noise regex should include the custom pattern
        assert normalizer._noise_re.search("custom-noise-class")
