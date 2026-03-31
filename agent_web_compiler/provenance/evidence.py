"""Evidence objects — verifiable source content with multi-level grounding.

An Evidence object is more than a URL citation. It points to a specific
block, DOM path, PDF region, or screenshot area, tied to a page snapshot.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_web_compiler.core.action import Action
    from agent_web_compiler.core.block import Block
    from agent_web_compiler.core.document import AgentDocument


def _make_evidence_id(source_url: str | None, block_id: str | None) -> str:
    """Generate a deterministic evidence ID from source URL and block ID."""
    raw = f"{source_url or ''}{block_id or ''}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"ev_{digest}"


@dataclass
class Evidence:
    """A verifiable piece of source content.

    Unlike a URL citation, an Evidence object pinpoints the exact
    source: block text, DOM path, PDF bbox, screenshot region.
    """

    evidence_id: str
    source_type: str  # "web_block", "pdf_block", "action", "table_cell", "code_block"
    source_url: str | None = None
    snapshot_id: str | None = None

    # Content
    block_id: str | None = None
    text: str = ""
    section_path: list[str] = field(default_factory=list)

    # Multi-level provenance
    dom_path: str | None = None
    page: int | None = None
    bbox: list[float] | None = None  # [x1, y1, x2, y2]
    screenshot_region_id: str | None = None
    char_range: list[int] | None = None  # [start, end]

    # Metadata
    content_type: str = ""  # "paragraph", "table", "code", "heading", etc.
    language: str | None = None
    timestamp: float = 0.0
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        d: dict[str, Any] = {
            "evidence_id": self.evidence_id,
            "source_type": self.source_type,
            "source_url": self.source_url,
            "snapshot_id": self.snapshot_id,
            "block_id": self.block_id,
            "text": self.text,
            "section_path": self.section_path,
            "dom_path": self.dom_path,
            "page": self.page,
            "bbox": self.bbox,
            "screenshot_region_id": self.screenshot_region_id,
            "char_range": self.char_range,
            "content_type": self.content_type,
            "language": self.language,
            "timestamp": self.timestamp,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }
        return d

    @staticmethod
    def from_block(
        block: Block,
        doc: AgentDocument,
        snapshot_id: str | None = None,
    ) -> Evidence:
        """Create Evidence from a compiled Block.

        Extracts text, provenance (dom_path, bbox, page, char_range,
        screenshot), section_path, and content type from the block.
        """
        source_url = doc.source_url
        eid = _make_evidence_id(source_url, block.id)

        # Determine source_type based on block type and doc source
        block_type_str = block.type.value if hasattr(block.type, "value") else str(block.type)
        source_type_map = {
            "table": "table_cell",
            "code": "code_block",
        }
        source_type = source_type_map.get(block_type_str, "web_block")
        if doc.source_type and hasattr(doc.source_type, "value") and doc.source_type.value == "pdf":
            source_type = "pdf_block"

        # Extract provenance details
        dom_path: str | None = None
        page_num: int | None = None
        bbox: list[float] | None = None
        char_range: list[int] | None = None
        screenshot_region_id: str | None = None

        prov = block.provenance
        if prov is not None:
            if prov.dom is not None:
                dom_path = prov.dom.dom_path
            if prov.page is not None:
                page_num = prov.page.page
                bbox = list(prov.page.bbox) if prov.page.bbox else None
                char_range = list(prov.page.char_range) if prov.page.char_range else None
            if prov.screenshot is not None:
                screenshot_region_id = prov.screenshot.screenshot_region_id

        return Evidence(
            evidence_id=eid,
            source_type=source_type,
            source_url=source_url,
            snapshot_id=snapshot_id,
            block_id=block.id,
            text=block.text,
            section_path=list(block.section_path),
            dom_path=dom_path,
            page=page_num,
            bbox=bbox,
            screenshot_region_id=screenshot_region_id,
            char_range=char_range,
            content_type=block_type_str,
            language=block.metadata.get("language") if block.metadata else None,
            timestamp=time.time(),
            confidence=block.importance,
            metadata={},
        )

    @staticmethod
    def from_action(
        action: Action,
        doc: AgentDocument,
        snapshot_id: str | None = None,
    ) -> Evidence:
        """Create Evidence from a compiled Action.

        Extracts label, selector, role, provenance, and state_effect.
        """
        source_url = doc.source_url
        eid = _make_evidence_id(source_url, action.id)

        dom_path: str | None = None
        page_num: int | None = None
        bbox: list[float] | None = None
        screenshot_region_id: str | None = None

        prov = action.provenance
        if prov is not None:
            if prov.dom is not None:
                dom_path = prov.dom.dom_path
            if prov.page is not None:
                page_num = prov.page.page
                bbox = list(prov.page.bbox) if prov.page.bbox else None
            if prov.screenshot is not None:
                screenshot_region_id = prov.screenshot.screenshot_region_id

        action_type_str = action.type.value if hasattr(action.type, "value") else str(action.type)

        meta: dict[str, Any] = {
            "action_type": action_type_str,
            "selector": action.selector,
            "role": action.role,
        }
        if action.state_effect is not None:
            meta["state_effect"] = {
                "may_navigate": action.state_effect.may_navigate,
                "may_open_modal": action.state_effect.may_open_modal,
                "may_download": action.state_effect.may_download,
                "target_url": action.state_effect.target_url,
            }

        return Evidence(
            evidence_id=eid,
            source_type="action",
            source_url=source_url,
            snapshot_id=snapshot_id,
            block_id=action.id,
            text=action.label,
            section_path=[],
            dom_path=dom_path,
            page=page_num,
            bbox=bbox,
            screenshot_region_id=screenshot_region_id,
            char_range=None,
            content_type=action_type_str,
            language=None,
            timestamp=time.time(),
            confidence=action.confidence,
            metadata=meta,
        )


class EvidenceBuilder:
    """Builds Evidence objects from compiled AgentDocuments.

    Extracts all evidenceable content: blocks, actions, table cells,
    and creates structured Evidence objects with full provenance.
    """

    def build_from_document(
        self,
        doc: AgentDocument,
        snapshot_id: str | None = None,
    ) -> list[Evidence]:
        """Extract all evidence from a compiled document.

        Creates Evidence for each block and each action.
        """
        evidence_list: list[Evidence] = []

        for block in doc.blocks:
            ev = self.build_from_block(block, doc, snapshot_id)
            evidence_list.append(ev)

        for action in doc.actions:
            ev = self.build_from_action(action, doc, snapshot_id)
            evidence_list.append(ev)

        return evidence_list

    def build_from_block(
        self,
        block: Block,
        doc: AgentDocument,
        snapshot_id: str | None = None,
    ) -> Evidence:
        """Build evidence from a single block."""
        return Evidence.from_block(block, doc, snapshot_id)

    def build_from_action(
        self,
        action: Action,
        doc: AgentDocument,
        snapshot_id: str | None = None,
    ) -> Evidence:
        """Build evidence from a single action."""
        return Evidence.from_action(action, doc, snapshot_id)

    def build_from_search_result(
        self,
        result: Any,
        snapshot_id: str | None = None,
    ) -> Evidence:
        """Build evidence from a search result.

        Accepts any object with block_id, doc_id, text, section_path,
        score, and provenance attributes (e.g. SearchResult).
        """
        source_url: str | None = None
        if hasattr(result, "provenance") and result.provenance:
            source_url = result.provenance.get("source_url")

        block_id = getattr(result, "block_id", None) or getattr(result, "action_id", None) or ""
        eid = _make_evidence_id(source_url, block_id)

        page_num: int | None = None
        if hasattr(result, "metadata") and result.metadata:
            page_num = result.metadata.get("page")

        section_path = list(result.section_path) if hasattr(result, "section_path") and result.section_path else []

        kind = getattr(result, "kind", "block")
        source_type = "action" if kind == "action" else "web_block"

        return Evidence(
            evidence_id=eid,
            source_type=source_type,
            source_url=source_url,
            snapshot_id=snapshot_id,
            block_id=block_id,
            text=getattr(result, "text", ""),
            section_path=section_path,
            page=page_num,
            content_type=kind,
            timestamp=time.time(),
            confidence=min(getattr(result, "score", 0.5), 1.0),
        )
