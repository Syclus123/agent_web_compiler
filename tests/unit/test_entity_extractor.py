"""Tests for EntityExtractor — structured entity extraction from block text."""

from __future__ import annotations

from agent_web_compiler.core.block import Block, BlockType
from agent_web_compiler.extractors.entity_extractor import Entity, EntityExtractor

# --------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------- #

def _block(text: str, order: int = 0) -> Block:
    return Block(
        id=f"b_{order:03d}",
        type=BlockType.PARAGRAPH,
        text=text,
        order=order,
    )


# --------------------------------------------------------------------- #
# Date extraction
# --------------------------------------------------------------------- #

class TestDateExtraction:
    def test_long_date(self) -> None:
        ext = EntityExtractor()
        entities = ext.extract_entities("Published on March 15, 2026")
        dates = [e for e in entities if e.type == "date"]
        assert len(dates) == 1
        assert dates[0].value == "March 15, 2026"
        assert dates[0].normalized == "2026-03-15"

    def test_abbreviated_month(self) -> None:
        ext = EntityExtractor()
        entities = ext.extract_entities("Updated Jan 5, 2025")
        dates = [e for e in entities if e.type == "date"]
        assert len(dates) == 1
        assert dates[0].normalized == "2025-01-05"

    def test_iso_date(self) -> None:
        ext = EntityExtractor()
        entities = ext.extract_entities("Date: 2026-03-31")
        dates = [e for e in entities if e.type == "date"]
        assert len(dates) == 1
        assert dates[0].normalized == "2026-03-31"

    def test_slash_date(self) -> None:
        ext = EntityExtractor()
        entities = ext.extract_entities("Filed on 15/03/2026")
        dates = [e for e in entities if e.type == "date"]
        assert len(dates) == 1
        assert dates[0].value == "15/03/2026"

    def test_month_day_without_year(self) -> None:
        ext = EntityExtractor()
        entities = ext.extract_entities("Sale starts Mar 15")
        dates = [e for e in entities if e.type == "date"]
        assert len(dates) == 1
        assert dates[0].normalized is None  # no year


# --------------------------------------------------------------------- #
# Price extraction
# --------------------------------------------------------------------- #

class TestPriceExtraction:
    def test_dollar(self) -> None:
        ext = EntityExtractor()
        entities = ext.extract_entities("Price: $99.99")
        prices = [e for e in entities if e.type == "price"]
        assert len(prices) == 1
        assert prices[0].value == "$99.99"

    def test_euro(self) -> None:
        ext = EntityExtractor()
        entities = ext.extract_entities("Cost: €50")
        prices = [e for e in entities if e.type == "price"]
        assert len(prices) == 1
        assert prices[0].value == "€50"

    def test_comma_separated(self) -> None:
        ext = EntityExtractor()
        entities = ext.extract_entities("Total: $1,299.00")
        prices = [e for e in entities if e.type == "price"]
        assert len(prices) == 1
        assert prices[0].value == "$1,299.00"


# --------------------------------------------------------------------- #
# Email extraction
# --------------------------------------------------------------------- #

class TestEmailExtraction:
    def test_basic_email(self) -> None:
        ext = EntityExtractor()
        entities = ext.extract_entities("Contact: user@example.com")
        emails = [e for e in entities if e.type == "email"]
        assert len(emails) == 1
        assert emails[0].value == "user@example.com"
        assert emails[0].normalized == "user@example.com"

    def test_complex_email(self) -> None:
        ext = EntityExtractor()
        entities = ext.extract_entities("Email: john.doe+tag@company.co.uk")
        emails = [e for e in entities if e.type == "email"]
        assert len(emails) == 1


# --------------------------------------------------------------------- #
# URL extraction
# --------------------------------------------------------------------- #

class TestURLExtraction:
    def test_https_url(self) -> None:
        ext = EntityExtractor()
        entities = ext.extract_entities("Visit https://example.com/page")
        urls = [e for e in entities if e.type == "url"]
        assert len(urls) == 1
        assert urls[0].value == "https://example.com/page"

    def test_http_url(self) -> None:
        ext = EntityExtractor()
        entities = ext.extract_entities("See http://legacy.test/path?q=1")
        urls = [e for e in entities if e.type == "url"]
        assert len(urls) == 1


