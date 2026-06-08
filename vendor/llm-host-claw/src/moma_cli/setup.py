from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Literal


RepairTarget = Literal["python", "web", "browsers", "all"]


def repo_root() -> Path:
    return _repo_root()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _run_checked(command: list[str], *, cwd: Path) -> None:
    result = subprocess.run(command, cwd=str(cwd), env=os.environ.copy())
    if result.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {result.returncode}: {' '.join(command)}")


def _resolve_executable(*names: str) -> str:
    for name in names:
        resolved = shutil.which(name)
        if resolved:
            return resolved
    raise FileNotFoundError(f"Executable not found. Tried: {', '.join(names)}")


def _try_resolve_executable(*names: str) -> str | None:
    for name in names:
        resolved = shutil.which(name)
        if resolved:
            return resolved
    return None


def _swarm_ui_dir() -> Path:
    return _repo_root() / "swarm-ui"


def _has_swarm_ui_dependencies() -> bool:
    return (_swarm_ui_dir() / "node_modules" / "next" / "package.json").exists()


def _has_playwright_chromium() -> bool:
    cache_root = Path.home() / "AppData" / "Local" / "ms-playwright"
    if os.name != "nt":
        cache_root = Path.home() / ".cache" / "ms-playwright"
    return cache_root.exists() and any(child.name.startswith("chromium") for child in cache_root.iterdir())


def inspect_local_install_status() -> dict[str, object]:
    uv_executable = _try_resolve_executable("uv")
    npm_executable = _try_resolve_executable("npm.cmd", "npm")
    ui_dir = _swarm_ui_dir()
    return {
        "repo_root": str(_repo_root()),
        "swarm_ui_dir": str(ui_dir),
        "has_uv": bool(uv_executable),
        "uv_executable": uv_executable,
        "has_npm": bool(npm_executable),
        "npm_executable": npm_executable,
        "swarm_ui_exists": ui_dir.exists(),
        "swarm_ui_dependencies_installed": _has_swarm_ui_dependencies(),
        "playwright_chromium_installed": _has_playwright_chromium(),
    }


def build_local_install_checks() -> list[dict[str, object]]:
    status = inspect_local_install_status()
    checks = [
        {
            "key": "python_toolchain",
            "label": "Python toolchain (uv)",
            "ok": bool(status["has_uv"]),
            "details": status.get("uv_executable") or "uv not found on PATH",
        },
        {
            "key": "web_toolchain",
            "label": "Web toolchain (npm)",
            "ok": bool(status["has_npm"]),
            "details": status.get("npm_executable") or "npm not found on PATH",
        },
        {
            "key": "swarm_ui_dir",
            "label": "swarm-ui directory",
            "ok": bool(status["swarm_ui_exists"]),
            "details": status.get("swarm_ui_dir"),
        },
        {
            "key": "swarm_ui_dependencies",
            "label": "swarm-ui npm dependencies",
            "ok": bool(status["swarm_ui_dependencies_installed"]),
            "details": "next installed" if status["swarm_ui_dependencies_installed"] else "next missing in node_modules",
        },
        {
            "key": "playwright_chromium",
            "label": "Playwright Chromium",
            "ok": bool(status["playwright_chromium_installed"]),
            "details": "installed" if status["playwright_chromium_installed"] else "not installed",
        },
    ]
    return checks


def repair_local_install(*, target: RepairTarget = "all", include_dev: bool = False) -> list[str]:
    repo_root = _repo_root()
    ui_dir = _swarm_ui_dir()
    steps: list[str] = []

    if target in {"all", "python", "browsers"}:
        uv_executable = _resolve_executable("uv")
    else:
        uv_executable = _try_resolve_executable("uv")

    if target in {"all", "web"}:
        npm_executable = _resolve_executable("npm.cmd", "npm")
    else:
        npm_executable = _try_resolve_executable("npm.cmd", "npm")

    if target in {"all", "python"}:
        sync_command = [str(uv_executable), "sync"]
        if include_dev:
            sync_command.extend(["--extra", "dev"])
        _run_checked(sync_command, cwd=repo_root)
        steps.append("Python dependencies installed with uv sync")

    if target in {"all", "web"}:
        assert npm_executable is not None
        _run_checked([npm_executable, "install"], cwd=ui_dir)
        steps.append("swarm-ui dependencies installed with npm install")

    if target in {"all", "browsers"}:
        if uv_executable is None:
            raise FileNotFoundError("uv is required to install Playwright Chromium")
        _run_checked([str(uv_executable), "run", "playwright", "install", "chromium"], cwd=repo_root)
        steps.append("Playwright Chromium installed")

    return steps


def bootstrap_local_install(*, include_dev: bool = False, install_browsers: bool = False) -> list[str]:
    target: RepairTarget = "all"
    if not install_browsers:
        steps = repair_local_install(target="python", include_dev=include_dev)
        steps.extend(repair_local_install(target="web", include_dev=include_dev))
        return steps
    return repair_local_install(target=target, include_dev=include_dev)
