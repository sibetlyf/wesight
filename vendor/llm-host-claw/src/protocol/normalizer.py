from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Optional, cast
from uuid import uuid4

from protocol.response_events import AgentModeType, AgentRef, ResponseEventEnvelope, ResponseEventType, ResponseProtocolContext


def create_response_id() -> str:
    return f"resp_{uuid4().hex}"


class ResponseEventNormalizer:
    def __init__(self, context: ResponseProtocolContext):
        self.context = context
        self.sequence = 0
        self._started = False
        self._message_item_created: set[tuple[str, str]] = set()
        self._reasoning_item_created: set[tuple[str, str]] = set()
        self._function_items: dict[str, dict[str, Any]] = {}

    def normalize(self, event: Any) -> list[ResponseEventEnvelope]:
        payload = self._to_dict(event)
        event_name = payload.get("event") or getattr(event, "event", type(event).__name__)
        if event_name == "ExternalAgentRunResponseContentEvent":
            return self._normalize_external_event(payload)
        return self._normalize_raw_event(payload, parent_agent=None, spawned_by_call_id=None, mode=None)

    def _normalize_external_event(self, payload: dict[str, Any]) -> list[ResponseEventEnvelope]:
        metadata = self._to_dict(payload.get("metadata"))
        outer_tool_call_id = payload.get("tool_call_id") or metadata.get("tool_call_id")
        raw_event = self._to_dict(metadata.get("raw_event"))
        source = metadata.get("source") or ("subagent" if raw_event else None)
        event_name = metadata.get("event")
        if event_name == "SubagentStarted":
            agent = self._agent_ref(metadata, parent_agent=metadata.get("parent_agent_id"), spawned_by_call_id=outer_tool_call_id, mode=payload.get("mode") or metadata.get("mode"))
            return [self._emit("response.subagent.started", metadata.get("run_id") or metadata.get("agent_id") or "subagent-run", agent, {
                "subagent_id": agent.id,
                "subagent_name": agent.name,
                "parent_agent_id": agent.parent_agent_id,
                "spawned_by_call_id": outer_tool_call_id,
            })]
        if event_name == "SubagentCompleted":
            agent = self._agent_ref(metadata, parent_agent=metadata.get("parent_agent_id"), spawned_by_call_id=outer_tool_call_id, mode=payload.get("mode") or metadata.get("mode"))
            return [self._emit("response.subagent.completed", metadata.get("run_id") or metadata.get("agent_id") or "subagent-run", agent, {
                "subagent_id": agent.id,
                "subagent_name": agent.name,
                "parent_agent_id": agent.parent_agent_id,
                "spawned_by_call_id": outer_tool_call_id,
            })]
        nested = raw_event or metadata
        if not nested:
            return []
        parent_agent_id = metadata.get("parent_agent_id") or self.context.root_agent_id
        mode = payload.get("mode") or metadata.get("mode") or "subagent"
        if source == "subagent":
            return self._normalize_raw_event(
                nested,
                parent_agent=parent_agent_id,
                spawned_by_call_id=outer_tool_call_id,
                mode=mode,
            )
        return self._normalize_raw_event(nested, parent_agent=parent_agent_id, spawned_by_call_id=outer_tool_call_id, mode=mode)

    def _normalize_raw_event(
        self,
        payload: dict[str, Any],
        *,
        parent_agent: Optional[str],
        spawned_by_call_id: Optional[str],
        mode: Optional[str],
    ) -> list[ResponseEventEnvelope]:
        event_name = payload.get("event")
        agent = self._agent_ref(payload, parent_agent=parent_agent, spawned_by_call_id=spawned_by_call_id, mode=mode)
        run_id = payload.get("run_id") or f"run_{uuid4().hex}"
        out: list[ResponseEventEnvelope] = []

        if event_name == "RunStarted":
            out.append(self._emit("response.created", run_id, agent, {
                "status": "created",
                "model": payload.get("model"),
                "provider": payload.get("model_provider"),
            }))
            self._started = True
            return out

        if event_name == "ModelRequestStarted":
            if not self._started:
                out.append(self._emit("response.created", run_id, agent, {"status": "created"}))
                self._started = True
            out.append(self._emit("response.in_progress", run_id, agent, {"status": "in_progress"}))
            return out

        if event_name == "RunContent":
            content = payload.get("content") or ""
            reasoning = payload.get("reasoning_content") or ""
            if reasoning:
                item_id = self._ensure_reasoning_item(run_id, agent, out)
                out.append(self._emit("response.reasoning.delta", run_id, agent, {
                    "item_id": item_id,
                    "output_index": 1,
                    "delta": reasoning,
                }))
            if content:
                item_id = self._ensure_message_item(run_id, agent, out)
                out.append(self._emit("response.output_text.delta", run_id, agent, {
                    "item_id": item_id,
                    "output_index": 0,
                    "content_index": 0,
                    "delta": content,
                }))
            return out

        if event_name == "ToolCallStarted":
            tool = self._to_dict(payload.get("tool"))
            call_id = tool.get("tool_call_id") or payload.get("tool_call_id") or f"call_{uuid4().hex}"
            item_id = f"item_fc_{call_id}"
            name = tool.get("tool_name") or tool.get("name") or "unknown_tool"
            arguments = tool.get("tool_args") or {}
            self._function_items[call_id] = {"item_id": item_id, "name": name, "arguments": arguments}
            out.append(self._emit("response.output_item.added", run_id, agent, {
                "output_index": 2,
                "item": {
                    "id": item_id,
                    "type": "function_call",
                    "call_id": call_id,
                    "name": name,
                    "status": "in_progress",
                },
            }))
            out.append(self._emit("response.function_call_arguments.done", run_id, agent, {
                "item_id": item_id,
                "call_id": call_id,
                "output_index": 2,
                "name": name,
                "arguments": arguments,
            }))
            out.append(self._emit("response.tool_call.started", run_id, agent, {
                "call_id": call_id,
                "item_id": item_id,
                "name": name,
                "arguments": arguments,
            }))
            return out

        if event_name == "ToolCallCompleted":
            tool = self._to_dict(payload.get("tool"))
            call_id = tool.get("tool_call_id") or payload.get("tool_call_id") or f"call_{uuid4().hex}"
            info = self._function_items.get(call_id, {})
            item_id = info.get("item_id", f"item_fc_{call_id}")
            name = tool.get("tool_name") or tool.get("name") or info.get("name") or "unknown_tool"
            result = tool.get("result")
            out.append(self._emit("response.tool_call.completed", run_id, agent, {
                "call_id": call_id,
                "item_id": item_id,
                "name": name,
                "output": result,
                "output_text": self._result_preview(result),
            }))
            out.append(self._emit("response.output_item.done", run_id, agent, {
                "output_index": 2,
                "item": {
                    "id": item_id,
                    "type": "function_call",
                    "call_id": call_id,
                    "name": name,
                    "status": "completed",
                },
            }))
            return out

        if event_name == "ToolCallError":
            tool = self._to_dict(payload.get("tool"))
            call_id = tool.get("tool_call_id") or payload.get("tool_call_id") or f"call_{uuid4().hex}"
            info = self._function_items.get(call_id, {})
            item_id = info.get("item_id", f"item_fc_{call_id}")
            name = tool.get("tool_name") or tool.get("name") or info.get("name") or "unknown_tool"
            message = payload.get("message") or tool.get("tool_call_error") or "tool call failed"
            out.append(self._emit("response.tool_call.failed", run_id, agent, {
                "call_id": call_id,
                "item_id": item_id,
                "name": name,
                "error": {"code": "TOOL_ERROR", "message": str(message)},
            }))
            return out

        if event_name == "RunCompleted":
            out.extend(self._emit_done_events(run_id, agent))
            out.append(self._emit("response.completed", run_id, agent, {
                "status": "completed",
                "usage": payload.get("usage") or {},
            }))
            return out

        if event_name == "RunError":
            out.append(self._emit("response.failed", run_id, agent, {
                "status": "failed",
                "error": {
                    "code": "RUN_ERROR",
                    "message": str(payload.get("message") or payload.get("content") or "run failed"),
                },
            }))
            return out

        if event_name == "ModelRequestCompleted":
            return []

        return out

    def _emit_done_events(self, run_id: str, agent: AgentRef) -> list[ResponseEventEnvelope]:
        out: list[ResponseEventEnvelope] = []
        message_key = (run_id, agent.id)
        reasoning_key = (run_id, agent.id)
        if message_key in self._message_item_created:
            out.append(self._emit("response.output_text.done", run_id, agent, {
                "item_id": self._message_item_id(run_id, agent.id),
                "output_index": 0,
                "content_index": 0,
                "text": "",
            }))
            out.append(self._emit("response.output_item.done", run_id, agent, {
                "output_index": 0,
                "item": {
                    "id": self._message_item_id(run_id, agent.id),
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                },
            }))
        if reasoning_key in self._reasoning_item_created:
            out.append(self._emit("response.reasoning.done", run_id, agent, {
                "item_id": self._reasoning_item_id(run_id, agent.id),
                "output_index": 1,
                "text": "",
            }))
            out.append(self._emit("response.output_item.done", run_id, agent, {
                "output_index": 1,
                "item": {
                    "id": self._reasoning_item_id(run_id, agent.id),
                    "type": "reasoning",
                    "status": "completed",
                },
            }))
        return out

    def _ensure_message_item(self, run_id: str, agent: AgentRef, out: list[ResponseEventEnvelope]) -> str:
        key = (run_id, agent.id)
        item_id = self._message_item_id(run_id, agent.id)
        if key not in self._message_item_created:
            out.append(self._emit("response.output_item.added", run_id, agent, {
                "output_index": 0,
                "item": {
                    "id": item_id,
                    "type": "message",
                    "role": "assistant",
                    "status": "in_progress",
                },
            }))
            self._message_item_created.add(key)
        return item_id

    def _ensure_reasoning_item(self, run_id: str, agent: AgentRef, out: list[ResponseEventEnvelope]) -> str:
        key = (run_id, agent.id)
        item_id = self._reasoning_item_id(run_id, agent.id)
        if key not in self._reasoning_item_created:
            out.append(self._emit("response.output_item.added", run_id, agent, {
                "output_index": 1,
                "item": {
                    "id": item_id,
                    "type": "reasoning",
                    "status": "in_progress",
                },
            }))
            self._reasoning_item_created.add(key)
        return item_id

    def _message_item_id(self, run_id: str, agent_id: str) -> str:
        return f"item_msg_{agent_id}_{run_id}"

    def _reasoning_item_id(self, run_id: str, agent_id: str) -> str:
        return f"item_reason_{agent_id}_{run_id}"

    def _emit(self, event_type: ResponseEventType, run_id: str, agent: AgentRef, data: dict[str, Any]) -> ResponseEventEnvelope:
        envelope = ResponseEventEnvelope(
            type=event_type,
            response_id=self.context.response_id,
            session_id=self.context.session_id,
            run_id=run_id,
            sequence=self.sequence,
            agent=agent,
            data=data,
        )
        self.sequence += 1
        return envelope

    def _agent_ref(
        self,
        payload: dict[str, Any],
        *,
        parent_agent: Optional[str],
        spawned_by_call_id: Optional[str],
        mode: Optional[str],
    ) -> AgentRef:
        agent_id = str(payload.get("agent_id") or self.context.root_agent_id or "unknown-agent")
        agent_name = str(payload.get("agent_name") or self.context.root_agent_name or agent_id)
        is_root = self.context.root_agent_id is None or agent_id == self.context.root_agent_id
        kind = "orchestrator" if is_root and parent_agent is None else ("router" if mode == "router" else "subagent")
        role = "lead" if kind == "orchestrator" else agent_name
        return AgentRef(
            id=agent_id,
            name=agent_name,
            kind=kind,
            mode=cast(AgentModeType, mode or "subagent"),
            parent_agent_id=parent_agent,
            spawned_by_call_id=spawned_by_call_id,
            role=role,
        )

    def _to_dict(self, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if hasattr(value, "to_dict"):
            try:
                data = value.to_dict()
                return data if isinstance(data, dict) else {}
            except Exception:
                pass
        if hasattr(value, "model_dump"):
            try:
                data = value.model_dump()
                return data if isinstance(data, dict) else {}
            except Exception:
                pass
        if is_dataclass(value) and not isinstance(value, type):
            try:
                return asdict(value)
            except Exception:
                return {}
        if hasattr(value, "__dict__"):
            try:
                return {
                    k: v for k, v in vars(value).items() if not k.startswith("_")
                }
            except Exception:
                return {}
        return {}

    def _result_preview(self, result: Any) -> str:
        if result is None:
            return ""
        if isinstance(result, str):
            return result
        try:
            text = str(result)
            return text if len(text) <= 500 else text[:497] + "..."
        except Exception:
            return ""
