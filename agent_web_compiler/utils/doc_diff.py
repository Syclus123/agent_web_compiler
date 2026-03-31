"""Document diff — compute semantic changes between two AgentDocuments.

Enables incremental agent workflows: instead of re-reading the full page
after an action, the agent can see exactly what changed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from agent_web_compiler.core.document import AgentDocument

# Threshold above which two blocks are considered the "same block, modified"
_SIMILARITY_THRESHOLD = 0.8


@dataclass
class BlockChange:
    """Describes a change to a single content block."""

    change_type: str  # "added", "removed", "modified"
    block_id: str
    old_text: str | None = None
    new_text: str | None = None
    section_path: list[str] | None = None


@dataclass
class ActionChange:
    """Describes a change to a single action."""

    change_type: str  # "added", "removed", "modified"
    action_id: str
    label: str = ""
    old_state: dict[str, Any] | None = None
    new_state: dict[str, Any] | None = None


@dataclass
class DocumentDiff:
    """Semantic diff between two AgentDocuments."""

    blocks_added: list[BlockChange] = field(default_factory=list)
    blocks_removed: list[BlockChange] = field(default_factory=list)
    blocks_modified: list[BlockChange] = field(default_factory=list)
    actions_added: list[ActionChange] = field(default_factory=list)
    actions_removed: list[ActionChange] = field(default_factory=list)
    actions_modified: list[ActionChange] = field(default_factory=list)
    title_changed: bool = False
    old_title: str = ""
    new_title: str = ""

    @property
    def has_changes(self) -> bool:
        """Return True if any changes were detected."""
        return bool(
            self.blocks_added
            or self.blocks_removed
            or self.blocks_modified
            or self.actions_added
            or self.actions_removed
            or self.actions_modified
            or self.title_changed
        )

    def summary(self) -> str:
        """Human-readable summary of changes."""
        lines: list[str] = []

        if self.title_changed:
            lines.append(
                f'Page changed: "{self.old_title}" -> "{self.new_title}"'
            )

        # Block summary line
        parts: list[str] = []
        if self.blocks_added:
            parts.append(f"+{len(self.blocks_added)} blocks added")
        if self.blocks_removed:
            parts.append(f"-{len(self.blocks_removed)} removed")
        if self.blocks_modified:
            parts.append(f"{len(self.blocks_modified)} modified")
        if parts:
            lines.append(", ".join(parts))

        # Action summary line
        action_parts: list[str] = []
        if self.actions_added:
            labels = [a.label for a in self.actions_added if a.label]
            if labels:
                action_parts.append(
                    f'+{len(self.actions_added)} action added (new "{labels[0]}" button)'
                )
            else:
                action_parts.append(f"+{len(self.actions_added)} action added")
        if self.actions_removed:
            action_parts.append(f"-{len(self.actions_removed)} action removed")
        if self.actions_modified:
            action_parts.append(f"{len(self.actions_modified)} action modified")
        if action_parts:
            lines.append(", ".join(action_parts))

        # Key changes detail
        details: list[str] = []
        for m in self.blocks_modified:
            old_preview = _truncate(m.old_text or "", 40)
            new_preview = _truncate(m.new_text or "", 40)
            details.append(f'  [modified] Changed: "{old_preview}" -> "{new_preview}"')
        for a in self.blocks_added:
            preview = _truncate(a.new_text or "", 50)
            section = " > ".join(a.section_path) if a.section_path else ""
            if section:
                details.append(f'  [added] New section: "{section}"')
            else:
                details.append(f'  [added] New block: "{preview}"')
        for r in self.blocks_removed:
            preview = _truncate(r.old_text or "", 50)
            section = " > ".join(r.section_path) if r.section_path else ""
            if section:
                details.append(f'  [removed] Section "{section}" removed')
            else:
                details.append(f'  [removed] Block removed: "{preview}"')

        if details:
            lines.append("Key changes:")
            lines.extend(details)

        if not lines:
            return "No changes detected."

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the diff to a plain dictionary."""
        return {
            "title_changed": self.title_changed,
            "old_title": self.old_title,
            "new_title": self.new_title,
            "blocks_added": [_block_change_dict(c) for c in self.blocks_added],
            "blocks_removed": [_block_change_dict(c) for c in self.blocks_removed],
            "blocks_modified": [_block_change_dict(c) for c in self.blocks_modified],
            "actions_added": [_action_change_dict(c) for c in self.actions_added],
            "actions_removed": [_action_change_dict(c) for c in self.actions_removed],
            "actions_modified": [_action_change_dict(c) for c in self.actions_modified],
            "has_changes": self.has_changes,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _block_change_dict(c: BlockChange) -> dict[str, Any]:
    d: dict[str, Any] = {
        "change_type": c.change_type,
        "block_id": c.block_id,
    }
    if c.old_text is not None:
        d["old_text"] = c.old_text
    if c.new_text is not None:
        d["new_text"] = c.new_text
    if c.section_path is not None:
        d["section_path"] = c.section_path
    return d


def _action_change_dict(c: ActionChange) -> dict[str, Any]:
    d: dict[str, Any] = {
        "change_type": c.change_type,
        "action_id": c.action_id,
        "label": c.label,
    }
    if c.old_state is not None:
        d["old_state"] = c.old_state
    if c.new_state is not None:
        d["new_state"] = c.new_state
    return d


def _text_similarity(a: str, b: str) -> float:
    """Compute similarity ratio between two text strings."""
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def diff_documents(old: AgentDocument, new: AgentDocument) -> DocumentDiff:
    """Compute semantic diff between two documents.

    Blocks are matched by text similarity (not by ID, since IDs may change
    between compiles). Actions are matched by selector as the most stable
    identifier.

    Args:
        old: The previous version of the document.
        new: The current version of the document.

    Returns:
        A DocumentDiff describing all semantic changes.
    """
    diff = DocumentDiff()

    # Title
    if old.title != new.title:
        diff.title_changed = True
        diff.old_title = old.title
        diff.new_title = new.title

    # --- Block matching ---
    # Build a list of (index, text) for old and new blocks
    old_blocks = [(i, b) for i, b in enumerate(old.blocks)]
    new_blocks = [(i, b) for i, b in enumerate(new.blocks)]

    # Track which blocks have been matched
    old_matched: set[int] = set()
    new_matched: set[int] = set()

    # First pass: find exact text matches
    old_text_index: dict[str, list[int]] = {}
    for idx, block in old_blocks:
        old_text_index.setdefault(block.text, []).append(idx)

    for new_idx, new_block in new_blocks:
        candidates = old_text_index.get(new_block.text, [])
        for old_idx in candidates:
            if old_idx not in old_matched:
                old_matched.add(old_idx)
                new_matched.add(new_idx)
                break

    # Second pass: fuzzy match remaining blocks
    unmatched_old = [(i, b) for i, b in old_blocks if i not in old_matched]
    unmatched_new = [(i, b) for i, b in new_blocks if i not in new_matched]

    # Compute similarity matrix and greedily match best pairs
    matches: list[tuple[int, int, float]] = []
    for oi, ob in unmatched_old:
        for ni, nb in unmatched_new:
            sim = _text_similarity(ob.text, nb.text)
            if sim >= _SIMILARITY_THRESHOLD:
                matches.append((oi, ni, sim))

    # Sort by similarity descending, greedily assign
    matches.sort(key=lambda x: x[2], reverse=True)
    for oi, ni, _sim in matches:
        if oi in old_matched or ni in new_matched:
            continue
        old_matched.add(oi)
        new_matched.add(ni)
        old_block = old.blocks[oi]
        new_block = new.blocks[ni]
        diff.blocks_modified.append(
            BlockChange(
                change_type="modified",
                block_id=new_block.id,
                old_text=old_block.text,
                new_text=new_block.text,
                section_path=new_block.section_path or old_block.section_path or None,
            )
        )

    # Remaining unmatched old blocks → removed
    for oi, ob in old_blocks:
        if oi not in old_matched:
            diff.blocks_removed.append(
                BlockChange(
                    change_type="removed",
                    block_id=ob.id,
                    old_text=ob.text,
                    section_path=ob.section_path or None,
                )
            )

    # Remaining unmatched new blocks → added
    for ni, nb in new_blocks:
        if ni not in new_matched:
            diff.blocks_added.append(
                BlockChange(
                    change_type="added",
                    block_id=nb.id,
                    new_text=nb.text,
                    section_path=nb.section_path or None,
                )
            )

    # --- Action matching (by selector, then label) ---
    old_actions_by_selector: dict[str | None, list[int]] = {}
    for idx, action in enumerate(old.actions):
        key = action.selector or action.label
        old_actions_by_selector.setdefault(key, []).append(idx)

    old_action_matched: set[int] = set()
    new_action_matched: set[int] = set()

    for new_idx, new_action in enumerate(new.actions):
        key = new_action.selector or new_action.label
        candidates = old_actions_by_selector.get(key, [])
        for old_idx in candidates:
            if old_idx not in old_action_matched:
                old_action_matched.add(old_idx)
                new_action_matched.add(new_idx)
                old_action = old.actions[old_idx]
                # Check if the action actually changed
                if (
                    old_action.label != new_action.label
                    or old_action.type != new_action.type
                    or old_action.role != new_action.role
                ):
                    diff.actions_modified.append(
                        ActionChange(
                            change_type="modified",
                            action_id=new_action.id,
                            label=new_action.label,
                            old_state={
                                "type": old_action.type.value,
                                "label": old_action.label,
                                "role": old_action.role,
                            },
                            new_state={
                                "type": new_action.type.value,
                                "label": new_action.label,
                                "role": new_action.role,
                            },
                        )
                    )
                break

    for old_idx, old_action in enumerate(old.actions):
        if old_idx not in old_action_matched:
            diff.actions_removed.append(
                ActionChange(
                    change_type="removed",
                    action_id=old_action.id,
                    label=old_action.label,
                )
            )

    for new_idx, new_action in enumerate(new.actions):
        if new_idx not in new_action_matched:
            diff.actions_added.append(
                ActionChange(
                    change_type="added",
                    action_id=new_action.id,
                    label=new_action.label,
                )
            )

    return diff
