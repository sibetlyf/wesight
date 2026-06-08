#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Agno Toolkit - 封装 ccr/opencode CLI 工具"""
import os


from typing import List, Optional
import asyncio
import platform
import shlex
import shutil
import signal
import subprocess

import json
from pathlib import Path
from dataclasses import asdict
from agno.tools import Toolkit
from agno.run.agent import ToolCallStartedEvent, ToolExecution, RunContentEvent
from agno.run.base import RunContext


from core.tools.vibe_tool.datamodel import ParseData
from core.tools.vibe_tool.task_graph import TaskDependencyGraph, Decision
from configs.vibe_toolkit import VibeCodingToolkitConfig
from moma_cli.sandbox import current_sandbox_manager
from protocol.external_agent_run_response_event import ExternalAgentRunResponseContentEvent
from protocol.envar import EnVar


IS_WINDOWS = platform.system() == "Windows"

# session_state 中存储 {task_name: record_id} 字典的 key
_SESSION_TASK_MAP_KEY = "vibe_task_map"
# session_state 中存储最近 task_name 的 key（供 undo/redo 回退用）
_SESSION_LAST_TASK_KEY = "vibe_last_task_name"


def _dbg_print_event(event, run_context) -> None:
    """DEBUG: 格式化打印 ExternalAgentRunResponseContentEvent 的 metadata 及 run_context"""
    import pprint
    sep = "─" * 80
    print(f"\n{'═'*80}")
    print(f"  [VIBE-EVENT DEBUG]  type={getattr(event, 'type', '?')}")
    print(sep)
    # metadata
    meta = getattr(event, "metadata", None)
    if meta is not None:
        meta_dict = vars(meta) if hasattr(meta, "__dict__") else meta
        print("  [metadata]")
        pprint.pprint(meta_dict, indent=4, width=120)
    else:
        print("  [metadata] None")
    print(sep)
    # run_context
    ctx_dict = {
        "session_id":    getattr(run_context, "session_id", None),
        "run_id":        getattr(run_context, "run_id", None),
        "session_state": getattr(run_context, "session_state", None),
    }
    print("  [run_context]")
    pprint.pprint(ctx_dict, indent=4, width=120)
    print(f"{'═'*80}\n")


