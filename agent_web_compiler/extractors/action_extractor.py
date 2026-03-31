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


def _find_enclosing_form(el: HtmlElement) -> HtmlElement | None:
    """Walk up from *el* to find the nearest ``<form>`` ancestor, or None."""
    parent = el.getparent()
    while parent is not None:
        if parent.tag == "form":
            return parent
        parent = parent.getparent()
    return None


# Types that are form-control inputs (should be merged into composite action)
_FORM_CONTROL_TYPES = frozenset({
    ActionType.INPUT,
    ActionType.SELECT,
    ActionType.TOGGLE,
    ActionType.UPLOAD,
    ActionType.SUBMIT,
})


def _input_field_type(el: HtmlElement) -> str:
    """Return the HTML input type string for a form control element."""
    tag = el.tag
    if tag == "textarea":
        return "text"
    if tag == "select":
        return "select"
    if tag == "input":
        return (el.get("type") or "text").lower()
    return "text"


def _input_field_name(el: HtmlElement, label: str) -> str:
    """Return a field name for a form control, preferring the name attribute."""
    name = el.get("name")
    if name and name.strip():
        return name.strip()
    return label


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

        # --- Form field grouping ---
        actions = self._group_form_actions(actions, root, config)

        # Sort by priority descending (stable)
        actions.sort(key=lambda a: a.priority, reverse=True)
        return actions

    @staticmethod
    def _group_form_actions(
        actions: list[Action],
        root: HtmlElement,
        config: CompileConfig,
    ) -> list[Action]:
        """Group input/select/toggle actions by enclosing ``<form>`` element.

        For each ``<form>`` that contains at least one submit/click action,
        create a single composite SUBMIT action and remove the individual
        form-control actions.  Standalone inputs (not inside a form, or in a
        form with no submit) are kept unchanged.  Navigate/download actions
        inside forms are also kept.
        """
        if not actions:
            return actions

        # Build a map from action id -> lxml element so we can find forms.
        # We re-query the DOM to pair each action with its element.
        all_elements = root.cssselect(_INTERACTIVE_SELECTOR)
        selector_to_element: dict[str, HtmlElement] = {}
        for el in all_elements:
            sel = _build_selector(el)
            if sel not in selector_to_element:
                selector_to_element[sel] = el

        # Map: form element id(…) -> (form_el, [action indices of controls], [submit indices])
        form_info_t = tuple[HtmlElement, list[int], list[int]]
        form_map: dict[int, form_info_t] = {}

        for idx, action in enumerate(actions):
            if action.selector is None:
                continue
            el = selector_to_element.get(action.selector)
            if el is None:
                continue
            form_el = _find_enclosing_form(el)
            if form_el is None:
                continue

            form_key = id(form_el)
            if form_key not in form_map:
                form_map[form_key] = (form_el, [], [])

            _, controls, submits = form_map[form_key]
            if action.type in _FORM_CONTROL_TYPES:
                controls.append(idx)
            if action.type in (ActionType.SUBMIT, ActionType.CLICK):
                submits.append(idx)

        # Build composite actions for forms that have a submit control
        indices_to_remove: set[int] = set()
        composite_actions: list[Action] = []

        for form_el, control_indices, submit_indices in form_map.values():
            if not submit_indices:
                continue  # No submit button — keep individual actions

            # Pick the first submit/click as the representative
            submit_idx = submit_indices[0]
            submit_action = actions[submit_idx]

            # Gather field info from non-submit controls
            required_fields: list[str] = []
            value_schema: dict[str, str] = {}
            max_priority = submit_action.priority
            max_confidence = submit_action.confidence

            for ci in control_indices:
                ctrl = actions[ci]
                max_priority = max(max_priority, ctrl.priority)
                max_confidence = max(max_confidence, ctrl.confidence)

                if ctrl.type == ActionType.SUBMIT:
                    continue  # Don't add submit button as a field
                if ctrl.type == ActionType.CLICK:
                    continue  # Don't add plain click as a field

                el = selector_to_element.get(ctrl.selector or "")
                if el is None:
                    continue

                field_name = _input_field_name(el, ctrl.label)
                field_type = _input_field_type(el)
                required_fields.append(field_name)
                value_schema[field_name] = field_type

            # Mark all form-control indices for removal
            for ci in control_indices:
                indices_to_remove.add(ci)

            # Build the composite action
            form_selector = _build_selector(form_el)

            provenance: Provenance | None = None
            if config.include_provenance:
                provenance = Provenance(dom=_build_dom_provenance(form_el))

            composite = Action(
                id=submit_action.id,
                type=ActionType.SUBMIT,
                label=submit_action.label,
                selector=form_selector,
                role=submit_action.role,
                required_fields=required_fields,
                value_schema=value_schema if value_schema else None,
                confidence=max_confidence,
                priority=max_priority,
                state_effect=submit_action.state_effect,
                provenance=provenance,
                group="form",
            )
            composite_actions.append(composite)

        # Build the final list: keep non-removed actions, add composites
        result: list[Action] = []
        for idx, action in enumerate(actions):
            if idx not in indices_to_remove:
                result.append(action)
        result.extend(composite_actions)
        return result
