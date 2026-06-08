from __future__ import annotations

import argparse
import json
import os
import sys

from .bootstrap import (
    bootstrap_environment,
    environment_summary,
    list_sessions,
    read_config_preview,
)
from .commands import (
    announce_mcp_health,
    default_orchestrator_factory,
    print_headless_result,
    run_chat_loop,
    run_headless_once,
    run_once,
    stream_headless_once,
)
from .history import (
    format_history_lines,
    format_history_session_lines,
    list_history_entries,
    list_history_sessions,
    read_history_entry,
)
from .mcp import check_mcp_servers, import_mcp_config, list_mcp_servers, remove_mcp_server, write_mcp_server
from .renderer import EventRenderer
from .setup import bootstrap_local_install, build_local_install_checks, inspect_local_install_status, repair_local_install
from .web import run_backend_server, run_web_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="moma", description="MOMA local CLI")
    parser.add_argument("--config", help="Path to orchestrator config (.json/.yaml/.yml)")
    parser.add_argument("--workspace", help="Base userspace directory for CLI state")
    parser.add_argument("--session-id", help="Reuse a specific session id")
    parser.add_argument("--user-id", help="Override USER_ID")
    parser.add_argument("--api-key", help="Override API_KEY")
    parser.add_argument("--authorization", help="Override AUTHORIZATION")
    parser.add_argument("--mcp-config", help="Path to MCP config (.json/.yaml/.yml) to import into workspace/tools")
    parser.add_argument("--sandbox", action="store_true", help="Restrict file access to the sandbox root")
    parser.add_argument("--sandbox-root", help="Sandbox root directory; defaults to the session workspace")
    parser.add_argument("--json", action="store_true", dest="json_mode", help="Emit raw JSON response events")
    parser.add_argument("--headless", action="store_true", help="Disable UI and emit structured JSON output")
    parser.add_argument("--stream", action="store_true", help="Stream headless events as SSE")

    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run a single prompt")
    run_parser.add_argument("prompt", nargs="+", help="Prompt to send")

    chat_parser = subparsers.add_parser("chat", help="Start interactive chat mode")
    chat_parser.add_argument("--prompt", help="Optional first prompt before entering interactive mode")

    subparsers.add_parser("sessions", help="List known local sessions")
    history_parser = subparsers.add_parser("history", help="Inspect saved local conversation history")
    history_subparsers = history_parser.add_subparsers(dest="history_command")
    history_subparsers.add_parser("list", help="List saved history records")
    history_show_parser = history_subparsers.add_parser("show", help="Show one saved history record")
    history_show_parser.add_argument("entry_id", help="History entry id or prefix")

    resume_parser = subparsers.add_parser("resume", help="Resume a saved conversation by session id")
    resume_parser.add_argument("session_id", nargs="?", help="Session id to resume")

    web_parser = subparsers.add_parser("web", help="Start web UI and backend service")
    web_parser.add_argument("--host", default="127.0.0.1", help="Host to bind the web server")
    web_parser.add_argument("--port", type=int, default=3018, help="Port to bind the web server")
    web_parser.add_argument("--no-install", action="store_true", help="Do not auto-install missing swarm-ui npm dependencies")

    serve_parser = subparsers.add_parser("serve", help="Start backend API service only")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Host to bind the backend service")
    serve_parser.add_argument("--port", type=int, default=3019, help="Port to bind the backend service")

    init_parser = subparsers.add_parser("init", help="Install local Python and web dependencies for first use")
    init_parser.add_argument("--dev", action="store_true", help="Also install Python dev dependencies")
    init_parser.add_argument("--with-browsers", action="store_true", help="Also install Playwright Chromium")

    doctor_parser = subparsers.add_parser("doctor", help="Show CLI bootstrap and config status")
    doctor_parser.add_argument("--fix", action="store_true", help="Attempt to repair missing local dependencies")
    doctor_parser.add_argument("--dev", action="store_true", help="When combined with --fix, also install Python dev dependencies")
    doctor_parser.add_argument("--with-browsers", action="store_true", help="When combined with --fix, also install Playwright Chromium")
    doctor_parser.add_argument("--target", choices=["all", "python", "web", "browsers"], default="all", help="Choose which dependency group to repair")
    config_parser = subparsers.add_parser("config", help="Inspect orchestrator config")
    config_parser.add_argument("--path", required=True, help="Path to config file to inspect")

    mcp_parser = subparsers.add_parser("mcp", help="Manage workspace MCP server cards")
    mcp_subparsers = mcp_parser.add_subparsers(dest="mcp_command")
    mcp_subparsers.add_parser("list", help="List configured MCP servers")
    mcp_subparsers.add_parser("check", help="Probe configured MCP servers")
    mcp_import_parser = mcp_subparsers.add_parser("import", help="Import MCP config file into workspace/tools")
    mcp_import_parser.add_argument("--path", required=True, help="Path to MCP config file")
    mcp_add_parser = mcp_subparsers.add_parser("add", help="Add one MCP server card")
    mcp_add_parser.add_argument("--name", required=True, help="Server name")
    mcp_add_parser.add_argument("--url", required=True, help="Server URL")
    mcp_add_parser.add_argument("--transport", default="sse", choices=["sse", "streamable-http"], help="MCP transport")
    mcp_add_parser.add_argument("--timeout", type=float, default=30, help="Connection timeout seconds")
    mcp_add_parser.add_argument("--header", action="append", default=[], help="Repeated header in KEY=VALUE form")
    mcp_remove_parser = mcp_subparsers.add_parser("remove", help="Remove one MCP server card")
    mcp_remove_parser.add_argument("--name", required=True, help="Server name")

    return parser


