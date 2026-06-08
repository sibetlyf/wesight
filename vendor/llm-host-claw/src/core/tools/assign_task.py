from agno.tools import Toolkit
from agno.agent import Agent
from typing import (
    Optional,
    AsyncGenerator,
    List,
    override,
    Callable,
    Dict,
    Any,
    Literal,
    cast,
)
import os
from pathlib import Path

from configs.assign_task import AssignTaskConfig
from configs.orchestrator import OrchestratorConfig
from moma_cli.sandbox import ensure_within_root, sandbox_enabled
from protocol.envar import EnVar
from protocol.external_agent_run_response_event import ExternalAgentRunResponseContentEvent
from protocol.subagent_card import SubAgentCard
from lib.compression_manager import CustomCompressionManager
from agno.skills import Skills
from agno.run import RunContext
from agno.exceptions import StopAgentRun
from agno.tools.function import UserInputField


class AssignTaskTools(Toolkit):
    _SUBAGENT_DIR = "subagents"
    _AGENT_DIR = [Path(__file__).parent.parent, Path(__file__).parent]

    @override
    def __init__(
        self,
        *,
        cfg: AssignTaskConfig,
        envar: EnVar,
    ):
        # 确保子智能体目录存在

        self.envar = envar
        self.cfg = cfg

        os.makedirs(f"{self.envar.workspace}/{self._SUBAGENT_DIR}", exist_ok=True)

        # --- 自动拼装 router_task 传参指南 ---
        from core.abilities_loader import load_subagent_cards

        cards: list[SubAgentCard] = load_subagent_cards(envar=self.envar)
        guide_lines = []
        for c in cards:
            agent_mode = getattr(getattr(c, "agent_mode", None), "mode", None)
            entrypoint = getattr(c, "entrypoint", None)
            entrypoint_params = getattr(c, "entrypoint_params", None)
            if agent_mode == "router" and entrypoint and entrypoint_params:
                # 生成参数说明，告知大模型可以直接作为关键字参数传递
                params_list = ", ".join([f"{k} (<{v}>)" for k, v in entrypoint_params.items()])
                guide_lines.append(f"        - {c.name}: 额外参数: {params_list}")

        if guide_lines:
            guide_str = (
                "\n\n        【动态路由传参指南】\n        当路由给以下 Agent 时，请直接在 router_task 中传递对应的命名参数：\n"
                + "\n".join(guide_lines)
            )

            # 由于 __doc__ 可能是只读的（在某些内置类型上），直接修改函数对象的 __doc__
            if hasattr(self.router_task, "__func__"):
                self.router_task.__func__.__doc__ = (
                    self.router_task.__func__.__doc__ or ""
                ) + guide_str
            else:
                self.router_task.__doc__ = (self.router_task.__doc__ or "") + guide_str
        # -----------------------------------

        super().__init__(
            tools=[self.assign_task, self.router_task],
            exclude_tools=self.cfg.exclude_tools,
            stop_after_tool_call_tools=["router_task"],
            show_result_tools=["router_task"],
        )

    async def assign_task(
        self, subagent_name: str, task: str
    ) -> AsyncGenerator[ExternalAgentRunResponseContentEvent, None]:
        """
        分配任务给指定的子智能体。
        - 你需要告知子智能体所有必要信息
        - 如果任务依赖本地文件，你需要在 task 中指定文件路径，要求子智能体去读取文件内容。

        args:
            subagent_name (str): 子智能体名称。
            task (str): 任务描述
        """

        # 从 subagents 文件夹载入指定智能体，载入所有工具并且实例化，然后运行
        subagent_dir = os.path.join(self.envar.workspace, self._SUBAGENT_DIR, f"{subagent_name}.json")  # type: ignore
        if sandbox_enabled():
            ensure_within_root(subagent_dir)
        if not os.path.exists(subagent_dir):
            raise ValueError(f"Subagent {subagent_name} not found")

        with open(subagent_dir, "r") as f:
            card: SubAgentCard = SubAgentCard.model_validate_json(f.read())

        agent = self._get_agent(card)
        parent_agent_id = f"orchestrator-{self.envar.record_id}"
        yield ExternalAgentRunResponseContentEvent(
            content=f"子智能体 {subagent_name} 已启动",
            metadata=cast(Any, {
                "event": "SubagentStarted",
                "source": "subagent",
                "subagent_name": subagent_name,
                "agent_id": agent.id,
                "agent_name": agent.name,
                "parent_agent_id": parent_agent_id,
                "mode": "subagent",
            }),
        )
        try:
            async for event in agent.arun(
                input=task,
                user=self.envar.user_id,
                session_id=f"{subagent_name}-{self.envar.record_id}",
                authorization=self.envar.authorization,
                stream=True,
            ):
                yield ExternalAgentRunResponseContentEvent(
                    content=event.content,
                    metadata=cast(Any, {
                        "event": getattr(event, "event", type(event).__name__),
                        "source": "subagent",
                        "subagent_name": subagent_name,
                        "agent_id": agent.id,
                        "agent_name": agent.name,
                        "parent_agent_id": parent_agent_id,
                        "mode": "subagent",
                        "raw_event": event.to_dict() if hasattr(event, "to_dict") else event,
                    }),
                )
        except Exception as e:
            yield ExternalAgentRunResponseContentEvent(
                content=f"任务在执行过程中出错: {str(e)}",
                metadata=cast(Any, {
                    "event": "RunError",
                    "source": "subagent",
                    "subagent_name": subagent_name,
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "parent_agent_id": parent_agent_id,
                    "mode": "subagent",
                    "raw_event": {"event": "RunError", "message": str(e), "agent_id": agent.id, "agent_name": agent.name},
                }),
            )
        finally:
            yield ExternalAgentRunResponseContentEvent(
                content=f"子智能体 {subagent_name} 的执行已经退出",
                metadata=cast(Any, {
                    "event": "SubagentCompleted",
                    "source": "subagent",
                    "subagent_name": subagent_name,
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "parent_agent_id": parent_agent_id,
                    "mode": "subagent",
                }),
            )

    async def router_task(
        self,
        run_context: RunContext,
        subagent_name: str,
        task: str,
        mode: Literal["subagent", "router"],
        **kwargs,
    ) -> AsyncGenerator[ExternalAgentRunResponseContentEvent, None]:
        """
        异步路由任务。将任务直接分配给专业的智能体执行，或直接调用内置函数。
        """
        from core.abilities_loader import load_subagent_cards
        import importlib
        import inspect
        import json

        # 搜索项目目录下所有可用的AgentCard
        card: Optional[SubAgentCard] = next(
            (
                c
                for c in load_subagent_cards(envar=self.envar)
                if c.name == subagent_name
            ),
            None,
        )
        if not card:
            raise ValueError(f"Subagent {subagent_name} not found")

        # 1. 如果是 router 模式且定义了 entrypoint，则优先执行内置函数
        card_entrypoint = getattr(card, "entrypoint", None)
        if mode == "router" and card_entrypoint:
            try:
                parts = card_entrypoint.split(".")
                # 如果倒数第二个是首字母大写，推测是类方法
                if len(parts) >= 3 and parts[-2][0].isupper():
                    module_path = ".".join(parts[:-2])
                    class_name = parts[-2]
                    method_name = parts[-1]
                    module = importlib.import_module(module_path)
                    cls = getattr(module, class_name)

                    # 尝试实例化（传递 workspace_path）
                    init_sig = inspect.signature(cls.__init__)
                    init_kwargs = {}
                    if "workspace_path" in init_sig.parameters:
                        init_kwargs["workspace_path"] = self.envar.workspace
                    if "envar" in init_sig.parameters:
                        init_kwargs["envar"] = self.envar

                    instance = cls(**init_kwargs)
                    func = getattr(instance, method_name)
                else:
                    module_path = ".".join(parts[:-1])
                    func_name = parts[-1]
                    module = importlib.import_module(module_path)
                    func = getattr(module, func_name)

                # 优先使用 kwargs 中的参数，如果没有则尝试解析 task (保持兼容)
                task_kwargs = dict(kwargs)

                # 兼容某些模型将额外参数封装在 kwargs 字段中的情况 (可能是字典或 JSON 字符串)
                if "kwargs" in task_kwargs:
                    extra = task_kwargs.pop("kwargs")
                    if isinstance(extra, dict):
                        task_kwargs.update(extra)
                    elif isinstance(extra, str):
                        try:
                            import json
                            parsed_extra = json.loads(extra)
                            if isinstance(parsed_extra, dict):
                                task_kwargs.update(parsed_extra)
                        except Exception:
                            pass

                if task and not any(k in task_kwargs for k in ["task", "prompt", "requirements"]):
                    # 如果 task 有内容且 kwargs 里没传主要输入字段，尝试解析 task
                    try:
                        import json
                        parsed = json.loads(task)
                        if isinstance(parsed, dict):
                            task_kwargs.update(parsed)
                    except Exception:
                        pass

                # 分析函数的参数并自动绑定
                sig = inspect.signature(func)
                call_kwargs = {}
                for param_name in sig.parameters:
                    if param_name in task_kwargs:
                        call_kwargs[param_name] = task_kwargs[param_name]
                    elif param_name == "run_context":
                        call_kwargs["run_context"] = run_context
                    elif param_name == "envar":
                        call_kwargs["envar"] = self.envar
                    elif param_name == "subagent_name":
                        call_kwargs["subagent_name"] = subagent_name
                    elif param_name in ["task", "prompt", "requirements"]:
                        # 如果 kwargs 里没有，则使用原始 task 字符串作为主输入
                        if param_name not in call_kwargs:
                            call_kwargs[param_name] = task_kwargs.get(param_name, task)

                # 执行内置函数，并保持流式返回格式一致
                async for event in func(**call_kwargs):
                    content = event.content if hasattr(event, "content") else str(event)
                    yield ExternalAgentRunResponseContentEvent(
                        content=content,
                        metadata=event,
                    )
            except Exception as e:
                import traceback

                traceback.print_exc()
                yield ExternalAgentRunResponseContentEvent(
                    content=f"内置函数执行出错: {str(e)}",
                    metadata=cast(Any, {
                        "event": "RunError",
                        "source": "subagent",
                        "subagent_name": subagent_name,
                        "parent_agent_id": f"orchestrator-{self.envar.record_id}",
                        "mode": mode,
                        "raw_event": {"event": "RunError", "message": str(e)},
                    }),
                )
            finally:
                yield ExternalAgentRunResponseContentEvent(
                    content=f"智能体 {subagent_name} 的执行已经退出",
                    metadata=cast(Any, {
                        "event": "SubagentCompleted",
                        "source": "subagent",
                        "subagent_name": subagent_name,
                        "parent_agent_id": f"orchestrator-{self.envar.record_id}",
                        "mode": mode,
                    }),
                )
            return

        # 2. 如果没有entrypoint，则创建 Agent
        agent = self._get_agent(card)
        parent_agent_id = f"orchestrator-{self.envar.record_id}"

        yield ExternalAgentRunResponseContentEvent(
            content=f"智能体 {subagent_name} 已启动",
            metadata=cast(Any, {
                "event": "SubagentStarted",
                "source": "subagent",
                "subagent_name": subagent_name,
                "agent_id": agent.id,
                "agent_name": agent.name,
                "parent_agent_id": parent_agent_id,
                "mode": mode,
            }),
        )

        try:
            async for event in agent.arun(
                input=task,
                user=self.envar.user_id,
                session_id=f"{subagent_name}-{self.envar.record_id}",
                authorization=self.envar.authorization,
                stream=True,
            ):
                yield ExternalAgentRunResponseContentEvent(
                    content=event.content,
                    metadata=cast(Any, {
                        "event": getattr(event, "event", type(event).__name__),
                        "source": "subagent",
                        "subagent_name": subagent_name,
                        "agent_id": agent.id,
                        "agent_name": agent.name,
                        "parent_agent_id": parent_agent_id,
                        "mode": mode,
                        "raw_event": event.to_dict() if hasattr(event, "to_dict") else event,
                    }),
                )
        except Exception as e:
            import traceback

            traceback.print_exc()
            yield ExternalAgentRunResponseContentEvent(
                content=f"任务在执行过程中出错: {str(e)}",
                metadata=cast(Any, {
                    "event": "RunError",
                    "source": "subagent",
                    "subagent_name": subagent_name,
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "parent_agent_id": parent_agent_id,
                    "mode": mode,
                    "raw_event": {"event": "RunError", "message": str(e), "agent_id": agent.id, "agent_name": agent.name},
                }),
            )

        finally:
            yield ExternalAgentRunResponseContentEvent(
                content=f"智能体 {subagent_name} 的执行已经退出",
                metadata=cast(Any, {
                    "event": "SubagentCompleted",
                    "source": "subagent",
                    "subagent_name": subagent_name,
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "parent_agent_id": parent_agent_id,
                    "mode": mode,
                }),
            )

    def _get_agent(self, card: SubAgentCard) -> Agent:
        """
        从智能体卡片中获取智能体实例。

        参数:
            card (SubAgentCard): 智能体卡片

        返回:
            Agent: 智能体实例
        """

        from core.abilities_loader import load_tools, load_skills

        try:
            orchestrator_cfg = OrchestratorConfig.from_env()
            
            tools: List[Toolkit] = load_tools(
                cfgs=orchestrator_cfg.toolkits,  # type: ignore
                envar=self.envar,
                exclude_tools=self.cfg.unauthorize_tools,
            )
            
            skills: Skills = load_skills(envar=self.envar)  # type: ignore

            cfg_model = cast(Any, self.cfg).model
            envar_api_key = cast(Any, self.envar).api_key
            model = cfg_model.get_model(
                api_key=envar_api_key,
            )
            
            compress_manager = CustomCompressionManager.from_config(
                cfg=cast(Any, self.cfg).compression_manager,
                api_key=envar_api_key,
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise

        return Agent(
            name=card.name,
            id=f"{card.name}-{self.envar.record_id}",
            model=model,
            add_datetime_to_context=True,
            add_history_to_context=True,
            description=card.description,
            instructions=card.instructions,
            compression_manager=compress_manager,
            tools=tools,
            skills=skills,
        )


# 用于检测Agent模式的钩子
async def assign_task_hook(
    run_context: RunContext,
    function_call: Callable,
    arguments: Dict[str, Any],
) -> AsyncGenerator:

    session_state = run_context.session_state or {}
    agent_mode = str(arguments.get("mode") or session_state.get("agent_mode") or "subagent")
    stop_after_agent_run = bool(session_state.get("stop_after_agent_run"))
    last_user_message = None

    try:
        if agent_mode == "router":
            # 获取最后一条用户输入
            for message in reversed(run_context.messages or []):
                if message.role == "user":
                    last_user_message = message.content
                    break

            if not last_user_message:
                raise ValueError("未找到用户输入，请补充内容")

            arguments["task"] = last_user_message
            generator = await function_call(**arguments)
            async for event in generator:
                yield event
        else:
            result = await function_call(**arguments)
            if hasattr(result, "__aiter__"):
                async for event in result:
                    yield event
            else:
                yield result

        if stop_after_agent_run:
            raise StopAgentRun(f"{last_user_message or ''}任务已完成，执行模式是{agent_mode}")
    except StopAgentRun:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise StopAgentRun(f"任务执行失败: {str(e)}")