class VibeCodingToolkit(Toolkit):
    """调用 ccr/opencode CLI 的 Agno 工具
    
    支持同一协调器 session 多次调用 vibe_tool，每次调用产生不同的 record_id。
    通过 run_context.session_state 存储 session_id -> record_id 列表的映射。
    内置任务依赖图自动决策：判断新任务是否应该继续上一个 vibe coding 会话。
    """

    def __init__(self,
                 *,
                 cfg: VibeCodingToolkitConfig,
                 envar: EnVar,
                 **kwargs):
        super().__init__(
            name="vibe_coding",
            instructions="""这是核心的智能编程代理引擎。当你被要求开发、编写代码、初始化项目（如 Vite、React 等）、修复 bug、重构或执行任何涉及文件系统和多步命令的复杂前端/后端工程任务时，必须优先调用本工具，而不是一步步调用单纯的 bash shell。直接把用户的全部要求原封不动传给 arun_prompt！"""
        )

        self.envar = envar
        self.agent_type = cfg.agent_type
        self.workspace_path = self.envar.workspace
        self.cfg = cfg
        self.task_graph = TaskDependencyGraph()
        
        self._cleanup_dangling_processes()

        # 注册工具
        self.register(self.coding_assign_task)

    async def undo_coding_task(self, run_context: RunContext, task_name: str):
        """
        撤销对话中的最后一条消息。移除最近的用户消息、所有后续响应以及所有文件更改。task_name 用于定位要撤销的任务会话。

        Args:
            task_name: 任务名称，用于唯一标识该编程任务。
        
        """
        record_id = self._get_record_id_by_task(run_context, task_name)
        if not record_id:
            yield ExternalAgentRunResponseContentEvent(
                type="content",
                agent_id=run_context.session_id,
                agent_name=run_context.session_id,
                run_id=run_context.run_id,
                session_id=run_context.session_id,
                content=f"没有找到任务 '{task_name}' 对应的可撤销对话"
            )
            return
        
        # 使用 record_id 执行 undo
        async for event in self._run_command(run_context, "/undo", record_id):
            yield event
        
        yield ExternalAgentRunResponseContentEvent(
            type="content",
            agent_id=run_context.session_id,
            agent_name=run_context.session_id,
            run_id=run_context.run_id,
            session_id=run_context.session_id,
            content=f"任务 '{task_name}' 已返回到上次对话"
        )

    async def redo_coding_task(self, run_context: RunContext, task_name: str):
        """
        重做之前撤销的消息。仅在使用 undo_coding_task 后可用。task_name 用于定位要重做的任务会话。

        Args:
            task_name: 任务名称，用于唯一标识该编程任务。
        
        """
        record_id = self._get_record_id_by_task(run_context, task_name)
        if not record_id:
            yield ExternalAgentRunResponseContentEvent(
                type="content",
                agent_id=run_context.session_id,
                agent_name=run_context.session_id,
                run_id=run_context.run_id,
                session_id=run_context.session_id,
                content="没有可重做的对话"
            )
            return
        
        async for event in self._run_command(run_context, "/redo", record_id):
            yield event
        
        yield ExternalAgentRunResponseContentEvent(
            type="content",
            agent_id=run_context.session_id,
            agent_name=run_context.session_id,
            run_id=run_context.run_id,
            session_id=run_context.session_id,
            content=f"任务 '{task_name}' 重做完成"
        )

    def _get_task_map(self, run_context: RunContext) -> dict:
        """从 session_state 获取 {task_name: record_id} 字典"""
        session_state = run_context.session_state or {}
        return session_state.get(_SESSION_TASK_MAP_KEY, {})

    def _cleanup_dangling_processes(self):
        """尝试清理可能残留的悬挂进程，解除文件锁"""
        if platform.system() == "Windows":
            cli_name = "opencode" if self.agent_type == "opencode" else "ccr"
            try:
                import psutil
                current_workspace = os.path.normpath(self.workspace_path).lower()
                for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'cwd']):
                    try:
                        name = (proc.info.get('name') or "").lower()
                        if name not in ('node.exe', 'cmd.exe', 'bash.exe'):
                            continue
                            
                        # 匹配目录
                        cwd = proc.info.get('cwd') or ""
                        if cwd and os.path.normpath(cwd).lower().startswith(current_workspace):
                            proc.kill()
                            continue
                            
                        # 匹配命令行特征
                        cmdline = proc.info.get('cmdline') or []
                        cmd_str = " ".join(cmdline).lower()
                        if cli_name in cmd_str or "vibe_coding" in cmd_str:
                            proc.kill()
                    except Exception:
                        pass
            except ImportError:
                # 兜底：若未安装 psutil，使用 wmic 根据命令行杀进程（注意这通常能杀掉大部分残留）
                try:
                    subprocess.run(
                        f'wmic process where "name=\'node.exe\' and commandline like \'%{cli_name}%\'" call terminate',
                        shell=True, capture_output=True
                    )
                except Exception:
                    pass
            except Exception:
                pass

    def _set_record_id_for_task(self, run_context: RunContext, task_name: str, record_id: str):
        """将 task_name → record_id 写入 session_state"""
        if run_context.session_state is None:
            run_context.session_state = {}
        task_map = run_context.session_state.get(_SESSION_TASK_MAP_KEY, {})
        task_map[task_name] = record_id
        run_context.session_state[_SESSION_TASK_MAP_KEY] = task_map
        run_context.session_state[_SESSION_LAST_TASK_KEY] = task_name

    def _get_record_id_by_task(self, run_context: RunContext, task_name: str) -> Optional[str]:
        """按 task_name 查找 record_id"""
        return self._get_task_map(run_context).get(task_name)

    def _get_record_ids(self, run_context: RunContext) -> List[str]:
        """兼容接口：返回所有已知 record_id 列表"""
        return list(self._get_task_map(run_context).values())

    def _add_record_id(self, run_context: RunContext, record_id: str):
        """兼容接口：仅当当前任务上下文已知 task_name 时才写入"""
        # 直接更新最近一次任务的 record_id
        if run_context.session_state is None:
            run_context.session_state = {}
        last_task = run_context.session_state.get(_SESSION_LAST_TASK_KEY)
        if last_task:
            self._set_record_id_for_task(run_context, last_task, record_id)

    def _get_latest_record_id(self, run_context: RunContext) -> Optional[str]:
        """获取最近一次任务对应的 record_id"""
        if run_context.session_state is None:
            return None
        last_task = run_context.session_state.get(_SESSION_LAST_TASK_KEY)
        if last_task:
            return self._get_record_id_by_task(run_context, last_task)
        # 兜底：返回最后一个值
        records = self._get_record_ids(run_context)
        return records[-1] if records else None

    def _build_cmd(self, prompt: str, use_resume: bool, record_id: Optional[str] = None) -> list:
        """构建命令行
        
        Args:
            prompt: 提示词
            use_resume: 是否继续上次会话
            record_id: 指定使用的 record_id（可选，None 表示新会话）
        """
        self._prompt_tmp = None
        if platform.system() == "Windows":
            prompt = prompt.replace('\n', ' ').replace('\r', ' ')
        
        # 确定使用的 record_id
        session_id = None
        if use_resume:
            if record_id:
                session_id = record_id

        escaped = shlex.quote(prompt)
        session = f"-r {session_id}" if session_id else ""
        if self.agent_type == "opencode":
            session = f"--session {session_id}" if session_id else ""
            cmd = f"opencode run {escaped} {session} --format json".replace("  ", " ").strip()
        else:
            cmd = f"ccr code -p {session} --output-format stream-json --verbose --dangerously-skip-permissions {escaped}".replace(
                "  ", " ").strip()
        
        if platform.system() == "Windows":
            return ["cmd.exe", "/c", f"cd /d {self.workspace_path} && {cmd}"]
        else:
            return ["/bin/bash", "-c", f"cd {shlex.quote(self.workspace_path)} && {cmd}"]

    async def _run_command(
        self,
        run_context: RunContext,
        prompt: str,
        record_id: Optional[str],
        include_record_ids: bool = True,
        include_todos: bool = False
    ):
        """执行命令的公共方法，供 arun_prompt、undo_prompt、redo_prompt 复用
        
        Args:
            run_context: RunContext
            prompt: 提示词或命令
            record_id: 使用的 record_id（None 表示新会话）
            include_record_ids: 是否在返回事件中包含 record_id 列表
            include_todos: 是否在返回事件中包含 TodoItem
        """
        if self.agent_type == "opencode":
            from core.tools.vibe_tool.opencode_parser import OpenCodeStreamParser as _Parser, OpenCodeMessageExtractor as _Extractor
        else:
            from core.tools.vibe_tool.parser import StreamParser as _Parser, MessageExtractor as _Extractor

        parser = _Parser(max_workers=4)
        extractor = _Extractor()
        last_text_by_id = {}

        cmd = self._build_cmd(prompt, record_id is not None, record_id)
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        if IS_WINDOWS:
            git_bash_path = os.environ.get("CLAUDE_CODE_GIT_BASH_PATH")
            if not git_bash_path:
                possible_paths = [
                    r"E:\Git\bin\bash.exe",
                    r"C:\Program Files\Git\bin\bash.exe",
                    r"C:\Program Files (x86)\Git\bin\bash.exe",
                ]
                for path in possible_paths:
                    if os.path.exists(path):
                        git_bash_path = path
                        break
            if git_bash_path:
                env["CLAUDE_CODE_GIT_BASH_PATH"] = git_bash_path
        prepared = current_sandbox_manager().prepare_spawn(
            argv=cmd,
            cwd=self.workspace_path,
            env=env,
        )

        process = await asyncio.create_subprocess_exec(
            *prepared.argv,
            cwd=prepared.cwd,
            env=prepared.env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            limit=100 * 1024 * 1024,
            start_new_session=True,
        )

        def _make_event(content: str | list, meta=None) -> ExternalAgentRunResponseContentEvent:
            event = ExternalAgentRunResponseContentEvent(
                type="document",
                agent_id=run_context.session_id,
                agent_name=run_context.session_id,
                run_id=run_context.run_id,
                session_id=run_context.session_id,
                content=content,
                metadata=meta,
            )
            # ── DEBUG ──────────────────────────────────────────────────────────
            _dbg_print_event(event, run_context)
            # ───────────────────────────────────────────────────────────────────
            return event

        try:
            while True:
                assert process.stdout is not None
                raw = await process.stdout.readline()
                if not raw:
                    break

                line = raw.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("{"):
                    continue

                # 解析 JSON -> ParseData
                parse_data: Optional[ParseData] = None
                async for pd in parser.parse_line_async(line):
                    parse_data = pd
                    break

                if parse_data is None:
                    continue

                # 更新 record_id 映射
                if parse_data.session_id:
                    self._add_record_id(run_context, parse_data.session_id)

                # type=result → 任务完成
                if parse_data.type == "result":
                    # 将任务信息添加到 task_graph（用于后续自动决策）
                    if parse_data.session_id:
                        task_graph = self.task_graph
                        # 从 parse_data 提取文件信息
                        files_created = [
                            file_info["file_path"]
                            for file_info in (parse_data.write_files or [])
                            if isinstance(file_info, dict) and "file_path" in file_info
                        ]
                        
                        task_graph.add_task(
                            record_id=parse_data.session_id,
                            prompt=prompt or "",
                            task_desc=f"Vibe coding task: {(prompt or '')[:100]}",
                            files_created=files_created,
                            files_modified=[],
                        )
                    
                    metadata = RunContentEvent(
                        agent_id=run_context.session_id,
                        agent_name=run_context.run_id,
                        run_id=run_context.run_id,
                        session_id=run_context.session_id,
                        content_type="html",
                        content=json.dumps(parse_data.message, ensure_ascii=False) if isinstance(parse_data.message, dict) else str(parse_data.message),
                    )
                    if include_record_ids:
                        current_record_ids = self._get_record_ids(run_context)
                        metadata.metadata = {"vibe_record_ids": current_record_ids}

                    yield ExternalAgentRunResponseContentEvent(
                        type="content",
                        agent_id=run_context.session_id,
                        agent_name=run_context.session_id,
                        run_id=run_context.run_id,
                        session_id=run_context.session_id,
                        content=json.dumps(parse_data.message, ensure_ascii=False) if isinstance(parse_data.message, dict) else str(parse_data.message),
                        metadata=metadata
                    )
                    await asyncio.sleep(0.0001)
                    break

                # 提取文本增量
                text_content = await extractor.extract_text_content(parse_data)
                msg_id = parse_data.uuid or "default"
                last_text = last_text_by_id.get(msg_id, "")
                new_text = text_content[len(last_text):] if len(text_content) > len(last_text) else ""
                if new_text:
                    last_text_by_id[msg_id] = text_content

                # TodoItem
                if include_todos:
                    for todo in (parse_data.todo_list or []):
                        yield _make_event(
                            content="",
                            meta=ToolCallStartedEvent(
                                agent_id=run_context.session_id,
                                agent_name=run_context.run_id,
                                run_id=run_context.run_id,
                                session_id=run_context.session_id,
                                tool=ToolExecution(
                                    tool_call_id=msg_id,
                                    tool_name="TodoItem",
                                    tool_args={"content": todo.content, "status": todo.status,
                                               "activeForm": todo.activeForm}
                                )
                            )
                        )
                        new_text = ""
                        await asyncio.sleep(0.0001)

                # ToolCall
                for tc in (parse_data.tool_calls or []):
                    yield _make_event(
                        content="",
                        meta=ToolCallStartedEvent(
                            tool=ToolExecution(
                                tool_call_id=tc.id or f"call_{msg_id}",
                                tool_name=tc.name,
                                tool_args=tc.input
                            )
                        )
                    )
                    new_text = ""
                    await asyncio.sleep(0.0001)

                # ToolCallResult
                if parse_data.tool_use_result:
                    yield _make_event(
                        content="",
                        meta=ToolCallStartedEvent(
                            tool=ToolExecution(
                                tool_call_id=f"result_{msg_id}",
                                tool_name="ToolResult",
                                tool_args=parse_data.tool_use_result
                            )
                        )
                    )
                    new_text = ""
                    await asyncio.sleep(0.0001)

                # 剩余文本
                if new_text and new_text.strip():
                    yield _make_event(
                        content=new_text,
                        meta=RunContentEvent(
                            agent_id=run_context.session_id,
                            agent_name=run_context.run_id,
                            run_id=run_context.run_id,
                            session_id=run_context.session_id,
                            content_type="html",
                            content=parse_data.message,
                        )
                    )

                await asyncio.sleep(0.0001)

        finally:
            parser.shutdown()
            if 'process' in locals() and getattr(process, 'returncode', None) is None:
                try:
                    # 1. 优先等待它自行退出
                    if process.returncode is None:
                        try:
                            await asyncio.wait_for(process.wait(), timeout=2.0)
                        except asyncio.TimeoutError:
                            pass
                    
                    # 2. 超时未退出则强制终止进程树
                    if process.returncode is None:
                        if platform.system() == "Windows":
                            subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], 
                                         capture_output=True, timeout=5)
                        else:
                            killpg = getattr(os, "killpg", None)
                            getpgid = getattr(os, "getpgid", None)
                            if killpg and getpgid:
                                killpg(getpgid(process.pid), signal.SIGTERM)
                            else:
                                process.terminate()
                except Exception:
                    try:
                        process.kill()
                    except Exception:
                        pass
                
                # 3. 阻塞等待底层回收资源，解除操作系统的文件锁定
                try:
                    await asyncio.wait_for(process.wait(), timeout=3.0)
                except Exception:
                    pass
                
                # 4. 解除 Python 层面的管道引用
                if getattr(process, "stdout", None):
                    process.stdout = None  # type: ignore
                if getattr(process, "stderr", None):
                    process.stderr = None  # type: ignore

    async def coding_assign_task(self, run_context: RunContext, task_name: str, prompt: str, use_resume: bool = False, auto_decide: bool = True):
        """
        全能型端到端开发工具。 异步执行复杂的编程任务，包括但不限于项目全生命周期开发、架构搭建（如 Vite、React）、代码重构及自动化测试。该工具具备极强的任务理解与自主规划能力，严禁协调器将用户的原始开发指令拆分为多个子任务。 
        请务必将完整、原始的需求直接传递给此工具，以确保上下文的完整性并最大化执行效率。当其他单一功能工具无法胜任时，该工具是首选的终极解决方案。
        
        Args:
            task_name: 任务名称，用于唯一标识该编程任务。相同 task_name 会自动关联到上次会话，无需手动传入 record_id。
            prompt: 编程任务描述
            use_resume: 是否强制续接该 task_name 对应的上次会话
            auto_decide: 是否启用自动决策（根据任务名称和历史记录判断是否应该 resume）
        
        返回的事件 metadata 中会包含当前 task_name → record_id 映射，协调器可据此获取。
        """
         # 检查所需 CLI 工具是否已安装
        cli_name = "opencode" if self.agent_type == "opencode" else "ccr"

        if shutil.which(cli_name) is None:
            raise RuntimeError(
                f"VibeCodingToolkit 初始化失败：未检测到 '{cli_name}' 命令。\n"
                f"请先安装该工具后再使用。\n"
                f"  opencode: npm install -g opencode-ai\n"
                f"  ccr:      npm install -g claude-code-router"
            )
        try:
            # 用于保存工作目录的临时内容
            workdir = self.workspace_path

            # VibeCoding 专用工作目录
            workspace_path = os.path.join(self.workspace_path, 'runs', f'{task_name}')
            if not os.path.exists(workspace_path):
                os.makedirs(workspace_path)
            self.workspace_path = workspace_path
            
            # 初始化 session_state 并设置当前 task_name
            if run_context.session_state is None:
                run_context.session_state = {}
            run_context.session_state[_SESSION_LAST_TASK_KEY] = task_name

            # 查找该 task_name 是否已有对应的 record_id（
            existing_record_id = self._get_record_id_by_task(run_context, task_name)

            # 确定是否续接
            effective_record_id: Optional[str] = None

            if use_resume and existing_record_id:
                # 明确要求续接
                effective_record_id = existing_record_id
            elif auto_decide and existing_record_id:
                # 自动决策：基于任务图判断
                task_graph = self.task_graph
                decision_result = task_graph.decide(prompt)
                print(decision_result.decision)
                if decision_result.decision == Decision.RESUME and decision_result.confidence >= 0.6:
                    print(decision_result)
                    effective_record_id = existing_record_id
                elif decision_result.decision == Decision.NEW_TASK:
                    effective_record_id = None  # 全新任务
                else:
                    # 不确定：记录决策信息，保守选择新建
                    run_context.session_state["last_decision"] = decision_result.to_dict()
                    effective_record_id = None
            # 否则：无历史记录，直接新建

            # 调用公共方法执行命令（包含 TodoItem 处理）
            async for event in self._run_command(
                run_context, prompt, effective_record_id,
                include_record_ids=True, include_todos=True
            ):
                yield event

        except Exception as e:
            # 记录错误
            error_msg = f"执行编程任务失败: {str(e)}"
            print(f"DEBUG: {error_msg}")
            
            # 尝试清理工作目录
            try:
                if os.path.exists(workspace_path):
                    shutil.rmtree(workspace_path)
                    print(f"DEBUG: 已清理工作目录: {workspace_path}")
            except Exception as cleanup_error:
                print(f"DEBUG: 清理工作目录失败: {cleanup_error}")
            
            # 重新抛出异常
            raise RuntimeError(error_msg) from e
        
        # 恢复工作目录
        self.workspace_path = workdir
