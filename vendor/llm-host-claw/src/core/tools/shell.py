import os
import subprocess
import asyncio
import platform
from typing import List, override
from agno.tools import Toolkit

from configs.shell import ShellConfig
from moma_cli.sandbox import SandboxManager, ensure_within_root, sandbox_enabled, sandbox_root, validate_shell_command
from protocol import EnVar


class Shell(Toolkit):
    """
    通用 shell 工具包，供代理使用

    功能：
    - 运行 shell 命令
    - 管理文件
    - 搜索文件
    - 检查工作区结构
    """

    @override
    def __init__(self, envar: EnVar, cfg: ShellConfig, **kwargs):
        """
        初始化 Shell 工具包

        Args:
            envar: 环境变量
            cfg: Shell 配置
        """
        # 先设置实例变量
        self.envar = envar

        # 确保 runs 目录存在
        os.makedirs(envar.runspace, exist_ok=True)

        # allow paths
        self.allow_paths: List[str] = [os.path.abspath("src/core/skills")]
        self.allow_paths.append(os.path.join(self.envar.workspace, "skills"))
        self.allow_paths.append(os.path.join(self.envar.userspace, "runs"))
        self._sandbox_root = str(sandbox_root() or self.envar.workspace)
        self._sandbox = SandboxManager(root=self._sandbox_root)

        if not self.envar.runspace:
            raise ValueError("runspace does not exist")

        self.cfg = cfg

        # 然后调用父类构造函数
        super().__init__(
            name="shell",
            tools=[
                self.shell,
                self.read_file,
                self.write_file,
                self.list_dir,
                self.file_tree,
                self.grep,
            ],
            exclude_tools=self.cfg.exclude_tools,
        )

    def ensure_workspace(self, path: str, allow_session: bool = False) -> str:
        """
        确保路径在工作区内

        Args:
            path: 相对工作区的路径
            allow_session: 是否允许在会话内操作，默认 False
        Returns:
            绝对路径
        """
        runspace = os.path.abspath(self.envar.runspace)
        ensure_space = self.envar.sessionspace if allow_session else runspace
        # path以$开头，从环境变量读取拿到完整路径，$RUNSPACE/a.jpg
        if path.startswith("$"):
            path = os.path.expandvars(path)
        # 如果是相对路径，认为是在工作区下操作
        if not os.path.isabs(path):
            full = os.path.abspath(os.path.join(runspace, path))
        else:
            full = os.path.abspath(path)

        # 检查路径是否超出工作区范围或者allow_paths
        if not any(full.startswith(p) for p in self.allow_paths + [ensure_space]):
            raise ValueError(f"不允许超出目录范围: {ensure_space}")
        if sandbox_enabled():
            full = str(ensure_within_root(full, self._sandbox_root))
        return full

    # =====================================================
    # Shell
    # =====================================================

    async def shell(self, command: str) -> str:
        """
        执行 shell 命令
        规则：
            - 每次命令独立执行（不会保留 cd 状态）
        示例：
           - shell(command="uv add requests") # python采用uv管理依赖
           - shell(command="npm install axios")
           - shell(command="python3 scripts.py")
           - shell(command="cd xxx && your_command")
        Args:
            command: 要执行的 shell 命令

        Returns:
            命令输出
        """

        for c in self.cfg.blocked_commands:
            if c in command:
                raise ValueError(f"Blocked command: {c}")

        validate_shell_command(command, root=self._sandbox_root)

        def run_sync():
            try:
                if platform.system() == "Windows":
                    argv = ["cmd.exe", "/d", "/c", command]
                else:
                    argv = ["/bin/bash", "-lc", command]
                prepared = self._sandbox.prepare_spawn(
                    argv=argv,
                    cwd=str(ensure_within_root(self.envar.runspace, self._sandbox_root)),
                    env=os.environ.copy(),
                )
                result = subprocess.run(
                    prepared.argv,
                    cwd=prepared.cwd,
                    capture_output=True,
                    text=True,
                    timeout=self.cfg.timeout,
                    env=prepared.env,
                )

                output = result.stdout + result.stderr

            except subprocess.TimeoutExpired as e:
                output: str = (e.stdout or "") + (e.stderr or "")  # type: ignore
                output += "\n[command timeout]\n"
            # 限制输出长度
            if len(output) > self.cfg.max_output:
                output = output[: self.cfg.max_output] + "\n[truncated]\n"

            return output

        return await asyncio.to_thread(run_sync)

    # =====================================================
    # 文件读取
    # =====================================================

    async def read_file(self, path: str) -> str:
        """
        读取文件内容，当前路径已经在`runs/`目录下

        Args:
            path: 绝对路径或文件名
        """

        full = self.ensure_workspace(path)

        def read_file_sync():
            with open(full, "r", encoding="utf-8") as f:
                return f.read()

        return await asyncio.to_thread(read_file_sync)

    # =====================================================
    # 文件写入
    # =====================================================

    async def write_file(self, path: str, content: str) -> str:
        """
        写入文件，例如：write_file(path="report.md", content="这是一个报告")

        Args:
            path: 绝对路径或文件名
            content: 文件内容
        """

        full = self.ensure_workspace(path)

        def write_file_sync():
            with open(full, "w", encoding="utf-8") as f:
                f.write(content)
            return "file written"

        return await asyncio.to_thread(write_file_sync)

    # =====================================================
    # 列出目录
    # =====================================================

    async def list_dir(self, path: str = ".") -> List[str]:
        """
        列出目录中的文件

        Args:
            path: directory relative to workspace
        """

        full = self.ensure_workspace(path)

        def list_dir_sync():
            return os.listdir(full)

        return await asyncio.to_thread(list_dir_sync)

    # =====================================================
    # 文件树
    # =====================================================

    async def file_tree(self, path: str = ".", depth: int = 3) -> str:
        """
        显示目录树

        Args:
            path: 目录路径
            depth: 最大深度，默认3
        """

        base = self.ensure_workspace(path)

        def file_tree_sync():
            lines = []
            for root, dirs, files in os.walk(base):
                level = root.replace(base, "").count(os.sep)
                if level > depth:
                    continue
                indent = "  " * level
                lines.append(f"{indent}{os.path.basename(root)}/")
                subindent = "  " * (level + 1)
                for f in files:
                    lines.append(f"{subindent}{f}")
            return "\n".join(lines)

        return await asyncio.to_thread(file_tree_sync)

    # =====================================================
    # 搜索
    # =====================================================
    async def grep(
        self,
        query: str,
        target: str = ".",
    ) -> str:
        """
        在指定文件或目录中搜索文本，默认路径为`runs/`,示例：
            - grep("TODO")
            - grep("class Agent", "src/")
            - grep("main", "app.py")

        Args:
            query: 要搜索的文本内容
            target: 搜索目标，可以是：
                - 目录（会递归搜索，例如 "src/"）
                - 单个文件（例如 "app.py"）
                - 默认为当前 workspace 根目录
        """

        def run_sync():

            # 确保路径在 workspace 内
            target_path = self.ensure_workspace(target)

            try:
                # 优先使用 ripgrep（更快）
                cmd = ["rg", query, "--line-number", target_path]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                )
            except FileNotFoundError:
                # fallback 到 grep
                if target_path.endswith(
                    tuple([".py", ".js", ".ts", ".json", ".txt", ".md", ".html"])
                ):
                    cmd = ["grep", "-n", query, target_path]
                else:
                    cmd = ["grep", "-rn", query, target_path]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                )

            output = result.stdout

            if len(output) > self.cfg.max_output:
                output = output[: self.cfg.max_output] + "\n[truncated]\n"

            return output

        return await asyncio.to_thread(run_sync)
