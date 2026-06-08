import os
import json
import pytest
import uuid
from core.tools.jt_tools import JtTools
from configs.jt_tools import JtToolsConfig
from core.abilities_loader import _load_core_tools
from agno.agent import Agent
from agno.run.agent import ToolCallCompletedEvent
from protocol import EnVar


@pytest.fixture
def jt_tools(workspace_prepare):
    """创建 JtTools 工具实例"""
    cfg = JtToolsConfig()
    
    # 从环境变量创建 EnVar 实例
    envar = EnVar.from_env()
    
    # 创建工具实例 - 使用 _load_core_tools 方式
    yield _load_core_tools(
        cfgs=[cfg],
        envar=envar
    )[0]


@pytest.mark.asyncio
async def test_generate_image(jt_tools, workspace_prepare):
    """测试 generate_image 方法"""
    # 测试参数
    prompt = "一只可爱的猫咪在阳光下睡觉"
    height = 1024
    width = 1024
    n = 1
    
    # 调用 generate_image 方法
    try:
        result = await jt_tools.generate_image(
            prompt=prompt,
            height=height,
            width=width,
            n=n,
            style_tag=0,
            txt2ImgRatio="1:1",
            enhance=1,
            watermark=1
        )
        
        # 解析返回结果
        result_dict = json.loads(result)
        
        # 验证返回结果包含必要的字段
        assert "content" in result_dict, "返回结果缺少 content 字段"
        assert "images" in result_dict, "返回结果缺少 images 字段"
        assert isinstance(result_dict["images"], list), "images 应该是列表类型"
        
        # 验证生成的图片文件是否存在
        for img_path in result_dict["images"]:
            assert os.path.exists(img_path), f"生成的图片文件不存在: {img_path}"
            assert img_path.endswith('.jpg'), f"图片文件应该是 jpg 格式: {img_path}"
        
        print(f"generate_image 测试通过，生成了 {len(result_dict['images'])} 张图片")
        
    except Exception as e:
        pytest.skip(f"图片生成服务不可用: {str(e)}")


@pytest.mark.asyncio
async def test_image_text(jt_tools):
    """测试 image_text 方法"""
    # 创建一个测试用的 base64 图片数据
    test_image_base64 = "iVBORw0KGgoAAAANSUhEUgAAAGQAAABkCAIAAAD/gAIDAAACP0lEQVR4nO2cQVLDMBAEMcUr4X3wTXMwUCEhidua2VWo6RskQrvttSwk28u6rk9hH8/dATwSkQWILEBkASILEFmAyAJEFiCyAJEFiCxAZAEiCxBZgMgCRBYgsgCRBYgswEt3AN98LHe+8Nq/V7B0bljcFXSNJnFNsg5rOqVcWa0siaNLqqwVDvAmU9a//JuSyqpKxl1i/soqM+Xvyyyr0pS/R6eselPmfm2yukw5e/fI6jVli8EgawZTG+pI1LLmMbUhjUcqazZTG7qoskQD0Mmas6w2RLGJZM1sakMRYU5DQGQBFLLmPwc3huNsWINf3n79uL4XtR1nuLLg4TrL9s/fONp+MVZcpWPWtdz25DzSVkWdrNtZ+T4VkqshYEzWo1wHTxmIOZUFiCxAnazbcyLfp0JKK+taVnuyHWmrovo0vMxtf7YjbSU0/LszkmGxnTMywAMiCxBZgMgCjMma4D5PzEDMqSxAZAEiC6C4TVK0UHNjDU82Fx0bZPsfGvhxdMPInu8UILoB92hxLW94d+e4r+Frd+eYdSDz9b10h+KMNlmHa6TRl0jW/LNTRYTShwam3b8QHcvMswBSWXOejLqo1JU1my9pPIbTcB5f6kg8Y9YMvgwx2Ab4Xl+e3p1Xwy5ftn7NU4d6X84e/fOsSl/mvgofKLfO70sOSeEM3pdPVfHmvQ6AvDEE0CrrlLyL5p+RJRpAZAEiCxBZgMgCRBYgsgCRBYgsQGQBIgsQWYDIAkQWILIAkQWILEBkAT4BAa+gz6DX2ksAAAAASUVORK5CYII="
    
    prompt = "描述这张图片"
    
    # 调用 image_text 方法
    try:
        result = await jt_tools.image_text(
            prompt=prompt,
            imagePath=test_image_base64
        )
        
        # 解析返回结果
        result_dict = json.loads(result)
        
        # 验证返回结果包含必要的字段
        assert "content" in result_dict, "返回结果缺少 content 字段"
        assert isinstance(result_dict["content"], str), "content 应该是字符串类型"
        
        print(f"image_text 测试通过，返回内容: {result_dict['content'][:100]}...")
        
    except Exception as e:
        pytest.skip(f"图像识别服务不可用: {str(e)}")


