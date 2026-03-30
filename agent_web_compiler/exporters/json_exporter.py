"""JSON exporter — serializes AgentDocument to JSON."""

from __future__ import annotations

import json

from agent_web_compiler.core.document import AgentDocument


def to_json(doc: AgentDocument, indent: int = 2) -> str:
    """Serialize an AgentDocument to a JSON string.

    Args:
        doc: The compiled document to serialize.
        indent: JSON indentation level (default 2).

    Returns:
        JSON string representation.
    """
    return json.dumps(to_dict(doc), indent=indent, default=str, ensure_ascii=False)


def to_dict(doc: AgentDocument) -> dict:
    """Convert an AgentDocument to a plain dict.

    Uses Pydantic's model_dump with JSON-compatible serialization
    so that datetimes, enums, etc. are properly converted.

    Args:
        doc: The compiled document to convert.

    Returns:
        Plain dictionary suitable for JSON serialization.
    """
    return doc.model_dump(mode="json")
