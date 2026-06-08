from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Iterator, Protocol, TextIO

from protocol.extra_info import ExtraInfo

from core.orchestrator import Orchestrator
from protocol.response_events import ResponseEventEnvelope

from .bootstrap import bootstrap_environment
from .history import list_history_sessions, read_latest_history_for_session, write_history_entry
from .renderer import EventRenderer
from .slash_commands import SlashCommandResult, SlashCommandSpec, get_slash_suggestions, handle_slash_command


class OrchestratorFactory(Protocol):
    def __call__(self) -> OrchestratorLike: ...


class OrchestratorLike(Protocol):
    def run(
        self, message: str, extra: ExtraInfo | None = None
    ) -> AsyncIterator[ResponseEventEnvelope | object]: ...


@dataclass
class CliSession:
    renderer: EventRenderer
    orchestrator_factory: OrchestratorFactory
    command_context: dict[str, str]
    running: bool = True


@dataclass
class InputState:
    prompt: str
    suggestions: list[SlashCommandSpec]
    selected_index: int = 0


@dataclass
class HeadlessRunResult:
    mode: str
    prompt: str
    exit_code: int
    events: list[dict[str, object]]
    message_count: int
    tool_count: int
    subagent_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "prompt": self.prompt,
            "exit_code": self.exit_code,
            "message_count": self.message_count,
            "tool_count": self.tool_count,
            "subagent_count": self.subagent_count,
            "events": self.events,
        }


def default_orchestrator_factory() -> OrchestratorLike:
    return Orchestrator()


def format_sse_event(event_name: str, payload: dict[str, object]) -> str:
    return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@contextmanager
def quiet_third_party_noise() -> Iterator[None]:
    previous_disable = logging.root.manager.disable
    try:
        logging.disable(logging.INFO)
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=r".*SSE as a standalone transport is deprecated.*",
            )
            yield
    finally:
        logging.disable(previous_disable)


def run_once(
    *,
    prompt: str,
    renderer: EventRenderer,
    orchestrator_factory: OrchestratorFactory,
    resume_session_id: str | None = None,
) -> int:
    prompt = prompt.strip()
    if not prompt:
        raise ValueError("Prompt cannot be empty")

    effective_resume_session_id = resume_session_id or os.environ.get("SESSION_ID")

    slash_result = handle_slash_command(prompt, renderer, _command_context())
    if slash_result.handled:
        return slash_result.exit_code

    if effective_resume_session_id:
        _resume_session_events(renderer, effective_resume_session_id)

    events = asyncio.run(_stream_prompt(prompt, renderer, orchestrator_factory()))
    write_history_entry(prompt=prompt, mode="run", events=events)
    return 0


def run_headless_once(
    *,
    prompt: str,
    orchestrator_factory: OrchestratorFactory,
    resume_session_id: str | None = None,
) -> HeadlessRunResult:
    prompt = prompt.strip()
    if not prompt:
        raise ValueError("Prompt cannot be empty")

    effective_resume_session_id = resume_session_id or os.environ.get("SESSION_ID")

    events: list[dict[str, object]] = []
    message_count = 0
    tool_count = 0
    subagent_count = 0

    if effective_resume_session_id:
        try:
            restored = read_latest_history_for_session(effective_resume_session_id)
            raw_events = restored.get("events")
            if isinstance(raw_events, list):
                for raw_event in raw_events:
                    if isinstance(raw_event, dict):
                        events.append(raw_event)
        except FileNotFoundError:
            pass

    async def _collect() -> None:
        nonlocal message_count, tool_count, subagent_count
        async for event in orchestrator_factory().run(prompt, extra=None):
            normalized = (
                event
                if isinstance(event, ResponseEventEnvelope)
                else ResponseEventEnvelope.model_validate(event)
            )
            payload = normalized.model_dump()
            events.append(payload)
            if normalized.type.startswith("response.output_text") or normalized.type == "response.created":
                message_count += 1
            if normalized.type.startswith("response.tool_call"):
                tool_count += 1
            if normalized.type.startswith("response.subagent"):
                subagent_count += 1

    with quiet_third_party_noise():
        asyncio.run(_collect())
    write_history_entry(prompt=prompt, mode="headless", events=events)
    return HeadlessRunResult(
        mode="headless",
        prompt=prompt,
        exit_code=0,
        events=events,
        message_count=message_count,
        tool_count=tool_count,
        subagent_count=subagent_count,
    )