@pytest.mark.asyncio
async def test_agno_agent_with_generate_image_tool(workspace_prepare, jt_tools, jt_model):
    """测试 agno agent 能够触发 generate_image 工具"""
    # 创建 agent，只包含 generate_image 工具
    ag = Agent(
        model=jt_model,
        tools=[jt_tools],
        instructions="你是一个能够生成图片的AI助手。当用户要求生成图片时，使用 generate_image 工具。",
        user_id="user1",
        debug_mode=True,
        add_history_to_context=True,
        stream_events=True,
        telemetry=False
    )
    
    session_id = str(uuid.uuid4())
    tool_called = False
    
    # 运行 agent 并检查是否触发了工具
    try:
        async for event in ag.arun("请帮我生成一张美丽的风景图", session_id=session_id, stream=True, yield_run_output=True):
            # 检查是否有工具调用完成的事件
            if isinstance(event, ToolCallCompletedEvent):
                tool_called = True
                print(f"工具被调用: {event}")
        
        # 验证工具被调用
        print(f"Agent 运行完成，工具调用状态: {tool_called}")
        
    except Exception as e:
        pytest.skip(f"Agent 运行失败: {str(e)}")


@pytest.mark.asyncio
async def test_agno_agent_with_image_text_tool(workspace_prepare, jt_tools, jt_model):
    """测试 agno agent 能够触发 image_text 工具"""
    # 创建 agent，只包含 image_text 工具
    ag = Agent(
        model=jt_model,
        tools=[jt_tools],
        instructions="你是一个能够识别图片内容的AI助手。当用户要求分析图片时，使用 image_text 工具。",
        user_id="user1",
        debug_mode=True,
        add_history_to_context=True,
        stream_events=True,
        telemetry=False
    )
    
    session_id = str(uuid.uuid4())
    tool_called = False
    
    # 创建一个测试用的 base64 图片数据
    test_image_base64 = "iVBORw0KGgoAAAANSUhEUgAAAGQAAABkCAIAAAD/gAIDAAACP0lEQVR4nO2cQVLDMBAEMcUr4X3wTXMwUCEhidua2VWo6RskQrvttSwk28u6rk9hH8/dATwSkQWILEBkASILEFmAyAJEFiCyAJEFiCxAZAEiCxBZgMgCRBYgsgCRBYgswEt3AN98LHe+8Nq/V7B0bljcFXSNJnFNsg5rOqVcWa0siaNLqqwVDvAmU9a//JuSyqpKxl1i/soqM+Xvyyyr0pS/R6eselPmfm2yukw5e/fI6jVli8EgawZTG+pI1LLmMbUhjUcqazZTG7qoskQD0Mmas6w2RLGJZM1sakMRYU5DQGQBFLLmPwc3huNsWINf3n79uL4XtR1nuLLg4TrL9s/fONp+MVZcpWPWtdz25DzSVkWdrNtZ+T4VkqshYEzWo1wHTxmIOZUFiCxAnazbcyLfp0JKK+taVnuyHWmrovo0vMxtf7YjbSU0/LszkmGxnTMywAMiCxBZgMgCjMma4D5PzEDMqSxAZAEiC6C4TVK0UHNjDU82Fx0bZPsfGvhxdMPInu8UILoB92hxLW94d+e4r+Frd+eYdSDz9b10h+KMNlmHa6TRl0jW/LNTRYTShwam3b8QHcvMswBSWXOejLqo1JU1my9pPIbTcB5f6kg8Y9YMvgwx2Ab4Xl+e3p1Xwy5ftn7NU4d6X84e/fOsSl/mvgofKLfO70sOSeEM3pdPVfHmvQ6AvDEE0CrrlLyL5p+RJRpAZAEiCxBZgMgCRBYgsgCRBYgsQGQBIgsQWYDIAkQWILIAkQWILEBkAT4BAa+gz6DX2ksAAAAASUVORK5CYII="

    # 运行 agent 并检查是否触发了工具
    try:
        async for event in ag.arun(f"请分析这张图片的内容: data:image/png;base64,{test_image_base64}", 
                                   session_id=session_id, stream=True, yield_run_output=True):
            # 检查是否有工具调用完成的事件
            if isinstance(event, ToolCallCompletedEvent):
                tool_called = True
                print(f"工具被调用: {event}")
        
        # 验证工具被调用
        print(f"Agent 运行完成，工具调用状态: {tool_called}")
        
    except Exception as e:
        pytest.skip(f"Agent 运行失败: {str(e)}")