# --------------------------------------------------------------------- #
# Phone extraction
# --------------------------------------------------------------------- #

class TestPhoneExtraction:
    def test_us_phone(self) -> None:
        ext = EntityExtractor()
        entities = ext.extract_entities("Call (555) 123-4567")
        phones = [e for e in entities if e.type == "phone"]
        assert len(phones) == 1

    def test_intl_phone(self) -> None:
        ext = EntityExtractor()
        entities = ext.extract_entities("Phone: +1-555-123-4567")
        phones = [e for e in entities if e.type == "phone"]
        assert len(phones) == 1


# --------------------------------------------------------------------- #
# Percentage and number-with-unit extraction
# --------------------------------------------------------------------- #

class TestPercentageExtraction:
    def test_integer_percent(self) -> None:
        ext = EntityExtractor()
        entities = ext.extract_entities("Accuracy: 85%")
        pcts = [e for e in entities if e.type == "percentage"]
        assert len(pcts) == 1
        assert pcts[0].value == "85%"

    def test_decimal_percent(self) -> None:
        ext = EntityExtractor()
        entities = ext.extract_entities("Growth rate: 92.5%")
        pcts = [e for e in entities if e.type == "percentage"]
        assert len(pcts) == 1
        assert pcts[0].value == "92.5%"


class TestNumberWithUnit:
    def test_millimeters(self) -> None:
        ext = EntityExtractor()
        entities = ext.extract_entities("Thickness: 40mm")
        nums = [e for e in entities if e.type == "number_with_unit"]
        assert len(nums) == 1
        assert nums[0].value == "40mm"

    def test_hours(self) -> None:
        ext = EntityExtractor()
        entities = ext.extract_entities("Estimated: 30 hours")
        nums = [e for e in entities if e.type == "number_with_unit"]
        assert len(nums) == 1

    def test_weight(self) -> None:
        ext = EntityExtractor()
        entities = ext.extract_entities("Weight: 250g")
        nums = [e for e in entities if e.type == "number_with_unit"]
        assert len(nums) == 1


# --------------------------------------------------------------------- #
# Mixed text and block annotation
# --------------------------------------------------------------------- #

class TestMixedExtraction:
    def test_multiple_entities_in_text(self) -> None:
        ext = EntityExtractor()
        text = "On March 15, 2026, the product costs $99.99. Contact sales@co.com."
        entities = ext.extract_entities(text)
        types = {e.type for e in entities}
        assert "date" in types
        assert "price" in types
        assert "email" in types

    def test_sorted_by_start(self) -> None:
        ext = EntityExtractor()
        text = "Price: $50, email: a@b.com, date: 2026-01-01"
        entities = ext.extract_entities(text)
        starts = [e.start for e in entities]
        assert starts == sorted(starts)


class TestAnnotateBlocks:
    def test_entities_added_to_metadata(self) -> None:
        ext = EntityExtractor()
        blocks = [
            _block("The price is $49.99", order=0),
            _block("No entities here just text", order=1),
        ]
        result = ext.annotate_blocks(blocks)
        assert len(result) == 2
        assert "entities" in result[0].metadata
        assert len(result[0].metadata["entities"]) >= 1
        assert result[0].metadata["entities"][0]["type"] == "price"
        # Block without entities should not have the key
        assert "entities" not in result[1].metadata

    def test_original_blocks_not_mutated(self) -> None:
        ext = EntityExtractor()
        original = _block("Cost: $10", order=0)
        original_meta = dict(original.metadata)
        ext.annotate_blocks([original])
        assert original.metadata == original_meta

    def test_entity_to_dict(self) -> None:
        e = Entity(type="price", value="$10", normalized=None, start=0, end=3)
        d = e.to_dict()
        assert d["type"] == "price"
        assert d["value"] == "$10"
        assert "normalized" not in d  # None should be excluded

    def test_entity_to_dict_with_normalized(self) -> None:
        e = Entity(type="date", value="2026-01-01", normalized="2026-01-01", start=0, end=10)
        d = e.to_dict()
        assert d["normalized"] == "2026-01-01"


class TestEmptyInput:
    def test_empty_text(self) -> None:
        ext = EntityExtractor()
        assert ext.extract_entities("") == []

    def test_empty_blocks(self) -> None:
        ext = EntityExtractor()
        assert ext.annotate_blocks([]) == []
