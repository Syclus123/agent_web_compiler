"""DOM utilities for working with lxml elements."""

from __future__ import annotations

import re
from typing import Any

from lxml.html import HtmlElement


def build_css_path(element: HtmlElement) -> str:
    """Build a CSS selector path for an lxml element.

    Walks from the element up to the root, building a selector like
    ``html > body > div:nth-child(2) > p:nth-child(1)``.

    Args:
        element: An lxml HTML element.

    Returns:
        A CSS selector string that uniquely identifies the element in its tree.
    """
    parts: list[str] = []
    current: Any = element

    while current is not None:
        if not hasattr(current, "tag") or not isinstance(current.tag, str):
            break

        tag = current.tag
        parent = current.getparent()

        if parent is not None:
            # Count position among same-tag siblings (1-indexed for nth-child).
            siblings = [
                child for child in parent if isinstance(child.tag, str) and child.tag == tag
            ]
            if len(siblings) > 1:
                index = siblings.index(current) + 1
                tag = f"{tag}:nth-child({index})"

        parts.append(tag)
        current = parent

    parts.reverse()
    return " > ".join(parts)


def get_element_text(element: HtmlElement) -> str:
    """Get clean text content from an lxml element.

    Extracts all text (including tail text of children), collapses whitespace,
    and strips leading/trailing whitespace.

    Args:
        element: An lxml HTML element.

    Returns:
        Clean text content of the element.
    """
    raw = element.text_content()
    return re.sub(r"\s+", " ", raw).strip()


def get_element_attrs(element: HtmlElement) -> dict[str, str]:
    """Get all attributes of an lxml element as a dict.

    Args:
        element: An lxml HTML element.

    Returns:
        Dictionary mapping attribute names to their string values.
    """
    return dict(element.attrib)


def is_visible(element: HtmlElement) -> bool:
    """Check if an element is likely visible based on tag and attributes.

    This is a heuristic check based on the element's ``style`` attribute,
    ``hidden`` attribute, and ``type`` attribute. It does **not** evaluate
    external CSS stylesheets or JavaScript.

    Args:
        element: An lxml HTML element.

    Returns:
        False if the element is likely hidden, True otherwise.
    """
    # Check the HTML hidden attribute.
    if element.get("hidden") is not None:
        return False

    # Check for input type="hidden".
    if element.tag == "input" and element.get("type", "").lower() == "hidden":
        return False

    # Check inline style for display:none or visibility:hidden.
    style = element.get("style", "")
    if style:
        style_lower = style.lower().replace(" ", "")
        if "display:none" in style_lower:
            return False
        if "visibility:hidden" in style_lower:
            return False

    return True
