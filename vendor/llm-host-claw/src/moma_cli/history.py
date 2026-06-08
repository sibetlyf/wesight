from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .sandbox import ensure_within_root, sandbox_enabled


def resolve_history_dir(workspace: str | None = None) -> Path | None:
    workspace_value = workspace or os.environ.get("WORKSPACE")
    if not workspace_value:
        return None
    workspace_path = ensure_within_root(workspace_value) if sandbox_enabled() else Path(workspace_value).expanduser().resolve()
    history_dir = workspace_path / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    return history_dir


def write_history_entry(
    *,
    prompt: str,
    mode: str,
    events: list[dict[str, object]],
    workspace: str | None = None,
    session_id: str | None = None,
    runspace: str | None = None,
    userspace: str | None = None,
) -> Path | None:
    history_dir = resolve_history_dir(workspace)
    if history_dir is None:
        return None

    created_at = datetime.now(UTC)
    entry_id = f"hist_{created_at.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    payload = {
        "version": 1,
        "entry_id": entry_id,
        "created_at": created_at.isoformat(),
        "session_id": session_id or os.environ.get("SESSION_ID") or "unknown",
        "userspace": userspace or os.environ.get("USERSPACE"),
        "workspace": str(Path(workspace or os.environ.get("WORKSPACE", "")).expanduser().resolve()),
        "runspace": str(Path(runspace or os.environ.get("RUNSPACE", "")).expanduser().resolve()) if (runspace or os.environ.get("RUNSPACE")) else None,
        "mode": mode,
        "prompt": prompt,
        "message_count": _count_matching_events(events, "response.output_text") + _count_exact_events(events, "response.created"),
        "tool_count": _count_matching_events(events, "response.tool_call"),
        "subagent_count": _count_matching_events(events, "response.subagent"),
        "assistant_text_preview": _build_assistant_preview(events),
        "events": events,
    }
    path = history_dir / f"{entry_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def list_history_entries(userspace: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    userspace_value = userspace or os.environ.get("USERSPACE")
    if not userspace_value:
        return []
    sessions_dir = Path(userspace_value).expanduser().resolve() / "sessions"
    if sandbox_enabled():
        sessions_dir = ensure_within_root(sessions_dir)
    if not sessions_dir.exists():
        return []

    entries: list[dict[str, Any]] = []
    for path in sessions_dir.glob("*/history/*.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        entries.append(
            {
                "entry_id": raw.get("entry_id") or path.stem,
                "created_at": raw.get("created_at"),
                "session_id": raw.get("session_id"),
                "workspace": raw.get("workspace"),
                "mode": raw.get("mode"),
                "prompt": raw.get("prompt"),
                "assistant_text_preview": raw.get("assistant_text_preview", ""),
                "path": str(path),
            }
        )
    entries.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return entries[:limit]


def read_history_entry(entry_id: str, userspace: str | None = None) -> dict[str, Any]:
    entries = list_history_entries(userspace, limit=500)
    normalized = entry_id.strip()
    for entry in entries:
        candidate = str(entry.get("entry_id") or "")
        if candidate == normalized or candidate.startswith(normalized):
            path = Path(str(entry["path"]))
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError(f"Invalid history record: {path}")
            return raw
    raise FileNotFoundError(f"History entry not found: {entry_id}")


def list_history_sessions(userspace: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    entries = list_history_entries(userspace, limit=500)
    latest_by_session: dict[str, dict[str, Any]] = {}
    for entry in entries:
        session_id = str(entry.get("session_id") or "unknown")
        if session_id not in latest_by_session:
            latest_by_session[session_id] = entry
    sessions = list(latest_by_session.values())
    sessions.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return sessions[:limit]


def read_latest_history_for_session(session_id: str, userspace: str | None = None) -> dict[str, Any]:
    normalized = session_id.strip()
    entries = list_history_entries(userspace, limit=500)
    for entry in entries:
        candidate = str(entry.get("session_id") or "")
        if candidate == normalized:
            path = Path(str(entry["path"]))
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError(f"Invalid history record: {path}")
            return raw
    raise FileNotFoundError(f"History session not found: {session_id}")


def format_history_lines(entries: list[dict[str, Any]]) -> list[str]:
    if not entries:
        return ["[history] no saved records"]
    lines: list[str] = []
    for entry in entries:
        entry_id = str(entry.get("entry_id") or "unknown")
        created_at = str(entry.get("created_at") or "unknown")
        session_id = str(entry.get("session_id") or "unknown")
        prompt = str(entry.get("prompt") or "").replace("\n", " ").strip()
        preview = prompt[:48] + ("..." if len(prompt) > 48 else "")
        lines.append(f"[history] {entry_id} session={session_id} at {created_at} prompt={preview}")
    return lines


def format_history_session_lines(entries: list[dict[str, Any]]) -> list[str]:
    if not entries:
        return ["[resume] no saved conversations"]
    lines: list[str] = []
    for index, entry in enumerate(entries, start=1):
        created_at = str(entry.get("created_at") or "unknown")
        session_id = str(entry.get("session_id") or "unknown")
        prompt = str(entry.get("prompt") or "").replace("\n", " ").strip()
        preview = prompt[:48] + ("..." if len(prompt) > 48 else "")
        lines.append(f"[resume] {index}. session={session_id} at {created_at} prompt={preview}")
    return lines


def _count_matching_events(events: list[dict[str, object]], prefix: str) -> int:
    count = 0
    for event in events:
        event_type = event.get("type")
        if isinstance(event_type, str) and event_type.startswith(prefix):
            count += 1
    return count


def _count_exact_events(events: list[dict[str, object]], event_type: str) -> int:
    count = 0
    for event in events:
        if event.get("type") == event_type:
            count += 1
    return count


def _build_assistant_preview(events: list[dict[str, object]]) -> str:
    chunks: list[str] = []
    for event in events:
        if event.get("type") != "response.output_text.delta":
            continue
        data = event.get("data")
        if isinstance(data, dict) and isinstance(data.get("delta"), str):
            chunks.append(data["delta"])
    text = "".join(chunks).strip()
    return text[:240]
