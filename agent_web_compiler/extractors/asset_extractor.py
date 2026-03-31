"""Asset extractor — finds referenced assets (images, stylesheets, etc.) in HTML."""

from __future__ import annotations

import lxml.html
from lxml.html import HtmlElement

from agent_web_compiler.core.document import Asset


class AssetExtractor:
    """Extracts referenced assets from HTML content.

    Finds images, stylesheets, scripts, and fonts referenced in the document.
    """

    def extract(self, html: str) -> list[Asset]:
        """Extract assets from HTML.

        Args:
            html: Raw or normalized HTML string.

        Returns:
            List of Asset objects found in the document.
        """
        if not html or not html.strip():
            return []

        root = lxml.html.fromstring(html)
        assets: list[Asset] = []
        order = 0

        # --- Images ---
        for img in root.iter("img"):
            if not isinstance(img, HtmlElement):
                continue
            src = img.get("src")
            if not src:
                continue
            alt = img.get("alt")
            assets.append(
                Asset(
                    id=f"asset_{order:03d}",
                    type="image",
                    url=src,
                    alt=alt,
                )
            )
            order += 1

        # --- Stylesheets ---
        for link in root.iter("link"):
            if not isinstance(link, HtmlElement):
                continue
            rel = (link.get("rel") or "").lower()
            if "stylesheet" in rel:
                href = link.get("href")
                if href:
                    assets.append(
                        Asset(
                            id=f"asset_{order:03d}",
                            type="stylesheet",
                            url=href,
                            mime_type=link.get("type"),
                        )
                    )
                    order += 1

        # --- Scripts ---
        for script in root.iter("script"):
            if not isinstance(script, HtmlElement):
                continue
            src = script.get("src")
            if src:
                assets.append(
                    Asset(
                        id=f"asset_{order:03d}",
                        type="script",
                        url=src,
                        mime_type=script.get("type"),
                    )
                )
                order += 1

        return assets