def _parse_headers(values: list[str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"Invalid header '{value}'. Expected KEY=VALUE")
        key, header_value = value.split("=", 1)
        headers[key] = header_value
    return headers


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.headless and args.json_mode:
        print("--headless and --json cannot be used together", file=sys.stderr)
        return 2

    renderer = EventRenderer(json_mode=args.json_mode)

    if args.command == "sessions":
        sessions = list_sessions(args.workspace)
        if args.json_mode:
            print(json.dumps(sessions, ensure_ascii=False))
        elif not sessions:
            print("No sessions found.")
        else:
            for session in sessions:
                print(f"{session['session_id']}\t{session['workspace']}")
        return 0

    if args.command == "history":
        userspace = args.workspace or None
        if args.history_command in {None, "list"}:
            entries = list_history_entries(userspace)
            if args.json_mode:
                print(json.dumps(entries, ensure_ascii=False))
            else:
                for line in format_history_lines(entries):
                    print(line)
            return 0
        if args.history_command == "show":
            try:
                record = read_history_entry(args.entry_id, userspace)
            except Exception as exc:
                print(f"History lookup failed: {exc}", file=sys.stderr)
                return 2
            if args.json_mode:
                print(json.dumps(record, ensure_ascii=False, indent=2))
            else:
                print(f"entry_id: {record.get('entry_id')}")
                print(f"session_id: {record.get('session_id')}")
                print(f"created_at: {record.get('created_at')}")
                print(f"mode: {record.get('mode')}")
                print(f"prompt: {record.get('prompt')}")
                preview = str(record.get("assistant_text_preview") or "").strip()
                if preview:
                    print(f"preview: {preview}")
            return 0

    if args.command == "resume":
        userspace = args.workspace or None
        if not args.session_id:
            sessions = list_history_sessions(userspace)
            if args.json_mode:
                print(json.dumps(sessions, ensure_ascii=False))
            else:
                for line in format_history_session_lines(sessions):
                    print(line)
            return 0
        argv_resume = list(argv or [])
        filtered_args: list[str] = []
        skip_next = False
        for index, item in enumerate(argv_resume):
            if skip_next:
                skip_next = False
                continue
            if item == "resume":
                filtered_args.extend(["--session-id", args.session_id, "chat"])
                break
            if item in {"--json", "--headless", "--stream"}:
                continue
            filtered_args.append(item)
        return main(filtered_args)

    if args.command == "doctor":
        summary = environment_summary(args.workspace, args.session_id, args.config)
        install_status = inspect_local_install_status()
        checks = build_local_install_checks()
        if args.fix:
            try:
                repaired_steps = repair_local_install(target=args.target, include_dev=args.dev)
                if args.with_browsers and args.target not in {"all", "browsers"}:
                    repaired_steps.extend(repair_local_install(target="browsers", include_dev=args.dev))
            except Exception as exc:
                print(f"CLI doctor --fix failed: {exc}", file=sys.stderr)
                return 1
            install_status = inspect_local_install_status()
            checks = build_local_install_checks()
        else:
            repaired_steps = []
        payload = {
            **summary,
            **install_status,
            "checks": checks,
            "all_checks_ok": all(bool(item.get("ok")) for item in checks),
            "repaired_steps": repaired_steps,
        }
        if args.json_mode:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            for key, value in payload.items():
                if key == "checks":
                    print("checks:")
                    for item in value:
                        status_text = "ok" if item.get("ok") else "missing"
                        print(f"- {item.get('key')}: {status_text} ({item.get('details')})")
                else:
                    print(f"{key}: {value}")
        return 0

    if args.command == "init":
        try:
            steps = bootstrap_local_install(include_dev=args.dev, install_browsers=args.with_browsers)
        except Exception as exc:
            print(f"CLI init failed: {exc}", file=sys.stderr)
            return 1
        if args.json_mode:
            print(json.dumps({"steps": steps}, ensure_ascii=False, indent=2))
        else:
            print("MOMA local install complete.")
            for step in steps:
                print(f"- {step}")
            print("Next:")
            print("- moma --config config.json chat")
            print("- moma --config config.json web")
        return 0

    if args.command == "config":
        try:
            preview = read_config_preview(args.path)
        except Exception as exc:
            print(f"Config inspection failed: {exc}", file=sys.stderr)
            return 2
        if args.json_mode:
            print(json.dumps(preview, ensure_ascii=False))
        else:
            for key, value in preview.items():
                print(f"{key}: {value}")
        return 0

    if args.command == "mcp":
        try:
            bootstrap_environment(
                config_path=args.config,
                mcp_config_path=args.mcp_config,
                workspace=args.workspace,
                session_id=args.session_id,
                user_id=args.user_id,
                api_key=args.api_key,
                authorization=args.authorization,
                sandbox=args.sandbox,
                sandbox_root=args.sandbox_root,
                require_orchestrator_config=False,
            )
        except Exception as exc:
            print(f"CLI bootstrap failed: {exc}", file=sys.stderr)
            return 2

        workspace = (os.environ.get("WORKSPACE") if args.session_id else None) or args.workspace or None
        if args.mcp_command == "list":
            servers = list_mcp_servers(workspace)
            if args.json_mode:
                print(json.dumps(servers, ensure_ascii=False))
            elif not servers:
                print("No MCP servers configured.")
            else:
                for server in servers:
                    print(f"{server['name']}\t{server['transport']}\t{server['url']}")
            return 0

        if args.mcp_command == "check":
            results = check_mcp_servers(workspace)
            if args.json_mode:
                print(json.dumps(results, ensure_ascii=False))
            elif not results:
                print("No MCP servers configured.")
            else:
                for item in results:
                    if item.get("status") == "ok":
                        print(f"{item['name']}: ok ({item.get('tool_count', 0)} tools)")
                    else:
                        print(f"{item['name']}: failed - {item.get('error', 'unknown error')}")
            return 0

        if args.mcp_command == "import":
            imported = import_mcp_config(args.path, workspace)
            if args.json_mode:
                print(json.dumps(imported, ensure_ascii=False))
            else:
                print(f"Imported MCP servers: {', '.join(imported)}")
            return 0

        if args.mcp_command == "add":
            headers = _parse_headers(args.header)
            path = write_mcp_server(
                name=args.name,
                url=args.url,
                transport=args.transport,
                headers=headers or None,
                timeout=args.timeout,
                workspace=workspace,
            )
            if args.json_mode:
                print(json.dumps({"name": args.name, "path": str(path)}, ensure_ascii=False))
            else:
                print(f"Added MCP server: {args.name} -> {path}")
            return 0

        if args.mcp_command == "remove":
            removed = remove_mcp_server(args.name, workspace)
            if not removed:
                print(f"MCP server not found: {args.name}", file=sys.stderr)
                return 1
            print(f"Removed MCP server: {args.name}")
            return 0

        mcp_parser = build_parser()
        mcp_parser.print_help()
        return 0

    try:
        bootstrap_environment(
            config_path=args.config,
            mcp_config_path=args.mcp_config,
            workspace=args.workspace,
            session_id=args.session_id,
            user_id=args.user_id,
            api_key=args.api_key,
            authorization=args.authorization,
            sandbox=args.sandbox,
            sandbox_root=args.sandbox_root,
        )
    except Exception as exc:
        print(f"CLI bootstrap failed: {exc}", file=sys.stderr)
        return 2

    if args.command == "web":
        try:
            return run_web_server(host=args.host, port=args.port, userspace=args.workspace, auto_install=not args.no_install)
        except Exception as exc:
            print(f"CLI web failed: {exc}", file=sys.stderr)
            return 1

    if args.command == "serve":
        try:
            return run_backend_server(host=args.host, port=args.port, userspace=args.workspace)
        except Exception as exc:
            print(f"CLI serve failed: {exc}", file=sys.stderr)
            return 1

    if args.command == "run":
        prompt = " ".join(args.prompt)
        try:
            if args.headless:
                if args.stream:
                    result = stream_headless_once(
                        prompt=prompt,
                        orchestrator_factory=default_orchestrator_factory,
                        stdout=sys.stdout,
                    )
                    return result.exit_code
                result = run_headless_once(
                    prompt=prompt,
                    orchestrator_factory=default_orchestrator_factory,
                )
                print_headless_result(result, stdout=sys.stdout)
                return result.exit_code
            announce_mcp_health(renderer)
            return run_once(
                prompt=prompt,
                renderer=renderer,
                orchestrator_factory=default_orchestrator_factory,
            )
        except Exception as exc:
            print(f"CLI run failed: {exc}", file=sys.stderr)
            return 1

    if args.command == "chat":
        try:
            if args.headless:
                if not args.prompt:
                    print("--headless chat requires --prompt", file=sys.stderr)
                    return 2
                if args.stream:
                    result = stream_headless_once(
                        prompt=args.prompt,
                        orchestrator_factory=default_orchestrator_factory,
                        stdout=sys.stdout,
                    )
                    return result.exit_code
                result = run_headless_once(
                    prompt=args.prompt,
                    orchestrator_factory=default_orchestrator_factory,
                )
                print_headless_result(result, stdout=sys.stdout)
                return result.exit_code
            if args.prompt:
                announce_mcp_health(renderer)
                run_once(
                    prompt=args.prompt,
                    renderer=renderer,
                    orchestrator_factory=default_orchestrator_factory,
                )
            else:
                announce_mcp_health(renderer)
            return run_chat_loop(
                renderer=renderer,
                orchestrator_factory=default_orchestrator_factory,
                input_stream=sys.stdin,
            )
        except Exception as exc:
            print(f"CLI chat failed: {exc}", file=sys.stderr)
            return 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
