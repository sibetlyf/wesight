from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .history import (
    format_history_lines,
    format_history_session_lines,
    list_history_entries,
    list_history_sessions,
    read_history_entry,
    read_latest_history_for_session,
)

from .mcp import (
    check_mcp_servers,
    format_mcp_status_lines,
    import_mcp_config,
    list_mcp_servers,
    remove_mcp_server,
    write_mcp_server,
)
from .renderer import EventRenderer


@dataclass(frozen=True)
class SlashCommandResult:
    handled: bool
    should_exit: bool = False
    exit_code: int = 0
    restore_session_id: str | None = None


@dataclass(frozen=True)
class SlashCommandSpec:
    command: str
    description: str


SLASH_COMMANDS: tuple[SlashCommandSpec, ...] = (
    SlashCommandSpec("/help", "Show this help message"),
    SlashCommandSpec("/exit", "Exit interactive mode"),
    SlashCommandSpec("/quit", "Exit interactive mode"),
    SlashCommandSpec("/clear", "Print a visual separator"),
    SlashCommandSpec("/session", "Show current session id"),
    SlashCommandSpec("/history", "List saved local history records"),
    SlashCommandSpec("/history list", "List saved local history records"),
    SlashCommandSpec("/history show", "Show one saved history record"),
    SlashCommandSpec("/resume", "List saved conversations for resume"),
    SlashCommandSpec("/resume <session-id|index>", "Resume one saved conversation"),
    SlashCommandSpec("/workspace", "Show current workspace path"),
    SlashCommandSpec("/runspace", "Show current runspace path"),
    SlashCommandSpec("/mcp", "List configured MCP servers"),
    SlashCommandSpec("/mcp list", "List configured MCP servers"),
    SlashCommandSpec("/mcp check", "Probe configured MCP servers"),
    SlashCommandSpec("/mcp add", "Add one MCP server"),
    SlashCommandSpec("/mcp remove", "Remove one MCP server"),
    SlashCommandSpec("/mcp import", "Import MCP config file"),
)


def _build_help_text() -> str:
    lines = ["Available commands:"]
    for spec in SLASH_COMMANDS:
        lines.append(f"{spec.command:<12} {spec.description}")
    return "\n".join(lines)


HELP_TEXT = _build_help_text()


def get_slash_suggestions(prefix: str) -> list[SlashCommandSpec]:
    normalized = prefix.strip()
    if not normalized.startswith("/"):
        return []
    if normalized == "/":
        return list(SLASH_COMMANDS)
    if normalized.startswith("/resume"):
        dynamic = _get_resume_suggestions(normalized)
        if dynamic:
            return dynamic
    return [spec for spec in SLASH_COMMANDS if spec.command.startswith(normalized)]


def _get_resume_suggestions(prefix: str) -> list[SlashCommandSpec]:
    userspace = None
    target = prefix[len("/resume") :].strip().lower() if prefix.startswith("/resume") else ""
    suggestions: list[SlashCommandSpec] = []
    for index, entry in enumerate(list_history_sessions(userspace, limit=8), start=1):
        session_id = str(entry.get("session_id") or "").strip()
        if not session_id:
            continue
        if target and target not in session_id.lower() and target not in str(index):
            continue
        prompt = str(entry.get("prompt") or "").replace("\n", " ").strip()
        prompt_preview = prompt[:36] + ("..." if len(prompt) > 36 else "")
        created_at = str(entry.get("created_at") or "unknown")
        suggestions.append(
            SlashCommandSpec(
                command=f"/resume {session_id}",
                description=f"Resume {session_id} · {created_at} · {prompt_preview}".strip(),
            )
        )
    if suggestions:
        return suggestions
    return [spec for spec in SLASH_COMMANDS if spec.command.startswith(prefix)]


def handle_slash_command(
    command: str,
    renderer: EventRenderer,
    context: Mapping[str, str] | None = None,
) -> SlashCommandResult:
    normalized = command.strip()
    if not normalized.startswith("/"):
        return SlashCommandResult(handled=False)

    if normalized in {"/exit", "/quit"}:
        renderer.print_system("Bye.")
        return SlashCommandResult(handled=True, should_exit=True)
    if normalized == "/help":
        renderer.print_system(HELP_TEXT.rstrip())
        return SlashCommandResult(handled=True)
    if normalized == "/clear":
        renderer.print_system("-" * 40)
        return SlashCommandResult(handled=True)
    if normalized == "/session":
        session_id = (context or {}).get("session_id", "unknown")
        renderer.print_system(f"session: {session_id}")
        return SlashCommandResult(handled=True)
    if normalized.startswith("/history"):
        return _handle_history_slash_command(normalized, renderer, context)
    if normalized.startswith("/resume"):
        return _handle_resume_slash_command(normalized, renderer, context)
    if normalized == "/workspace":
        workspace = (context or {}).get("workspace", "unknown")
        renderer.print_system(f"workspace: {workspace}")
        return SlashCommandResult(handled=True)
    if normalized == "/runspace":
        runspace = (context or {}).get("runspace", "unknown")
        renderer.print_system(f"runspace: {runspace}")
        return SlashCommandResult(handled=True)
    if normalized.startswith("/mcp"):
        return _handle_mcp_slash_command(normalized, renderer, context)

    renderer.print_system(f"Unknown command: {normalized}")
    return SlashCommandResult(handled=True, exit_code=1)


