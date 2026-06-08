import pytest
import pytest_asyncio
import os
import yaml
from functools import wraps
from typing import Optional, List
from protocol import ExtraInfo, EnVar
from core.orchestrator import Orchestrator
from configs import OrchestratorConfig
from core.tools.vibe_tool.vibe_toolkit import VibeCodingToolkit
from configs.vibe_toolkit import VibeCodingToolkitConfig
from agno.run.agent import ToolCallCompletedEvent
from agno.models.base import Model
from agno.session.summary import SessionSummaryManager
from agno.compression.manager import CompressionManager


async def assert_tool_call(orchestrator, prompt, expected_tool):
    tool_called = False
    async for event in orchestrator.run(prompt, extra=ExtraInfo()):
        if isinstance(event, ToolCallCompletedEvent):
            tool_name = getattr(event, "tool_call_name", None)
            if not tool_name and getattr(event, "tool", None):
                tool_name = getattr(event.tool, "name", None)
            if not tool_name and getattr(event, "tool", None):
                tool_name = getattr(event.tool, "tool_name", None)
            if tool_name == expected_tool:
                tool_called = True
    assert tool_called, f"Failed to trigger {expected_tool}"


@pytest_asyncio.fixture
async def custom_vibe_orchestrator(workspace_prepare):
    # Patch CustomSessionManager __init__
    from lib.session_manager import CustomSessionManager

    def patched_session_init(
            self,
            model: Optional[Model] = None,
            session_summary_prompt: Optional[str] = None,
            summary_request_message: str = 'Provide the summary of the conversation.',
            summaries_updated: bool = False,
            last_n_runs: Optional[int] = None,
            conversation_limit: Optional[int] = None,
            num_context_windows: Optional[int] = None,
    ):
        SessionSummaryManager.__init__(
            self,
            model=model,
            session_summary_prompt=session_summary_prompt,
            summary_request_message=summary_request_message,
            summaries_updated=summaries_updated,
            last_n_runs=last_n_runs,
            conversation_limit=conversation_limit,
        )
        self.num_context_windows = num_context_windows

    CustomSessionManager.__init__ = patched_session_init

    # Patch CustomCompressionManager __init__
    from lib.compression_manager import CustomCompressionManager

    def patched_compression_init(
            self,
            model: Optional[Model] = None,
            compress_tool_results: bool = True,
            compress_tool_results_limit: Optional[int] = None,
            compress_token_limit: Optional[int] = None,
            compress_tool_call_instructions: Optional[str] = None,
            stats: Optional[dict] = None,
            tool_keep_last: Optional[List[List[str]]] = None,
            tool_not_compress: Optional[List[str]] = None,
    ):
        CompressionManager.__init__(
            self,
            model=model,
            compress_tool_results=compress_tool_results,
            compress_tool_results_limit=compress_tool_results_limit,
            compress_token_limit=compress_token_limit,
            compress_tool_call_instructions=compress_tool_call_instructions,
            stats=stats if stats is not None else {},
        )
        self.tool_keep_last = tool_keep_last if tool_keep_last is not None else [["write_todo", "update_todo"]]
        self.tool_not_compress = tool_not_compress if tool_not_compress is not None else []

    CustomCompressionManager.__init__ = patched_compression_init

    with open("tests/test_config.yaml", 'r', encoding='utf-8') as f:
        test_config = yaml.safe_load(f)

    if "toolkits" in test_config:
        test_config["toolkits"] = [
            tk for tk in test_config["toolkits"]
            if "jt_tools" not in tk.get("target", "")
        ]

    config = OrchestratorConfig.model_validate(test_config)
    config.to_env()

    api_key = test_config["model"].get("api_key", "123")
    os.environ["AUTHORIZATION"] = api_key

    orch = Orchestrator()

    from agno.models.openai import OpenAILike
    pure_model = OpenAILike(
        id=test_config["model"].get("id", "deepseek-ai/DeepSeek-V4-Flash"),
        base_url=test_config["model"].get("base_url", "https://api.siliconflow.cn/v1"),
        api_key=api_key
    )

    orch.model = pure_model
    orch.agent.model = pure_model

    original_vibe_init = VibeCodingToolkit.__init__

    @wraps(original_vibe_init)
    def patched_vibe_init(self, *args, **kwargs):
        if "cfg" not in kwargs:
            kwargs["cfg"] = VibeCodingToolkitConfig(agent_type="opencode")
        return original_vibe_init(self, *args, **kwargs)

    VibeCodingToolkit.__init__ = patched_vibe_init

    # Export subagents to JSON for assign_task lookup
    from core.abilities_loader import load_subagent_cards
    envar = EnVar.from_env()
    subagent_dir = os.path.join(envar.workspace, "subagents")
    os.makedirs(subagent_dir, exist_ok=True)

    for card in load_subagent_cards(envar=envar):
        if card.name in ["vibe_coding", "web_creator"]:
            with open(os.path.join(subagent_dir, f"{card.name}.json"), "w", encoding="utf-8") as f:
                f.write(card.model_dump_json())

    yield orch

    # Close SQLite connection to release Windows file locks
    if hasattr(orch, "agent") and orch.agent.db:
        try:
            await orch.agent.db.close()
        except Exception:
            pass


# @pytest.mark.asyncio
# async def test_router_task_vibe_coding(custom_vibe_orchestrator):
#     await assert_tool_call(
#         custom_vibe_orchestrator,
#         "请帮我用 vibe_coding 打印 hello world，使用 router_task，模式为 router。",
#         "router_task"
#     )


@pytest.mark.asyncio
async def test_router_task_web_creator(custom_vibe_orchestrator):
    await assert_tool_call(
        custom_vibe_orchestrator,
        "请帮我用 web_creator 生成一个简单的网页，使用 router_task，模式为 router。",
        "router_task"
    )


# @pytest.mark.asyncio
# async def test_assign_task_vibe_coding(custom_vibe_orchestrator):
#     await assert_tool_call(
#         custom_vibe_orchestrator,
#         "请使用 assign_task QZ工具分配任务给 vibe_coding，让它写一个打印 hello world 的 Python 脚本。",
#         "assign_task"
#     )


@pytest.mark.asyncio
async def test_assign_task_web_creator(custom_vibe_orchestrator):
    await assert_tool_call(
        custom_vibe_orchestrator,
        "请使用 assign_task 工具分配任务给 web_creator，让它帮我生成一个展示天气预报的网页界面。",
        "assign_task"
    )
