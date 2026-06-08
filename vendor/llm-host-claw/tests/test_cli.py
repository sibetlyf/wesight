from __future__ import annotations

import io
import json
from pathlib import Path
import importlib
import os
import runpy

import pytest

from moma_cli.commands import run_chat_loop, run_headless_once, run_once, stream_headless_once
from moma_cli.history import list_history_entries, read_history_entry
from moma_cli.mcp import import_mcp_config, import_mcp_payload, list_mcp_servers, write_mcp_server
from moma_cli.main import main
from moma_cli.renderer import ANSI_BLUE, ANSI_CYAN, ANSI_GREEN, ANSI_RED, ANSI_YELLOW, EventRenderer
from moma_cli.sandbox import ensure_within_root
from moma_cli.slash_commands import get_slash_suggestions, handle_slash_command
from protocol.response_events import AgentRef, ResponseEventEnvelope


class FakeOrchestrator:
    def __init__(self, events: list[ResponseEventEnvelope]):
        self._events = events

    async def run(self, message: str, extra=None):
        for event in self._events:
            yield event


def make_event(event_type: str, sequence: int, data: dict, *, agent_name: str = "Orchestrator") -> ResponseEventEnvelope:
    return ResponseEventEnvelope(
        type=event_type,
        response_id="resp_test",
        session_id="session_test",
        run_id="run_test",
        sequence=sequence,
        agent=AgentRef(id="orch_1", name=agent_name, kind="orchestrator", mode="subagent"),
        data=data,
    )


@pytest.fixture
def cli_config_file(tmp_path: Path) -> Path:
    config_path = tmp_path / "orchestrator.json"
    config_path.write_text(
        json.dumps(
            {
                "model": {
                    "id": "test-model",
                    "provider": "openai",
                    "base_url": "https://example.com/v1",
                    "api_key": "EMPTY",
                },
                "toolkits": [],
            }
        ),
        encoding="utf-8",
    )
    return config_path


