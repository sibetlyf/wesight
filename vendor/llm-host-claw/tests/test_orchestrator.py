import pytest
from protocol import ExtraInfo
from core.orchestrator import Orchestrator
import os


def tree_workspace():
    # shell tree打印一下workspace路径结构
    os.system("tree -a {}".format(os.environ["WORKSPACE"]))


@pytest.mark.asyncio
async def test_orchestrator_base(langfuse_fixture, orchestrator_ready):
    # 测试 Orchestrator 类
    orchestrator: Orchestrator = orchestrator_ready
    tree_workspace()
    extra = ExtraInfo()
    async for i in orchestrator.run(
        "我要写一篇AI在教育领域的落地应用调研报告，包括但不限于智能教学、智能评估、智能推荐等，数据来源要有引用。",
        extra=extra,
    ):
        # async for i in orchestrator.run("查一下北京的天气情况", extra=extra):
        pass
    tree_workspace()


@pytest.mark.asyncio
async def test_orchestrator_tour(langfuse_fixture, orchestrator_ready):
    # 测试 Orchestrator 类
    orchestrator: Orchestrator = orchestrator_ready
    tree_workspace()
    extra = ExtraInfo()
    async for i in orchestrator.run(
        "分别制定北京到西安、上海、广州的旅游计划报表，最后再对比一下，下周一到下周五，全面一点",
        extra=extra,
    ):
        # async for i in orchestrator.run("查一下北京的天气情况", extra=extra):
        pass
    tree_workspace()


@pytest.mark.asyncio
async def test_orchestrator_ppt(langfuse_fixture, orchestrator_ready):
    # 测试 Orchestrator 类
    orchestrator: Orchestrator = orchestrator_ready
    tree_workspace()
    extra = ExtraInfo()
    async for i in orchestrator.run(
        "给我生成一个PPT，主题是当前AI的发展对高校学生的就业影响，不超过7页，要有相关图表数据分析和对比，数据来源要有引用",
        extra=extra,
    ):
        # async for i in orchestrator.run("查一下北京的天气情况", extra=extra):
        pass
    tree_workspace()


@pytest.mark.asyncio
async def test_orchestrator_simple(langfuse_fixture, orchestrator_ready):
    # 测试 Orchestrator 类
    orchestrator: Orchestrator = orchestrator_ready
    tree_workspace()
    extra = ExtraInfo()
    async for i in orchestrator.run("雷军年龄多大了，看看今天的天气", extra=extra):
        # async for i in orchestrator.run("查一下北京的天气情况", extra=extra):
        pass
    tree_workspace()


@pytest.mark.asyncio
async def test_orchestrator_error(langfuse_fixture, orchestrator_ready):
    # 测试 Orchestrator 类
    orchestrator: Orchestrator = orchestrator_ready
    tree_workspace()
    extra = ExtraInfo()
    async for i in orchestrator.run("你是谁", extra=extra):
        # async for i in orchestrator.run("查一下北京的天气情况", extra=extra):
        pass
    tree_workspace()
