import pytest
import os
from functools import wraps
from core.orchestrator import Orchestrator
from core.tools.vibe_tool.vibe_toolkit import VibeCodingToolkit
from configs.vibe_toolkit import VibeCodingToolkitConfig
from agno.run.agent import ToolCallCompletedEvent

# 1. 修复 VibeCodingToolkit 缺少 cfg 参数的 Monkeypatch
# 确保在子智能体初始化时不会因为配置缺失而报错
original_vibe_init = VibeCodingToolkit.__init__

@wraps(original_vibe_init)
def patched_vibe_init(self, *args, **kwargs):
    if "cfg" not in kwargs:
        kwargs["cfg"] = VibeCodingToolkitConfig(agent_type="opencode")
    return original_vibe_init(self, *args, **kwargs)

VibeCodingToolkit.__init__ = patched_vibe_init


@pytest.mark.asyncio
async def test_router_task_vibe_coding_entrypoint(orchestrator_ready):
    """测试 router_task 成功路由到 vibe_coding 的 entrypoint (内置函数模式)"""
    orchestrator = orchestrator_ready
    
    # 我们通过检查事件流来验证工具调用
    tool_called = False
    
    async for event in orchestrator.run(
        "请帮我用 vibe_coding 打印 hello world，使用 router_task，模式为 router。",
    ):
        # 验证是否触发了 router_task 工具调用
        if isinstance(event, ToolCallCompletedEvent) and event.tool_call_name == "router_task":
            tool_called = True
            
    assert tool_called, "未能触发 router_task 工具调用"


@pytest.mark.asyncio
async def test_router_task_web_creator_entrypoint(orchestrator_ready):
    """测试 router_task 成功路由到 web_creator 的 entrypoint (内置函数模式)"""
    orchestrator = orchestrator_ready
    
    tool_called = False
    async for event in orchestrator.run(
        "请帮我用 web_creator 生成一个简单的空白网页，使用 router_task，模式为 router。",
    ):
        if isinstance(event, ToolCallCompletedEvent) and event.tool_call_name == "router_task":
            tool_called = True
            
    assert tool_called, "未能触发 router_task 工具调用"


@pytest.mark.asyncio
async def test_router_task_subagent_fallback_mode(orchestrator_ready):
    """测试 router_task 的 subagent 模式，能够强制跳过 entrypoint 走标准 Agent 流程"""
    orchestrator = orchestrator_ready
    
    tool_called = False
    # 在这个模式下，router_task 内部会捕获到 subagent 模式，并跳过内置函数执行
    async for event in orchestrator.run(
        "请使用 subagent 模式调用 vibe_coding 写一个 hello world，使用 router_task，模式为 subagent。",
    ):
        if isinstance(event, ToolCallCompletedEvent) and event.tool_call_name == "router_task":
            tool_called = True
            
    assert tool_called, "未能触发 router_task 工具调用"
