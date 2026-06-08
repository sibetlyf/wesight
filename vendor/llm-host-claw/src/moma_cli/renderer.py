from __future__ import annotations

import json
import os
import shutil
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

from protocol.response_events import ResponseEventEnvelope


ANSI_RESET = "\x1b[0m"
ANSI_BOLD = "\x1b[1m"
ANSI_DIM = "\x1b[2m"
ANSI_CYAN = "\x1b[36m"
ANSI_MAGENTA = "\x1b[35m"
ANSI_GREEN = "\x1b[32m"
ANSI_YELLOW = "\x1b[33m"
ANSI_RED = "\x1b[31m"
ANSI_BLUE = "\x1b[34m"
ANSI_CLEAR = "\x1b[2J\x1b[H"
ANSI_HOME = "\x1b[H"
ANSI_CLEAR_TO_END = "\x1b[J"
ANSI_WHITE = "\x1b[37m"


@dataclass
class TranscriptLine:
    text: str
    color: str = ""
    role: str = "message"
    agent_name: str = ""


@dataclass
class SubagentCard:
    agent_id: str
    name: str
    status: str = "running"
    kind: str = "subagent"
    active: bool = False
    last_event: str = ""
    last_text: str = ""
    log_lines: list[str] = field(default_factory=list)
    metadata_lines: list[str] = field(default_factory=list)


@dataclass
class TodoStepView:
    step_id: int
    title: str
    status: str


@dataclass
class TodoPlanView:
    mission_id: int
    title: str
    done: bool
    steps: list[TodoStepView] = field(default_factory=list)


