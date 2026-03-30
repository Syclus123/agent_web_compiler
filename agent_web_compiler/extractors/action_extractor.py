"""Action extractor — finds interactive affordances in HTML."""

from __future__ import annotations

import re

import lxml.html
from lxml.html import HtmlElement

from agent_web_compiler.core.action import Action, ActionType, StateEffect
from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.core.provenance import DOMProvenance, Provenance

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HIDDEN_RE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.IGNORECASE)


def _is_hidden(el: HtmlElement) -> bool:
    """Return True if the element is visually hidden via inline style or the hidden attr."""
    style = el.get("style", "")
    if _HIDDEN_RE.search(style):
        return True
    return el.get("hidden") is not None


def _text_content(el: HtmlElement) -> str:
    """Return stripped text content of an element (direct + children)."""
    return (el.text_content() or "").strip()


def _extract_label(el: HtmlElement) -> str:
    """Derive a human-readable label from an element using multiple heuristics."""
    # Explicit ARIA / accessibility attributes first
    for attr in ("aria-label", "aria-labelledby", "title", "alt"):
        val = el.get(attr)
        if val and val.strip():
            return val.strip()

    # value attribute (for input/button with value)
    val = el.get("value")
    if val and val.strip() and el.tag in ("input", "button"):
        return val.strip()

    # placeholder for inputs/textareas
    placeholder = el.get("placeholder")
    if placeholder and placeholder.strip():
        return placeholder.strip()

    # Text content
    text = _text_content(el)
    if text:
        # Truncate very long labels
        return text[:120]

    # Try parent <label> element
    el_id = el.get("id")
    if el_id:
        root = el.getroottree().getroot()
        labels = root.cssselect(f'label[for="{el_id}"]')
        if labels:
            label_text = _text_content(labels[0])
            if label_text:
                return label_text[:120]

    # Check if element is wrapped in a <label>
    parent = el.getparent()
    if parent is not None and parent.tag == "label":
        label_text = _text_content(parent)
        if label_text:
            return label_text[:120]

    # name attribute as last resort
    name = el.get("name")
    if name and name.strip():
        return name.strip()

    return ""


def _build_selector(el: HtmlElement) -> str:
    """Build a CSS selector preferring id, then unique class, then nth-child path."""
    # Prefer id
    el_id = el.get("id")
    if el_id:
        return f"#{el_id}"

    # Try tag + unique class combination
    classes = el.get("class", "").split()
    if classes:
        root = el.getroottree().getroot()
        for cls in classes:
            selector = f"{el.tag}.{cls}"
            try:
                matches = root.cssselect(selector)
                if len(matches) == 1:
                    return selector
            except Exception:  # noqa: BLE001 — cssselect may reject odd class names
                continue

    # Fall back to nth-child path from root
    parts: list[str] = []
    current: HtmlElement | None = el
    while current is not None:
        parent = current.getparent()
        if parent is None:
            parts.append(current.tag)
            break
        siblings = [c for c in parent if isinstance(c, HtmlElement) and c.tag == current.tag]
        if len(siblings) > 1:
            idx = siblings.index(current) + 1
            parts.append(f"{current.tag}:nth-of-type({idx})")
        else:
            parts.append(current.tag)
        current = parent
    parts.reverse()
    return " > ".join(parts)


def _build_dom_provenance(el: HtmlElement) -> DOMProvenance:
    """Create a DOMProvenance from an lxml element."""
    return DOMProvenance(
        dom_path=_build_selector(el),
        element_tag=el.tag,
        element_id=el.get("id"),
        element_classes=el.get("class", "").split() if el.get("class") else [],
    )


# ---------------------------------------------------------------------------
# Role inference
# ---------------------------------------------------------------------------

_SEARCH_TERMS = {"search", "query", "q", "find", "lookup"}
_LOGIN_TERMS = {"login", "log-in", "signin", "sign-in", "password"}
_PAGINATION_NEXT = {"next", "»", "›", "next page", "next_page"}
_PAGINATION_PREV = {"prev", "previous", "«", "‹", "prev page", "previous page"}


def _infer_role(el: HtmlElement, label: str, action_type: ActionType) -> str | None:
    """Infer a semantic role from context clues."""
    label_lower = label.lower()
    name = (el.get("name") or "").lower()
    el_id = (el.get("id") or "").lower()
    form_action = ""

    # Walk up to find enclosing form
    parent = el.getparent()
    while parent is not None:
        if parent.tag == "form":
            form_action = (parent.get("action") or "").lower()
            break
        parent = parent.getparent()

    combined = f"{label_lower} {name} {el_id} {form_action}"

    # Search
    if any(t in combined for t in _SEARCH_TERMS):
        if action_type == ActionType.SUBMIT:
            return "submit_search"
        if action_type == ActionType.INPUT:
            return "search_input"
        return "search"

    # Login / auth
    if any(t in combined for t in _LOGIN_TERMS):
        if action_type == ActionType.SUBMIT:
            return "login"
        if action_type == ActionType.INPUT:
            return "login_input"

    # Pagination
    if any(t in label_lower for t in _PAGINATION_NEXT):
        return "next_page"
    if any(t in label_lower for t in _PAGINATION_PREV):
        return "prev_page"

    # Navigation
    if action_type == ActionType.NAVIGATE:
        return "navigation"

    return None


# ---------------------------------------------------------------------------
# Confidence & priority
# ---------------------------------------------------------------------------


def _compute_confidence(el: HtmlElement, label: str) -> float:
    """Higher when the element has explicit accessible labelling."""
    if el.get("aria-label") or el.get("title"):
        return 0.9
    if label and len(label) > 2:
        return 0.8
    if el.get("name") or el.get("id"):
        return 0.7
    return 0.5


