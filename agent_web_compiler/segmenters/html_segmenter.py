"""HTML segmenter — splits cleaned HTML into typed semantic blocks."""

from __future__ import annotations

import re
from typing import Any

import lxml.html
from lxml.html import HtmlElement

from agent_web_compiler.core.block import Block, BlockType
from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.core.provenance import DOMProvenance, Provenance


class HTMLSegmenter:
    """Segments HTML into typed semantic blocks.

    Walks the DOM tree in document order and produces a flat list of
    :class:`Block` objects with heading-based section paths, importance
    scores, and DOM provenance.
    """

    HEADING_TAGS: set[str] = {"h1", "h2", "h3", "h4", "h5", "h6"}
    LIST_TAGS: set[str] = {"ul", "ol", "dl"}
    TABLE_TAG: str = "table"
    CODE_TAGS: set[str] = {"pre", "code"}
    QUOTE_TAG: str = "blockquote"
    FIGURE_TAGS: set[str] = {"figure", "figcaption"}

    # Importance scores by block type.
    _IMPORTANCE: dict[BlockType, float] = {
        BlockType.HEADING: 0.9,
        BlockType.PARAGRAPH: 0.7,
        BlockType.TABLE: 0.8,
        BlockType.CODE: 0.7,
        BlockType.LIST: 0.6,
        BlockType.QUOTE: 0.5,
        BlockType.FIGURE_CAPTION: 0.6,
        BlockType.IMAGE: 0.5,
    }

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def segment(self, html: str, config: CompileConfig) -> list[Block]:
        """Parse *html* into a list of semantic blocks.

        Args:
            html: Cleaned HTML string to segment.
            config: Compilation configuration controlling provenance,
                raw-HTML inclusion, etc.

        Returns:
            Ordered list of :class:`Block` objects.
        """
        if not html or not html.strip():
            return []

        root = lxml.html.fromstring(html)
        blocks: list[Block] = []
        # heading_stack entries: (level, heading_text)
        heading_stack: list[tuple[int, str]] = []
        order = 0

        for element in root.iter():
            if not isinstance(element, HtmlElement):
                continue

            tag = element.tag.lower() if isinstance(element.tag, str) else None
            if tag is None:
                continue

            # Skip hidden elements (display:none, visibility:hidden, aria-hidden, hidden attr)
            if self._is_hidden(element):
                continue

            block_type = self._classify(element, tag)
            if block_type is None:
                continue

            # Skip elements whose ancestor was already captured as a block
            # (e.g. <code> inside <pre>, <li> inside <ul>).
            if self._is_nested_duplicate(element, tag, block_type):
                continue

            text = (element.text_content() or "").strip()
            # For images: use alt text since text_content is empty
            if block_type is BlockType.IMAGE:
                alt = element.get("alt", "")
                text = alt.strip() if alt else "[Image]"
            # Collapse whitespace for non-code blocks
            elif block_type is BlockType.CODE:
                # For code: preserve structure but strip leading/trailing
                text = text.strip()
            elif block_type is BlockType.LIST:
                # For lists: extract items properly
                items = self._extract_list_items(element)
                text = "\n".join(items) if items else re.sub(r"\s+", " ", text).strip()
            elif block_type is BlockType.TABLE:
                # For tables: use clean text (structured data goes in metadata)
                text = re.sub(r"\s+", " ", text).strip()
            else:
                text = re.sub(r"\s+", " ", text).strip()
            if not text:
                continue

            # -- heading stack maintenance --------------------------------
            if block_type is BlockType.HEADING:
                level = int(tag[1])  # 'h1' -> 1
                # Pop headings at same or deeper level.
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, text))
            else:
                level = None

            section_path = [h[1] for h in heading_stack]

            # -- metadata -------------------------------------------------
            metadata: dict[str, Any] = {}
            if block_type is BlockType.HEADING and level is not None:
                metadata["level"] = level

            if block_type is BlockType.TABLE:
                row_count, col_count = self._table_dimensions(element)
                metadata["row_count"] = row_count
                metadata["col_count"] = col_count
                headers, rows = self._extract_table_data(element)
                if headers:
                    metadata["headers"] = headers
                if rows is not None:
                    metadata["rows"] = rows

            if block_type is BlockType.CODE:
                lang = self._detect_code_language(element)
                if lang:
                    metadata["language"] = lang

            # -- provenance -----------------------------------------------
            provenance: Provenance | None = None
            if config.include_provenance:
                dom_path = self._css_path(element)
                provenance = Provenance(
                    dom=DOMProvenance(
                        dom_path=dom_path,
                        element_tag=tag,
                        element_id=element.get("id"),
                        element_classes=(element.get("class") or "").split()
                        if element.get("class")
                        else [],
                    ),
                    raw_html=lxml.html.tostring(element, encoding="unicode")
                    if config.include_raw_html
                    else None,
                )

            block_html: str | None = None
            if config.include_raw_html:
                block_html = lxml.html.tostring(element, encoding="unicode")

            block = Block(
                id=f"b_{order:03d}",
                type=block_type,
                text=text,
                html=block_html,
                section_path=section_path,
                order=order,
                importance=self._IMPORTANCE.get(block_type, 0.5),
                level=level,
                metadata=metadata,
                provenance=provenance,
            )
            blocks.append(block)
            order += 1

        return blocks

    # ------------------------------------------------------------------ #
    # Visibility helpers
    # ------------------------------------------------------------------ #

    _HIDDEN_STYLE_RE = re.compile(
        r"display\s*:\s*none|visibility\s*:\s*hidden", re.IGNORECASE,
    )

    @classmethod
    def _is_hidden(cls, element: HtmlElement) -> bool:
        """Return True if element or any ancestor is hidden.

        Checks: style="display:none", style="visibility:hidden",
        hidden attribute, aria-hidden="true".
        """
        el: HtmlElement | None = element
        while el is not None:
            if not isinstance(el, HtmlElement):
                break
            # hidden attribute
            if el.get("hidden") is not None:
                return True
            # aria-hidden
            if el.get("aria-hidden", "").lower() == "true":
                return True
            # inline style
            style = el.get("style", "")
            if style and cls._HIDDEN_STYLE_RE.search(style):
                return True
            el = el.getparent()
        return False

    # ------------------------------------------------------------------ #
    # Classification helpers
    # ------------------------------------------------------------------ #

    def _classify(self, element: HtmlElement, tag: str) -> BlockType | None:
        """Return the :class:`BlockType` for *element*, or ``None`` to skip."""
        if tag in self.HEADING_TAGS:
            return BlockType.HEADING
        if tag == "p":
            return BlockType.PARAGRAPH
        if tag in self.LIST_TAGS:
            return BlockType.LIST
        if tag == self.TABLE_TAG:
            return BlockType.TABLE
        if tag in self.CODE_TAGS:
            return BlockType.CODE
        if tag == self.QUOTE_TAG:
            return BlockType.QUOTE
        if tag in self.FIGURE_TAGS:
            return BlockType.FIGURE_CAPTION
        if tag == "img":
            return BlockType.IMAGE
        if tag == "details":
            return BlockType.FAQ
        return None

    def _is_nested_duplicate(
        self, element: HtmlElement, tag: str, block_type: BlockType
    ) -> bool:
        """Return ``True`` when *element* is inside an ancestor already captured.

        Avoids double-counting, e.g. ``<code>`` inside ``<pre>``,
        ``<figcaption>`` inside ``<figure>``, or nested ``<ul>/<ol>``
        inside a parent list.
        """
        if tag == "code":
            parent = element.getparent()
            if parent is not None and parent.tag == "pre":
                return True
        if tag in ("figcaption",):
            parent = element.getparent()
            if parent is not None and parent.tag == "figure":
                return True
        # Nested lists: a <ul>/<ol>/<dl> inside an <li> of another list
        if tag in ("ul", "ol", "dl"):
            ancestor = element.getparent()
            while ancestor is not None:
                if isinstance(ancestor, HtmlElement) and ancestor.tag in ("ul", "ol", "dl"):
                    return True
                ancestor = ancestor.getparent()
        return False

    # ------------------------------------------------------------------ #
    # Metadata helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _table_dimensions(table: HtmlElement) -> tuple[int, int]:
        """Return ``(row_count, col_count)`` for a ``<table>`` element.

        Accounts for ``colspan`` attributes when counting columns and
        ``rowspan`` when counting unique rows.
        """
        rows = table.findall(".//tr")
        # Count unique rows by deduplicating (handles rowspan conceptually —
        # the actual row count is the number of <tr> elements).
        row_count = len(rows)
        col_count = 0
        if rows:
            first_row = rows[0]
            cells = first_row.findall("td") + first_row.findall("th")
            for cell in cells:
                try:
                    col_count += int(cell.get("colspan", "1"))
                except (ValueError, TypeError):
                    col_count += 1
        return row_count, col_count

    @staticmethod
    def _extract_table_data(table: HtmlElement) -> tuple[list[str] | None, list[list[str]] | None]:
        """Extract structured headers and rows from a table element.

        Handles:
        - Tables with <thead> and <tbody> sections
        - Tables with no <tr> (raw text in table)
        - Tables with mixed th/td in data rows
        """
        # First try to extract from thead/tbody structure
        thead = table.find(".//thead")
        tbody = table.find(".//tbody")

        headers: list[str] | None = None
        data_rows: list[list[str]] = []

        if thead is not None:
            header_rows = thead.findall("tr")
            if header_rows:
                ths = header_rows[0].findall("th")
                if not ths:
                    ths = header_rows[0].findall("td")
                if ths:
                    headers = [
                        re.sub(r"\s+", " ", (th.text_content() or "")).strip() for th in ths
                    ]

        # Get body rows from tbody if present, otherwise all rows
        if tbody is not None:
            body_rows = tbody.findall("tr")
        else:
            body_rows = table.findall(".//tr")

        for i, row in enumerate(body_rows):
            ths = row.findall("th")
            tds = row.findall("td")

            # If we already got headers from thead, skip header detection
            if headers is not None:
                # Collect all cells (mixed th/td)
                cells = tds + ths if tds else ths
                if cells:
                    data_rows.append(
                        [re.sub(r"\s+", " ", (c.text_content() or "")).strip() for c in cells]
                    )
            elif ths and not tds and i == 0:
                # First row with only <th> — treat as headers
                headers = [
                    re.sub(r"\s+", " ", (th.text_content() or "")).strip() for th in ths
                ]
            elif tds:
                # Data row — include any mixed th cells too
                all_cells = list(row)
                cells = [
                    c for c in all_cells
                    if isinstance(c, HtmlElement) and c.tag in ("td", "th")
                ]
                data_rows.append(
                    [re.sub(r"\s+", " ", (c.text_content() or "")).strip() for c in cells]
                )
            elif ths and i > 0:
                # Later header-only rows treated as data
                data_rows.append(
                    [re.sub(r"\s+", " ", (th.text_content() or "")).strip() for th in ths]
                )

        return headers, data_rows if data_rows else None

    @staticmethod
    def _extract_list_items(list_el: HtmlElement) -> list[str]:
        """Extract individual list item texts from a ul/ol/dl.

        For ``<dl>`` elements, ``<dt>``/``<dd>`` pairs are merged into
        a single ``"term: definition"`` string.
        """
        if list_el.tag == "dl":
            return HTMLSegmenter._extract_dl_items(list_el)

        items: list[str] = []
        for child in list_el:
            if not isinstance(child, HtmlElement):
                continue
            if child.tag == "li":
                # Get only the direct text, not text from nested sub-lists
                parts: list[str] = []
                if child.text and child.text.strip():
                    parts.append(child.text.strip())
                for sub in child:
                    if isinstance(sub, HtmlElement) and sub.tag not in ("ul", "ol", "dl"):
                        sub_text = (sub.text_content() or "").strip()
                        if sub_text:
                            parts.append(sub_text)
                    if sub.tail and sub.tail.strip():
                        parts.append(sub.tail.strip())
                item_text = re.sub(r"\s+", " ", " ".join(parts)).strip()
                if item_text:
                    items.append(item_text)
        return items

    @staticmethod
    def _extract_dl_items(dl_el: HtmlElement) -> list[str]:
        """Extract dt/dd pairs from a definition list as 'term: definition'."""
        items: list[str] = []
        current_dt: str = ""
        for child in dl_el:
            if not isinstance(child, HtmlElement):
                continue
            text = re.sub(r"\s+", " ", (child.text_content() or "")).strip()
            if child.tag == "dt":
                current_dt = text
            elif child.tag == "dd":
                if current_dt:
                    items.append(f"{current_dt}: {text}")
                else:
                    items.append(text)
                current_dt = ""
        # Leftover dt without dd
        if current_dt:
            items.append(current_dt)
        return items

    @staticmethod
    def _detect_code_language(element: HtmlElement) -> str | None:
        """Attempt to detect a programming language from class attributes.

        Common convention: ``<code class="language-python">`` or
        ``<pre class="lang-js">``. Checks the element itself, its parent,
        and its children.
        """
        candidates = [element]
        parent = element.getparent()
        if parent is not None:
            candidates.append(parent)
        # Also check child elements (e.g. <pre> containing <code class="language-x">)
        for child in element:
            if isinstance(child, HtmlElement):
                candidates.append(child)

        for el in candidates:
            classes = (el.get("class") or "").split()
            for cls in classes:
                for prefix in ("language-", "lang-"):
                    if cls.startswith(prefix):
                        return cls[len(prefix) :]
        return None

    # ------------------------------------------------------------------ #
    # Provenance helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _css_path(element: HtmlElement) -> str:
        """Build a CSS-style selector path for *element*.

        Example: ``html > body > div.content > p:nth-child(3)``
        """
        parts: list[str] = []
        current: HtmlElement | None = element
        while current is not None:
            tag = current.tag
            if not isinstance(tag, str):
                break

            part = tag
            # Append classes for disambiguation.
            classes = (current.get("class") or "").strip()
            if classes:
                part += "." + ".".join(classes.split())

            # Append nth-child when there are siblings with the same tag.
            parent = current.getparent()
            if parent is not None:
                same_tag_siblings = [
                    c for c in parent if isinstance(c, HtmlElement) and c.tag == tag
                ]
                if len(same_tag_siblings) > 1:
                    idx = same_tag_siblings.index(current) + 1  # 1-indexed
                    part += f":nth-child({idx})"

            parts.append(part)
            current = parent

        parts.reverse()
        return " > ".join(parts)
