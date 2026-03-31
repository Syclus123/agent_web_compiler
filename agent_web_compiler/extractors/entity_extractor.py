"""Entity extraction — identifies structured data within block text.

Extracts dates, prices, emails, URLs, phone numbers, percentages, and
numbers with units using pure regex patterns. No external dependencies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from agent_web_compiler.core.block import Block


@dataclass
class Entity:
    """A structured entity found in text."""

    type: str  # "date", "price", "email", "url", "phone", "number_with_unit", "percentage"
    value: str
    normalized: str | None = None  # e.g. "2026-03-31" for dates
    start: int = 0  # char offset in source text
    end: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for storage in block metadata."""
        d: dict[str, Any] = {
            "type": self.type,
            "value": self.value,
            "start": self.start,
            "end": self.end,
        }
        if self.normalized is not None:
            d["normalized"] = self.normalized
        return d


# ------------------------------------------------------------------ #
# Regex patterns
# ------------------------------------------------------------------ #

_MONTH_NAMES = (
    "January|February|March|April|May|June"
    "|July|August|September|October|November|December"
)
_MONTH_ABBR = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"

_MONTH_NUM: dict[str, str] = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "jun": "06", "jul": "07", "aug": "08", "sep": "09",
    "oct": "10", "nov": "11", "dec": "12",
}

# "March 15, 2026" or "Mar 15, 2026" or "March 15 2026" or "Mar 15"
_DATE_LONG_RE = re.compile(
    rf"\b({_MONTH_NAMES}|{_MONTH_ABBR})\s+(\d{{1,2}})(?:,?\s+(\d{{4}}))?\b",
    re.IGNORECASE,
)
# "2026-03-15"
_DATE_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
# "15/03/2026" or "03/15/2026"
_DATE_SLASH_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")

# "$99.99", "€50", "¥1000", "$1,299.00"
_PRICE_RE = re.compile(r"[$€£¥]\s?\d[\d,]*(?:\.\d{1,2})?")

# Standard email
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# URLs — http/https only
_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")

# Phone numbers: (555) 123-4567, +1-555-123-4567, 555.123.4567, etc.
_PHONE_RE = re.compile(
    r"(?:\+\d{1,3}[-.\s]?)?"             # optional country code
    r"(?:\(?\d{2,4}\)?[-.\s])?"           # optional area code (with or without parens)
    r"\d{2,4}[-.\s]\d{3,4}(?:[-.\s]\d{3,4})?"  # main number
)

# Percentages: "85%", "92.5%"
_PERCENT_RE = re.compile(r"\b\d+(?:\.\d+)?%")

# Numbers with units: "40mm", "30 hours", "250g", "1,000 requests"
_NUMBER_UNIT_RE = re.compile(
    r"\b\d[\d,]*(?:\.\d+)?\s?"
    r"(?:mm|cm|m|km|in|ft|yd|mi|mg|g|kg|lb|oz|ml|l|L"
    r"|px|pt|em|rem|GB|MB|KB|TB"
    r"|hours?|hrs?|minutes?|mins?|seconds?|secs?"
    r"|days?|weeks?|months?|years?"
    r"|requests?|items?|users?|pages?|files?|bytes?)\b"
)


class EntityExtractor:
    """Extracts structured entities from text using regex patterns.

    Thread-safe and stateless — all patterns are module-level compiled regexes.
    """

    def extract_entities(self, text: str) -> list[Entity]:
        """Extract all recognized entities from *text*.

        Returns entities sorted by start offset. Overlapping matches are
        kept (callers can de-duplicate if needed).
        """
        entities: list[Entity] = []

        # Dates — long form
        for m in _DATE_LONG_RE.finditer(text):
            month_str = m.group(1).lower()
            day = m.group(2).zfill(2)
            year = m.group(3)
            month = _MONTH_NUM.get(month_str, "01")
            normalized: str | None = None
            if year:
                normalized = f"{year}-{month}-{day}"
            entities.append(Entity(
                type="date", value=m.group(), normalized=normalized,
                start=m.start(), end=m.end(),
            ))

        # Dates — ISO
        for m in _DATE_ISO_RE.finditer(text):
            entities.append(Entity(
                type="date", value=m.group(),
                normalized=m.group(),
                start=m.start(), end=m.end(),
            ))

        # Dates — slash
        for m in _DATE_SLASH_RE.finditer(text):
            entities.append(Entity(
                type="date", value=m.group(), normalized=None,
                start=m.start(), end=m.end(),
            ))

        # Prices
        for m in _PRICE_RE.finditer(text):
            entities.append(Entity(
                type="price", value=m.group(), start=m.start(), end=m.end(),
            ))

        # Emails
        for m in _EMAIL_RE.finditer(text):
            entities.append(Entity(
                type="email", value=m.group(), normalized=m.group().lower(),
                start=m.start(), end=m.end(),
            ))

        # URLs
        for m in _URL_RE.finditer(text):
            entities.append(Entity(
                type="url", value=m.group(), start=m.start(), end=m.end(),
            ))

        # Phones
        for m in _PHONE_RE.finditer(text):
            entities.append(Entity(
                type="phone", value=m.group(), start=m.start(), end=m.end(),
            ))

        # Percentages
        for m in _PERCENT_RE.finditer(text):
            entities.append(Entity(
                type="percentage", value=m.group(), start=m.start(), end=m.end(),
            ))

        # Numbers with units
        for m in _NUMBER_UNIT_RE.finditer(text):
            entities.append(Entity(
                type="number_with_unit", value=m.group(),
                start=m.start(), end=m.end(),
            ))

        entities.sort(key=lambda e: e.start)
        return entities

    def annotate_blocks(self, blocks: list[Block]) -> list[Block]:
        """Extract entities for each block and store in metadata["entities"].

        Returns a new list — input blocks are not mutated.
        """
        result: list[Block] = []
        for block in blocks:
            entities = self.extract_entities(block.text)
            if entities:
                new_meta = dict(block.metadata)
                new_meta["entities"] = [e.to_dict() for e in entities]
                result.append(block.model_copy(update={"metadata": new_meta}))
            else:
                result.append(block)
        return result
