"""Trace recorder — structured logging of agent decisions.

Records the chain of decisions an agent makes: which blocks were retrieved,
which evidence was selected, which action was chosen, and why.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


def _make_step_id() -> str:
    """Generate a unique step ID."""
    return f"step_{uuid.uuid4().hex[:10]}"


def _make_session_id() -> str:
    """Generate a unique session ID."""
    return f"trace_{uuid.uuid4().hex[:12]}"


@dataclass
class TraceStep:
    """A single step in an agent's decision trace."""

    step_id: str
    step_type: str  # "query", "retrieve", "rerank", "select_evidence", "select_action", "execute", "answer"
    timestamp: float = 0.0
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)
    evidence_ids: list[str] = field(default_factory=list)
    action_ids: list[str] = field(default_factory=list)
    decision_summary: str = ""
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "step_id": self.step_id,
            "step_type": self.step_type,
            "timestamp": self.timestamp,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "evidence_ids": self.evidence_ids,
            "action_ids": self.action_ids,
            "decision_summary": self.decision_summary,
            "duration_ms": self.duration_ms,
        }


@dataclass
class TraceSession:
    """A complete trace of an agent task."""

    session_id: str
    query: str = ""
    steps: list[TraceStep] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0
    final_answer: str | None = None
    citations: list[str] = field(default_factory=list)  # citation_ids

    def add_step(self, step: TraceStep) -> None:
        """Add a step to this trace session."""
        self.steps.append(step)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "session_id": self.session_id,
            "query": self.query,
            "steps": [s.to_dict() for s in self.steps],
            "start_time": self.start_time,
            "end_time": self.end_time,
            "final_answer": self.final_answer,
            "citations": self.citations,
            "duration_ms": self.duration_ms,
            "step_count": self.step_count,
        }

    def to_markdown(self) -> str:
        """Render trace as readable markdown."""
        lines: list[str] = []
        lines.append(f"# Trace: {self.session_id}")
        if self.query:
            lines.append(f"\n**Query**: {self.query}")
        lines.append(f"**Duration**: {self.duration_ms:.1f}ms")
        lines.append(f"**Steps**: {self.step_count}")
        lines.append("")

        for i, step in enumerate(self.steps):
            lines.append(f"## Step {i + 1}: {step.step_type}")
            if step.decision_summary:
                lines.append(f"**Decision**: {step.decision_summary}")
            if step.evidence_ids:
                lines.append(f"**Evidence**: {', '.join(step.evidence_ids)}")
            if step.action_ids:
                lines.append(f"**Actions**: {', '.join(step.action_ids)}")
            if step.duration_ms > 0:
                lines.append(f"**Duration**: {step.duration_ms:.1f}ms")
            lines.append("")

        if self.final_answer:
            lines.append("## Final Answer")
            lines.append(self.final_answer)

        if self.citations:
            lines.append("")
            lines.append(f"**Citations**: {', '.join(self.citations)}")

        return "\n".join(lines)

    @property
    def duration_ms(self) -> float:
        """Total session duration in milliseconds."""
        if self.end_time > 0 and self.start_time > 0:
            return (self.end_time - self.start_time) * 1000.0
        return 0.0

    @property
    def step_count(self) -> int:
        """Number of steps in this trace."""
        return len(self.steps)


class TraceRecorder:
    """Records agent decision traces."""

    def __init__(self) -> None:
        self._sessions: dict[str, TraceSession] = {}

    def start_session(self, query: str = "") -> TraceSession:
        """Start a new trace session.

        Returns the session object so callers can reference its ID.
        """
        session = TraceSession(
            session_id=_make_session_id(),
            query=query,
            start_time=time.time(),
        )
        self._sessions[session.session_id] = session
        return session

    def record_step(
        self,
        session_id: str,
        step_type: str,
        *,
        input_data: dict[str, Any] | None = None,
        output_data: dict[str, Any] | None = None,
        evidence_ids: list[str] | None = None,
        action_ids: list[str] | None = None,
        decision_summary: str = "",
        duration_ms: float = 0.0,
    ) -> TraceStep:
        """Record a step in an existing trace session.

        Raises KeyError if session_id is not found.
        """
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"Trace session not found: {session_id}")

        step = TraceStep(
            step_id=_make_step_id(),
            step_type=step_type,
            timestamp=time.time(),
            input_data=input_data or {},
            output_data=output_data or {},
            evidence_ids=evidence_ids or [],
            action_ids=action_ids or [],
            decision_summary=decision_summary,
            duration_ms=duration_ms,
        )
        session.add_step(step)
        return step

    def end_session(
        self,
        session_id: str,
        answer: str | None = None,
        citations: list[str] | None = None,
    ) -> TraceSession:
        """End a trace session and record the final answer.

        Raises KeyError if session_id is not found.
        """
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"Trace session not found: {session_id}")

        session.end_time = time.time()
        session.final_answer = answer
        if citations:
            session.citations = citations
        return session

    def get_session(self, session_id: str) -> TraceSession | None:
        """Retrieve a session by ID."""
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[TraceSession]:
        """List all recorded sessions, oldest first."""
        sessions = list(self._sessions.values())
        sessions.sort(key=lambda s: s.start_time)
        return sessions