def _compute_priority(el: HtmlElement, action_type: ActionType, role: str | None) -> float:
    """Higher for primary / submit actions, lower for generic nav links."""
    # Primary / submit buttons
    if action_type == ActionType.SUBMIT:
        return 0.9

    # Explicit primary styling hint
    classes = el.get("class", "").lower()
    if "primary" in classes or "btn-primary" in classes or "cta" in classes:
        return 0.85

    if action_type == ActionType.CLICK:
        return 0.7

    if action_type == ActionType.INPUT:
        return 0.6

    if action_type == ActionType.SELECT:
        return 0.6

    if action_type == ActionType.TOGGLE:
        return 0.5

    if action_type in (ActionType.DOWNLOAD, ActionType.UPLOAD):
        return 0.7

    if action_type == ActionType.NAVIGATE:
        if role in ("next_page", "prev_page"):
            return 0.6
        return 0.3

    return 0.5


# ---------------------------------------------------------------------------
# State‐effect inference
# ---------------------------------------------------------------------------


def _infer_state_effect(el: HtmlElement, action_type: ActionType) -> StateEffect | None:
    """Predict side-effects of triggering the action."""
    may_navigate = action_type == ActionType.NAVIGATE
    may_download = el.get("download") is not None
    may_open_modal = (el.get("data-toggle") or "").lower() == "modal" or (
        el.get("data-bs-toggle") or ""
    ).lower() == "modal"

    target_url: str | None = None
    if action_type == ActionType.NAVIGATE:
        target_url = el.get("href")

    if not (may_navigate or may_download or may_open_modal or target_url):
        return None

    return StateEffect(
        may_navigate=may_navigate,
        may_download=may_download,
        may_open_modal=may_open_modal,
        target_url=target_url,
    )


# ---------------------------------------------------------------------------
# Group assignment
# ---------------------------------------------------------------------------


def _assign_group(action_type: ActionType) -> str:
    """Assign the action to a logical group."""
    if action_type == ActionType.NAVIGATE or action_type == ActionType.DOWNLOAD:
        return "navigation"
    if action_type in (ActionType.INPUT, ActionType.SUBMIT, ActionType.SELECT,
                       ActionType.TOGGLE, ActionType.UPLOAD):
        return "form"
    return "interaction"


# ---------------------------------------------------------------------------
# Element → ActionType mapping
# ---------------------------------------------------------------------------


def _classify_element(el: HtmlElement) -> ActionType | None:
    """Map an HTML element to its ActionType, or None if not interactive."""
    tag = el.tag

    if tag == "button":
        return ActionType.CLICK

    if tag == "a" and el.get("href") is not None:
        if el.get("download") is not None:
            return ActionType.DOWNLOAD
        return ActionType.NAVIGATE

    if tag == "textarea":
        return ActionType.INPUT

    if tag == "select":
        return ActionType.SELECT

    if tag == "input":
        input_type = (el.get("type") or "text").lower()
        if input_type == "submit":
            return ActionType.SUBMIT
        if input_type in ("checkbox", "radio"):
            return ActionType.TOGGLE
        if input_type == "file":
            return ActionType.UPLOAD
        if input_type == "hidden":
            return None
        return ActionType.INPUT

    return None


# ---------------------------------------------------------------------------
# ActionExtractor
# ---------------------------------------------------------------------------

# Selector for all potentially interactive elements
_INTERACTIVE_SELECTOR = (
    "button, a[href], input, textarea, select"
)


class ActionExtractor:
    """Extracts interactive affordances (actions) from HTML.

    Scans the DOM for buttons, links, inputs, selects, and textareas, then
    builds typed :class:`Action` objects with labels, selectors, roles,
    confidence scores, predicted state effects, and provenance.
    """

    def extract(self, html: str, config: CompileConfig) -> list[Action]:
        """Extract all interactive actions from the page.

        Parameters
        ----------
        html:
            Raw HTML string to analyse.
        config:
            Compilation configuration (used to gate provenance inclusion).

        Returns
        -------
        list[Action]
            Actions sorted by descending priority, deduplicated by selector.
        """
        if not html or not html.strip():
            return []

        root: HtmlElement = lxml.html.fromstring(html)
        elements = root.cssselect(_INTERACTIVE_SELECTOR)

        actions: list[Action] = []
        seen_selectors: set[str] = set()
        order = 0

        for el in elements:
            # Skip hidden elements
            if _is_hidden(el):
                continue

            action_type = _classify_element(el)
            if action_type is None:
                continue

            label = _extract_label(el)
            if not label:
                continue

            selector = _build_selector(el)

            # Deduplicate by selector
            if selector in seen_selectors:
                continue
            seen_selectors.add(selector)

            role = _infer_role(el, label, action_type)
            confidence = _compute_confidence(el, label)
            priority = _compute_priority(el, action_type, role)
            state_effect = _infer_state_effect(el, action_type)
            group = _assign_group(action_type)

            action_id = f"a_{order:03d}_{action_type.value}"

            provenance: Provenance | None = None
            if config.include_provenance:
                provenance = Provenance(dom=_build_dom_provenance(el))

            actions.append(
                Action(
                    id=action_id,
                    type=action_type,
                    label=label,
                    selector=selector,
                    role=role,
                    confidence=confidence,
                    priority=priority,
                    state_effect=state_effect,
                    provenance=provenance,
                    group=group,
                )
            )
            order += 1

        # Sort by priority descending (stable)
        actions.sort(key=lambda a: a.priority, reverse=True)
        return actions