def print_headless_result(result: HeadlessRunResult, *, stdout: TextIO) -> None:
    stdout.write(json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n")
    stdout.flush()


def stream_headless_once(
    *,
    prompt: str,
    orchestrator_factory: OrchestratorFactory,
    stdout: TextIO,
    resume_session_id: str | None = None,
) -> HeadlessRunResult:
    prompt = prompt.strip()
    if not prompt:
        raise ValueError("Prompt cannot be empty")

    effective_resume_session_id = resume_session_id or os.environ.get("SESSION_ID")

    events: list[dict[str, object]] = []
    message_count = 0
    tool_count = 0
    subagent_count = 0

    if effective_resume_session_id:
        try:
            restored = read_latest_history_for_session(effective_resume_session_id)
            raw_events = restored.get("events")
            if isinstance(raw_events, list):
                for raw_event in raw_events:
                    if not isinstance(raw_event, dict):
                        continue
                    events.append(raw_event)
                    event_type = raw_event.get("type")
                    if isinstance(event_type, str):
                        stdout.write(format_sse_event(event_type, raw_event))
                        stdout.flush()
        except FileNotFoundError:
            pass

    async def _collect() -> None:
        nonlocal message_count, tool_count, subagent_count
        async for event in orchestrator_factory().run(prompt, extra=None):
            normalized = (
                event
                if isinstance(event, ResponseEventEnvelope)
                else ResponseEventEnvelope.model_validate(event)
            )
            payload = normalized.model_dump()
            events.append(payload)
            if normalized.type.startswith("response.output_text") or normalized.type == "response.created":
                message_count += 1
            if normalized.type.startswith("response.tool_call"):
                tool_count += 1
            if normalized.type.startswith("response.subagent"):
                subagent_count += 1
            stdout.write(format_sse_event(normalized.type, payload))
            stdout.flush()

    with quiet_third_party_noise():
        asyncio.run(_collect())
    write_history_entry(prompt=prompt, mode="headless_stream", events=events)
    result = HeadlessRunResult(
        mode="headless",
        prompt=prompt,
        exit_code=0,
        events=events,
        message_count=message_count,
        tool_count=tool_count,
        subagent_count=subagent_count,
    )
    stdout.write(format_sse_event("response.summary", result.to_dict()))
    stdout.flush()
    return result


def run_chat_loop(
    *,
    renderer: EventRenderer,
    orchestrator_factory: OrchestratorFactory,
    input_stream: TextIO,
) -> int:
    session = CliSession(
        renderer=renderer,
        orchestrator_factory=orchestrator_factory,
        command_context=_command_context(),
    )
    renderer.begin_chat()
    renderer.print_system("Interactive mode. Type /help for commands, /exit to quit.")

    while session.running:
        try:
            line = _read_chat_input(session, input_stream)
        except KeyboardInterrupt:
            renderer.print_system("Interrupted. Exiting.")
            return 130

        if line == "":
            return 0

        prompt = line.strip()
        if not prompt:
            continue

        if prompt.startswith("/"):
            suggestions = get_slash_suggestions(prompt)
            exact = any(spec.command == prompt for spec in suggestions)
            if prompt == "/resume" or prompt.startswith("/resume ") or prompt.startswith("/history show "):
                exact = True
            if suggestions and not exact and not renderer.live_layout:
                renderer.print_suggestions(prompt, [(spec.command, spec.description) for spec in suggestions[:6]])
                continue

        renderer.record_user_prompt(prompt)

        slash_result = handle_slash_command(prompt, renderer, session.command_context)
        if slash_result.handled:
            if slash_result.restore_session_id:
                _restore_history_session(session, slash_result.restore_session_id)
            if slash_result.should_exit:
                return slash_result.exit_code
            continue

        try:
            events = asyncio.run(_stream_prompt(prompt, renderer, session.orchestrator_factory()))
            write_history_entry(prompt=prompt, mode="chat", events=events)
        except KeyboardInterrupt:
            renderer.print_system("Interrupted current run.")
            return 130

    return 0


async def _stream_prompt(
    prompt: str,
    renderer: EventRenderer,
    orchestrator: OrchestratorLike,
) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    async for event in orchestrator.run(prompt, extra=None):
        normalized = (
            event
            if isinstance(event, ResponseEventEnvelope)
            else ResponseEventEnvelope.model_validate(event)
        )
        events.append(normalized.model_dump())
        renderer.render(normalized)
    renderer.finish()
    return events


def _command_context() -> dict[str, str]:
    return {
        "session_id": os.environ.get("SESSION_ID") or os.environ.get("RECORD_ID", "unknown"),
        "userspace": os.environ.get("USERSPACE", "unknown"),
        "workspace": os.environ.get("WORKSPACE", "unknown"),
        "runspace": os.environ.get("RUNSPACE", "unknown"),
    }


def _restore_history_session(session: CliSession, restore_session_id: str) -> None:
    _resume_session_events(session.renderer, restore_session_id)
    session.command_context = _command_context()


def _resume_session_events(renderer: EventRenderer, restore_session_id: str) -> None:
    try:
        record = read_latest_history_for_session(restore_session_id, os.environ.get("USERSPACE"))
    except FileNotFoundError:
        return
    prompt = record.get("prompt")
    if isinstance(prompt, str) and prompt.strip():
        renderer.record_user_prompt(prompt)
    raw_events = record.get("events")
    if isinstance(raw_events, list):
        for raw_event in raw_events:
            if not isinstance(raw_event, dict):
                continue
            renderer.render(ResponseEventEnvelope.model_validate(raw_event))
        renderer.finish()


def announce_mcp_health(renderer: EventRenderer) -> None:
    from .mcp import check_mcp_servers, format_mcp_status_lines

    if renderer.json_mode:
        return

    with quiet_third_party_noise():
        for line in format_mcp_status_lines(check_mcp_servers(os.environ.get("WORKSPACE"))):
            renderer.print_system(line)


def _read_chat_input(session: CliSession, input_stream: TextIO) -> str:
    session.renderer.prepare_for_input()
    if session.renderer.live_layout and _supports_live_key_input(input_stream):
        return _read_live_input(session)
    line = input_stream.readline()
    if line:
        session.renderer.clear_input_state()
    return line


def _supports_live_key_input(input_stream: TextIO) -> bool:
    if os.name != "nt":
        return False
    if input_stream is not sys.stdin:
        return False
    return bool(getattr(input_stream, "isatty", lambda: False)())


def _read_live_input(session: CliSession) -> str:
    import msvcrt

    state = InputState(prompt="", suggestions=[])
    session.renderer.update_input_state(
        state.prompt,
        [spec.command for spec in state.suggestions],
        state.selected_index,
        [spec.description for spec in state.suggestions],
    )

    while True:
        key = msvcrt.getwch()
        if key in {"\r", "\n"}:
            if state.suggestions and state.prompt.startswith("/"):
                selected_command = state.suggestions[state.selected_index].command
                state.prompt = selected_command
                session.renderer.update_input_state(state.prompt, [state.prompt], 0, [state.suggestions[state.selected_index].description])
                session.renderer.clear_input_state()
                return selected_command + "\n"
            session.renderer.clear_input_state()
            return state.prompt + "\n"
        if key == "\t":
            if state.suggestions:
                state.prompt = state.suggestions[state.selected_index].command
                state.suggestions = _suggestion_commands(state.prompt, session.command_context)
                state.selected_index = 0
                session.renderer.update_input_state(
                    state.prompt,
                    [spec.command for spec in state.suggestions],
                    state.selected_index,
                    [spec.description for spec in state.suggestions],
                )
            continue
        if key == "\x03":
            raise KeyboardInterrupt
        if key == "\x08":
            state.prompt = state.prompt[:-1]
            state.suggestions = _suggestion_commands(state.prompt, session.command_context)
            state.selected_index = min(state.selected_index, max(0, len(state.suggestions) - 1))
            session.renderer.update_input_state(
                state.prompt,
                [spec.command for spec in state.suggestions],
                state.selected_index,
                [spec.description for spec in state.suggestions],
            )
            continue
        if key in {"\x00", "\xe0"}:
            special = msvcrt.getwch()
            if special == "H" and state.suggestions:
                state.selected_index = (state.selected_index - 1) % len(state.suggestions)
            elif special == "P" and state.suggestions:
                state.selected_index = (state.selected_index + 1) % len(state.suggestions)
            session.renderer.update_input_state(
                state.prompt,
                [spec.command for spec in state.suggestions],
                state.selected_index,
                [spec.description for spec in state.suggestions],
            )
            continue
        if key == "\x1b":
            state.suggestions = []
            state.selected_index = 0
            session.renderer.update_input_state(state.prompt, [], state.selected_index, [])
            continue
        if key.isprintable():
            state.prompt += key
            state.suggestions = _suggestion_commands(state.prompt, session.command_context)
            state.selected_index = 0
            session.renderer.update_input_state(
                state.prompt,
                [spec.command for spec in state.suggestions],
                state.selected_index,
                [spec.description for spec in state.suggestions],
            )


def _suggestion_commands(prompt: str, command_context: dict[str, str] | None = None) -> list[SlashCommandSpec]:
    suggestions = list(get_slash_suggestions(prompt))
    normalized = prompt.strip()
    if not normalized.startswith("/resume"):
        return suggestions

    userspace = (command_context or {}).get("userspace")
    session_entries = list_history_sessions(userspace, limit=8)
    target = normalized[len("/resume") :].strip().lower()

    dynamic_specs: list[SlashCommandSpec] = []
    for index, entry in enumerate(session_entries, start=1):
        session_id = str(entry.get("session_id") or "").strip()
        if not session_id:
            continue
        if target and target not in session_id.lower() and target not in str(index):
            continue
        prompt_preview = str(entry.get("prompt") or "").replace("\n", " ").strip()
        prompt_preview = prompt_preview[:36] + ("..." if len(prompt_preview) > 36 else "")
        created_at = str(entry.get("created_at") or "unknown")
        dynamic_specs.append(
            SlashCommandSpec(
                command=f"/resume {session_id}",
                description=f"Resume {session_id} · {created_at} · {prompt_preview}".strip(),
            )
        )
    return dynamic_specs or suggestions
