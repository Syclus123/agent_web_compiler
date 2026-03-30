"""Text utilities for cleaning, truncating, and extracting text."""

from __future__ import annotations

import re

from lxml import html as lxml_html


def clean_whitespace(text: str) -> str:
    """Normalize whitespace: collapse runs of whitespace to a single space and strip.

    Args:
        text: Input text.

    Returns:
        Text with collapsed whitespace and leading/trailing whitespace removed.
    """
    return re.sub(r"\s+", " ", text).strip()


def truncate(text: str, max_length: int = 500, suffix: str = "...") -> str:
    """Truncate text to max_length, adding suffix if truncated.

    If the text is already within max_length, it is returned unchanged.
    When truncated, the result including the suffix will not exceed max_length.

    Args:
        text: Input text.
        max_length: Maximum length of the returned string (including suffix).
        suffix: String appended when text is truncated.

    Returns:
        The original text if short enough, otherwise truncated with suffix.
    """
    if len(text) <= max_length:
        return text
    if max_length <= len(suffix):
        return suffix[:max_length]
    return text[: max_length - len(suffix)] + suffix


def count_tokens_approx(text: str) -> int:
    """Approximate token count using words * 1.3.

    This is a rough heuristic for English text. For accurate counts,
    use a proper tokenizer.

    Args:
        text: Input text.

    Returns:
        Estimated token count (always >= 0).
    """
    if not text or not text.strip():
        return 0
    word_count = len(text.split())
    return max(1, int(word_count * 1.3))


def extract_text_from_html(html: str) -> str:
    """Extract plain text from an HTML string using lxml.

    Strips all tags and returns clean text with normalized whitespace.

    Args:
        html: Raw HTML string.

    Returns:
        Plain text extracted from the HTML.
    """
    if not html or not html.strip():
        return ""
    try:
        doc = lxml_html.fromstring(html)
    except Exception:
        # If lxml cannot parse the input, return empty string rather than crash.
        return ""
    raw_text = doc.text_content()
    return clean_whitespace(raw_text)