@dataclass
class EventRenderer:
    json_mode: bool = False
    stdout: TextIO = field(default_factory=lambda: sys.stdout)
    stderr: TextIO = field(default_factory=lambda: sys.stderr)
    force_live_layout: bool = False
    _text_buffers: dict[str, list[str]] = field(default_factory=dict)
    _reasoning_buffers: dict[str, list[str]] = field(default_factory=dict)
    _last_agent_name: str | None = None
    _transcript: list[TranscriptLine] = field(default_factory=list)
    _active_message_index: dict[str, int] = field(default_factory=dict)
    _subagents: dict[str, SubagentCard] = field(default_factory=dict)
    _todos: list[TodoPlanView] = field(default_factory=list)
    _input_label: str = "MOMA > "
    _last_prompt: str = ""
    _chat_started: bool = False
    _input_placeholder: str = "Type a prompt or /help"
    _screen_initialized: bool = False
    _pending_live_deltas: int = 0
    _live_redraw_every: int = 4
    _input_buffer: str = ""
    _slash_suggestions: list[str] = field(default_factory=list)
    _slash_suggestion_details: list[str] = field(default_factory=list)
    _selected_suggestion: int = 0

    def _mark_active_agent(self, agent_id: str | None) -> None:
        for card in self._subagents.values():
            card.active = bool(agent_id) and card.agent_id == agent_id

    def _record_message(self, text: str, color: str = "", role: str = "message", agent_name: str = "") -> None:
        self._transcript.append(TranscriptLine(text=text, color=color, role=role, agent_name=agent_name))

    @property
    def live_layout(self) -> bool:
        if self.json_mode:
            return False
        if self.force_live_layout:
            return True
        return bool(getattr(self.stdout, "isatty", lambda: False)())

    def begin_chat(self) -> None:
        self._chat_started = True
        if self.live_layout:
            self._redraw()

    def prepare_for_input(self, label: str = "MOMA > ") -> None:
        self._input_label = label
        if not self.live_layout:
            return
        self._redraw()
        self.stdout.write("\x1b[2A")
        self.stdout.write("\r")
        self.stdout.write(self._input_label)
        self.stdout.flush()

    def record_user_prompt(self, prompt: str) -> None:
        prompt = prompt.strip()
        if not prompt:
            return
        if self.live_layout:
            self._input_buffer = ""
            self._slash_suggestions = []
            self._selected_suggestion = 0
            self._record_message(f"[you] {prompt}", ANSI_BLUE, role="user", agent_name="you")
            self._last_prompt = ""
            self._redraw()
            return
        self._last_prompt = prompt

    def update_input_state(
        self,
        prompt: str,
        suggestions: list[str] | None = None,
        selected_index: int = 0,
        suggestion_details: list[str] | None = None,
    ) -> None:
        self._input_buffer = prompt
        self._slash_suggestions = suggestions or []
        self._slash_suggestion_details = suggestion_details or []
        if self._slash_suggestions:
            self._selected_suggestion = max(0, min(selected_index, len(self._slash_suggestions) - 1))
        else:
            self._selected_suggestion = 0
        self._last_prompt = prompt
        if self.live_layout:
            self._redraw()

    def clear_input_state(self) -> None:
        self.update_input_state("", [], 0, [])

    def print_suggestions(self, prompt: str, suggestions: list[tuple[str, str]]) -> None:
        self.print_status(f"Suggestions for {prompt}:", ANSI_DIM)
        for command, description in suggestions:
            self.print_status(f"  {command:<14} {description}", ANSI_GREEN)

    def render(self, event: ResponseEventEnvelope) -> None:
        if self.json_mode:
            self.stdout.write(json.dumps(event.model_dump(), ensure_ascii=False) + "\n")
            self.stdout.flush()
            return

        if self.live_layout:
            self._render_live(event)
            return

        self._render_plain(event)

    def finish(self) -> None:
        if self.json_mode:
            return
        if self.live_layout:
            self._reload_todos_from_workspace()
            self._redraw()
            return
        self._ensure_trailing_newline()

    def print_system(self, message: str) -> None:
        self.print_status(message, ANSI_DIM)

    def print_status(self, message: str, color: str) -> None:
        if self.live_layout:
            self._append_transcript(message, color)
            self._reload_todos_from_workspace()
            self._redraw()
            return

        self._ensure_trailing_newline()
        self.stdout.write(f"{color}{message}{ANSI_RESET}\n")
        self.stdout.flush()
        self._last_agent_name = None

    def _render_plain(self, event: ResponseEventEnvelope) -> None:
        event_type = event.type
        if event_type == "response.created":
            self.print_status(f"[{event.agent.name}] started", self._agent_color(event))
            return
        if event_type == "response.in_progress":
            return
        if event_type == "response.output_text.delta":
            self._render_text_delta_plain(event)
            return
        if event_type == "response.output_text.done":
            self._render_text_done_plain(event)
            return
        if event_type == "response.reasoning.delta":
            self._render_reasoning_delta_plain(event)
            return
        if event_type == "response.reasoning.done":
            self._render_reasoning_done_plain(event)
            return
        if event_type == "response.tool_call.started":
            self.print_status(f"[tool] {event.data.get('name', 'unknown_tool')} started", ANSI_YELLOW)
            return
        if event_type == "response.tool_call.completed":
            output_text = event.data.get("output_text") or ""
            tool_name = event.data.get("name", "unknown_tool")
            if output_text:
                self.print_status(f"[tool] {tool_name} completed: {output_text}", ANSI_YELLOW)
            else:
                self.print_status(f"[tool] {tool_name} completed", ANSI_YELLOW)
            return
        if event_type == "response.tool_call.failed":
            error = event.data.get("error") or {}
            self.print_status(
                f"[tool] {event.data.get('name', 'unknown_tool')} failed: {error.get('message', 'unknown error')}"
            , ANSI_RED)
            return
        if event_type == "response.subagent.started":
            self.print_status(f"[subagent] {event.data.get('subagent_name', event.agent.name)} started", self._agent_color(event))
            return
        if event_type == "response.subagent.completed":
            self.print_status(f"[subagent] {event.data.get('subagent_name', event.agent.name)} completed", self._agent_color(event))
            return
        if event_type == "response.failed":
            error = event.data.get("error") or {}
            self.print_status(f"[error] {error.get('message', 'run failed')}", ANSI_RED)
            return
        if event_type == "response.completed":
            self._ensure_trailing_newline()
            self.print_status(f"[{event.agent.name}] completed", self._agent_color(event))

    def _render_live(self, event: ResponseEventEnvelope) -> None:
        event_type = event.type
        color = self._agent_color(event)
        self._reload_todos_from_workspace()
        should_redraw = event_type != "response.output_text.delta"

        if event.agent.kind != "orchestrator":
            card = self._subagents.setdefault(
                event.agent.id,
                SubagentCard(agent_id=event.agent.id, name=event.agent.name, kind=event.agent.kind),
            )
            self._mark_active_agent(event.agent.id)
            if event_type == "response.completed":
                card.status = "completed"
            elif event_type == "response.failed":
                card.status = "failed"
            else:
                card.status = "running"
            card.last_event = event_type
        else:
            self._mark_active_agent(None)

        if event_type == "response.created":
            self._record_message(f"[{event.agent.name}] started", color, role="system", agent_name=event.agent.name)
            self._append_subagent_log(event, "started")
        elif event_type == "response.output_text.delta":
            created_new_message = self._render_text_delta_live(event, color)
            self._pending_live_deltas += 1
            should_redraw = created_new_message or self._pending_live_deltas >= self._live_redraw_every
        elif event_type == "response.output_text.done":
            item_id = str(event.data.get("item_id") or "")
            self._active_message_index.pop(item_id, None)
            should_redraw = True
        elif event_type == "response.reasoning.delta":
            item_id = str(event.data.get("item_id") or event.event_id)
            delta = str(event.data.get("delta") or "")
            if delta:
                self._reasoning_buffers.setdefault(item_id, []).append(delta)
            should_redraw = False
        elif event_type == "response.reasoning.done":
            item_id = str(event.data.get("item_id") or "")
            chunks = self._reasoning_buffers.pop(item_id, [])
            if chunks:
                self._record_message(
                    f"[{event.agent.name} reasoning] {''.join(chunks)}",
                    self._metadata_color(event),
                    role="reasoning",
                    agent_name=event.agent.name,
                )
                self._append_subagent_log(event, f"reasoning: {''.join(chunks)}")
        elif event_type == "response.tool_call.started":
            tool_name = str(event.data.get("name") or "unknown_tool")
            self._record_message(
                f"[tool:{event.agent.name}] {tool_name} started",
                self._metadata_color(event),
                role="tool",
                agent_name=event.agent.name,
            )
            self._append_subagent_log(event, f"tool start: {tool_name}")
            self._append_subagent_metadata(event, f"tool={tool_name}")
        elif event_type == "response.tool_call.completed":
            tool_name = str(event.data.get("name") or "unknown_tool")
            output_text = str(event.data.get("output_text") or "").strip()
            message = f"[tool:{event.agent.name}] {tool_name} completed"
            if output_text:
                message += f": {output_text}"
            self._record_message(message, self._metadata_color(event), role="tool", agent_name=event.agent.name)
            self._append_subagent_log(event, f"tool done: {tool_name}")
            self._reload_todos_from_workspace()
        elif event_type == "response.tool_call.failed":
            tool_name = str(event.data.get("name") or "unknown_tool")
            error = event.data.get("error") or {}
            self._record_message(
                f"[tool:{event.agent.name}] {tool_name} failed: {error.get('message', 'unknown error')}",
                ANSI_RED,
                role="tool",
                agent_name=event.agent.name,
            )
            self._append_subagent_log(event, f"tool failed: {tool_name}")
        elif event_type == "response.subagent.started":
            subagent_name = str(event.data.get("subagent_name") or event.agent.name)
            card = self._subagents.setdefault(
                event.agent.id,
                SubagentCard(agent_id=event.agent.id, name=subagent_name, kind=event.agent.kind),
            )
            card.status = "running"
            card.last_event = "started"
            self._record_message(f"[subagent] {subagent_name} started", color, role="system", agent_name=subagent_name)
            self._append_subagent_log(event, "started")
            self._append_subagent_metadata(event, f"kind={card.kind}")
        elif event_type == "response.subagent.completed":
            subagent_name = str(event.data.get("subagent_name") or event.agent.name)
            card = self._subagents.setdefault(
                event.agent.id,
                SubagentCard(agent_id=event.agent.id, name=subagent_name, kind=event.agent.kind),
            )
            card.status = "completed"
            card.last_event = "completed"
            self._record_message(f"[subagent] {subagent_name} completed", color, role="system", agent_name=subagent_name)
            self._append_subagent_log(event, "completed")
        elif event_type == "response.failed":
            error = event.data.get("error") or {}
            self._record_message(f"[error] {error.get('message', 'run failed')}", ANSI_RED, role="error", agent_name=event.agent.name)
            self._append_subagent_log(event, f"failed: {error.get('message', 'run failed')}")
        elif event_type == "response.completed":
            self._record_message(f"[{event.agent.name}] completed", color, role="system", agent_name=event.agent.name)
            self._append_subagent_log(event, "completed")

        if event.agent.kind != "orchestrator" and event.agent.id in self._subagents:
            card = self._subagents[event.agent.id]
            if event_type == "response.output_text.delta":
                item_id = str(event.data.get("item_id") or event.event_id)
                card.last_text = "".join(self._text_buffers.get(item_id, []))[-140:]
                if delta := str(event.data.get("delta") or "").strip():
                    self._append_subagent_log(event, delta)

        if should_redraw:
            self._pending_live_deltas = 0
            self._redraw()

    def _render_text_delta_plain(self, event: ResponseEventEnvelope) -> None:
        item_id = str(event.data.get("item_id") or event.event_id)
        delta = str(event.data.get("delta") or "")
        if not delta:
            return
        if self._last_agent_name != event.agent.name:
            self._ensure_trailing_newline()
            color = self._agent_color(event)
            self.stdout.write(f"{color}[{event.agent.name}] {ANSI_RESET}")
            self._last_agent_name = event.agent.name
        self.stdout.write(f"{self._agent_color(event)}{delta}{ANSI_RESET}")
        self.stdout.flush()
        self._text_buffers.setdefault(item_id, []).append(delta)

    def _render_text_done_plain(self, event: ResponseEventEnvelope) -> None:
        item_id = str(event.data.get("item_id") or "")
        self._text_buffers.pop(item_id, None)
        self._ensure_trailing_newline()

    def _render_reasoning_delta_plain(self, event: ResponseEventEnvelope) -> None:
        item_id = str(event.data.get("item_id") or event.event_id)
        delta = str(event.data.get("delta") or "")
        if delta:
            self._reasoning_buffers.setdefault(item_id, []).append(delta)

    def _render_reasoning_done_plain(self, event: ResponseEventEnvelope) -> None:
        item_id = str(event.data.get("item_id") or "")
        chunks = self._reasoning_buffers.pop(item_id, [])
        if chunks:
            self.print_status(f"[reasoning] {''.join(chunks)}", ANSI_GREEN)

    def _render_text_delta_live(self, event: ResponseEventEnvelope, color: str) -> bool:
        item_id = str(event.data.get("item_id") or event.event_id)
        delta = str(event.data.get("delta") or "")
        if not delta:
            return False
        self._text_buffers.setdefault(item_id, []).append(delta)
        if item_id not in self._active_message_index:
            role = "subagent" if event.agent.kind != "orchestrator" else "message"
            self._record_message(f"[{event.agent.name}] {delta}", color, role=role, agent_name=event.agent.name)
            self._active_message_index[item_id] = len(self._transcript) - 1
            return True
        index = self._active_message_index[item_id]
        prefix = f"[{event.agent.name}] "
        role = "subagent" if event.agent.kind != "orchestrator" else "message"
        self._transcript[index] = TranscriptLine(
            prefix + "".join(self._text_buffers[item_id]),
            color,
            role=role,
            agent_name=event.agent.name,
        )
        return False

    def _append_transcript(self, text: str, color: str = "") -> None:
        self._record_message(text, color)

    def _append_subagent_log(self, event: ResponseEventEnvelope, text: str) -> None:
        if event.agent.kind == "orchestrator":
            return
        if event.agent.id not in self._subagents:
            self._subagents[event.agent.id] = SubagentCard(
                agent_id=event.agent.id,
                name=event.agent.name,
                kind=event.agent.kind,
            )
        card = self._subagents[event.agent.id]
        normalized = text.strip()
        if not normalized:
            return
        card.log_lines.append(normalized)
        if len(card.log_lines) > 5:
            card.log_lines = card.log_lines[-5:]

    def _append_subagent_metadata(self, event: ResponseEventEnvelope, text: str) -> None:
        if event.agent.kind == "orchestrator":
            return
        card = self._subagents.setdefault(
            event.agent.id,
            SubagentCard(agent_id=event.agent.id, name=event.agent.name, kind=event.agent.kind),
        )
        normalized = text.strip()
        if not normalized or normalized in card.metadata_lines:
            return
        card.metadata_lines.append(normalized)
        if len(card.metadata_lines) > 4:
            card.metadata_lines = card.metadata_lines[-4:]

    def _reload_todos_from_workspace(self) -> None:
        workspace = os.environ.get("WORKSPACE")
        if not workspace:
            self._todos = []
            return
        todo_dir = Path(workspace) / "todo"
        if not todo_dir.exists():
            self._todos = []
            return
        plans: list[TodoPlanView] = []
        for path in sorted(todo_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            steps: list[TodoStepView] = []
            for raw_step in payload.get("steps", []):
                if not isinstance(raw_step, dict):
                    continue
                steps.append(
                    TodoStepView(
                        step_id=int(raw_step.get("step_id", 0) or 0),
                        title=str(raw_step.get("title") or raw_step.get("content") or "step"),
                        status=str(raw_step.get("status") or "pending"),
                    )
                )
            plans.append(
                TodoPlanView(
                    mission_id=int(payload.get("mission_id", 0) or 0),
                    title=str(payload.get("title") or path.stem),
                    done=all(step.status in {"completed", "failed"} for step in steps) if steps else False,
                    steps=steps,
                )
            )
        self._todos = plans

    def _redraw(self) -> None:
        width, height = shutil.get_terminal_size((120, 32))
        width = max(width, 80)
        height = max(height, 20)
        left_width = max(40, int(width * 0.68))
        right_width = max(24, width - left_width - 3)
        content_height = max(8, height - 9)
        suggestion_slots = min(4, max(0, len(self._slash_suggestions)))
        input_box_height = 4 + suggestion_slots
        content_height = max(8, height - (input_box_height + 5))

        left_lines = self._build_transcript_lines(left_width)
        right_lines = self._build_sidebar_lines(right_width, content_height)

        visible_left = left_lines[-content_height:]
        while len(visible_left) < content_height:
            visible_left.insert(0, "")
        while len(right_lines) < content_height:
            right_lines.append("")

        logo = f"{ANSI_BOLD}{ANSI_CYAN}MOMA{ANSI_RESET}"
        header = logo.center(width)
        separator = "─" * width
        input_top = f"{ANSI_BOLD}{ANSI_BLUE}┌{'─' * max(10, width - 2)}┐{ANSI_RESET}"
        input_title = f"{ANSI_BOLD}{ANSI_BLUE}│{ANSI_RESET}{ANSI_BOLD} Chat {ANSI_RESET}{ANSI_DIM}(Enter to send, /help for commands){ANSI_RESET}"
        input_title = self._pad_box_line(input_title, width)
        preview = self._input_buffer if self._input_buffer else (self._last_prompt if self._last_prompt else self._input_placeholder)
        preview = self._truncate_plain(preview, max(8, width - len(self._input_label) - 6))
        prompt_line = f"{ANSI_BOLD}{ANSI_BLUE}│{ANSI_RESET}{ANSI_BOLD}{self._input_label}{ANSI_RESET}{preview}"
        prompt_line = self._pad_box_line(prompt_line, width)
        suggestion_lines = self._build_input_suggestion_lines(width)
        input_bottom = f"{ANSI_BOLD}{ANSI_BLUE}└{'─' * max(10, width - 2)}┘{ANSI_RESET}"

        if not self._screen_initialized:
            self.stdout.write(ANSI_CLEAR)
            self._screen_initialized = True
        else:
            self.stdout.write(ANSI_HOME)
        self.stdout.write(header + "\n")
        self.stdout.write(separator + "\n")
        for i in range(content_height):
            left = self._pad_visible_line(visible_left[i], left_width)
            right = self._pad_visible_line((right_lines[i] if i < len(right_lines) else "")[:right_width], right_width)
            self.stdout.write(f"{left} │ {right}\n")
        self.stdout.write(separator + "\n")
        self.stdout.write(input_top + "\n")
        self.stdout.write(input_title + "\n")
        self.stdout.write(prompt_line + "\n")
        for line in suggestion_lines:
            self.stdout.write(line + "\n")
        self.stdout.write(input_bottom)
        self.stdout.write(ANSI_CLEAR_TO_END)
        if not self._chat_started:
            self.stdout.write("\n")
        self.stdout.flush()

    def _build_transcript_lines(self, width: int) -> list[str]:
        lines: list[str] = []
        for item in self._transcript:
            lines.extend(self._build_message_block(item, width))
        return lines or [""]

    def _build_sidebar_lines(self, width: int, height: int) -> list[str]:
        lines: list[str] = []
        lines.extend(self._wrap_colored_line("Subagents", ANSI_BOLD + ANSI_MAGENTA, width))
        if not self._subagents:
            lines.extend(self._wrap_colored_line("- idle", ANSI_DIM, width))
        else:
            for card in self._subagents.values():
                status_color = ANSI_GREEN if card.status == "completed" else ANSI_YELLOW if card.status == "running" else ANSI_RED
                accent = ANSI_BOLD + (ANSI_CYAN if card.active else status_color)
                marker = "●" if card.active else "○"
                lines.extend(self._wrap_colored_line("┏" + "━" * max(4, width - 2) + "┓" if card.active else "┌" + "─" * max(4, width - 2) + "┐", accent if card.active else ANSI_DIM, width))
                lines.extend(self._wrap_colored_line(f"{marker} {card.name} [{card.status}]", accent, width))
                if card.active:
                    lines.extend(self._wrap_colored_line("active now", ANSI_BOLD + ANSI_CYAN, width))
                if card.last_event:
                    lines.extend(self._wrap_colored_line(f"event: {card.last_event}", ANSI_DIM, width))
                if card.metadata_lines:
                    lines.extend(self._wrap_colored_line("metadata:", ANSI_DIM, width))
                    for meta in card.metadata_lines[-2:]:
                        lines.extend(self._wrap_colored_line(f"· {meta}", ANSI_CYAN if card.active else ANSI_DIM, width))
                if card.last_text:
                    lines.extend(self._wrap_colored_line("output:", ANSI_DIM, width))
                    lines.extend(self._wrap_colored_line(card.last_text, accent if card.active else ANSI_MAGENTA, width))
                if card.log_lines:
                    lines.extend(self._wrap_colored_line("log:", ANSI_DIM, width))
                for log_line in card.log_lines[-3:]:
                    lines.extend(self._wrap_colored_line(f"· {log_line}", ANSI_YELLOW if card.active else ANSI_DIM, width))
                lines.extend(self._wrap_colored_line("┗" + "━" * max(4, width - 2) + "┛" if card.active else "└" + "─" * max(4, width - 2) + "┘", accent if card.active else ANSI_DIM, width))
                lines.append("")

        lines.extend(self._wrap_colored_line("Todos", ANSI_BOLD + ANSI_CYAN, width))
        if not self._todos:
            lines.extend(self._wrap_colored_line("- none", ANSI_DIM, width))
        else:
            for plan in self._todos:
                plan_color = ANSI_GREEN if plan.done else ANSI_CYAN
                lines.extend(self._wrap_colored_line(f"#{plan.mission_id} {plan.title}", ANSI_BOLD + plan_color, width))
                for step in plan.steps:
                    marker = self._todo_marker(step.status)
                    lines.extend(self._wrap_colored_line(f"{marker} {step.title}", self._todo_color(step.status), width))
                lines.append("")
        return lines[:height]

    def _wrap_colored_line(self, text: str, color: str, width: int) -> list[str]:
        raw = text or ""
        wrapped = textwrap.wrap(raw, width=max(8, width), replace_whitespace=False, drop_whitespace=False) or [raw[:width]]
        if color:
            return [f"{color}{line}{ANSI_RESET}" for line in wrapped]
        return wrapped

    def _build_message_block(self, item: TranscriptLine, width: int) -> list[str]:
        inner_width = max(12, width - 4)
        role_styles = {
            "user": (ANSI_BLUE, "YOU"),
            "subagent": (ANSI_MAGENTA, f"SUBAGENT · {item.agent_name}" if item.agent_name else "SUBAGENT"),
            "tool": (ANSI_YELLOW, "TOOL"),
            "reasoning": (ANSI_GREEN, "REASONING"),
            "error": (ANSI_RED, "ERROR"),
            "system": (item.color or ANSI_WHITE, "SYSTEM"),
            "message": (ANSI_CYAN, item.agent_name or "MOMA"),
        }
        color, label = role_styles.get(item.role, (item.color or ANSI_CYAN, "MESSAGE"))
        label_width = len(self._strip_ansi(label))
        lines = [f"{color}┌─ {label} {'─' * max(2, inner_width - label_width - 2)}┐{ANSI_RESET}"]
        for wrapped in textwrap.wrap(item.text or "", width=inner_width, replace_whitespace=False, drop_whitespace=False) or [""]:
            body = wrapped.ljust(inner_width)
            lines.append(f"{color}│{ANSI_RESET} {item.color}{body}{ANSI_RESET} {color}│{ANSI_RESET}")
        lines.append(f"{color}└{'─' * (inner_width + 2)}┘{ANSI_RESET}")
        return lines

    def _truncate_plain(self, text: str, width: int) -> str:
        if len(text) <= width:
            return text
        if width <= 1:
            return text[:width]
        return text[: width - 1] + "…"

    def _pad_box_line(self, raw_line: str, width: int) -> str:
        visible = self._strip_ansi(raw_line)
        padding = max(0, width - len(visible) - 1)
        return raw_line + (" " * padding) + f"{ANSI_BOLD}{ANSI_BLUE}│{ANSI_RESET}"

    def _pad_visible_line(self, text: str, width: int) -> str:
        visible = self._visible_len(text)
        if visible >= width:
            return text
        return text + (" " * (width - visible))

    def _visible_len(self, text: str) -> int:
        return len(self._strip_ansi(text))

    def _strip_ansi(self, text: str) -> str:
        for code in (ANSI_RESET, ANSI_BOLD, ANSI_DIM, ANSI_CYAN, ANSI_MAGENTA, ANSI_GREEN, ANSI_YELLOW, ANSI_RED, ANSI_BLUE, ANSI_WHITE):
            text = text.replace(code, "")
        return text

    def _agent_color(self, event: ResponseEventEnvelope) -> str:
        if event.agent.kind == "orchestrator":
            return ANSI_CYAN
        if event.agent.kind == "router":
            return ANSI_YELLOW
        palette = [ANSI_MAGENTA, ANSI_GREEN, ANSI_BLUE, ANSI_WHITE]
        key = event.agent.id or event.agent.name
        return palette[sum(ord(ch) for ch in key) % len(palette)]

    def _metadata_color(self, event: ResponseEventEnvelope) -> str:
        return ANSI_BOLD + self._agent_color(event)

    def _build_input_suggestion_lines(self, width: int) -> list[str]:
        lines: list[str] = []
        if not self._slash_suggestions:
            return lines
        is_resume_menu = self._input_buffer.strip().startswith("/resume")
        title = "Resume Sessions" if is_resume_menu else "Slash Commands"
        header = f"{ANSI_BOLD}{ANSI_BLUE}│{ANSI_RESET}{ANSI_BOLD}{ANSI_CYAN} {title} {ANSI_RESET}"
        lines.append(self._pad_box_line(header, width))
        if is_resume_menu:
            hint = f"{ANSI_BOLD}{ANSI_BLUE}│{ANSI_RESET}{ANSI_DIM} ↑↓ choose, Enter restore, Esc close {ANSI_RESET}"
            lines.append(self._pad_box_line(hint, width))
        for index, suggestion in enumerate(self._slash_suggestions[:4]):
            selected = index == self._selected_suggestion
            prefix = "▶" if selected else "·"
            color = ANSI_BOLD + ANSI_GREEN if selected else ANSI_DIM
            detail = self._slash_suggestion_details[index] if index < len(self._slash_suggestion_details) else ""
            command_text = self._truncate_plain(f"{prefix} {suggestion}", max(8, width - 6))
            line = f"{ANSI_BOLD}{ANSI_BLUE}│{ANSI_RESET}{color}{command_text}{ANSI_RESET}"
            lines.append(self._pad_box_line(line, width))
            if detail:
                detail_color = ANSI_CYAN if selected else ANSI_DIM
                detail_text = self._truncate_plain(f"  {detail}", max(8, width - 6))
                detail_line = f"{ANSI_BOLD}{ANSI_BLUE}│{ANSI_RESET}{detail_color}{detail_text}{ANSI_RESET}"
                lines.append(self._pad_box_line(detail_line, width))
        return lines

    def _todo_marker(self, status: str) -> str:
        return {
            "completed": "[x]",
            "running": "[~]",
            "failed": "[!]",
            "pending": "[ ]",
        }.get(status, "[?]")

    def _todo_color(self, status: str) -> str:
        return {
            "completed": ANSI_GREEN,
            "running": ANSI_YELLOW,
            "failed": ANSI_RED,
            "pending": ANSI_DIM,
        }.get(status, ANSI_DIM)

    def _ensure_trailing_newline(self) -> None:
        if self._last_agent_name is not None:
            self.stdout.write("\n")
            self.stdout.flush()
            self._last_agent_name = None