def _handle_mcp_slash_command(
    command: str,
    renderer: EventRenderer,
    context: Mapping[str, str] | None,
) -> SlashCommandResult:
    workspace = (context or {}).get("workspace")
    parts = command.split()
    if len(parts) == 1 or parts[1] == "list":
        servers = list_mcp_servers(workspace)
        if not servers:
            renderer.print_system("[mcp] no configured servers")
            return SlashCommandResult(handled=True)
        for server in servers:
            renderer.print_system(
                f"[mcp] {server['name']} {server['transport']} {server['url']}"
            )
        return SlashCommandResult(handled=True)

    subcommand = parts[1]
    if subcommand == "check":
        for line in format_mcp_status_lines(check_mcp_servers(workspace)):
            renderer.print_system(line)
        return SlashCommandResult(handled=True)

    if subcommand == "add":
        if len(parts) < 4:
            renderer.print_system("Usage: /mcp add <name> <url> [sse|streamable-http]")
            return SlashCommandResult(handled=True, exit_code=1)
        name = parts[2]
        url = parts[3]
        transport = parts[4] if len(parts) >= 5 else "sse"
        path = write_mcp_server(name=name, url=url, transport=transport, workspace=workspace)
        renderer.print_system(f"[mcp] added {name}: {path}")
        return SlashCommandResult(handled=True)

    if subcommand == "remove":
        if len(parts) < 3:
            renderer.print_system("Usage: /mcp remove <name>")
            return SlashCommandResult(handled=True, exit_code=1)
        removed = remove_mcp_server(parts[2], workspace)
        if removed:
            renderer.print_system(f"[mcp] removed {parts[2]}")
            return SlashCommandResult(handled=True)
        renderer.print_system(f"[mcp] server not found: {parts[2]}")
        return SlashCommandResult(handled=True, exit_code=1)

    if subcommand == "import":
        if len(parts) < 3:
            renderer.print_system("Usage: /mcp import <path>")
            return SlashCommandResult(handled=True, exit_code=1)
        imported = import_mcp_config(parts[2], workspace)
        renderer.print_system(f"[mcp] imported: {', '.join(imported)}")
        return SlashCommandResult(handled=True)

    renderer.print_system("Usage: /mcp [list|check|add|remove|import]")
    return SlashCommandResult(handled=True, exit_code=1)


def _handle_history_slash_command(
    command: str,
    renderer: EventRenderer,
    context: Mapping[str, str] | None,
) -> SlashCommandResult:
    userspace = (context or {}).get("userspace")
    parts = command.split(maxsplit=2)
    if len(parts) == 1 or parts[1] == "list":
        for line in format_history_lines(list_history_entries(userspace)):
            renderer.print_system(line)
        return SlashCommandResult(handled=True)
    if parts[1] == "show":
        if len(parts) < 3:
            renderer.print_system("Usage: /history show <entry-id>")
            return SlashCommandResult(handled=True, exit_code=1)
        record = read_history_entry(parts[2], userspace)
        renderer.print_system(
            f"[history] {record.get('entry_id')} session={record.get('session_id')} mode={record.get('mode')} prompt={record.get('prompt')}"
        )
        preview = str(record.get("assistant_text_preview") or "").strip()
        if preview:
            renderer.print_system(f"[history] preview: {preview}")
        return SlashCommandResult(handled=True)
    renderer.print_system("Usage: /history [list|show <entry-id>]")
    return SlashCommandResult(handled=True, exit_code=1)


def _handle_resume_slash_command(
    command: str,
    renderer: EventRenderer,
    context: Mapping[str, str] | None,
) -> SlashCommandResult:
    userspace = (context or {}).get("userspace")
    parts = command.split(maxsplit=1)
    if len(parts) == 1:
        for line in format_history_session_lines(list_history_sessions(userspace)):
            renderer.print_system(line)
        renderer.print_system("[resume] use /resume <session-id|index>")
        return SlashCommandResult(handled=True)

    sessions = list_history_sessions(userspace)
    target = parts[1].strip()
    record: dict[str, object]
    if target.isdigit():
        index = int(target)
        if index < 1 or index > len(sessions):
            renderer.print_system(f"[resume] invalid selection: {target}")
            return SlashCommandResult(handled=True, exit_code=1)
        record = read_latest_history_for_session(str(sessions[index - 1].get("session_id") or ""), userspace)
    else:
        record = read_latest_history_for_session(target, userspace)

    renderer.print_system(
        f"[resume] restoring latest record from session {record.get('session_id')}"
    )
    return SlashCommandResult(
        handled=True,
        restore_session_id=str(record.get("session_id") or "unknown"),
    )
