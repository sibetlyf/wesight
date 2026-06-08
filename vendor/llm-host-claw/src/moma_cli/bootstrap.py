from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from configs.orchestrator import OrchestratorConfig
from .mcp import import_mcp_config, import_mcp_payload

DEFAULT_USER_ID = "cli-user"
DEFAULT_AUTHORIZATION = "CLI"


def split_main_config(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    orchestrator_payload = dict(payload)
    mcp_payload: dict[str, Any] | None = None

    if isinstance(payload.get("mcpServers"), dict):
        mcp_payload = {"mcpServers": payload["mcpServers"]}
        orchestrator_payload.pop("mcpServers", None)
    elif isinstance(payload.get("servers"), list):
        mcp_payload = {"servers": payload["servers"]}
        orchestrator_payload.pop("servers", None)

    return orchestrator_payload, mcp_payload


def bootstrap_environment(
    *,
    config_path: str | None,
    mcp_config_path: str | None,
    workspace: str | None,
    session_id: str | None,
    user_id: str | None,
    api_key: str | None,
    authorization: str | None,
    sandbox: bool = False,
    sandbox_root: str | None = None,
    require_orchestrator_config: bool = True,
) -> dict[str, str]:
    resolved_session_id = session_id or f"session-{uuid.uuid4().hex[:12]}"
    userspace = Path(workspace).expanduser().resolve() if workspace else (Path.cwd() / ".moma_cli")
    sessionspace = userspace / "sessions"
    workspace_dir = sessionspace / resolved_session_id
    runspace = workspace_dir / "runs"

    for directory in (userspace, sessionspace, workspace_dir, runspace):
        directory.mkdir(parents=True, exist_ok=True)

    env_updates = {
        "USERSPACE": str(userspace),
        "SESSIONSPACE": str(sessionspace),
        "SESSION_ID": resolved_session_id,
        "WORKSPACE": str(workspace_dir),
        "RUNSPACE": str(runspace),
        "USER_ID": user_id or os.environ.get("USER_ID", DEFAULT_USER_ID),
        "RECORD_ID": os.environ.get("RECORD_ID", uuid.uuid4().hex),
        "AUTHORIZATION": authorization or os.environ.get("AUTHORIZATION", DEFAULT_AUTHORIZATION),
        "MOMA_SANDBOX_ENABLED": "true" if sandbox else "false",
        "MOMA_SANDBOX_ROOT": str(Path(sandbox_root).expanduser().resolve()) if sandbox_root else str(workspace_dir),
    }

    if api_key:
        env_updates["API_KEY"] = api_key
    elif os.environ.get("API_KEY"):
        env_updates["API_KEY"] = os.environ["API_KEY"]

    for key, value in env_updates.items():
        os.environ[key] = value

    if config_path:
        config = load_config_file(config_path)
        orchestrator_config, embedded_mcp_config = split_main_config(config)
        if require_orchestrator_config or "model" in orchestrator_config or "toolkits" in orchestrator_config:
            OrchestratorConfig.model_validate(orchestrator_config).to_env()
    elif require_orchestrator_config and not os.environ.get("ORCHESTRATOR_CONFIG"):
        raise ValueError(
            "ORCHESTRATOR_CONFIG is not set. Pass --config to the CLI or export ORCHESTRATOR_CONFIG first."
        )
    else:
        embedded_mcp_config = None

    if embedded_mcp_config:
        import_mcp_payload(embedded_mcp_config, str(workspace_dir))

    if mcp_config_path:
        import_mcp_config(mcp_config_path, str(workspace_dir))

    return env_updates


def resolve_userspace(workspace: str | None) -> Path:
    return Path(workspace).expanduser().resolve() if workspace else (Path.cwd() / ".moma_cli")


def list_sessions(workspace: str | None) -> list[dict[str, str]]:
    userspace = resolve_userspace(workspace)
    sessionspace = userspace / "sessions"
    if not sessionspace.exists():
        return []

    sessions: list[dict[str, str]] = []
    for entry in sorted(sessionspace.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
        if not entry.is_dir():
            continue
        runs_dir = entry / "runs"
        sessions.append(
            {
                "session_id": entry.name,
                "workspace": str(entry),
                "runs_dir": str(runs_dir),
            }
        )
    return sessions


def environment_summary(workspace: str | None, session_id: str | None, config_path: str | None) -> dict[str, str | bool | int | None]:
    from .mcp import count_mcp_servers

    userspace = resolve_userspace(workspace)
    sessionspace = userspace / "sessions"
    resolved_session_id = session_id or os.environ.get("SESSION_ID") or os.environ.get("RECORD_ID") or None
    workspace_value = os.environ.get("WORKSPACE")
    embedded_mcp_server_count = 0
    if config_path:
        try:
            preview = read_config_preview(config_path)
            embedded_mcp_server_count = int(preview.get("mcp_server_count", 0) or 0)
        except Exception:
            embedded_mcp_server_count = 0
    return {
        "userspace": str(userspace),
        "sessionspace": str(sessionspace),
        "session_id": resolved_session_id,
        "config_path": str(Path(config_path).expanduser().resolve()) if config_path else None,
        "has_orchestrator_config": bool(config_path or os.environ.get("ORCHESTRATOR_CONFIG")),
        "has_api_key": bool(os.environ.get("API_KEY")),
        "workspace": workspace_value,
        "runspace": os.environ.get("RUNSPACE"),
        "mcp_server_count": (count_mcp_servers(workspace_value) if workspace_value else 0) + embedded_mcp_server_count,
    }


def read_config_preview(config_path: str) -> dict[str, Any]:
    config = load_config_file(config_path)
    orchestrator_config, embedded_mcp_config = split_main_config(config)
    model = orchestrator_config.get("model") if isinstance(orchestrator_config, dict) else None
    toolkits = orchestrator_config.get("toolkits") if isinstance(orchestrator_config, dict) else None
    toolkit_targets: list[str] = []
    if isinstance(toolkits, list):
        for item in toolkits:
            if isinstance(item, dict) and isinstance(item.get("target"), str):
                toolkit_targets.append(item["target"])
    mcp_server_count = 0
    if embedded_mcp_config:
        if isinstance(embedded_mcp_config.get("servers"), list):
            mcp_server_count = len(embedded_mcp_config["servers"])
        elif isinstance(embedded_mcp_config.get("mcpServers"), dict):
            mcp_server_count = len(embedded_mcp_config["mcpServers"])
    return {
        "model": model,
        "toolkit_count": len(toolkit_targets),
        "toolkits": toolkit_targets,
        "mcp_server_count": mcp_server_count,
    }


def load_config_file(config_path: str) -> dict[str, Any]:
    path = Path(config_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")
    if suffix == ".json":
        data = json.loads(text)
    elif suffix in {".yaml", ".yml"}:
        import yaml

        data = yaml.safe_load(text)
    else:
        raise ValueError("Config file must be .json, .yaml, or .yml")

    if not isinstance(data, dict):
        raise ValueError("Config file must contain an object at the top level")
    return data
