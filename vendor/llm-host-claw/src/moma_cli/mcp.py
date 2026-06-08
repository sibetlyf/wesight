from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Literal, cast

from agno.tools.mcp import MCPTools

from .sandbox import ensure_within_root, sandbox_enabled
from protocol.mcp_card import MCPCard


def resolve_mcp_tools_dir(workspace: str | None = None) -> Path:
    workspace_path = Path(workspace or "").expanduser().resolve() if workspace else Path.cwd()
    if not workspace:
        workspace_env = Path(str(Path.cwd()))
        try:
            from os import environ

            if environ.get("WORKSPACE"):
                workspace_env = Path(environ["WORKSPACE"]).expanduser().resolve()
        except Exception:
            workspace_env = Path.cwd()
        workspace_path = workspace_env
    if sandbox_enabled():
        workspace_path = ensure_within_root(workspace_path)
    tools_dir = workspace_path / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    return tools_dir


def _safe_mcp_name(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip())
    slug = slug.strip("-.")
    return slug or "mcp-server"


def list_mcp_servers(workspace: str | None = None) -> list[dict[str, Any]]:
    tools_dir = resolve_mcp_tools_dir(workspace)
    servers: list[dict[str, Any]] = []
    for path in sorted(tools_dir.glob("*.json")):
        raw_payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw_payload, dict):
            raise ValueError(f"Invalid MCP card file: {path}")
        card = MCPCard.model_validate(raw_payload)
        servers.append(
            {
                "name": str(raw_payload.get("name") or path.stem),
                "file": str(path),
                "url": card.url,
                "transport": card.transport,
                "timeout": card.timeout,
                "headers": card.headers or {},
            }
        )
    return servers


def write_mcp_server(
    *,
    name: str,
    url: str,
    transport: str = "sse",
    headers: dict[str, Any] | None = None,
    timeout: float = 30,
    workspace: str | None = None,
) -> Path:
    normalized_transport = cast(Literal["sse", "streamable-http"], transport)
    card = MCPCard(url=url, transport=normalized_transport, headers=headers, timeout=timeout)
    tools_dir = resolve_mcp_tools_dir(workspace)
    target = tools_dir / f"{_safe_mcp_name(name)}.json"
    payload = card.model_dump(exclude_none=True)
    payload["name"] = name
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def remove_mcp_server(name: str, workspace: str | None = None) -> bool:
    tools_dir = resolve_mcp_tools_dir(workspace)
    target = tools_dir / f"{_safe_mcp_name(name)}.json"
    if not target.exists():
        return False
    target.unlink()
    return True


def import_mcp_config(config_path: str, workspace: str | None = None) -> list[str]:
    from .bootstrap import load_config_file

    payload = load_config_file(config_path)
    return import_mcp_payload(payload, workspace)


def import_mcp_payload(payload: dict[str, Any], workspace: str | None = None) -> list[str]:
    imported: list[str] = []

    if isinstance(payload.get("servers"), list):
        entries = payload["servers"]
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("Each MCP server entry must be an object")
            name = entry.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Each MCP server entry in servers[] must include a non-empty name")
            transport = entry.get("transport") or entry.get("type") or "sse"
            write_mcp_server(
                name=name,
                url=str(entry["url"]),
                transport=str(transport),
                headers=entry.get("headers"),
                timeout=float(entry.get("timeout", 30)),
                workspace=workspace,
            )
            imported.append(name)
        return imported

    if isinstance(payload.get("mcpServers"), dict):
        for name, entry in payload["mcpServers"].items():
            if not isinstance(entry, dict):
                raise ValueError("Each MCP server entry in mcpServers must be an object")
            if "url" not in entry:
                raise ValueError(f"MCP server '{name}' is missing required field: url")
            if "command" in entry:
                raise ValueError(
                    f"MCP server '{name}' uses stdio/command style config, which this CLI does not support yet; only url-based sse/streamable-http cards are supported"
                )
            transport = entry.get("transport") or entry.get("type") or "sse"
            write_mcp_server(
                name=str(name),
                url=str(entry["url"]),
                transport=str(transport),
                headers=entry.get("headers"),
                timeout=float(entry.get("timeout", 30)),
                workspace=workspace,
            )
            imported.append(str(name))
        return imported

    if "url" in payload:
        name = payload.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Single MCP card config must include a non-empty name")
        transport = payload.get("transport") or payload.get("type") or "sse"
        write_mcp_server(
            name=name,
            url=str(payload["url"]),
            transport=str(transport),
            headers=payload.get("headers"),
            timeout=float(payload.get("timeout", 30)),
            workspace=workspace,
        )
        return [name]

    raise ValueError("MCP config file must be one of: {servers: [...]}, {mcpServers: {...}}, or a single MCP card object")


async def _probe_card(name: str, card: MCPCard, file_path: str) -> dict[str, Any]:
    toolkit = MCPTools(
        transport=card.transport,
        server_params=card.agno_server_params,
        timeout_seconds=max(1, int(card.timeout)),
    )
    result: dict[str, Any] = {
        "name": name,
        "file": file_path,
        "url": card.url,
        "transport": card.transport,
        "status": "failed",
        "tool_count": 0,
    }
    try:
        await asyncio.wait_for(toolkit.connect(force=True), timeout=max(1.0, float(card.timeout) + 5.0))
        initialized = bool(getattr(toolkit, "_initialized", False))
        if not initialized:
            result["error"] = "MCPTools did not finish initialization"
            return result
        result["status"] = "ok"
        result["tool_count"] = len(getattr(toolkit, "functions", {}))
        return result
    except Exception as exc:
        result["error"] = str(exc)
        return result
    finally:
        try:
            await toolkit.close()
        except Exception:
            pass


async def check_mcp_servers_async(workspace: str | None = None) -> list[dict[str, Any]]:
    tools_dir = resolve_mcp_tools_dir(workspace)
    results: list[dict[str, Any]] = []
    for path in sorted(tools_dir.glob("*.json")):
        raw_payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw_payload, dict):
            raise ValueError(f"Invalid MCP card file: {path}")
        card = MCPCard.model_validate(raw_payload)
        results.append(await _probe_card(str(raw_payload.get("name") or path.stem), card, str(path)))
    return results


def check_mcp_servers(workspace: str | None = None) -> list[dict[str, Any]]:
    return asyncio.run(check_mcp_servers_async(workspace))


def count_mcp_servers(workspace: str | None = None) -> int:
    return len(list_mcp_servers(workspace))


def format_mcp_status_lines(results: list[dict[str, Any]]) -> list[str]:
    if not results:
        return ["[mcp] no configured servers"]
    lines: list[str] = []
    for item in results:
        if item.get("status") == "ok":
            lines.append(
                f"[mcp] {item['name']} ok ({item.get('tool_count', 0)} tools) {item['transport']} {item['url']}"
            )
        else:
            lines.append(
                f"[mcp] {item['name']} failed: {item.get('error', 'unknown error')}"
            )
    return lines