@pytest.fixture
def cli_config_with_mcp_file(tmp_path: Path) -> Path:
    config_path = tmp_path / "orchestrator-with-mcp.json"
    config_path.write_text(
        json.dumps(
            {
                "model": {
                    "id": "test-model",
                    "provider": "openai",
                    "base_url": "https://example.com/v1",
                    "api_key": "EMPTY",
                },
                "toolkits": [],
                "mcpServers": {
                    "exa": {
                        "url": "https://example.com/sse",
                        "transport": "sse",
                        "timeout": 15
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return config_path


def test_renderer_human_mode_displays_message_tool_and_subagent() -> None:
    output = io.StringIO()
    renderer = EventRenderer(stdout=output, stderr=io.StringIO())

    events = [
        make_event("response.created", 0, {"status": "created"}),
        make_event(
            "response.output_text.delta",
            1,
            {"item_id": "item_msg_1", "output_index": 0, "content_index": 0, "delta": "Hello"},
        ),
        make_event(
            "response.output_text.done",
            2,
            {"item_id": "item_msg_1", "output_index": 0, "content_index": 0, "text": "Hello"},
        ),
        make_event("response.tool_call.started", 3, {"name": "shell"}),
        make_event("response.tool_call.completed", 4, {"name": "shell", "output_text": "ok"}),
        make_event("response.subagent.started", 5, {"subagent_name": "writer"}),
        make_event("response.subagent.completed", 6, {"subagent_name": "writer"}),
        make_event("response.completed", 7, {"status": "completed"}),
    ]

    for event in events:
        renderer.render(event)
    renderer.finish()

    rendered = output.getvalue()
    assert "[Orchestrator] started" in rendered
    assert "[Orchestrator] " in rendered
    assert "Hello" in rendered
    assert "[tool] shell started" in rendered
    assert "[tool] shell completed: ok" in rendered
    assert "[subagent] writer started" in rendered
    assert "[subagent] writer completed" in rendered
    assert ANSI_CYAN in rendered
    assert ANSI_YELLOW in rendered


def test_get_slash_suggestions_returns_matching_commands() -> None:
    suggestions = get_slash_suggestions("/mcp")

    commands = [spec.command for spec in suggestions]
    assert "/mcp" in commands
    assert "/mcp list" in commands
    assert "/mcp check" in commands
    descriptions = {spec.command: spec.description for spec in suggestions}
    assert descriptions["/mcp check"] == "Probe configured MCP servers"


def test_get_slash_suggestions_includes_history_restore_commands() -> None:
    suggestions = get_slash_suggestions("/h")
    commands = [spec.command for spec in suggestions]
    assert "/history" in commands
    assert "/history list" in commands
    suggestions = get_slash_suggestions("/r")
    commands = [spec.command for spec in suggestions]
    assert "/resume" in commands


def test_get_slash_suggestions_expands_resume_sessions_from_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    userspace = tmp_path / "userspace"
    history_dir = userspace / "sessions" / "session-a" / "history"
    history_dir.mkdir(parents=True)
    (history_dir / "hist_demo.json").write_text(
        json.dumps(
            {
                "version": 1,
                "entry_id": "hist_demo",
                "created_at": "2026-06-05T00:00:00+00:00",
                "session_id": "session-a",
                "workspace": str(userspace / "sessions" / "session-a"),
                "mode": "chat",
                "prompt": "hello history",
                "assistant_text_preview": "preview text",
                "events": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("USERSPACE", str(userspace))

    suggestions = get_slash_suggestions("/resume s")

    commands = [spec.command for spec in suggestions]
    assert "/resume session-a" in commands
    details = {spec.command: spec.description for spec in suggestions}
    assert "hello history" in details["/resume session-a"]


def test_handle_resume_command_accepts_dynamic_session_suggestion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    userspace = tmp_path / "userspace"
    history_dir = userspace / "sessions" / "session-a" / "history"
    history_dir.mkdir(parents=True)
    (history_dir / "hist_demo.json").write_text(
        json.dumps(
            {
                "version": 1,
                "entry_id": "hist_demo",
                "created_at": "2026-06-05T00:00:00+00:00",
                "session_id": "session-a",
                "workspace": str(userspace / "sessions" / "session-a"),
                "mode": "chat",
                "prompt": "hello history",
                "assistant_text_preview": "preview text",
                "events": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    renderer = EventRenderer(stdout=io.StringIO(), stderr=io.StringIO())

    result = handle_slash_command("/resume session-a", renderer, {"userspace": str(userspace)})

    assert result.handled is True
    assert result.restore_session_id == "session-a"


def test_renderer_live_layout_renders_logo_subagent_and_todos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = io.StringIO()
    renderer = EventRenderer(stdout=output, stderr=io.StringIO(), force_live_layout=True)

    workspace = tmp_path / "workspace"
    todo_dir = workspace / "todo"
    todo_dir.mkdir(parents=True)
    (todo_dir / "plan.json").write_text(
        json.dumps(
            {
                "mission_id": 1,
                "title": "Ship CLI UI",
                "steps": [
                    {"step_id": 1, "title": "Render layout", "status": "running"},
                    {"step_id": 2, "title": "Verify tests", "status": "pending"},
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("WORKSPACE", str(workspace))

    renderer.begin_chat()
    renderer.record_user_prompt("hello")
    renderer.render(
        ResponseEventEnvelope(
            type="response.subagent.started",
            response_id="resp_test",
            session_id="session_test",
            run_id="run_sub",
            sequence=0,
            agent=AgentRef(
                id="sub_1",
                name="writer",
                kind="subagent",
                mode="subagent",
                parent_agent_id="orch_1",
            ),
            data={"subagent_name": "writer"},
        )
    )
    renderer.render(
        ResponseEventEnvelope(
            type="response.output_text.delta",
            response_id="resp_test",
            session_id="session_test",
            run_id="run_sub",
            sequence=1,
            agent=AgentRef(
                id="sub_1",
                name="writer",
                kind="subagent",
                mode="subagent",
                parent_agent_id="orch_1",
            ),
            data={"item_id": "item_sub", "delta": "working"},
        )
    )
    renderer.prepare_for_input()

    rendered = output.getvalue()
    assert "MOMA" in rendered
    assert "Subagents" in rendered
    assert "writer [running]" in rendered
    assert "metadata:" in rendered
    assert "kind=subagent" in rendered
    assert "output:" in rendered
    assert "log:" in rendered
    assert "· started" in rendered
    assert "· working" in rendered
    assert "Todos" in rendered
    assert "Ship CLI UI" in rendered
    assert "Render layout" in rendered
    assert "MOMA >" in rendered
    assert "Chat" in rendered
    assert "Enter to send, /help for commands" in rendered
    assert "YOU" in rendered
    assert "SUBAGENT" in rendered
    assert "MOMA > hello" not in rendered
    assert "┌" in rendered
    assert "└" in rendered
    assert ANSI_BLUE in rendered
    assert ANSI_GREEN in rendered or ANSI_YELLOW in rendered


def test_renderer_live_layout_shows_slash_suggestions() -> None:
    output = io.StringIO()
    renderer = EventRenderer(stdout=output, stderr=io.StringIO(), force_live_layout=True)

    renderer.begin_chat()
    renderer.update_input_state(
        "/m",
        ["/mcp", "/mcp list", "/mcp check"],
        1,
        ["List configured MCP servers", "List configured MCP servers", "Probe configured MCP servers"],
    )

    rendered = output.getvalue()
    assert "Slash Commands" in rendered
    assert "/mcp" in rendered
    assert "/mcp list" in rendered
    assert "▶ /mcp list" in rendered
    assert "Probe configured MCP servers" in rendered


def test_renderer_live_layout_shows_resume_session_suggestions() -> None:
    output = io.StringIO()
    renderer = EventRenderer(stdout=output, stderr=io.StringIO(), force_live_layout=True)

    renderer.begin_chat()
    renderer.update_input_state(
        "/resume s",
        ["/resume session-a"],
        0,
        ["Resume session-a · 2026-06-05T00:00:00+00:00 · hello history"],
    )

    rendered = output.getvalue()
    assert "Resume Sessions" in rendered
    assert "choose, Enter restore, Esc close" in rendered
    assert "/resume session-a" in rendered
    assert "Resume session-a" in rendered


def test_renderer_live_layout_uses_distinct_role_colors() -> None:
    output = io.StringIO()
    renderer = EventRenderer(stdout=output, stderr=io.StringIO(), force_live_layout=True)

    renderer.begin_chat()
    renderer.record_user_prompt("hello")
    renderer.render(make_event("response.output_text.delta", 1, {"item_id": "orch_item", "delta": "orchestrator"}))
    renderer.render(
        ResponseEventEnvelope(
            type="response.reasoning.done",
            response_id="resp_test",
            session_id="session_test",
            run_id="run_sub",
            sequence=2,
            agent=AgentRef(id="sub_1", name="writer", kind="subagent", mode="subagent", parent_agent_id="orch_1"),
            data={"item_id": "reasoning_1"},
        )
    )
    renderer._reasoning_buffers["reasoning_1"] = ["thinking"]
    renderer.render(
        ResponseEventEnvelope(
            type="response.reasoning.done",
            response_id="resp_test",
            session_id="session_test",
            run_id="run_sub",
            sequence=3,
            agent=AgentRef(id="sub_1", name="writer", kind="subagent", mode="subagent", parent_agent_id="orch_1"),
            data={"item_id": "reasoning_1"},
        )
    )
    renderer.render(
        ResponseEventEnvelope(
            type="response.tool_call.started",
            response_id="resp_test",
            session_id="session_test",
            run_id="run_sub",
            sequence=4,
            agent=AgentRef(id="sub_1", name="writer", kind="subagent", mode="subagent", parent_agent_id="orch_1"),
            data={"name": "shell"},
        )
    )
    renderer.render(
        ResponseEventEnvelope(
            type="response.failed",
            response_id="resp_test",
            session_id="session_test",
            run_id="run_sub",
            sequence=5,
            agent=AgentRef(id="sub_1", name="writer", kind="subagent", mode="subagent", parent_agent_id="orch_1"),
            data={"error": {"message": "boom"}},
        )
    )

    rendered = output.getvalue()
    assert ANSI_BLUE in rendered
    assert ANSI_CYAN in rendered
    assert ANSI_GREEN in rendered
    assert ANSI_YELLOW in rendered
    assert ANSI_RED in rendered


def test_renderer_live_layout_highlights_active_subagent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = io.StringIO()
    renderer = EventRenderer(stdout=output, stderr=io.StringIO(), force_live_layout=True)

    workspace = tmp_path / "workspace"
    (workspace / "todo").mkdir(parents=True)
    monkeypatch.setenv("WORKSPACE", str(workspace))

    renderer.begin_chat()
    renderer.render(
        ResponseEventEnvelope(
            type="response.subagent.started",
            response_id="resp_test",
            session_id="session_test",
            run_id="run_sub",
            sequence=0,
            agent=AgentRef(id="sub_1", name="writer", kind="subagent", mode="subagent", parent_agent_id="orch_1"),
            data={"subagent_name": "writer"},
        )
    )
    renderer.render(
        ResponseEventEnvelope(
            type="response.output_text.delta",
            response_id="resp_test",
            session_id="session_test",
            run_id="run_sub",
            sequence=1,
            agent=AgentRef(id="sub_1", name="writer", kind="subagent", mode="subagent", parent_agent_id="orch_1"),
            data={"item_id": "item_sub", "delta": "working"},
        )
    )

    rendered = output.getvalue()
    assert "● writer [running]" in rendered
    assert "active now" in rendered
    assert "working" in rendered


def test_run_chat_loop_prints_suggestions_for_partial_slash_command() -> None:
    output = io.StringIO()
    renderer = EventRenderer(stdout=output, stderr=io.StringIO())
    input_stream = io.StringIO("/m\n/exit\n")

    exit_code = run_chat_loop(
        renderer=renderer,
        orchestrator_factory=lambda: FakeOrchestrator([]),
        input_stream=input_stream,
    )

    assert exit_code == 0
    rendered = output.getvalue()
    assert "Suggestions for /m:" in rendered
    assert "/mcp" in rendered
    assert "List configured MCP servers" in rendered
    assert "Bye." in rendered


def test_renderer_live_layout_clears_screen_only_once_for_streaming() -> None:
    output = io.StringIO()
    renderer = EventRenderer(stdout=output, stderr=io.StringIO(), force_live_layout=True)

    renderer.begin_chat()
    renderer.render(
        ResponseEventEnvelope(
            type="response.output_text.delta",
            response_id="resp_test",
            session_id="session_test",
            run_id="run_test",
            sequence=0,
            agent=AgentRef(id="orch_1", name="Orchestrator", kind="orchestrator", mode="subagent"),
            data={"item_id": "item_msg_1", "delta": "Hel"},
        )
    )
    renderer.render(
        ResponseEventEnvelope(
            type="response.output_text.delta",
            response_id="resp_test",
            session_id="session_test",
            run_id="run_test",
            sequence=1,
            agent=AgentRef(id="orch_1", name="Orchestrator", kind="orchestrator", mode="subagent"),
            data={"item_id": "item_msg_1", "delta": "lo"},
        )
    )

    rendered = output.getvalue()
    assert rendered.count("\x1b[2J\x1b[H") == 1
    assert "\x1b[H" in rendered
    assert "\x1b[J" in rendered


def test_renderer_live_layout_throttles_streaming_redraws() -> None:
    output = io.StringIO()
    renderer = EventRenderer(stdout=output, stderr=io.StringIO(), force_live_layout=True)

    renderer.begin_chat()
    for index, chunk in enumerate(["a", "b", "c", "d", "e"]):
        renderer.render(
            ResponseEventEnvelope(
                type="response.output_text.delta",
                response_id="resp_test",
                session_id="session_test",
                run_id="run_test",
                sequence=index,
                agent=AgentRef(id="orch_1", name="Orchestrator", kind="orchestrator", mode="subagent"),
                data={"item_id": "item_msg_1", "delta": chunk},
            )
        )

    rendered = output.getvalue()
    assert rendered.count("\x1b[2J\x1b[H") == 1
    assert rendered.count("\x1b[H") == 3


def test_renderer_live_layout_columns_align_visible_width(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = io.StringIO()
    renderer = EventRenderer(stdout=output, stderr=io.StringIO(), force_live_layout=True)

    workspace = tmp_path / "workspace"
    todo_dir = workspace / "todo"
    todo_dir.mkdir(parents=True)
    (todo_dir / "plan.json").write_text(
        json.dumps({"mission_id": 1, "title": "Align", "steps": []}),
        encoding="utf-8",
    )
    monkeypatch.setenv("WORKSPACE", str(workspace))

    renderer.begin_chat()
    renderer.record_user_prompt("align test")
    rendered = output.getvalue()

    layout_lines = [line for line in rendered.splitlines() if "│" in line and "MOMA" not in line and "Chat" not in line]
    assert layout_lines
    for line in layout_lines:
        stripped = renderer._strip_ansi(line)
        divider = stripped.find(" │ ")
        assert divider > 0
        left = stripped[:divider]
        right = stripped[divider + 3 :]
        assert len(left) >= 40
        assert len(right) >= 24


def test_run_headless_once_returns_structured_result() -> None:
    events = [
        make_event("response.created", 0, {"status": "created"}),
        make_event(
            "response.output_text.delta",
            1,
            {"item_id": "item_msg_1", "output_index": 0, "content_index": 0, "delta": "Hello"},
        ),
        make_event("response.tool_call.started", 2, {"name": "shell"}),
        make_event("response.subagent.started", 3, {"subagent_name": "writer"}),
        make_event("response.completed", 4, {"status": "completed"}),
    ]

    result = run_headless_once(prompt="hello", orchestrator_factory=lambda: FakeOrchestrator(events))

    payload = result.to_dict()
    assert payload["mode"] == "headless"
    assert payload["prompt"] == "hello"
    assert payload["exit_code"] == 0
    assert payload["message_count"] >= 2
    assert payload["tool_count"] == 1
    assert payload["subagent_count"] == 1
    assert len(payload["events"]) == len(events)


def test_run_once_persists_history_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = tmp_path / "workspace"
    runspace = workspace / "runs"
    workspace.mkdir(parents=True)
    runspace.mkdir(parents=True)
    monkeypatch.setenv("WORKSPACE", str(workspace))
    monkeypatch.setenv("RUNSPACE", str(runspace))
    monkeypatch.setenv("USERSPACE", str(tmp_path / "userspace"))
    monkeypatch.setenv("SESSION_ID", "session-history")

    output = io.StringIO()
    renderer = EventRenderer(stdout=output, stderr=io.StringIO())
    events = [
        make_event("response.created", 0, {"status": "created"}),
        make_event("response.output_text.delta", 1, {"item_id": "item_msg_1", "delta": "hello"}),
        make_event("response.completed", 2, {"status": "completed"}),
    ]

    exit_code = run_once(prompt="hello", renderer=renderer, orchestrator_factory=lambda: FakeOrchestrator(events))

    assert exit_code == 0
    entries = list_history_entries(str(tmp_path / "userspace"))
    assert len(entries) == 0  # userspace glob should ignore unrelated base path when workspace is direct
    history_files = list((workspace / "history").glob("*.json"))
    assert len(history_files) == 1
    record = json.loads(history_files[0].read_text(encoding="utf-8"))
    assert record["prompt"] == "hello"
    assert record["mode"] == "run"
    assert len(record["events"]) == len(events)


def test_run_headless_once_persists_history_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    userspace = tmp_path / "userspace"
    workspace = userspace / "sessions" / "session-headless"
    runspace = workspace / "runs"
    runspace.mkdir(parents=True)
    monkeypatch.setenv("WORKSPACE", str(workspace))
    monkeypatch.setenv("RUNSPACE", str(runspace))
    monkeypatch.setenv("USERSPACE", str(userspace))
    monkeypatch.setenv("SESSION_ID", "session-headless")

    events = [
        make_event("response.created", 0, {"status": "created"}),
        make_event("response.output_text.delta", 1, {"item_id": "item_msg_1", "delta": "hello"}),
        make_event("response.completed", 2, {"status": "completed"}),
    ]

    result = run_headless_once(prompt="hello", orchestrator_factory=lambda: FakeOrchestrator(events))

    assert result.exit_code == 0
    entries = list_history_entries(str(userspace))
    assert len(entries) == 1
    record = read_history_entry(str(entries[0]["entry_id"]), str(userspace))
    assert record["mode"] == "headless"
    assert record["prompt"] == "hello"


def test_run_chat_loop_supports_resume_by_session_selection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    userspace = tmp_path / "userspace"
    workspace = userspace / "sessions" / "session-a"
    runspace = workspace / "runs"
    runspace.mkdir(parents=True)
    monkeypatch.setenv("USERSPACE", str(userspace))
    monkeypatch.setenv("WORKSPACE", str(workspace))
    monkeypatch.setenv("RUNSPACE", str(runspace))
    monkeypatch.setenv("SESSION_ID", "session-a")

    history_dir = workspace / "history"
    history_dir.mkdir(parents=True)
    history_path = history_dir / "hist_demo.json"
    history_path.write_text(
        json.dumps(
            {
                "version": 1,
                "entry_id": "hist_demo",
                "created_at": "2026-06-05T00:00:00+00:00",
                "session_id": "session-a",
                "userspace": str(userspace),
                "workspace": str(workspace),
                "runspace": str(runspace),
                "mode": "chat",
                "prompt": "old prompt",
                "assistant_text_preview": "hello again",
                "events": [
                    make_event("response.created", 0, {"status": "created"}).model_dump(),
                    make_event("response.output_text.delta", 1, {"item_id": "item_msg_1", "delta": "hello again"}).model_dump(),
                    make_event("response.completed", 2, {"status": "completed"}).model_dump(),
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    output = io.StringIO()
    renderer = EventRenderer(stdout=output, stderr=io.StringIO())
    input_stream = io.StringIO("/resume\n/resume 1\n/session\n/exit\n")

    exit_code = run_chat_loop(
        renderer=renderer,
        orchestrator_factory=lambda: FakeOrchestrator([]),
        input_stream=input_stream,
    )

    assert exit_code == 0
    rendered = output.getvalue()
    assert "[resume] 1. session=session-a" in rendered
    assert "[resume] restoring latest record from session session-a" in rendered
    assert "old prompt" in rendered
    assert "hello again" in rendered
    assert "session: session-a" in rendered


def test_run_headless_once_resumes_with_session_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    userspace = tmp_path / "userspace"
    workspace = userspace / "sessions" / "session-a"
    runspace = workspace / "runs"
    history_dir = workspace / "history"
    history_dir.mkdir(parents=True)
    runspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("USERSPACE", str(userspace))
    monkeypatch.setenv("WORKSPACE", str(workspace))
    monkeypatch.setenv("RUNSPACE", str(runspace))
    monkeypatch.setenv("SESSION_ID", "session-a")

    history_path = history_dir / "hist_demo.json"
    history_path.write_text(
        json.dumps(
            {
                "version": 1,
                "entry_id": "hist_demo",
                "created_at": "2026-06-05T00:00:00+00:00",
                "session_id": "session-a",
                "userspace": str(userspace),
                "workspace": str(workspace),
                "runspace": str(runspace),
                "mode": "chat",
                "prompt": "old prompt",
                "assistant_text_preview": "hello again",
                "events": [
                    make_event("response.created", 0, {"status": "created"}).model_dump(),
                    make_event("response.output_text.delta", 1, {"item_id": "item_msg_1", "delta": "hello again"}).model_dump(),
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    live_events = [make_event("response.completed", 2, {"status": "completed"})]
    result = run_headless_once(
        prompt="new prompt",
        orchestrator_factory=lambda: FakeOrchestrator(live_events),
        resume_session_id="session-a",
    )

    payload = result.to_dict()
    assert payload["events"][0]["type"] == "response.created"
    assert payload["events"][1]["type"] == "response.output_text.delta"
    assert payload["events"][2]["type"] == "response.completed"


def test_stream_headless_once_emits_sse_and_summary() -> None:
    events = [
        make_event("response.created", 0, {"status": "created"}),
        make_event(
            "response.output_text.delta",
            1,
            {"item_id": "item_msg_1", "output_index": 0, "content_index": 0, "delta": "Hello"},
        ),
        make_event("response.completed", 2, {"status": "completed"}),
    ]
    output = io.StringIO()

    result = stream_headless_once(
        prompt="hello",
        orchestrator_factory=lambda: FakeOrchestrator(events),
        stdout=output,
    )

    chunks = [chunk for chunk in output.getvalue().split("\n\n") if chunk.strip()]
    assert result.exit_code == 0
    assert chunks[0].startswith("event: response.created\n")
    assert 'data: {"type": "response.created"' in chunks[0]
    assert chunks[-1].startswith("event: response.summary\n")
    assert '"mode": "headless"' in chunks[-1]
    assert '"prompt": "hello"' in chunks[-1]


def test_print_headless_result_uses_pretty_json() -> None:
    output = io.StringIO()
    result = run_headless_once(
        prompt="hello",
        orchestrator_factory=lambda: FakeOrchestrator([make_event("response.created", 0, {"status": "created"})]),
    )

    from moma_cli.commands import print_headless_result

    print_headless_result(result, stdout=output)

    rendered = output.getvalue()
    assert rendered.startswith("{\n")
    assert '  "mode": "headless"' in rendered
    assert rendered.endswith("\n")


def test_renderer_live_layout_updates_subagent_status_and_todos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = io.StringIO()
    renderer = EventRenderer(stdout=output, stderr=io.StringIO(), force_live_layout=True)

    workspace = tmp_path / "workspace"
    todo_dir = workspace / "todo"
    todo_dir.mkdir(parents=True)
    plan_path = todo_dir / "plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "mission_id": 7,
                "title": "Finish sidebar",
                "steps": [
                    {"step_id": 1, "title": "Build cards", "status": "running"},
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("WORKSPACE", str(workspace))

    subagent = AgentRef(
        id="sub_2",
        name="reviewer",
        kind="subagent",
        mode="subagent",
        parent_agent_id="orch_1",
    )

    renderer.begin_chat()
    renderer.render(
        ResponseEventEnvelope(
            type="response.subagent.started",
            response_id="resp_test",
            session_id="session_test",
            run_id="run_sub",
            sequence=0,
            agent=subagent,
            data={"subagent_name": "reviewer"},
        )
    )

    plan_path.write_text(
        json.dumps(
            {
                "mission_id": 7,
                "title": "Finish sidebar",
                "steps": [
                    {"step_id": 1, "title": "Build cards", "status": "completed"},
                ],
            }
        ),
        encoding="utf-8",
    )

    renderer.render(
        ResponseEventEnvelope(
            type="response.subagent.completed",
            response_id="resp_test",
            session_id="session_test",
            run_id="run_sub",
            sequence=1,
            agent=subagent,
            data={"subagent_name": "reviewer"},
        )
    )

    rendered = output.getvalue()
    assert "reviewer [completed]" in rendered
    assert "Finish sidebar" in rendered
    assert "Build cards" in rendered


def test_renderer_json_mode_outputs_raw_event_json() -> None:
    output = io.StringIO()
    renderer = EventRenderer(json_mode=True, stdout=output, stderr=io.StringIO())
    event = make_event("response.created", 0, {"status": "created"})

    renderer.render(event)

    parsed = json.loads(output.getvalue())
    assert parsed["type"] == "response.created"
    assert parsed["data"]["status"] == "created"


def test_run_once_streams_events_through_renderer() -> None:
    output = io.StringIO()
    renderer = EventRenderer(stdout=output, stderr=io.StringIO())
    events = [
        make_event("response.created", 0, {"status": "created"}),
        make_event(
            "response.output_text.delta",
            1,
            {"item_id": "item_msg_1", "output_index": 0, "content_index": 0, "delta": "Hi there"},
        ),
        make_event("response.completed", 2, {"status": "completed"}),
    ]

    exit_code = run_once(
        prompt="hello",
        renderer=renderer,
        orchestrator_factory=lambda: FakeOrchestrator(events),
    )

    assert exit_code == 0
    rendered = output.getvalue()
    assert "Hi there" in rendered
    assert "completed" in rendered


def test_chat_mode_handles_slash_commands_without_orchestrator() -> None:
    output = io.StringIO()
    renderer = EventRenderer(stdout=output, stderr=io.StringIO())
    workspace_root = Path.cwd() / ".moma-test-workspace"
    os.environ["WORKSPACE"] = str(workspace_root)
    input_stream = io.StringIO("/help\n/session\n/workspace\n/runspace\n/mcp list\n/clear\n/exit\n")

    exit_code = run_chat_loop(
        renderer=renderer,
        orchestrator_factory=lambda: FakeOrchestrator([]),
        input_stream=input_stream,
    )

    assert exit_code == 0
    rendered = output.getvalue()
    assert "Available commands:" in rendered
    assert "session:" in rendered
    assert "workspace:" in rendered
    assert "runspace:" in rendered
    assert "[mcp] no configured servers" in rendered
    assert "----------------------------------------" in rendered
    assert "Bye." in rendered


def test_main_run_command_supports_json_mode(cli_config_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    events = [make_event("response.created", 0, {"status": "created"})]
    main_module = importlib.import_module("moma_cli.main")

    def fake_run_once(*, prompt, renderer, orchestrator_factory):
        for event in events:
            renderer.render(event)
        renderer.finish()
        return 0

    monkeypatch.setattr(main_module, "run_once", fake_run_once)

    exit_code = main(
        [
            "--config",
            str(cli_config_file),
            "--workspace",
            str(tmp_path / "workspace"),
            "--json",
            "run",
            "hello",
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["type"] == "response.created"


def test_main_run_command_supports_headless_stream_mode(
    cli_config_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main_module = importlib.import_module("moma_cli.main")

    def fake_stream_headless_once(*, prompt, orchestrator_factory, stdout):
        stdout.write("event: response.created\n")
        stdout.write(json.dumps({"type": "response.created"}, ensure_ascii=False) + "\n\n")
        stdout.write("event: response.summary\n")
        stdout.write(json.dumps({"mode": "headless", "prompt": prompt}, ensure_ascii=False) + "\n\n")

        class Result:
            exit_code = 0

        return Result()

    monkeypatch.setattr(main_module, "stream_headless_once", fake_stream_headless_once)

    exit_code = main(
        [
            "--config",
            str(cli_config_file),
            "--workspace",
            str(tmp_path / "workspace"),
            "--headless",
            "--stream",
            "run",
            "hello",
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "event: response.created" in captured.out
    assert "event: response.summary" in captured.out


def test_main_chat_command_runs_initial_prompt(cli_config_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    main_module = importlib.import_module("moma_cli.main")

    def fake_run_once(*, prompt, renderer, orchestrator_factory):
        calls.append(prompt)
        return 0

    def fake_chat_loop(*, renderer, orchestrator_factory, input_stream):
        return 0

    monkeypatch.setattr(main_module, "run_once", fake_run_once)
    monkeypatch.setattr(main_module, "run_chat_loop", fake_chat_loop)

    exit_code = main(
        [
            "--config",
            str(cli_config_file),
            "--workspace",
            str(tmp_path / "workspace"),
            "chat",
            "--prompt",
            "first prompt",
        ]
    )

    assert exit_code == 0
    assert calls == ["first prompt"]


def test_module_entrypoint_delegates_to_cli_main(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str] | None] = []

    def fake_main(argv=None):
        calls.append(argv)
        return 7

    module_entry = importlib.import_module("moma_cli.__main__")
    monkeypatch.setattr(module_entry, "main", fake_main)

    exit_code = module_entry.main(["doctor"])

    assert exit_code == 7
    assert calls == [["doctor"]]


def test_module_main_executes_package_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str] | None] = []

    def fake_main(argv=None):
        calls.append(argv)
        return 3

    cli_main_module = importlib.import_module("moma_cli.main")
    monkeypatch.setattr(cli_main_module, "main", fake_main)

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("moma_cli", run_name="__main__")

    assert excinfo.value.code == 3
    assert calls == [None]


def test_main_sessions_command_lists_known_sessions(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    session_dir = tmp_path / "workspace" / "sessions" / "session-123"
    (session_dir / "runs").mkdir(parents=True)

    exit_code = main(["--workspace", str(tmp_path / "workspace"), "sessions"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "session-123" in captured.out


def test_main_history_list_command_outputs_saved_records(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    userspace = tmp_path / "workspace"
    history_dir = userspace / "sessions" / "session-a" / "history"
    history_dir.mkdir(parents=True)
    (history_dir / "hist_demo.json").write_text(
        json.dumps(
            {
                "version": 1,
                "entry_id": "hist_demo",
                "created_at": "2026-06-05T00:00:00+00:00",
                "session_id": "session-a",
                "workspace": str(userspace / "sessions" / "session-a"),
                "mode": "chat",
                "prompt": "hello history",
                "assistant_text_preview": "preview text",
                "events": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    exit_code = main(["--workspace", str(userspace), "history", "list"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "hist_demo" in captured.out
    assert "session=session-a" in captured.out


def test_main_history_show_command_outputs_record_details(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    userspace = tmp_path / "workspace"
    history_dir = userspace / "sessions" / "session-a" / "history"
    history_dir.mkdir(parents=True)
    (history_dir / "hist_demo.json").write_text(
        json.dumps(
            {
                "version": 1,
                "entry_id": "hist_demo",
                "created_at": "2026-06-05T00:00:00+00:00",
                "session_id": "session-a",
                "workspace": str(userspace / "sessions" / "session-a"),
                "mode": "chat",
                "prompt": "hello history",
                "assistant_text_preview": "preview text",
                "events": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    exit_code = main(["--workspace", str(userspace), "history", "show", "hist_demo"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "entry_id: hist_demo" in captured.out
    assert "session_id: session-a" in captured.out
    assert "prompt: hello history" in captured.out


def test_main_resume_without_session_id_lists_saved_conversations(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    userspace = tmp_path / "workspace"
    history_dir = userspace / "sessions" / "session-a" / "history"
    history_dir.mkdir(parents=True)
    (history_dir / "hist_demo.json").write_text(
        json.dumps(
            {
                "version": 1,
                "entry_id": "hist_demo",
                "created_at": "2026-06-05T00:00:00+00:00",
                "session_id": "session-a",
                "workspace": str(userspace / "sessions" / "session-a"),
                "mode": "chat",
                "prompt": "hello history",
                "assistant_text_preview": "preview text",
                "events": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    exit_code = main(["--workspace", str(userspace), "resume"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "[resume] 1. session=session-a" in captured.out


def test_main_resume_with_session_id_reenters_chat(cli_config_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    main_module = importlib.import_module("moma_cli.main")
    calls: list[tuple[str, str]] = []

    def fake_chat_loop(*, renderer, orchestrator_factory, input_stream):
        calls.append((os.environ.get("SESSION_ID", ""), os.environ.get("WORKSPACE", "")))
        return 0

    monkeypatch.setattr(main_module, "run_chat_loop", fake_chat_loop)

    exit_code = main(
        [
            "--config",
            str(cli_config_file),
            "--workspace",
            str(tmp_path / "workspace"),
            "resume",
            "session-a",
        ]
    )

    assert exit_code == 0
    assert calls
    assert calls[0][0] == "session-a"


def test_main_web_command_invokes_web_runner(cli_config_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    main_module = importlib.import_module("moma_cli.main")
    calls: list[tuple[str, int, str | None, bool]] = []

    def fake_run_web_server(*, host: str, port: int, userspace: str | None, auto_install: bool = True) -> int:
        calls.append((host, port, userspace, auto_install))
        return 0

    monkeypatch.setattr(main_module, "run_web_server", fake_run_web_server)

    exit_code = main(
        [
            "--config",
            str(cli_config_file),
            "--workspace",
            str(tmp_path / "workspace"),
            "web",
            "--host",
            "0.0.0.0",
            "--port",
            "4011",
        ]
    )

    assert exit_code == 0
    assert calls == [("0.0.0.0", 4011, str(tmp_path / "workspace"), True)]


def test_main_web_command_supports_no_install_flag(cli_config_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    main_module = importlib.import_module("moma_cli.main")
    calls: list[tuple[str, int, str | None, bool]] = []

    def fake_run_web_server(*, host: str, port: int, userspace: str | None, auto_install: bool = True) -> int:
        calls.append((host, port, userspace, auto_install))
        return 0

    monkeypatch.setattr(main_module, "run_web_server", fake_run_web_server)

    exit_code = main(
        [
            "--config",
            str(cli_config_file),
            "--workspace",
            str(tmp_path / "workspace"),
            "web",
            "--host",
            "127.0.0.1",
            "--port",
            "4012",
            "--no-install",
        ]
    )

    assert exit_code == 0
    assert calls == [("127.0.0.1", 4012, str(tmp_path / "workspace"), False)]


def test_main_serve_command_invokes_backend_runner(cli_config_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    main_module = importlib.import_module("moma_cli.main")
    calls: list[tuple[str, int, str | None]] = []

    def fake_run_backend_server(*, host: str, port: int, userspace: str | None) -> int:
        calls.append((host, port, userspace))
        return 0

    monkeypatch.setattr(main_module, "run_backend_server", fake_run_backend_server)

    exit_code = main(
        [
            "--config",
            str(cli_config_file),
            "--workspace",
            str(tmp_path / "workspace"),
            "serve",
            "--host",
            "0.0.0.0",
            "--port",
            "4019",
        ]
    )

    assert exit_code == 0
    assert calls == [("0.0.0.0", 4019, str(tmp_path / "workspace"))]


def test_main_init_command_invokes_bootstrap_install(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    main_module = importlib.import_module("moma_cli.main")
    calls: list[tuple[bool, bool]] = []

    def fake_bootstrap_local_install(*, include_dev: bool = False, install_browsers: bool = False) -> list[str]:
        calls.append((include_dev, install_browsers))
        return ["Python dependencies installed", "swarm-ui dependencies installed"]

    monkeypatch.setattr(main_module, "bootstrap_local_install", fake_bootstrap_local_install)

    exit_code = main(["init", "--dev", "--with-browsers"])

    assert exit_code == 0
    assert calls == [(True, True)]
    captured = capsys.readouterr()
    assert "MOMA local install complete." in captured.out
    assert "moma --config config.json chat" in captured.out


def test_main_doctor_fix_invokes_repair_install(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    main_module = importlib.import_module("moma_cli.main")
    calls: list[tuple[str, bool]] = []

    def fake_environment_summary(workspace, session_id, config_path):
        return {"userspace": "u", "workspace": "w"}

    def fake_inspect_local_install_status():
        return {"has_uv": True, "swarm_ui_dependencies_installed": True}

    def fake_build_local_install_checks():
        return [{"key": "python_toolchain", "ok": True, "details": "uv"}]

    def fake_repair_local_install(*, target: str = "all", include_dev: bool = False) -> list[str]:
        calls.append((target, include_dev))
        return ["Python dependencies installed", "swarm-ui dependencies installed"]

    monkeypatch.setattr(main_module, "environment_summary", fake_environment_summary)
    monkeypatch.setattr(main_module, "inspect_local_install_status", fake_inspect_local_install_status)
    monkeypatch.setattr(main_module, "build_local_install_checks", fake_build_local_install_checks)
    monkeypatch.setattr(main_module, "repair_local_install", fake_repair_local_install)

    exit_code = main(["doctor", "--fix", "--dev", "--with-browsers", "--target", "python"])

    assert exit_code == 0
    assert calls == [("python", True), ("browsers", True)]
    captured = capsys.readouterr()
    assert "checks:" in captured.out
    assert "repaired_steps:" in captured.out
    assert "Python dependencies installed" in captured.out


def test_main_doctor_fix_target_web_only(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    main_module = importlib.import_module("moma_cli.main")
    calls: list[tuple[str, bool]] = []

    monkeypatch.setattr(main_module, "environment_summary", lambda workspace, session_id, config_path: {"userspace": "u"})
    monkeypatch.setattr(main_module, "inspect_local_install_status", lambda: {"has_uv": True})
    monkeypatch.setattr(main_module, "build_local_install_checks", lambda: [{"key": "web_toolchain", "ok": False, "details": "npm missing"}])

    def fake_repair_local_install(*, target: str = "all", include_dev: bool = False) -> list[str]:
        calls.append((target, include_dev))
        return [f"repaired {target}"]

    monkeypatch.setattr(main_module, "repair_local_install", fake_repair_local_install)

    exit_code = main(["doctor", "--fix", "--target", "web"])

    assert exit_code == 0
    assert calls == [("web", False)]
    captured = capsys.readouterr()
    assert "repaired web" in captured.out


def test_bootstrap_environment_sets_sandbox_env(cli_config_file: Path, tmp_path: Path) -> None:
    from moma_cli.bootstrap import bootstrap_environment

    previous_enabled = os.environ.get("MOMA_SANDBOX_ENABLED")
    previous_root = os.environ.get("MOMA_SANDBOX_ROOT")

    try:
        bootstrap_environment(
            config_path=str(cli_config_file),
            mcp_config_path=None,
            workspace=str(tmp_path / "workspace"),
            session_id="session-sandbox",
            user_id=None,
            api_key=None,
            authorization=None,
            sandbox=True,
            sandbox_root=str(tmp_path / "workspace" / "safe-root"),
        )

        assert os.environ["MOMA_SANDBOX_ENABLED"] == "true"
        assert os.environ["MOMA_SANDBOX_ROOT"].endswith("safe-root")
    finally:
        if previous_enabled is None:
            os.environ.pop("MOMA_SANDBOX_ENABLED", None)
        else:
            os.environ["MOMA_SANDBOX_ENABLED"] = previous_enabled
        if previous_root is None:
            os.environ.pop("MOMA_SANDBOX_ROOT", None)
        else:
            os.environ["MOMA_SANDBOX_ROOT"] = previous_root


def test_sandbox_rejects_path_outside_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    safe_root = tmp_path / "safe"
    safe_root.mkdir(parents=True)
    monkeypatch.setenv("MOMA_SANDBOX_ENABLED", "true")
    monkeypatch.setenv("MOMA_SANDBOX_ROOT", str(safe_root))

    allowed = ensure_within_root(safe_root / "ok.txt")
    assert str(allowed).endswith("ok.txt")

    with pytest.raises(ValueError):
        ensure_within_root(tmp_path / "escape.txt")


def test_history_and_mcp_respect_sandbox_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    userspace = tmp_path / "safe-root"
    workspace = userspace / "sessions" / "session-a"
    workspace.mkdir(parents=True)
    monkeypatch.setenv("MOMA_SANDBOX_ENABLED", "true")
    monkeypatch.setenv("MOMA_SANDBOX_ROOT", str(userspace))
    monkeypatch.setenv("USERSPACE", str(userspace))
    monkeypatch.setenv("WORKSPACE", str(workspace))

    from moma_cli.history import resolve_history_dir
    from moma_cli.mcp import write_mcp_server, list_mcp_servers

    history_dir = resolve_history_dir(str(workspace))
    assert history_dir is not None
    assert str(history_dir).startswith(str(userspace))

    write_mcp_server(name="exa", url="https://example.com/sse", workspace=str(workspace))
    servers = list_mcp_servers(str(workspace))
    assert len(servers) == 1
    assert servers[0]["name"] == "exa"


def test_main_doctor_command_reports_bootstrap_state(cli_config_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(
        [
            "--config",
            str(cli_config_file),
            "--workspace",
            str(tmp_path / "workspace"),
            "doctor",
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "userspace:" in captured.out
    assert "has_orchestrator_config:" in captured.out
    assert "workspace:" in captured.out
    assert "mcp_server_count:" in captured.out


def test_main_doctor_command_reports_embedded_mcp_count(
    cli_config_with_mcp_file: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(
        [
            "--config",
            str(cli_config_with_mcp_file),
            "--workspace",
            str(tmp_path / "workspace"),
            "doctor",
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "mcp_server_count: 1" in captured.out


def test_main_config_command_reports_preview(cli_config_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["config", "--path", str(cli_config_file)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "toolkit_count:" in captured.out
    assert "model:" in captured.out


def test_main_config_command_supports_json_output(cli_config_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["--json", "config", "--path", str(cli_config_file)])

    assert exit_code == 0
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["toolkit_count"] == 0


def test_main_config_command_reports_embedded_mcp_count(
    cli_config_with_mcp_file: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["config", "--path", str(cli_config_with_mcp_file)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "mcp_server_count: 1" in captured.out


def test_import_mcp_config_supports_servers_list(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    config_path = tmp_path / "mcp.json"
    config_path.write_text(
        json.dumps(
            {
                "servers": [
                    {
                        "name": "exa",
                        "url": "https://example.com/sse",
                        "transport": "sse",
                        "timeout": 12
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    imported = import_mcp_config(str(config_path), str(workspace))

    assert imported == ["exa"]
    servers = list_mcp_servers(str(workspace))
    assert len(servers) == 1
    assert servers[0]["name"] == "exa"
    assert servers[0]["url"] == "https://example.com/sse"


def test_import_mcp_payload_accepts_type_alias(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    imported = import_mcp_payload(
        {
            "mcpServers": {
                "exa": {
                    "type": "sse",
                    "url": "https://example.com/sse"
                }
            }
        },
        str(workspace),
    )

    assert imported == ["exa"]
    servers = list_mcp_servers(str(workspace))
    assert len(servers) == 1
    assert servers[0]["transport"] == "sse"


def test_main_mcp_add_and_list_commands(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    workspace = tmp_path / "workspace"

    add_exit = main(
        [
            "--workspace",
            str(workspace),
            "mcp",
            "add",
            "--name",
            "exa",
            "--url",
            "https://example.com/sse",
        ]
    )

    assert add_exit == 0

    list_exit = main(["--workspace", str(workspace), "mcp", "list"])
    assert list_exit == 0
    captured = capsys.readouterr()
    assert "exa" in captured.out
    assert "https://example.com/sse" in captured.out


def test_main_single_config_file_imports_embedded_mcp_servers(
    cli_config_with_mcp_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main_module = importlib.import_module("moma_cli.main")

    def fake_run_once(*, prompt, renderer, orchestrator_factory):
        return 0

    monkeypatch.setattr(main_module, "run_once", fake_run_once)

    exit_code = main(
        [
            "--config",
            str(cli_config_with_mcp_file),
            "--workspace",
            str(tmp_path / "workspace"),
            "--session-id",
            "session-single-config",
            "run",
            "hello",
        ]
    )

    assert exit_code == 0
    servers = list_mcp_servers(str(tmp_path / "workspace" / "sessions" / "session-single-config"))
    assert len(servers) == 1
    assert servers[0]["name"] == "exa"


def test_main_mcp_list_reads_embedded_servers_from_single_config(
    cli_config_with_mcp_file: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(
        [
            "--config",
            str(cli_config_with_mcp_file),
            "--workspace",
            str(tmp_path / "workspace"),
            "--session-id",
            "session-mcp-list",
            "mcp",
            "list",
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "exa" in captured.out
    assert "https://example.com/sse" in captured.out


def test_main_standalone_mcp_config_still_supported(
    cli_config_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp_config_path = tmp_path / "mcp.json"
    mcp_config_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "exa": {
                        "url": "https://example.com/sse",
                        "transport": "sse"
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    main_module = importlib.import_module("moma_cli.main")

    def fake_run_once(*, prompt, renderer, orchestrator_factory):
        return 0

    monkeypatch.setattr(main_module, "run_once", fake_run_once)

    exit_code = main(
        [
            "--config",
            str(cli_config_file),
            "--mcp-config",
            str(mcp_config_path),
            "--workspace",
            str(tmp_path / "workspace"),
            "--session-id",
            "session-legacy-mcp",
            "run",
            "hello",
        ]
    )

    assert exit_code == 0
    servers = list_mcp_servers(str(tmp_path / "workspace" / "sessions" / "session-legacy-mcp"))
    assert len(servers) == 1
    assert servers[0]["name"] == "exa"


def test_main_run_announces_mcp_health(
    cli_config_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main_module = importlib.import_module("moma_cli.main")
    mcp_module = importlib.import_module("moma_cli.mcp")

    write_mcp_server(
        name="exa",
        url="https://example.com/sse",
        workspace=str(tmp_path / "workspace" / "sessions" / "session-fixed"),
    )

    def fake_check_mcp_servers(workspace=None):
        return [
            {
                "name": "exa",
                "status": "ok",
                "tool_count": 2,
                "transport": "sse",
                "url": "https://example.com/sse",
            }
        ]

    def fake_run_once(*, prompt, renderer, orchestrator_factory):
        renderer.print_system("run invoked")
        return 0

    monkeypatch.setattr(mcp_module, "check_mcp_servers", fake_check_mcp_servers)
    monkeypatch.setattr(main_module, "run_once", fake_run_once)

    exit_code = main(
        [
            "--config",
            str(cli_config_file),
            "--workspace",
            str(tmp_path / "workspace"),
            "--session-id",
            "session-fixed",
            "run",
            "hello",
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "[mcp] exa ok (2 tools)" in captured.out
    assert "run invoked" in captured.out
