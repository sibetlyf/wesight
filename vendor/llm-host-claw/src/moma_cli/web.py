from __future__ import annotations

import atexit
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from api.routes import orchestrator
from moma_cli.sandbox import current_sandbox_manager


_CHILD_PROCESSES: list[subprocess.Popen] = []


def _resolve_npm_executable() -> str:
    npm_executable = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm_executable:
        raise FileNotFoundError("npm executable not found. Install Node.js and ensure npm is on PATH.")
    return npm_executable


def _swarm_ui_dir() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    ui_dir = repo_root / "swarm-ui"
    if not ui_dir.exists():
        raise FileNotFoundError(f"swarm-ui directory not found: {ui_dir}")
    return ui_dir


def _has_swarm_ui_dependencies(ui_dir: Path) -> bool:
    return (ui_dir / "node_modules" / "next" / "package.json").exists()


def _ensure_swarm_ui_dependencies(*, auto_install: bool) -> tuple[Path, str]:
    ui_dir = _swarm_ui_dir()
    npm_executable = _resolve_npm_executable()
    if _has_swarm_ui_dependencies(ui_dir):
        return ui_dir, npm_executable
    if not auto_install:
        raise FileNotFoundError(
            f"swarm-ui dependencies are not installed in {ui_dir}. Run 'npm install' there first, or omit --no-install."
        )
    print(f"[web] installing swarm-ui dependencies in {ui_dir}")
    prepared = current_sandbox_manager().prepare_spawn(
        argv=[npm_executable, "install"],
        cwd=str(ui_dir),
        env=os.environ.copy(),
    )
    result = subprocess.run(prepared.argv, cwd=prepared.cwd, env=prepared.env)
    if result.returncode != 0:
        raise RuntimeError(f"swarm-ui dependency installation failed with exit code {result.returncode}")
    if not _has_swarm_ui_dependencies(ui_dir):
        raise RuntimeError(f"swarm-ui dependency installation completed but next is still missing in {ui_dir}")
    return ui_dir, npm_executable


def build_web_app() -> FastAPI:
    app = FastAPI(title="MOMA Web Backend")
    allowed_origins = [
        origin.strip()
        for origin in [
            os.environ.get("NEXT_PUBLIC_FRONTEND_ORIGIN", ""),
            "http://127.0.0.1:3018",
            "http://localhost:3018",
        ]
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(orchestrator.router, prefix="/api/orchestrator", tags=["orchestrator"])

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {
            "status": "healthy",
            "userspace": os.environ.get("USERSPACE"),
            "workspace": os.environ.get("WORKSPACE"),
            "session_id": os.environ.get("SESSION_ID"),
        }

    from moma_cli.history import list_history_sessions, read_latest_history_for_session

    @app.get("/api/web/sessions")
    async def list_sessions() -> dict[str, object]:
        return {"sessions": list_history_sessions(os.environ.get("USERSPACE"), limit=100)}

    @app.get("/api/web/history/latest")
    async def latest_session_history(session_id: str) -> dict[str, object]:
        record = read_latest_history_for_session(session_id, os.environ.get("USERSPACE"))
        return {
            "session_id": session_id,
            "events": record.get("events") or [],
            "prompt": record.get("prompt"),
        }

    return app


def _is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _wait_for_port(host: str, port: int, timeout_seconds: float) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if _is_port_open(host, port):
            return
        time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for {host}:{port}")


def _terminate_children() -> None:
    for proc in list(_CHILD_PROCESSES):
        if proc.poll() is not None:
            continue
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def _spawn_backend(host: str, port: int) -> subprocess.Popen:
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "moma_cli.web:build_web_app",
        "--factory",
        "--host",
        host,
        "--port",
        str(port),
    ]
    prepared = current_sandbox_manager().prepare_spawn(argv=command, cwd=os.getcwd(), env=os.environ.copy())
    proc = subprocess.Popen(prepared.argv, cwd=prepared.cwd, env=prepared.env)
    _CHILD_PROCESSES.append(proc)
    return proc


def _spawn_swarm_ui(frontend_host: str, frontend_port: int, backend_origin: str, *, auto_install: bool) -> subprocess.Popen:
    ui_dir, npm_executable = _ensure_swarm_ui_dependencies(auto_install=auto_install)
    env = os.environ.copy()
    env["NEXT_PUBLIC_BACKEND_ORIGIN"] = backend_origin
    env["BACKEND_ORIGIN"] = backend_origin
    env["NEXT_PUBLIC_DIRECT_BACKEND_MODE"] = "true"
    command = [npm_executable, "run", "dev", "--", "-H", frontend_host, "-p", str(frontend_port)]
    prepared = current_sandbox_manager().prepare_spawn(argv=command, cwd=str(ui_dir), env=env)
    proc = subprocess.Popen(prepared.argv, cwd=prepared.cwd, env=prepared.env)
    _CHILD_PROCESSES.append(proc)
    return proc


def run_web_server(*, host: str, port: int, userspace: str | None, auto_install: bool = True) -> int:
    backend_port = port + 1
    backend_origin = f"http://{host}:{backend_port}"
    frontend_origin = f"http://{host}:{port}/moma"
    os.environ["NEXT_PUBLIC_FRONTEND_ORIGIN"] = f"http://{host}:{port}"

    atexit.register(_terminate_children)

    if userspace:
        print(f"Userspace: {Path(userspace).expanduser().resolve()}")

    _spawn_backend(host, backend_port)
    _wait_for_port(host, backend_port, 20)

    _spawn_swarm_ui(host, port, backend_origin, auto_install=auto_install)
    _wait_for_port(host, port, 40)

    print(f"MOMA Web available at {frontend_origin}")
    print(f"MOMA Backend available at {backend_origin}")

    try:
        while True:
            time.sleep(1)
            for proc in list(_CHILD_PROCESSES):
                code = proc.poll()
                if code is not None and code != 0:
                    raise RuntimeError(f"Web child process exited with code {code}")
    except KeyboardInterrupt:
        _terminate_children()
        return 130


def run_backend_server(*, host: str, port: int, userspace: str | None) -> int:
    if userspace:
        print(f"Userspace: {Path(userspace).expanduser().resolve()}")
    print(f"MOMA Serve available at http://{host}:{port}")
    config = uvicorn.Config(build_web_app(), host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    try:
        server.run()
        return 0
    except KeyboardInterrupt:
        return 130