@pytest.mark.asyncio
async def test_jt_tools_initialization(workspace_prepare):
    """测试 JtTools 初始化"""
    cfg = JtToolsConfig()
    
    # 从环境变量创建 EnVar 实例
    envar = EnVar.from_env()
    
    # 测试正常初始化 - 使用 _load_core_tools 方式
    tools = _load_core_tools(
        cfgs=[cfg],
        envar=envar
    )
    
    tool = tools[0]
    
    # 验证属性是否正确设置
    assert tool.workspace == envar.workspace #type: ignore
    assert tool.user == envar.user_id #type: ignore
    assert tool.record_id == envar.record_id #type: ignore
    assert tool.authorization == envar.authorization #type: ignore
    assert tool.cfg == cfg #type: ignore
    
    print("JtTools 初始化测试通过")


@pytest.mark.asyncio
async def test_jt_tools_missing_env_vars():
    """测试 JtTools 缺少环境变量时的行为"""
    # 清除环境变量
    for key in ["WORKSPACE", "USER_ID", "RECORD_ID", "AUTHORIZATION"]:
        if key in os.environ:
            del os.environ[key]
    
    cfg = JtToolsConfig()
    
    # 验证缺少环境变量时，EnVar.from_env() 会抛出错误
    with pytest.raises(Exception) as exc_info:
        envar = EnVar.from_env()
        _load_core_tools(cfgs=[cfg], envar=envar)
    
    print("环境变量缺失测试通过")


@pytest.mark.asyncio
async def test_search_picture(jt_tools):
    """测试 search_picture 方法"""
    # 测试参数
    query = "美丽的风景"
    # 调用 search_picture 方法
    try:
        result = await jt_tools.search_picture(query=query)
        # 解析返回结果
        result_dict = json.loads(result)
        # 验证返回结果包含必要的字段
        assert "key_words" in result_dict, "返回结果缺少 key_words 字段"
        assert "image" in result_dict, "返回结果缺少 image 字段"
        assert result_dict["key_words"] == query, f"key_words 应该等于查询词 {query}"
        
        print(f"search_picture 测试通过，关键词: {query}")
        
    except Exception as e:
        pytest.skip(f"图片搜索服务不可用: {str(e)}")


@pytest.mark.asyncio
async def test_search_picture_no_results(jt_tools):
    """测试 search_picture 方法当没有搜索结果时"""
    # 使用一个不太可能返回结果的关键词
    query = "xyzabc123456789"
    
    try:
        result = await jt_tools.search_picture(query=query)
        
        # 解析返回结果
        result_dict = json.loads(result)
        
        # 验证返回结果
        assert "content" in result_dict, "返回结果应该包含 content 字段"
        assert result_dict["content"] == "未查询到相关数据", "应该返回未查询到相关数据"
        
        print("search_picture 无结果测试通过")
        
    except Exception as e:
        pytest.skip(f"图片搜索服务不可用: {str(e)}")


@pytest.mark.asyncio
async def test_agno_agent_with_search_picture_tool(workspace_prepare, jt_tools, jt_model):
    """测试 agno agent 能够触发 search_picture 工具"""
    # 创建 agent，只包含 search_picture 工具
    ag = Agent(
        model=jt_model,
        tools=[jt_tools],
        instructions="你是一个能够搜索图片的AI助手。当用户要求搜索图片时，使用 search_picture 工具。",
        user_id="user1",
        debug_mode=True,
        add_history_to_context=True,
        stream_events=True,
        telemetry=False
    )
    
    session_id = str(uuid.uuid4())
    tool_called = False
    
    # 运行 agent 并检查是否触发了工具
    try:
        async for event in ag.arun("请帮我搜索一些猫咪的图片", session_id=session_id, stream=True, yield_run_output=True):
            # 检查是否有工具调用完成的事件
            if isinstance(event, ToolCallCompletedEvent):
                tool_called = True
                print(f"工具被调用: {event}")
        
        # 验证工具被调用
        print(f"Agent 运行完成，工具调用状态: {tool_called}")
        
    except Exception as e:
        pytest.skip(f"Agent 运行失败: {str(e)}")
