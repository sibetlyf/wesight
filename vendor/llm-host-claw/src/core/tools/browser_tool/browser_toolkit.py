from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import os
import shutil
import uuid
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from typing import Any, AsyncIterator, Dict, Iterable, Optional

import browser_use as bu
import yaml
from browser_use import Agent

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from agno.models.openai.like import OpenAILike
from agno.run.agent import RunContentEvent
from agno.run.base import RunContext
from agno.tools import Toolkit

from configs import OrchestratorConfig
from configs.browse_use import BrowserUseConfig
from protocol import EnVar
from protocol.external_agent_run_response_event import ExternalAgentRunResponseContentEvent


def _is_10086_openai_compatible_endpoint(base_url: str) -> bool:
    try:
        host = (urlparse(str(base_url or "")).hostname or "").lower()
    except Exception:
        host = str(base_url or "").lower()
    return host == "10086.cn" or host.endswith(".10086.cn")


def _openai_compatible_no_thinking_extra_body(
    base_url: str,
    configured_extra_body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a no-thinking extra_body for OpenAI-compatible model calls.

    This is used by the OUTER Orchestrator model as well as any nested model
    configs that are represented in the YAML. BrowserUseToolkit's inner browser
    model has its own enforcement in configs.browse_use, but the outer model is
    the one that calls shell/write_todo before browser-use starts.
    """
    payload: Dict[str, Any] = dict(configured_extra_body or {})
    if _is_10086_openai_compatible_endpoint(base_url):
        for obsolete in ("thinking", "enable_thinking", "chat_template_kwargs"):
            payload.pop(obsolete, None)
        payload["enable_moderation"] = False
        payload["reasoning"] = {"enabled": False}
    else:
        # Current non-10086 gateway is DeepSeek-compatible. Force the browser
        # orchestration model out of thinking mode to avoid reasoning_content
        # tool-call continuation requirements.
        payload.setdefault("thinking", {"type": "disabled"})
    return payload


def _normalize_openai_compatible_model_cfg(model_cfg: Any) -> Any:
    """Return a copy of a model config with request_params.extra_body populated.

    Only configs with an explicit base_url are touched. Model configs without a
    base_url may belong to another provider/default registry and are left alone.
    """
    if not isinstance(model_cfg, dict):
        return model_cfg
    cfg = dict(model_cfg)
    base_url = str(cfg.get("base_url") or "").strip()
    if not base_url:
        return cfg

    configured_extra = cfg.get("extra_body")
    request_params = dict(cfg.get("request_params") or {})
    extra_body = _openai_compatible_no_thinking_extra_body(base_url, configured_extra)
    request_params["extra_body"] = extra_body
    cfg["request_params"] = request_params

    # Keep YAML backwards-compatible, but avoid accidentally passing top-level
    # extra_body to constructors that only understand request_params.
    cfg.pop("extra_body", None)
    return cfg


def _normalize_model_cfgs_in_obj(obj: Any) -> Any:
    """Recursively normalize nested `model:` dictionaries in raw YAML."""
    if isinstance(obj, list):
        return [_normalize_model_cfgs_in_obj(x) for x in obj]
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        for key, value in obj.items():
            if key == "model" and isinstance(value, dict):
                out[key] = _normalize_openai_compatible_model_cfg(value)
            else:
                out[key] = _normalize_model_cfgs_in_obj(value)
        return out
    return obj



DEFAULT_CONFIG_CANDIDATES = [os.environ.get("ORCHESTRATOR_CONFIG", "").strip()]


def new_session_id() -> str:
    return f"browser_chat_{uuid.uuid4().hex[:8]}"


def _first_existing_path(candidates: Iterable[str]) -> Optional[str]:
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def _load_yaml(path: Optional[str]) -> dict:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _sync_envar_to_env(envar: Any) -> None:
    data: Dict[str, Any] = {}
    with contextlib.suppress(Exception):
        dumped = envar.model_dump()
        if isinstance(dumped, dict):
            data.update(dumped)
    if not data:
        with contextlib.suppress(Exception):
            data.update(vars(envar))

    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, Path):
            value = str(value)
        elif not isinstance(value, (str, int, float, bool)):
            continue
        value_str = str(value).strip()
        if value_str:
            os.environ.setdefault(key, value_str)
            os.environ.setdefault(key.upper(), value_str)


def _iter_tool_containers(obj: Any) -> Iterable[Any]:
    for attr in ("tools", "toolkits", "available_tools", "toolkit_registry", "tool_registry", "agent"):
        value = getattr(obj, attr, None)
        if value is None:
            continue
        if isinstance(value, dict):
            yield from value.values()
        elif isinstance(value, (list, tuple, set)):
            yield from value
        else:
            yield value


def find_browser_toolkit(orchestrator: Any) -> Optional["BrowserUseToolkit"]:
    visited: set[int] = set()
    queue: list[Any] = [orchestrator]
    while queue:
        current = queue.pop(0)
        if current is None or id(current) in visited:
            continue
        visited.add(id(current))
        if isinstance(current, BrowserUseToolkit):
            return current
        for item in _iter_tool_containers(current):
            if isinstance(item, BrowserUseToolkit):
                return item
            queue.append(item)
        for attr in dir(current):
            if attr.startswith("__"):
                continue
            with contextlib.suppress(Exception):
                value = getattr(current, attr)
                if isinstance(value, BrowserUseToolkit):
                    return value
                if isinstance(value, (list, tuple, set, dict)):
                    queue.append(value)
    return None


def build_browser_orchestrator(
    config_path: Optional[str] = None,
    *,
    envar: EnVar,
    base_url: str | None = None,
    model_id: str | None = None,
):
    resolved_config_path = config_path or _first_existing_path(DEFAULT_CONFIG_CANDIDATES)
    if not resolved_config_path:
        raise FileNotFoundError("未找到 orchestrator 配置文件；请传入 config_path，或设置 ORCHESTRATOR_CONFIG。")

    test_config = _load_yaml(resolved_config_path)
    # Normalize nested model configs early, before OrchestratorConfig validates
    # and before any tool/model is constructed from the raw YAML.
    test_config = _normalize_model_cfgs_in_obj(test_config)

    model_cfg = dict(test_config.get("model") or {})

    if model_id is not None:
        model_cfg["id"] = model_id
    if base_url is not None:
        model_cfg["base_url"] = base_url
    if not model_cfg.get("api_key") and getattr(envar, "authorization", None):
        model_cfg["api_key"] = envar.authorization
    if model_cfg:
        model_cfg = _normalize_openai_compatible_model_cfg(model_cfg)
        test_config["model"] = model_cfg
    if model_cfg.get("api_key"):
        envar.authorization = str(model_cfg["api_key"])

    if "toolkits" in test_config:
        test_config["toolkits"] = [
            tk for tk in test_config["toolkits"]
            if "jt_tools" not in str(tk.get("target", ""))
        ]

    config = OrchestratorConfig.model_validate(test_config)
    config.to_env()
    _sync_envar_to_env(envar)

    from core.orchestrator import Orchestrator
    orch = Orchestrator(cfg=config, envar=envar)

    if model_cfg.get("id") and model_cfg.get("base_url") and model_cfg.get("api_key"):
        model_kwargs: Dict[str, Any] = {
            "id": str(model_cfg["id"]),
            "base_url": str(model_cfg["base_url"]).rstrip("/"),
            "api_key": str(model_cfg["api_key"]),
        }
        if isinstance(model_cfg.get("request_params"), dict):
            model_kwargs["request_params"] = dict(model_cfg["request_params"])
        model = OpenAILike(**model_kwargs)
        orch.model = model
        if getattr(orch, "agent", None) is not None:
            orch.agent.model = model

    return orch, resolved_config_path, find_browser_toolkit(orch)


@dataclass
class BrowserAgentEvent:
    event_type: str
    content: Any
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class BrowserConversationState:
    session_id: str
    browser: Any
    agent: Any
    llm: Any
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_used_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_url: Optional[str] = None
    last_title: Optional[str] = None
    latest_step: int = 0
    status: str = "ready"
    turn_count: int = 0
    user_data_dir: Optional[str] = None


class BrowserUseToolkit(Toolkit):
    """自动浏览器工具职责
    1. 把 browser-use 注册为 Agno tool；
    2. 管理浏览器 session；
    3. 把 browser-use 事件格式化返回给 orchestrator。
    """

    _GLOBAL_ACTIVE_RUNS: Dict[str, Dict[str, Any]] = {}
    _GLOBAL_RECENT_RUNS: Dict[str, Dict[str, Any]] = {}
    _GLOBAL_SESSION_STATES: Dict[str, BrowserConversationState] = {}
    _GLOBAL_SESSION_LOCKS: Dict[str, asyncio.Lock] = {}

    def __init__(self, *, cfg: BrowserUseConfig, envar: EnVar):
        cfg.validate()
        super().__init__(name=cfg.toolkit_name, instructions=cfg.toolkit_instructions)

        self.cfg = cfg
        self.envar = envar
        self.workspace = envar.workspace
        self.runspace = envar.runspace
        self.user = envar.user_id
        self.record_id = envar.record_id
        self.authorization = envar.authorization
        self._force_no_vision = False

        with contextlib.suppress(Exception):
            self.cfg.envar = envar
        with contextlib.suppress(Exception):
            self.cfg.workspace = self.workspace
        with contextlib.suppress(Exception):
            self.cfg.runspace = self.runspace

        cls = type(self)
        self._active_runs = cls._GLOBAL_ACTIVE_RUNS
        self._recent_runs = cls._GLOBAL_RECENT_RUNS
        self._session_states = cls._GLOBAL_SESSION_STATES
        self._session_locks = cls._GLOBAL_SESSION_LOCKS

        self.register(self.run_browser_agent)
        if getattr(cfg, "register_task_tools", True):
            self.register(self.cancel_task)
            self.register(self.get_task_status)
            self.register(self.list_active_tasks)
            self.register(self.list_browser_sessions)
            self.register(self.reset_browser_session)
            self.register(self.close_all_browsers)

    # -----------------------------
    # Public management tools
    # -----------------------------
    def list_active_tasks(self) -> str:
        """列出当前仍在执行中的浏览器任务。

        适用于查询 browser-use 代理当前有哪些任务正在运行，便于上层协调器
        了解任务数量、所属 session、任务提示词、启动时间、执行状态、
        最新步骤号以及最近访问的页面 URL。

        Returns:
            JSON 字符串，包含 active_count 和 tasks 列表。
        """
        return json.dumps(
            {
                "active_count": len(self._active_runs),
                "tasks": [
                    {
                        "task_id": task_id,
                        "session_id": meta.get("session_id"),
                        "prompt": meta.get("prompt"),
                        "started_at": meta.get("started_at"),
                        "status": meta.get("status", "running"),
                        "latest_step": meta.get("latest_step"),
                        "last_url": meta.get("last_url"),
                    }
                    for task_id, meta in self._active_runs.items()
                ],
            },
            ensure_ascii=False,
        )

    def get_task_status(self, task_id: str) -> str:
        """查询某个浏览器任务的执行状态。

        可用于按 task_id 查看一个任务当前是否仍在运行、是否已完成、失败、
        被取消，或根本不存在。同时返回该任务所属 session、原始 prompt、
        已执行到的步骤号以及最近访问的 URL。

        Args:
            task_id: 要查询的任务唯一标识。

        Returns:
            JSON 字符串，包含 task_id、status 以及相关运行信息。
        """
        meta = self._active_runs.get(task_id) or self._recent_runs.get(task_id)
        if not meta:
            return json.dumps({"task_id": task_id, "status": "not_found"}, ensure_ascii=False)
        return json.dumps(
            {
                "task_id": task_id,
                "session_id": meta.get("session_id"),
                "status": meta.get("status", "unknown"),
                "prompt": meta.get("prompt"),
                "started_at": meta.get("started_at"),
                "latest_step": meta.get("latest_step"),
                "last_url": meta.get("last_url"),
            },
            ensure_ascii=False,
        )

    def cancel_task(self, task_id: str) -> str:
        """取消一个正在运行中的浏览器任务。

        当某个 browser-use 任务执行时间过长、走错页面、或用户希望提前中止时，
        可调用本工具。若任务仍在运行，会向对应 asyncio task 发送取消信号；
        若任务不存在，则返回 not_found。

        Args:
            task_id: 要取消的任务唯一标识。

        Returns:
            JSON 字符串，表示取消请求的处理结果。
        """
        meta = self._active_runs.get(task_id)
        if not meta:
            return json.dumps({"task_id": task_id, "status": "not_found"}, ensure_ascii=False)
        task = meta.get("asyncio_task")
        if task and not task.done():
            task.cancel()
            meta["status"] = "cancelling"
            return json.dumps({"task_id": task_id, "status": "cancelling"}, ensure_ascii=False)
        return json.dumps({"task_id": task_id, "status": meta.get("status", "unknown")}, ensure_ascii=False)

    def list_browser_sessions(self) -> str:
        """列出当前缓存的全部浏览器会话。

        用于查看 BrowserUseToolkit 内部维护的 session 池，包括每个 session 的
        创建时间、最近使用时间、最近访问页面、标题、累计轮次、浏览器状态、
        profile 目录以及底层 browser/agent 类型，方便排查多轮会话复用情况。

        Returns:
            JSON 字符串，包含 session_count 和 sessions 列表。
        """
        sessions = []
        for session_id, state in self._session_states.items():
            sessions.append(
                {
                    "session_id": session_id,
                    "created_at": state.created_at,
                    "last_used_at": state.last_used_at,
                    "last_url": state.last_url,
                    "last_title": state.last_title,
                    "latest_step": state.latest_step,
                    "status": state.status,
                    "turn_count": state.turn_count,
                    "user_data_dir": state.user_data_dir,
                    "browser_type": type(state.browser).__name__ if state.browser is not None else None,
                    "agent_type": type(state.agent).__name__ if state.agent is not None else None,
                }
            )
        return json.dumps({"session_count": len(sessions), "sessions": sessions}, ensure_ascii=False)

    async def close_session_browser(self, session_id: str, delete_profile: bool = False) -> str:
        session_id = str(session_id or "browser_use")
        async with self._get_session_lock(session_id):
            state = self._session_states.pop(session_id, None)
            if state is None:
                return json.dumps({"session_id": session_id, "status": "not_found"}, ensure_ascii=False)
            await self._shutdown_state(state, delete_profile=delete_profile)
            await asyncio.sleep(0.1)
            return json.dumps(
                {
                    "session_id": session_id,
                    "status": "closed",
                    "delete_profile": bool(delete_profile),
                    "user_data_dir": state.user_data_dir,
                },
                ensure_ascii=False,
            )

    async def close_browser_for_session(self, session_id: str, *, delete_profile: bool) -> str:
        direct = await self.close_session_browser(session_id, delete_profile=delete_profile)
        payload = self._json_loads_maybe(direct)
        if payload.get("status") != "not_found":
            return direct

        sessions = self._json_loads_maybe(self.list_browser_sessions()).get("sessions") or []
        if not sessions:
            return direct
        best = max(sessions, key=lambda x: (str(x.get("last_used_at") or ""), str(x.get("created_at") or "")))
        fallback_id = best.get("session_id")
        if not fallback_id:
            return direct
        return await self.close_session_browser(str(fallback_id), delete_profile=delete_profile)

    async def reset_browser_session(
        self,
        run_context: RunContext,
        session_id: Optional[str] = None,
        delete_profile: bool = False,
    ) -> str:
        """重置指定 session 对应的浏览器实例。

        该工具会关闭当前 session 绑定的 browser-use 浏览器与 agent 状态，
        但保留上层 Agno 会话标识。适用于页面卡死、登录态异常、上下文污染、
        或希望重新开始浏览器环境时使用。

        Args:
            run_context: 当前 Agno 运行上下文，用于推导默认 session_id。
            session_id: 可选的目标会话 ID；为空时使用 run_context 中的 session。
            delete_profile: 是否同时删除该 session 的本地浏览器 profile 目录。

        Returns:
            JSON 字符串，描述浏览器会话是否成功关闭。
        """
        actual_session_id = self._resolve_session_id(run_context=run_context, session_id=session_id)
        return await self.close_session_browser(actual_session_id, delete_profile=delete_profile)

    async def close_all_browsers(self, delete_profiles: bool = False) -> str:
        """关闭当前 Toolkit 缓存的全部浏览器会话。

        适用于程序退出、资源回收、批量清理环境等场景。该工具会遍历所有
        已缓存的 session，依次关闭其浏览器实例；可选地删除对应 profile 目录。

        Args:
            delete_profiles: 是否在关闭后同时删除所有 session 的本地 profile。

        Returns:
            JSON 字符串，包含成功关闭与关闭失败的 session 列表。
        """
        closed = []
        failed = []
        for session_id in list(self._session_states.keys()):
            try:
                await self.close_session_browser(session_id, delete_profile=delete_profiles)
                closed.append(session_id)
            except Exception as exc:
                failed.append({"session_id": session_id, "error": str(exc)})
        return json.dumps(
            {"status": "ok" if not failed else "partial", "closed": closed, "failed": failed},
            ensure_ascii=False,
        )

    # -----------------------------
    # Agno tool entry
    # -----------------------------
    async def run_browser_agent(
        self,
        run_context: RunContext,
        prompt: str,
        session_id: Optional[str] = None,
        use_resume: bool = False,
        max_steps: Optional[int] = None,
    ):
        """执行一个 browser-use 浏览器代理任务，并流式返回执行过程。

        当需要访问网页、点击页面、输入内容、读取页面信息、延续多轮网页操作
        或复用已有浏览器会话时，应优先调用本工具。工具会自动为 session 复用
        浏览器与 agent，并在执行过程中持续输出状态、步骤、文本摘要、最终结果
        或错误信息。

        Args:
            run_context: 当前 Agno 运行上下文，用于获取 session_id、run_id 等信息。
            prompt: 交给 browser-use 执行的网页任务描述。
            session_id: 可选的浏览器会话 ID；为空时自动从 run_context 推导。
            use_resume: 是否优先复用该 session 已存在的 agent 上下文继续执行。
            max_steps: 本轮任务允许执行的最大步骤数；为空时使用配置默认值。

        Yields:
            ExternalAgentRunResponseContentEvent 流式事件，包含执行状态、步骤摘要、
            文本输出、最终结果或错误信息。
        """
        emit_intermediate = bool(getattr(self.cfg, "emit_intermediate_events_to_model", False))
        terminal_event: Optional[BrowserAgentEvent] = None
        fallback_event: Optional[BrowserAgentEvent] = None

        async for event in self._astream_browser_events(
            prompt=prompt,
            run_context=run_context,
            session_id=session_id,
            use_resume=use_resume,
            max_steps=max_steps,
        ):
            if emit_intermediate:
                yield self._to_agno_event(run_context, event)
                continue

            if event.event_type in {"result", "error", "cancelled"}:
                terminal_event = event
            elif fallback_event is None or event.event_type == "status":
                fallback_event = event

        final_event = terminal_event or fallback_event
        if final_event is not None:
            yield self._to_agno_event(run_context, final_event)

    async def _astream_browser_events(
        self,
        *,
        prompt: str,
        run_context: Optional[RunContext] = None,
        session_id: Optional[str] = None,
        use_resume: bool = False,
        max_steps: Optional[int] = None,
    ) -> AsyncIterator[BrowserAgentEvent]:
        actual_session_id = self._resolve_session_id(run_context=run_context, session_id=session_id)
        task_id = f"{str(actual_session_id).replace('-', '_')}_{uuid.uuid4().hex[:12]}"
        queue: asyncio.Queue[Optional[BrowserAgentEvent]] = asyncio.Queue()
        started_at = datetime.now(timezone.utc).isoformat()

        self._active_runs[task_id] = {
            "task_id": task_id,
            "session_id": actual_session_id,
            "prompt": prompt,
            "started_at": started_at,
            "status": "queued",
            "latest_step": 0,
            "last_url": self._session_states.get(actual_session_id).last_url if actual_session_id in self._session_states else None,
        }

        async def emit(event_type: str, content: Any, **metadata: Any) -> None:
            await queue.put(BrowserAgentEvent(event_type=event_type, content=content, metadata=metadata))

        async def producer() -> None:
            state: Optional[BrowserConversationState] = None
            try:
                async with self._get_session_lock(actual_session_id):
                    meta = self._active_runs.get(task_id)
                    if meta is not None:
                        meta["status"] = "starting"

                    prepared_prompt = self._prepare_agent_task(prompt)
                    state, browser_reused, agent_reused = await self._ensure_session_state(
                        actual_session_id,
                        initial_prompt=prepared_prompt,
                        reuse_agent=bool(use_resume),
                    )

                    if meta is not None:
                        meta["status"] = "running"

                    await emit(
                        "status",
                        {
                            "message": f"browser-use 已启动，准备执行任务：{prompt}",
                            "task_id": task_id,
                            "session_id": actual_session_id,
                            "browser_reused": browser_reused,
                            "agent_reused": agent_reused,
                            "turn_count": state.turn_count,
                            "browser_type": type(state.browser).__name__,
                            "agent_type": type(state.agent).__name__,
                            "last_url": state.last_url,
                        },
                        task_id=task_id,
                        session_id=actual_session_id,
                    )

                    if agent_reused:
                        await self._append_followup_task(state, prepared_prompt)
                    base_raw_step = self._infer_step_no(state.agent)

                    async def on_step_start(agent_instance: Any) -> None:
                        raw_step = self._infer_step_no(agent_instance)
                        step_no = max(1, raw_step - base_raw_step)
                        run_meta = self._active_runs.get(task_id)
                        if run_meta is not None:
                            run_meta["latest_step"] = step_no

                    async def on_step_end(agent_instance: Any) -> None:
                        snapshot = await self._collect_agent_snapshot(agent_instance)
                        raw_step = snapshot.get("step") or self._infer_step_no(agent_instance)
                        step_no = max(1, raw_step - base_raw_step)
                        run_meta = self._active_runs.get(task_id)
                        if run_meta is not None:
                            run_meta["latest_step"] = step_no
                            run_meta["last_url"] = snapshot.get("url")
                        self._touch_state(
                            state,
                            last_url=snapshot.get("url"),
                            last_title=snapshot.get("title"),
                            latest_step=step_no,
                        )

                    run_kwargs = {
                        "max_steps": max_steps or getattr(self.cfg, "max_steps", None),
                        "on_step_start": on_step_start,
                        "on_step_end": on_step_end,
                    }
                    run_kwargs = {k: v for k, v in run_kwargs.items() if v is not None}
                    try:
                        history = await state.agent.run(**run_kwargs)
                    except Exception as exc:
                        if (not self._force_no_vision) and self._is_vision_safety_block_error_text(exc):
                            self._force_no_vision = True
                            await emit(
                                "status",
                                {
                                    "message": "模型网关返回 403，疑似与页面视觉/截图上下文有关，已自动切换到文本/DOM 模式重试本任务。",
                                    "task_id": task_id,
                                    "session_id": actual_session_id,
                                },
                                task_id=task_id,
                                session_id=actual_session_id,
                            )
                            state.agent = await self._build_agent(
                                prompt=prepared_prompt,
                                llm=state.llm,
                                browser_handle=state.browser,
                                session_id=actual_session_id,
                            )
                            history = await state.agent.run(**run_kwargs)
                        else:
                            raise
                    result_payload = self._history_to_result(history)
                    page_state = await self._probe_current_page_state(state)
                    if page_state:
                        result_payload["page_state"] = page_state
                        result_payload["last_url"] = page_state.get("url") or result_payload.get("last_url")
                        result_payload["last_title"] = page_state.get("title") or result_payload.get("last_title")
                    if self._is_action_only_result(result_payload) and not self._page_state_indicates_completion(page_state):
                        result_payload["success"] = False
                        result_payload["needs_continue"] = True
                        result_payload["final_result"] = self._partial_progress_text(result_payload)
                    snapshot = await self._collect_agent_snapshot(state.agent)
                    self._touch_state(
                        state,
                        last_url=snapshot.get("url") or state.last_url,
                        last_title=snapshot.get("title") or state.last_title,
                        latest_step=snapshot.get("step") or state.latest_step,
                    )
                    state.turn_count += 1
                    run_meta = self._active_runs.get(task_id)
                    if run_meta is not None:
                        run_meta["status"] = "completed"
                    await emit("result", result_payload, task_id=task_id, session_id=actual_session_id)
            except asyncio.CancelledError:
                run_meta = self._active_runs.get(task_id)
                if run_meta is not None:
                    run_meta["status"] = "cancelled"
                await emit("cancelled", {"task_id": task_id, "session_id": actual_session_id, "prompt": prompt})
                raise
            except Exception as exc:
                run_meta = self._active_runs.get(task_id)
                if run_meta is not None:
                    run_meta["status"] = "failed"
                await emit(
                    "error",
                    {
                        "error": str(exc),
                        "task_id": task_id,
                        "session_id": actual_session_id,
                    },
                    task_id=task_id,
                    session_id=actual_session_id,
                )
                if state is not None and self._should_reset_session(exc):
                    with contextlib.suppress(Exception):
                        await self._discard_state(actual_session_id, state, delete_profile=False)
            finally:
                meta = self._active_runs.pop(task_id, None)
                if meta is not None:
                    self._recent_runs[task_id] = meta
                    while len(self._recent_runs) > 64:
                        self._recent_runs.pop(next(iter(self._recent_runs)), None)
                await queue.put(None)

        producer_task = asyncio.create_task(producer())
        self._active_runs[task_id]["asyncio_task"] = producer_task

        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            if not producer_task.done():
                producer_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await producer_task

    # -----------------------------
    # Event conversion
    # -----------------------------
    def _to_agno_event(self, run_context: RunContext, event: BrowserAgentEvent) -> ExternalAgentRunResponseContentEvent:
        content = self._stringify_content(event)
        session_id = self._resolve_session_id(run_context=run_context, session_id=event.metadata.get("session_id"))
        run_id = self._ctx_value(run_context, "run_id") or session_id
        metadata = RunContentEvent(
            agent_id=session_id,
            agent_name=session_id,
            run_id=run_id,
            session_id=session_id,
            content_type="html",
            content=content,
        )
        return ExternalAgentRunResponseContentEvent(
            type="content",
            agent_id=session_id,
            agent_name=session_id,
            run_id=run_id,
            session_id=session_id,
            content=content,
            metadata=metadata,
        )

    # -----------------------------
    # Session lifecycle
    # -----------------------------
    def _resolve_session_id(self, *, run_context: Optional[RunContext], session_id: Optional[str]) -> str:
        direct = self._ctx_value(run_context, "session_id")
        if direct:
            return str(direct)
        extracted = self._extract_session_id_from_obj(run_context)
        if extracted:
            return extracted
        if session_id:
            return str(session_id)
        return "browser_use"

    def _extract_session_id_from_obj(self, obj: Any) -> Optional[str]:
        if obj is None:
            return None
        keys = ("session_id", "agent_session_id", "conversation_id", "chat_session_id")
        if isinstance(obj, dict):
            for key in keys:
                value = obj.get(key)
                if value:
                    return str(value)
            for nested_key in ("metadata", "extra", "context"):
                nested = obj.get(nested_key)
                if nested is not None:
                    found = self._extract_session_id_from_obj(nested)
                    if found:
                        return found
            return None
        for key in keys:
            with contextlib.suppress(Exception):
                value = getattr(obj, key, None)
                if value:
                    return str(value)
        for nested_key in ("metadata", "extra", "context"):
            with contextlib.suppress(Exception):
                nested = getattr(obj, nested_key, None)
                if nested is not None:
                    found = self._extract_session_id_from_obj(nested)
                    if found:
                        return found
        return None

    def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        lock = self._session_locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._session_locks[session_id] = lock
        return lock

    async def _ensure_session_state(
        self,
        session_id: str,
        initial_prompt: str,
        *,
        reuse_agent: bool,
    ) -> tuple[BrowserConversationState, bool, bool]:
        state = self._session_states.get(session_id)
        if state is not None and await self._state_is_alive(state):
            self._touch_state(state)
            if reuse_agent:
                return state, True, True
            state.agent = await self._build_agent(prompt=initial_prompt, llm=state.llm, browser_handle=state.browser, session_id=session_id)
            state.latest_step = 0
            return state, True, False

        if state is not None:
            await self._discard_state(session_id, state, delete_profile=False)

        llm = self._build_llm()
        browser = await self._build_browser(session_id)
        agent = await self._build_agent(prompt=initial_prompt, llm=llm, browser_handle=browser, session_id=session_id)
        user_data_dir = self._session_user_data_dir(session_id)
        state = BrowserConversationState(
            session_id=session_id,
            browser=browser,
            agent=agent,
            llm=llm,
            user_data_dir=user_data_dir,
        )
        self._session_states[session_id] = state
        return state, False, False

    async def _state_is_alive(self, state: BrowserConversationState) -> bool:
        if state.browser is None:
            return False
        for attr in ("is_connected", "is_alive", "connected"):
            value = getattr(state.browser, attr, None)
            if callable(value):
                with contextlib.suppress(Exception):
                    result = value()
                    if asyncio.iscoroutine(result):
                        result = await result
                    return bool(result)
            elif value is not None:
                return bool(value)
        return True

    async def _discard_state(self, session_id: str, state: BrowserConversationState, delete_profile: bool = False) -> None:
        if self._session_states.get(session_id) is state:
            self._session_states.pop(session_id, None)
        await self._shutdown_state(state, delete_profile=delete_profile)

    async def _shutdown_state(self, state: BrowserConversationState, delete_profile: bool = False) -> None:
        state.status = "closing"
        browser = state.browser
        session = browser
        if hasattr(browser, "browser_session"):
            session = browser.browser_session
        elif hasattr(browser, "_session"):
            session = browser._session
        elif hasattr(browser, "_browser_session"):
            session = browser._browser_session
        if session is not None:
            reconnect_task = None
            if hasattr(session, "_auto_reconnect_task"):
                reconnect_task = session._auto_reconnect_task
            elif hasattr(session, "_reconnect_task"):
                reconnect_task = session._reconnect_task
            elif hasattr(session, "_connection") and hasattr(session._connection, "_reconnect_task"):
                reconnect_task = session._connection._reconnect_task
            if reconnect_task and not reconnect_task.done():
                reconnect_task.cancel()
                try:
                    await reconnect_task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass
            for stop_method in ("stop", "close", "aclose"):
                if hasattr(session, stop_method):
                    try:
                        result = getattr(session, stop_method)()
                        if asyncio.iscoroutine(result):
                            await result
                        break
                    except Exception:
                        continue
            if hasattr(session, "_connection"):
                conn = session._connection
                if hasattr(conn, "close"):
                    try:
                        await conn.close()
                    except Exception:
                        pass
                if hasattr(conn, "send_context") and hasattr(conn.send_context, "aclose"):
                    try:
                        await conn.send_context.aclose()
                    except Exception:
                        pass
        for method_name in ("kill", "close", "stop", "aclose"):
            method = getattr(browser, method_name, None)
            if method is None:
                continue
            try:
                result = method()
                if asyncio.iscoroutine(result):
                    await result
                break
            except Exception:
                continue
        current_task = asyncio.current_task()
        for task in asyncio.all_tasks():
            if task is current_task:
                continue
            task_name = getattr(task, "get_name", lambda: "")()
            coro_name = getattr(task.get_coro(), "__name__", "") if hasattr(task, "get_coro") else ""
            if any(name in task_name for name in ("reconnect", "send_context")) or \
                    any(name in coro_name for name in ("reconnect", "send_context")):
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    except Exception:
                        pass
        state.status = "closed"
        if delete_profile and state.user_data_dir:
            with contextlib.suppress(Exception):
                shutil.rmtree(state.user_data_dir, ignore_errors=True)

    def _touch_state(
        self,
        state: BrowserConversationState,
        *,
        last_url: Optional[str] = None,
        last_title: Optional[str] = None,
        latest_step: Optional[int] = None,
    ) -> None:
        state.last_used_at = datetime.now(timezone.utc).isoformat()
        state.status = "ready"
        if last_url is not None:
            state.last_url = last_url
        if last_title is not None:
            state.last_title = last_title
        if latest_step is not None:
            state.latest_step = latest_step

    def _session_user_data_dir(self, session_id: str) -> str:
        base_dir = getattr(self.cfg, "user_data_dir", None) or os.environ.get("BROWSER_TOOLKIT_SESSION_DIR")
        if base_dir:
            return str(Path(base_dir).expanduser().resolve() / session_id)
        if self.workspace:
            return str((Path(self.workspace).expanduser().resolve() / ".browser_toolkit_sessions" / session_id).resolve())
        return str((Path.cwd() / "tmp" / "browser_toolkit_sessions" / session_id).resolve())

    def _session_agent_file_dir(self, session_id: str) -> str:
        """Stable root for browser-use read_file/write_file artifacts.

        browser-use otherwise falls back to a system temporary directory (on Windows usually C:\\Users\\...\\AppData\\Local\\Temp).
        This path is deliberately separate from the Chromium profile directory.
        """
        configured = (
            getattr(self.cfg, "agent_file_system_dir", None)
            or os.environ.get("BROWSER_TOOLKIT_ARTIFACT_DIR")
        )
        if configured:
            base_dir = Path(configured).expanduser().resolve()
        elif self.runspace:
            base_dir = Path(self.runspace).expanduser().resolve()
        elif self.workspace:
            base_dir = Path(self.workspace).expanduser().resolve() / "runs"
        else:
            base_dir = Path.cwd().resolve() / "runs"
        target = base_dir / "browser_agent_files" / session_id
        target.mkdir(parents=True, exist_ok=True)
        return str(target)

    # -----------------------------
    # browser-use construction
    # -----------------------------
    async def _build_browser(self, session_id: str) -> Any:
        if getattr(self.cfg, "browser_factory", None) is not None:
            return await self._call_factory(
                self.cfg.browser_factory,
                session_id=session_id,
                cfg=self.cfg,
                envar=self.envar,
                workspace=self.workspace,
                runspace=self.runspace,
                user_data_dir=self._session_user_data_dir(session_id),
            )

        browser_cls = getattr(bu, "Browser", None)
        if browser_cls is None:
            raise RuntimeError("browser_use.Browser 不存在，无法创建浏览器。")
        browser_kwargs: Dict[str, Any] = dict(getattr(self.cfg, "browser_kwargs", {}) or {})
        browser_kwargs.setdefault("keep_alive", bool(getattr(self.cfg, "keep_alive", True)))
        session_user_data_dir = self._session_user_data_dir(session_id)
        Path(session_user_data_dir).mkdir(parents=True, exist_ok=True)
        browser_kwargs["user_data_dir"] = session_user_data_dir
        browser_kwargs.setdefault("profile_directory", "Default")
        for key in (
            "headless",
            "channel",
            "executable_path",
            "storage_state",
            "window_size",
            "window_position",
            "proxy",
            "args",
            "chromium_args",
        ):
            value = getattr(self.cfg, key, None)
            if value is not None and key not in browser_kwargs:
                browser_kwargs[key] = value
        return browser_cls(**browser_kwargs)

    async def _build_agent(self, *, prompt: str, llm: Any, browser_handle: Any, session_id: Optional[str] = None) -> Any:
        if getattr(self.cfg, "agent_factory", None) is not None:
            return await self._call_factory(
                self.cfg.agent_factory,
                prompt=prompt,
                llm=llm,
                browser=browser_handle,
                browser_session=browser_handle,
                cfg=self.cfg,
                envar=self.envar,
                workspace=self.workspace,
                runspace=self.runspace,
                file_system_path=self._session_agent_file_dir(session_id or "browser_use"),
            )

        profile = self._get_model_profile()
        agent_kwargs: Dict[str, Any] = dict(getattr(self.cfg, "agent_kwargs", {}) or {})
        base_kwargs = {
            "task": prompt,
            "llm": llm,
            "max_actions_per_step": self._effective_max_actions_per_step(profile),
            "max_failures": getattr(self.cfg, "max_failures", None),
            "use_vision": self._effective_use_vision(profile),
            "vision_detail_level": getattr(self.cfg, "vision_detail_level", None),
            "flash_mode": profile.get("flash_mode", getattr(self.cfg, "flash_mode", None)),
            "use_thinking": self._effective_use_thinking(profile),
            "step_timeout": self._effective_step_timeout(),
            "llm_timeout": self._effective_llm_timeout(),
            "directly_open_url": getattr(self.cfg, "directly_open_url", None),
            "final_response_after_failure": profile.get("final_response_after_failure", getattr(self.cfg, "final_response_after_failure", None)),
            "save_conversation_path": getattr(self.cfg, "save_conversation_path", None),
            "available_file_paths": getattr(self.cfg, "available_file_paths", None),
            "sensitive_data": getattr(self.cfg, "sensitive_data", None),
            "extend_system_message": getattr(self.cfg, "extend_system_message", None),
            "override_system_message": getattr(self.cfg, "override_system_message", None),
            "initial_actions": self._resolve_initial_actions(prompt),
            "generate_gif": getattr(self.cfg, "generate_gif", None),
            "calculate_cost": getattr(self.cfg, "calculate_cost", None),
        }
        for key, value in base_kwargs.items():
            if value is not None:
                agent_kwargs[key] = value
        sig = None
        with contextlib.suppress(Exception):
            sig = inspect.signature(Agent)
        params = set(sig.parameters) if sig else set()
        accepts_var_kwargs = bool(sig and any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()))
        if "file_system_path" in params or accepts_var_kwargs:
            agent_kwargs.setdefault("file_system_path", self._session_agent_file_dir(session_id or "browser_use"))
        if "browser_session" in params:
            agent_kwargs["browser_session"] = browser_handle
        elif "browser" in params:
            agent_kwargs["browser"] = browser_handle
        else:
            agent_kwargs["browser_session"] = browser_handle
        return Agent(**agent_kwargs)

    async def _append_followup_task(self, state: BrowserConversationState, prompt: str) -> None:
        add_new_task = getattr(state.agent, "add_new_task", None)
        if callable(add_new_task):
            result = add_new_task(prompt)
            if asyncio.iscoroutine(result):
                await result
            return
        state.agent = await self._build_agent(prompt=prompt, llm=state.llm, browser_handle=state.browser, session_id=state.session_id)

    def _prepare_agent_task(self, prompt: str) -> str:
        base_prompt = str(prompt or "").strip()
        contract = """

[Browser action/schema contract]
- Return only actions supported by this browser runtime. Use `scroll` with `down` and `pages`; do not use `scroll_up`, `scroll_down`, `scroll_to_top`, or `scroll_to_bottom`.
- Do not emit `extract`, `extract_content`, `screenshot`, `observe`, or `inspect` actions; page state is observed automatically after actions.
- Unless the task explicitly requests file creation/editing, do not use `write_file`, `replace_file`, or `read_file`; return final content through `done`.
- When the requested work is complete, immediately call `done` and stop interacting with the page.
"""
        return base_prompt + contract

    def _resolve_initial_actions(self, prompt: str) -> Optional[list[dict[str, Any]]]:
        configured = getattr(self.cfg, "initial_actions", None)
        return configured if configured else None

    def _build_llm(self) -> Any:
        if getattr(self.cfg, "build_inner_llm", None) is not None:
            return self.cfg.build_inner_llm()
        if getattr(self.cfg, "build_model", None) is not None:
            return self.cfg.build_model()
        if getattr(self.cfg, "build_outer_model", None) is not None:
            return self.cfg.build_outer_model()
        raise RuntimeError("BrowserUseToolkitConfig 缺少可用的 LLM 构建器。")

    def _effective_step_timeout(self) -> int | None:
        """Do not inject the test_config step_timeout into Agent by default.
        Your current test_config contains step_timeout=120, which makes browser-use
        abort a step while it is still recovering from DOM/AXTree collection. The
        old agent effectively relied on browser-use's own defaults. Keep an escape
        hatch for debugging, but otherwise omit this parameter.
        """
        raw_env = os.environ.get("BROWSER_USE_STEP_TIMEOUT")
        if raw_env:
            with contextlib.suppress(Exception):
                return max(10, int(raw_env))
        return None

    def _effective_use_vision(self, profile: Dict[str, Any]) -> bool | None:
        raw_env = os.environ.get("BROWSER_USE_USE_VISION")
        if raw_env:
            return raw_env.strip().lower() in {"1", "true", "yes", "on"}
        if self._force_no_vision:
            return False
        configured = profile.get("use_vision", getattr(self.cfg, "use_vision", None))
        if configured is not None:
            return bool(configured)
        return False

    def _effective_use_thinking(self, profile: Dict[str, Any]) -> bool | None:
        raw_env = os.environ.get("BROWSER_USE_USE_THINKING")
        if raw_env:
            return raw_env.strip().lower() in {"1", "true", "yes", "on"}
        configured = profile.get("use_thinking", getattr(self.cfg, "use_thinking", None))
        if configured is not None:
            return bool(configured)
        return False

    def _effective_llm_timeout(self) -> int | None:
        raw_env = os.environ.get("BROWSER_USE_LLM_TIMEOUT") or os.environ.get("OPENAI_REQUEST_TIMEOUT")
        if raw_env:
            with contextlib.suppress(Exception):
                return max(15, int(float(raw_env)))
        configured = getattr(self.cfg, "llm_timeout", None)
        if configured is not None:
            return configured
        return 60

    def _effective_max_actions_per_step(self, profile: Dict[str, Any]) -> int | None:
        configured = profile.get("max_actions_per_step", getattr(self.cfg, "max_actions_per_step", None))
        if configured is None:
            return 3
        try:
            value = int(configured)
        except Exception:
            return configured
        return max(value, 3)

    def _get_model_profile(self) -> Dict[str, Any]:
        resolver = getattr(self.cfg, "get_model_profile", None)
        if callable(resolver):
            with contextlib.suppress(Exception):
                profile = resolver()
                if isinstance(profile, dict):
                    return profile
        return {
            "use_vision": getattr(self.cfg, "use_vision", None),
            "use_thinking": getattr(self.cfg, "use_thinking", None),
            "max_actions_per_step": getattr(self.cfg, "max_actions_per_step", None),
            "flash_mode": getattr(self.cfg, "flash_mode", None),
            "final_response_after_failure": getattr(self.cfg, "final_response_after_failure", None),
        }

    async def _call_factory(self, factory: Any, **kwargs: Any) -> Any:
        sig = None
        with contextlib.suppress(Exception):
            sig = inspect.signature(factory)
        filtered = {k: v for k, v in kwargs.items() if sig is None or k in sig.parameters}
        result = factory(**filtered)
        if asyncio.iscoroutine(result):
            return await result
        return result

    # -----------------------------
    # Generic completion probing
    # -----------------------------
    async def _probe_current_page_state(self, state: BrowserConversationState) -> Dict[str, Any]:
        """Best-effort page probe after normal finish or timeout.

        This is intentionally generic and site-agnostic. It does not know about Bilibili,
        Baidu, stocks, videos sites, etc. It only asks the current page for URL/title and
        HTML media element state.
        """
        agent = getattr(state, "agent", None)
        page = getattr(agent, "page", None) if agent is not None else None
        if page is None:
            for holder in (agent, getattr(agent, "browser_session", None), getattr(state, "browser", None)):
                if holder is None:
                    continue
                for attr in ("page", "current_page", "active_page"):
                    with contextlib.suppress(Exception):
                        candidate = getattr(holder, attr, None)
                        if callable(candidate):
                            candidate = candidate()
                            if asyncio.iscoroutine(candidate):
                                candidate = await candidate
                        if candidate is not None:
                            page = candidate
                            break
                if page is not None:
                    break

        if page is None:
            return {}
        out: Dict[str, Any] = {}
        with contextlib.suppress(Exception):
            out["url"] = str(getattr(page, "url", "") or "")
        with contextlib.suppress(Exception):
            title = page.title()
            out["title"] = await title if asyncio.iscoroutine(title) else title
        js = r"""
        () => {
          const videos = Array.from(document.querySelectorAll('video')).map((v, i) => ({
            index: i,
            src: v.currentSrc || v.src || '',
            paused: v.paused,
            ended: v.ended,
            currentTime: Number.isFinite(v.currentTime) ? v.currentTime : null,
            duration: Number.isFinite(v.duration) ? v.duration : null,
            readyState: v.readyState,
            muted: v.muted,
            width: v.videoWidth || v.clientWidth || 0,
            height: v.videoHeight || v.clientHeight || 0
          }));
          const active = document.activeElement;
          return {
            videos,
            activeElement: active ? {
              tag: active.tagName,
              type: active.getAttribute('type') || '',
              value: active.value || ''
            } : null,
            bodyText: (document.body && document.body.innerText || '').slice(0, 1200)
          };
        }
        """
        with contextlib.suppress(Exception):
            evaluated = page.evaluate(js)
            evaluated = await evaluated if asyncio.iscoroutine(evaluated) else evaluated
            if isinstance(evaluated, dict):
                out.update(evaluated)

        return out

    def _page_state_indicates_completion(self, page_state: Dict[str, Any] | None) -> bool:
        if not page_state:
            return False
        for video in page_state.get("videos") or []:
            if not isinstance(video, dict):
                continue
            current = video.get("currentTime")
            ready = video.get("readyState") or 0
            paused = video.get("paused")
            ended = video.get("ended")
            try:
                current_num = float(current or 0)
            except Exception:
                current_num = 0.0
            if ended:
                continue
            if paused is False and ready >= 2:
                return True
            if current_num >= 1.0 and ready >= 2:
                return True
        return False

    def _completion_text_from_page_state(self, page_state: Dict[str, Any], payload: Dict[str, Any]) -> str:
        title = page_state.get("title") or payload.get("last_title") or "当前页面"
        url = page_state.get("url") or payload.get("last_url") or ""
        videos = page_state.get("videos") or []
        video_desc = ""
        if videos:
            v = videos[0]
            video_desc = (
                f"；检测到 video 元素，paused={v.get('paused')}，"
                f"currentTime={v.get('currentTime')}，readyState={v.get('readyState')}"
            )
        return f"浏览器已到达可验证的目标页面：{title}。{url}{video_desc}"

    def _is_action_only_result(self, payload: Dict[str, Any]) -> bool:
        final = self._compact_text(payload.get("final_result"), 160).lower()
        if not final:
            return False
        action_prefixes = (
            "sent keys", "typed", "clicked", "waited", "navigated",
            "发送", "输入", "点击", "等待", "已输入", "已点击",
        )
        if final.startswith(action_prefixes):
            return True
        has_content = bool(payload.get("extracted_content") or payload.get("outputs"))
        return (not has_content) and len(final) <= 80

    def _partial_progress_text(self, payload: Dict[str, Any]) -> str:
        last_url = payload.get("last_url") or self._last_nonempty(payload.get("urls"))
        actions = self._summarize_actions(payload.get("actions") or [], limit=4)
        parts = ["浏览器已有进度，但尚未达到可验证的任务完成状态。"]
        if last_url:
            parts.append(f"当前页面：{last_url}")
        if actions:
            parts.append("已执行动作：" + "；".join(a.lstrip("- ") for a in actions))
        return "\n".join(parts)


    # -----------------------------
    # History / formatting
    # -----------------------------
    async def _collect_agent_snapshot(self, agent_instance: Any) -> Dict[str, Any]:
        page = getattr(agent_instance, "page", None)
        url = None
        title = None
        if page is not None:
            with contextlib.suppress(Exception):
                url = getattr(page, "url", None)
            with contextlib.suppress(Exception):
                maybe_title = page.title()
                title = await maybe_title if asyncio.iscoroutine(maybe_title) else maybe_title

        history = getattr(agent_instance, "history", None)
        urls = None
        if history is not None:
            with contextlib.suppress(Exception):
                urls = history.urls()
                if not url and urls:
                    url = urls[-1]

        return {"step": self._infer_step_no(agent_instance), "url": url, "title": title, "urls": urls}

    def _history_to_result(self, history: Any) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        with contextlib.suppress(Exception):
            result["final_result"] = history.final_result()
        with contextlib.suppress(Exception):
            result["urls"] = history.urls()
        with contextlib.suppress(Exception):
            result["actions"] = self._jsonable(history.model_actions())
        with contextlib.suppress(Exception):
            result["thoughts"] = self._jsonable(history.model_thoughts())
        with contextlib.suppress(Exception):
            result["outputs"] = self._jsonable(history.model_outputs())
        with contextlib.suppress(Exception):
            result["extracted_content"] = self._jsonable(history.extracted_content())
        if not result:
            result["raw"] = self._jsonable(history)
        return result

    def _timeout_payload(self, state: BrowserConversationState) -> Dict[str, Any]:
        agent = getattr(state, "agent", None)
        history = getattr(agent, "history", None) if agent is not None else None
        if history is None:
            return {"last_url": state.last_url}
        with contextlib.suppress(Exception):
            payload = self._history_to_result(history)
            if state.last_url and not payload.get("last_url"):
                payload["last_url"] = state.last_url
            return payload
        return {"last_url": state.last_url}

    def _infer_step_no(self, agent_instance: Any) -> int:
        for attr in ("n_steps", "step_num", "current_step", "step_number", "step"):
            value = getattr(agent_instance, attr, None)
            if isinstance(value, int):
                return value
        history = getattr(agent_instance, "history", None)
        if history is not None:
            with contextlib.suppress(Exception):
                actions = history.model_actions()
                if actions:
                    return len(actions)
        return 0

    def _stringify_content(self, event: BrowserAgentEvent) -> str:
        if isinstance(event.content, str):
            return event.content
        content = self._jsonable(event.content)
        if isinstance(content, dict):
            if event.event_type == "result":
                return self._format_result_content(content)
            if event.event_type == "status":
                return self._format_status_content(content)
            if event.event_type in {"error", "cancelled"}:
                return self._format_error_content(event.event_type, content)
        return json.dumps(content, ensure_ascii=False)

    def _format_status_content(self, content: Dict[str, Any]) -> str:
        message = str(content.get("message") or "browser-use 已启动")
        task_id = content.get("task_id")
        session_id = content.get("session_id")
        suffix = []
        if task_id:
            suffix.append(f"task={task_id}")
        if session_id:
            suffix.append(f"session={session_id}")
        if content.get("browser_reused"):
            suffix.append("browser reused")
        if content.get("agent_reused"):
            suffix.append("agent reused")
        return f"🚀 {message}" + (f" ({', '.join(suffix)})" if suffix else "")

    def _format_error_content(self, event_type: str, content: Dict[str, Any]) -> str:
        title = "⚠️ 浏览器任务已取消" if event_type == "cancelled" else "❌ 浏览器任务出错"
        message = content.get("message") or content.get("error") or content.get("final_result") or content
        lines = [title, f"- 说明：{self._compact_text(message, 360)}"]
        last_url = content.get("last_url") or self._last_nonempty(content.get("urls"))
        if last_url:
            lines.append(f"- 当前页面：{last_url}")
        return "\n".join(lines)

    def _format_result_content(self, content: Dict[str, Any]) -> str:
        lines = ["✅ 浏览器任务已完成" if content.get("success", True) else "📌 浏览器任务结果"]

        final_result = content.get("final_result")
        if final_result:
            lines.append(f"\n**结果**：{self._compact_text(final_result, 800)}")

        last_url = content.get("last_url") or self._last_nonempty(content.get("urls"))
        if last_url:
            lines.append(f"\n**当前页面**：{last_url}")

        urls = self._unique_nonempty(content.get("urls"))
        if urls:
            lines.append("\n**访问轨迹**：")
            for i, url in enumerate(urls[:5], 1):
                lines.append(f"{i}. {url}")
            if len(urls) > 5:
                lines.append(f"... 另有 {len(urls) - 5} 个 URL")

        actions = content.get("actions") or []
        action_lines = self._summarize_actions(actions)
        if action_lines:
            lines.append("\n**已执行动作**：")
            lines.extend(action_lines)

        if not final_result and not urls and not action_lines:
            lines.append("\n" + json.dumps(content, ensure_ascii=False))

        return "\n".join(lines)

    def _summarize_actions(self, actions: Any, limit: int = 6) -> list[str]:
        if not isinstance(actions, list):
            return []
        lines: list[str] = []
        for item in actions[:limit]:
            if not isinstance(item, dict):
                continue
            action = {k: v for k, v in item.items() if k != "interacted_element"}
            if not action:
                continue
            name, payload = next(iter(action.items()))
            if isinstance(payload, dict):
                if name == "navigate":
                    desc = payload.get("url") or payload
                elif name == "click":
                    desc = f"index={payload.get('index')}" if payload.get("index") is not None else payload
                elif name == "input":
                    desc = f"index={payload.get('index')}, text={self._compact_text(payload.get('text'), 80)}"
                else:
                    desc = self._compact_text(payload, 120)
            else:
                desc = self._compact_text(payload, 120)
            lines.append(f"- {name}: {desc}")
        if len(actions) > limit:
            lines.append(f"- ... 另有 {len(actions) - limit} 个动作")
        return lines

    def _unique_nonempty(self, values: Any) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        if not isinstance(values, list):
            return result
        for value in values:
            text = str(value or "").strip()
            if text and text not in seen:
                seen.add(text)
                result.append(text)
        return result

    def _last_nonempty(self, values: Any) -> str:
        if not isinstance(values, list):
            return ""
        for value in reversed(values):
            text = str(value or "").strip()
            if text:
                return text
        return ""

    def _compact_text(self, value: Any, limit: int = 240) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            with contextlib.suppress(Exception):
                value = json.dumps(self._jsonable(value), ensure_ascii=False)
            if not isinstance(value, str):
                value = str(value)
        value = " ".join(value.split())
        return value[: limit - 3] + "..." if len(value) > limit else value

    def _jsonable(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {str(k): self._jsonable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._jsonable(v) for v in value]
        if is_dataclass(value):
            return self._jsonable(asdict(value))
        if hasattr(value, "model_dump"):
            with contextlib.suppress(Exception):
                return self._jsonable(value.model_dump())
        if hasattr(value, "dict"):
            with contextlib.suppress(Exception):
                return self._jsonable(value.dict())
        if hasattr(value, "__dict__"):
            with contextlib.suppress(Exception):
                return self._jsonable(vars(value))
        return str(value)

    def _ctx_value(self, ctx: Optional[RunContext], name: str) -> Optional[Any]:
        if ctx is None:
            return None
        if isinstance(ctx, dict):
            return ctx.get(name)
        with contextlib.suppress(Exception):
            return getattr(ctx, name)
        return None

    def _json_loads_maybe(self, raw: Any) -> dict:
        if isinstance(raw, dict):
            return raw
        if not isinstance(raw, str):
            return {}
        with contextlib.suppress(Exception):
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        return {}

    def _should_reset_session(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return any(token in message for token in ("browser closed", "target closed", "connection closed", "context closed"))
