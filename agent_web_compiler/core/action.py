"""Action model — an interactive affordance on a page."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from agent_web_compiler.core.provenance import Provenance


class ActionType(str, Enum):
    """Type of interactive action."""

    CLICK = "click"
    INPUT = "input"
    SELECT = "select"
    TOGGLE = "toggle"
    UPLOAD = "upload"
    DOWNLOAD = "download"
    NAVIGATE = "navigate"
    SUBMIT = "submit"


class StateEffect(BaseModel):
    """Predicted side effects of executing an action."""

    may_navigate: bool = Field(False, description="May cause page navigation")
    may_open_modal: bool = Field(False, description="May open a modal/dialog")
    may_download: bool = Field(False, description="May trigger a download")
    target_url: str | None = Field(None, description="Target URL if known")


class Action(BaseModel):
    """An interactive affordance extracted from a page.

    Represents something an agent can do: click a button, fill an input,
    submit a form, navigate a link, etc.
    """

    id: str = Field(..., description="Unique action identifier, e.g. 'a_search_submit'")
    type: ActionType = Field(..., description="Type of interaction")
    label: str = Field(..., description="Human-readable label for this action")
    selector: str | None = Field(
        None, description="CSS selector to target the element"
    )
    role: str | None = Field(
        None,
        description="Semantic role, e.g. 'submit_search', 'login', 'next_page'",
    )
    value_schema: dict[str, Any] | None = Field(
        None, description="Expected value schema for input actions"
    )
    required_fields: list[str] = Field(
        default_factory=list, description="Required input fields for form actions"
    )
    confidence: float = Field(
        0.5,
        ge=0.0,
        le=1.0,
        description="Confidence that this action is correctly identified",
    )
    priority: float = Field(
        0.5,
        ge=0.0,
        le=1.0,
        description="Estimated importance/relevance of this action",
    )
    state_effect: StateEffect | None = Field(
        None, description="Predicted side effects"
    )
    provenance: Provenance | None = Field(
        None, description="Origin tracking back to source element"
    )
    group: str | None = Field(
        None, description="Action group, e.g. 'navigation', 'search', 'form'"
    )
