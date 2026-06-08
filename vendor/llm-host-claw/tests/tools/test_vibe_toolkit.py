from pathlib import Path
import sys
import os
from protocol.envar import EnVar
# # 将项目根目录和 src 目录都加入路径，兼容直接 python 运行和 pytest 运行
# path_root = Path(__file__).parents[2]
# path_src = path_root / "src"
# sys.path.insert(0, str(path_src))
# sys.path.insert(0, str(path_root))

import pytest
import uuid
from core.tools.vibe_tool.vibe_toolkit import VibeCodingToolkit
from configs.vibe_toolkit import VibeCodingToolkitConfig
from agno.agent import Agent
from agno.run.agent import ToolCallCompletedEvent


@pytest.fixture
def vibe_toolkit_tools(workspace_prepare):
    # 创建配置
    cfg = VibeCodingToolkitConfig(agent_type="opencode")
    envar = EnVar.from_env()

    # 创建工具实例
    # 注意：VibeCodingToolkit 会尝试写配置文件，这里在测试环境下可能需要小心
    yield VibeCodingToolkit(cfg=cfg, envar=envar)


@pytest.mark.asyncio
async def test_agno_agent_with_vibe_tool(vibe_toolkit_tools, jt_model):
    """测试 agno agent 能够触发 vibe_coding 工具"""
    # 创建 agent
    # 这里直接使用 conftest.py 中的 jt_model 或者是 test_create_subagent_vibe.py 中的 inline model
    # 为了完全仿照，我们参考 test_create_subagent_vibe.py 的实现方式

    from agno.models.openai import OpenAILike

    model = OpenAILike(
        base_url="https://example.com/v1",
        id='qwen3.5-397B-fp8',
        api_key='TEST_API_KEY'
    )

    ag = Agent(
        model=model,
        tools=[vibe_toolkit_tools],
        instructions="你是一个资深的程序员，擅长使用各种编程工具来解决问题。",
        user_id="user1",
        debug_mode=True,
        add_history_to_context=True,
        stream_events=True,
        telemetry=False,
    )

    session_id = str(uuid.uuid4())
    tool_called = False

    # 运行 agent 并检查是否触发了工具
    # 这里的提问需要诱导 LLM 调用 vibe_coding 工具
    async for event in ag.arun(
        "写一个简单的React计算器，能够进行加减乘除运算",
        session_id=session_id,
        stream=True,
        yield_run_output=True,
        debug_mode=True,
    ):

        # 检查是否有工具调用完成的事件
        # VibeCodingToolkit 注册的函数名是 arun_prompt，但 Toolkit name 是 vibe_coding
        if isinstance(event, ToolCallCompletedEvent):
            tool_called = True

    # 验证工具被调用
    assert tool_called, "vibe_coding 工具未被触发"
