"""Generate /actions.json — declares what agents can DO on the site.

This is the "capability advertisement" for AI agents. Instead of
agents discovering actions by parsing HTML, the site proactively
declares what's possible.

Schema:
{
    "version": "0.1.0",
    "site": "example.com",
    "capabilities": ["search", "download", "navigate", "purchase"],
    "actions": [{
        "id": "search_products",
        "type": "submit",
        "label": "Search Products",
        "url": "/products",
        "role": "submit_search",
        "fields": [{"name": "q", "type": "text", "required": true}],
        "confidence": 0.95
    }],
    "forms": [{
        "id": "contact_form",
        "url": "/contact",
        "fields": [...],
        "submit_label": "Send Message"
    }]
}
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from agent_web_compiler.core.action import Action, ActionType
from agent_web_compiler.core.document import AgentDocument

# Map action roles to capability categories
_ROLE_TO_CAPABILITY: dict[str, str] = {
    "submit_search": "search",
    "search": "search",
    "download": "download",
    "login": "login",
    "signup": "signup",
    "purchase": "purchase",
    "add_to_cart": "purchase",
    "checkout": "purchase",
    "next_page": "navigate",
    "prev_page": "navigate",
    "navigate": "navigate",
    "filter": "filter",
    "sort": "sort",
}


def _infer_capability(action: Action) -> str:
    """Infer capability category from an action's role or type."""
    if action.role:
        cap = _ROLE_TO_CAPABILITY.get(action.role)
        if cap:
            return cap
        # Fallback: try prefix matching
        for key, val in _ROLE_TO_CAPABILITY.items():
            if key in action.role:
                return val

    # Fall back to action type
    type_map: dict[str, str] = {
        "navigate": "navigate",
        "download": "download",
        "submit": "submit",
        "input": "input",
    }
    return type_map.get(action.type.value, "interact")


def _dedup_key(action: Action) -> str:
    """Generate a deduplication key for an action."""
    return f"{action.role or ''}|{action.selector or ''}|{action.type.value}"


def _action_to_dict(action: Action, page_url: str) -> dict[str, Any]:
    """Serialize an action to an actions.json action dict."""
    d: dict[str, Any] = {
        "id": action.id,
        "type": action.type.value,
        "label": action.label,
        "url": page_url,
    }

    if action.role:
        d["role"] = action.role

    if action.required_fields:
        d["fields"] = [
            {"name": f, "type": "text", "required": True}
            for f in action.required_fields
        ]

    d["confidence"] = round(action.confidence, 2)
    return d


def _is_form_action(action: Action) -> bool:
    """Check if an action represents a form submission."""
    return action.type == ActionType.SUBMIT or bool(action.required_fields)


def _form_to_dict(action: Action, page_url: str) -> dict[str, Any]:
    """Serialize a form action to a forms entry."""
    d: dict[str, Any] = {
        "id": action.id,
        "url": page_url,
    }

    if action.required_fields:
        d["fields"] = [
            {"name": f, "type": "text", "required": True}
            for f in action.required_fields
        ]

    d["submit_label"] = action.label
    return d


def generate_actions_json(
    docs: list[AgentDocument],
    site_name: str = "",
    site_url: str = "",
) -> str:
    """Generate /actions.json from compiled pages.

    Args:
        docs: Compiled AgentDocuments representing site pages.
        site_url: The top-level site URL or domain.

    Returns:
        JSON string conforming to the actions.json schema.

    Raises:
        ValueError: If docs is empty.
    """
    if not docs:
        raise ValueError("At least one AgentDocument is required.")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Collect and deduplicate actions
    seen_keys: set[str] = set()
    all_actions: list[tuple[Action, str]] = []  # (action, page_url)
    capabilities: set[str] = set()

    for doc in docs:
        page_url = doc.source_url or ""
        for action in doc.actions:
            key = _dedup_key(action)
            if key not in seen_keys:
                seen_keys.add(key)
                all_actions.append((action, page_url))
                capabilities.add(_infer_capability(action))

    # Build actions list and forms list
    actions_list: list[dict[str, Any]] = []
    forms_list: list[dict[str, Any]] = []

    for action, page_url in all_actions:
        actions_list.append(_action_to_dict(action, page_url))
        if _is_form_action(action):
            forms_list.append(_form_to_dict(action, page_url))

    output: dict[str, Any] = {
        "version": "0.1.0",
        "site": site_url,
        "generated_at": now,
        "capabilities": sorted(capabilities),
        "actions": actions_list,
        "forms": forms_list,
    }

    return json.dumps(output, indent=2, ensure_ascii=False)
