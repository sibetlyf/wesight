import os
import tempfile
import shutil
import pytest
import uuid
from core.tools.web_tool.web_tool import WebTool
from configs.web_tool import WebToolConfig

from agno.agent import Agent
from agno.models.openai import OpenAILike
from agno.run import RunContext
from agno.run.agent import ToolCallCompletedEvent
from unittest.mock import MagicMock
from protocol import EnVar


@pytest.fixture
def workspace_env(workspace_prepare):
    """从环境变量获取工作目录信息"""
    envar = EnVar.from_env()
    yield {
        "workspace": envar.workspace,
        "runspace": envar.runspace,
        "userspace": envar.userspace,
        "sessionspace": envar.sessionspace,
    }


@pytest.fixture
def web_tools(workspace_env):
    """创建 WebTool 实例"""
    cfg = WebToolConfig()
    envar = EnVar.from_env()
    yield WebTool(cfg=cfg, envar=envar)


@pytest.mark.asyncio
async def test_agno_agent_triggers_web_tools(workspace_env):
    """测试 agno agent 能够触发 WebTool 工具"""
    cfg = WebToolConfig()
    envar = EnVar.from_env()
    web_tools = WebTool(cfg=cfg, envar=envar)

    ag = Agent(
        model=OpenAILike(
            id="qwen3-next-80b",
            api_key="TEST_API_KEY",
            base_url="https://example.com/v1"
        ),
        tools=[web_tools],
        instructions="你很聪明",
        user_id="user1",
        debug_mode=True,
        stream_events=True,
        telemetry=False
    )

    session_id = str(uuid.uuid4())
    tool_called = False

    query = """产品名称：moma coze 豆包 文心一言 智谱 kimi 腾讯元宝
结果通过率（人工）：66.67% 58.33% 58.33% 66.67% 41.67% 58.33% 58.33%
任务通过数量 8 7 7 8 5 7 7
任务总数 12

帮我画个图，横向的条形图，纵坐标是产品名称，横坐标是结果通过率（人工）， 从高到低排序，moma放在第一个， 需要在每个条上加备注信息, 任务通过数/任务总数，如 （8/12）"""
    async for event in ag.arun(
        input=query,
        session_id=session_id,
        session_state={},
        stream=True,
        yield_run_output=True
    ):
        if isinstance(event, ToolCallCompletedEvent):
            tool_called = True

    assert tool_called, "WebTools 工具未被触发"
