import pytest
import uuid
from core.tools.create_subagent import CreateSubagentTools
from configs.create_subagent import CreateSubagentConfig
from agno.agent import Agent
from agno.run.agent import ToolCallCompletedEvent


from core.abilities_loader import _load_core_tools


@pytest.fixture
def create_subagent_tools(workspace_prepare):
    # 创建配置
    cfg = CreateSubagentConfig(default_model="kimi-1.5")

    # 创建工具实例
    yield _load_core_tools(cfgs=[cfg])[0]


@pytest.mark.asyncio
async def test_agno_agent_with_tool(create_subagent_tools, jt_model):
    """测试 agno agent 能够触发 CreateSubagent 工具"""
    # 创建 agent
    ag = Agent(
        model=jt_model,
        tools=[create_subagent_tools],
        instructions="你很聪明",
        user_id="user1",
        debug_mode=True,
        add_history_to_context=True,
        stream_events=True,
        telemetry=False,
    )

    session_id = str(uuid.uuid4())
    tool_called = False

    # 运行 agent 并检查是否触发了工具
    async for event in ag.arun(
        "请创建一个专门写诗的智能体",
        session_id=session_id,
        stream=True,
        yield_run_output=True,
    ):

        # 检查是否有工具调用完成的事件
        if isinstance(event, ToolCallCompletedEvent):
            tool_called = True

    # 验证工具被调用
    assert tool_called, "工具未被触发"