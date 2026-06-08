from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


AgentKind = Literal["orchestrator", "subagent", "router", "team", "team_member", "system"]
AgentModeType = Literal["router", "subagent", "all", "system"]
ResponseEventType = Literal[
    "response.created",
    "response.in_progress",
    "response.completed",
    "response.failed",
    "response.output_item.added",
    "response.output_item.done",
    "response.output_text.delta",
    "response.output_text.done",
    "response.reasoning.delta",
    "response.reasoning.done",
    "response.function_call_arguments.delta",
    "response.function_call_arguments.done",
    "response.tool_call.started",
    "response.tool_call.completed",
    "response.tool_call.failed",
    "response.subagent.started",
    "response.subagent.completed",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentRef(BaseModel):
    id: str
    name: str
    kind: AgentKind = "orchestrator"
    mode: AgentModeType = "subagent"
    parent_agent_id: Optional[str] = None
    spawned_by_call_id: Optional[str] = None
    team_id: Optional[str] = None
    role: Optional[str] = None


class ResponseEventEnvelope(BaseModel):
    type: ResponseEventType
    event_id: str = Field(default_factory=lambda: f"evt_{uuid4().hex}")
    response_id: str
    session_id: str
    run_id: str
    sequence: int
    timestamp: str = Field(default_factory=utc_now_iso)
    agent: AgentRef
    data: dict[str, Any] = Field(default_factory=dict)


class ResponseProtocolContext(BaseModel):
    response_id: str
    session_id: str
    root_agent_id: Optional[str] = None
    root_agent_name: Optional[str] = None
