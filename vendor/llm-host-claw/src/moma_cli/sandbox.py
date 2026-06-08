from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"[A-Za-z]:\\[^\s\"']+")
UNIX_ABSOLUTE_PATH_RE = re.compile(r"(?<![A-Za-z0-9._-])/[^\s\"']+")


def sandbox_enabled() -> bool:
    return (os.environ.get("MOMA_SANDBOX_ENABLED") or "false").strip().lower() == "true"


def sandbox_root() -> Path | None:
    raw = (os.environ.get("MOMA_SANDBOX_ROOT") or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def sandbox_platform() -> str:
    raw = (os.environ.get("MOMA_SANDBOX_PLATFORM") or "").strip().lower()
    if raw:
        return raw
    current = platform.system().lower()
    if current.startswith("darwin"):
        return "macos"
    if current.startswith("linux"):
        return "linux"
    if current.startswith("windows"):
        return "windows"
    return current


def is_within_root(path: str | Path, root: str | Path | None = None) -> bool:
    target = Path(path).expanduser().resolve()
    resolved_root = Path(root).expanduser().resolve() if root is not None else sandbox_root()
    if resolved_root is None:
        return True
    try:
        target.relative_to(resolved_root)
        return True
    except ValueError:
        return False


def ensure_within_root(path: str | Path, root: str | Path | None = None) -> Path:
    target = Path(path).expanduser().resolve()
    if sandbox_enabled() and not is_within_root(target, root):
        raise ValueError(f"Path escapes sandbox root: {target}")
    return target


def validate_shell_command(command: str, *, root: str | Path | None = None) -> None:
    if not sandbox_enabled():
        return
    if "../" in command or "..\\" in command:
        raise ValueError("Sandbox mode blocks parent-directory traversal in shell commands")
    for pattern in (WINDOWS_ABSOLUTE_PATH_RE, UNIX_ABSOLUTE_PATH_RE):
        for raw_path in pattern.findall(command):
            normalized = raw_path.rstrip('"\'\'',)
            if not is_within_root(normalized, root):
                raise ValueError(f"Shell command references path outside sandbox root: {normalized}")


@dataclass(frozen=True)
class SandboxLaunchSpec:
    argv: list[str]
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SandboxPreparation:
    argv: list[str]
    cwd: str | None
    env: dict[str, str]
    mode: str
    notes: list[str] = field(default_factory=list)


class SandboxManager:
    def __init__(self, *, enabled: bool | None = None, root: str | Path | None = None):
        self.enabled = sandbox_enabled() if enabled is None else enabled
        self.root = Path(root).expanduser().resolve() if root is not None else sandbox_root()
        self.platform = sandbox_platform()

    def ensure_path(self, path: str | Path) -> Path:
        if not self.enabled:
            return Path(path).expanduser().resolve()
        return ensure_within_root(path, self.root)

    def validate_command(self, command: str) -> None:
        validate_shell_command(command, root=self.root)

    def prepare_spawn(
        self,
        *,
        argv: list[str],
        cwd: str | Path | None,
        env: Mapping[str, str] | None = None,
    ) -> SandboxPreparation:
        resolved_env = dict(env or os.environ.copy())
        resolved_cwd = str(Path(cwd).expanduser().resolve()) if cwd else None
        notes: list[str] = []

        if not self.enabled:
            return SandboxPreparation(argv=list(argv), cwd=resolved_cwd, env=resolved_env, mode="disabled")

        if self.root is None:
            raise ValueError("Sandbox enabled but no sandbox root configured")

        if resolved_cwd is not None:
            resolved_cwd = str(self.ensure_path(resolved_cwd))

        if self.platform == "linux":
            return self._prepare_linux(argv=list(argv), cwd=resolved_cwd, env=resolved_env)
        if self.platform == "macos":
            return self._prepare_macos(argv=list(argv), cwd=resolved_cwd, env=resolved_env)
        if self.platform == "windows":
            return self._prepare_windows(argv=list(argv), cwd=resolved_cwd, env=resolved_env)

        notes.append(f"Unknown sandbox platform '{self.platform}', falling back to logical sandbox only")
        return SandboxPreparation(argv=list(argv), cwd=resolved_cwd, env=resolved_env, mode="logical-fallback", notes=notes)

    def run_subprocess(self, *, argv: list[str], cwd: str | Path | None, env: Mapping[str, str] | None = None, **kwargs) -> subprocess.CompletedProcess:
        prepared = self.prepare_spawn(argv=argv, cwd=cwd, env=env)
        return subprocess.run(prepared.argv, cwd=prepared.cwd, env=prepared.env, **kwargs)

    def _prepare_linux(self, *, argv: list[str], cwd: str | None, env: dict[str, str]) -> SandboxPreparation:
        bwrap = shutil.which("bwrap")
        if bwrap and self.root is not None:
            root = str(self.root)
            wrapped = [
                bwrap,
                "--die-with-parent",
                "--ro-bind",
                "/",
                "/",
                "--bind",
                root,
                root,
                "--chdir",
                cwd or root,
                "--unshare-pid",
                "--new-session",
                "--",
                *argv,
            ]
            return SandboxPreparation(argv=wrapped, cwd=None, env=env, mode="linux-bwrap", notes=["bubblewrap filesystem sandbox enabled"])
        return SandboxPreparation(argv=argv, cwd=cwd, env=env, mode="linux-logical", notes=["bubblewrap unavailable; using logical sandbox only"])

    def _prepare_macos(self, *, argv: list[str], cwd: str | None, env: dict[str, str]) -> SandboxPreparation:
        sandbox_exec = "/usr/bin/sandbox-exec"
        if Path(sandbox_exec).exists() and self.root is not None:
            root = str(self.root).replace('"', '\\"')
            profile = (
                '(version 1) '
                '(deny default) '
                '(allow process*) '
                '(allow sysctl-read) '
                '(allow file-read*) '
                f'(allow file-write* (subpath "{root}")) '
                f'(allow file-read* (subpath "{root}"))'
            )
            wrapped = [sandbox_exec, "-p", profile, *argv]
            return SandboxPreparation(argv=wrapped, cwd=cwd, env=env, mode="macos-seatbelt", notes=["sandbox-exec profile enabled"])
        return SandboxPreparation(argv=argv, cwd=cwd, env=env, mode="macos-logical", notes=["sandbox-exec unavailable; using logical sandbox only"])

    def _prepare_windows(self, *, argv: list[str], cwd: str | None, env: dict[str, str]) -> SandboxPreparation:
        notes = [
            "Windows system sandbox helper not yet linked; using logical sandbox with restricted root enforcement",
            "Next step is a native restricted-token/ACL helper binary or pywin32 wrapper",
        ]
        env = dict(env)
        env.setdefault("MOMA_WINDOWS_SANDBOX_MODE", "logical")
        return SandboxPreparation(argv=argv, cwd=cwd, env=env, mode="windows-logical", notes=notes)


def current_sandbox_manager(root: str | Path | None = None) -> SandboxManager:
    return SandboxManager(root=root)
