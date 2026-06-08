import pytest
import uuid
from core.tools.amap_tools import AmapTools
from configs.amap_tools import AmapToolConfig
from agno.agent import Agent
from agno.run.agent import ToolCallCompletedEvent
from protocol import EnVar

from core.abilities_loader import _load_core_tools


@pytest.fixture
def amap_tools(workspace_prepare):
    # 创建配置
    cfg = AmapToolConfig()
    
    # 从环境变量创建 EnVar 实例
    envar = EnVar.from_env()
    
    # 创建工具实例
    yield _load_core_tools(cfgs=[cfg], envar=envar)[0]


@pytest.mark.asyncio
async def test_search_poi(amap_tools):
    """测试关键词搜索功能"""
    result = await amap_tools.search_poi(keywords="天安门", city="北京市")
    print("Text search result:", result)
    assert isinstance(result, str)
    assert "天安门" in result or "搜索结果" in result


@pytest.mark.asyncio
async def test_geocode_address(amap_tools):
    """测试地址解析功能"""
    result = await amap_tools.geocode_address(address="天安门", city="北京市")
    print("Geocode result:", result)
    assert isinstance(result, dict)
    # 成功解析应该包含 location 字段
    if "message" not in result:
        assert "location" in result
        assert "address" in result


@pytest.mark.asyncio
async def test_direction_walking(amap_tools):
    """测试步行路径规划功能"""
    result = await amap_tools.direction_walking(
        origin_address="天安门",
        destination_address="王府井",
        city="北京市",
        cityd="北京市"
    )
    print("Walking direction result:", result)
    assert isinstance(result, str)
    # 验证返回结果包含步行导航相关信息
    assert "步行" in result or "导航" in result or "message" in result


@pytest.mark.asyncio
async def test_direction_driving(amap_tools):
    """测试驾车路径规划功能"""
    result = await amap_tools.direction_driving(
        origin_address="天安门",
        destination_address="北京南站",
        city="北京市",
        cityd="北京市"
    )
    print("Driving direction result:", result)
    assert isinstance(result, str)
    # 验证返回结果包含驾车导航相关信息
    assert "驾车" in result or "导航" in result or "message" in result


@pytest.mark.asyncio
async def test_direction_bicycling(amap_tools):
    """测试骑行路径规划功能"""
    result = await amap_tools.direction_bicycling(
        origin_address="天安门",
        destination_address="王府井",
        city="北京市",
        cityd="北京市"
    )
    print("Bicycling direction result:", result)
    assert isinstance(result, str)
    # 验证返回结果包含骑行导航相关信息
    assert "骑行" in result or "导航" in result or "message" in result


@pytest.mark.asyncio
async def test_direction_transit_integrated(amap_tools):
    """测试公交地铁路径规划功能"""
    result = await amap_tools.direction_transit_integrated(
        origin_address="天安门",
        destination_address="北京南站",
        city="北京市",
        cityd="北京市"
    )
    print("Transit direction result:", result)
    assert isinstance(result, str)
    # 验证返回结果包含公交导航相关信息
    assert "公交" in result or "导航" in result or "message" in result


@pytest.mark.asyncio
async def test_distance_calculation(amap_tools):
    """测试距离计算功能"""
    result = await amap_tools.distance_calculation(
        origins_addresses="天安门",
        destination_address="王府井",
        city="北京市",
        cityd="北京市",
        type="0"  # 直线距离
    )
    print("Distance calculation result:", result)
    assert isinstance(result, str)
    # 验证返回结果包含距离信息
    assert "距离" in result or "公里" in result or "message" in result


@pytest.mark.asyncio
async def test_around_search(amap_tools):
    """测试周边搜索功能"""
    result = await amap_tools.around_search(
        keywords="咖啡店",
        location_address="天安门",
        city="北京市",
        radius="1000"
    )
    print("Around search result:", result)
    assert isinstance(result, str)
    # 验证返回结果包含周边搜索相关信息
    assert "周边" in result or "搜索" in result or "message" in result


def test_meters_to_km(amap_tools):
    """测试米到公里的转换功能"""
    # 测试小于1000米的情况
    result = amap_tools.meters_to_km(500)
    assert result == "500米"
    
    # 测试大于1000米的情况
    result = amap_tools.meters_to_km(1500)
    assert result == "1.5公里"
    
    # 测试字符串输入
    result = amap_tools.meters_to_km("2000")
    assert result == "2.0公里"
    
    # 测试空值
    result = amap_tools.meters_to_km("")
    assert result == "0.0公里"


def test_seconds_to_minutes(amap_tools):
    """测试秒到分钟的转换功能"""
    # 测试小于60秒的情况
    result = amap_tools.seconds_to_minutes(30)
    assert result == "30秒"
    
    # 测试大于60秒的情况
    result = amap_tools.seconds_to_minutes(120)
    assert result == "2分钟"
    
    # 测试字符串输入
    result = amap_tools.seconds_to_minutes("300")
    assert result == "5分钟"
    
    # 测试空值
    result = amap_tools.seconds_to_minutes("")
    assert result == "0分钟"


def test_parse_bicycling(amap_tools):
    """测试骑行数据解析功能"""
    test_data = {
        "paths": [
            {
                "distance": "2000",
                "duration": "600",
                "steps": [
                    {
                        "orientation": "东",
                        "instruction": "向东行驶",
                        "road": "长安街",
                        "distance": "1000",
                        "duration": "300"
                    }
                ]
            }
        ]
    }
    result = amap_tools.parse_bicycling(test_data)
    assert isinstance(result, list)
    assert len(result) > 0
    assert "title" in result[0]
    assert "total" in result[0]
    assert "steps" in result[0]


def test_parse_walking(amap_tools):
    """测试步行数据解析功能"""
    test_data = {
        "route": {
            "paths": [
                {
                    "distance": "1000",
                    "duration": "600",
                    "steps": [
                        {
                            "orientation": "南",
                            "instruction": "向南步行",
                            "road": "王府井大街",
                            "distance": "500",
                            "duration": "300"
                        }
                    ]
                }
            ]
        }
    }
    result = amap_tools.parse_walking(test_data)
    assert isinstance(result, list)
    assert len(result) > 0
    assert "title" in result[0]
    assert "total" in result[0]
    assert "steps" in result[0]


def test_parse_driving(amap_tools):
    """测试驾车数据解析功能"""
    test_data = {
        "paths": [
            {
                "distance": "5000",
                "duration": "600",
                "steps": [
                    {
                        "orientation": "北",
                        "instruction": "向北行驶",
                        "road": "二环",
                        "distance": "2000",
                        "duration": "200"
                    }
                ]
            }
        ]
    }
    result = amap_tools.parse_driving(test_data)
    assert isinstance(result, list)
    assert len(result) > 0
    assert "title" in result[0]
    assert "total" in result[0]
    assert "steps" in result[0]


def test_parse_distance(amap_tools):
    """测试距离计算数据解析功能"""
    test_data = {
        "results": [
            {"distance": "2000", "duration": "300"},
            {"distance": "3000", "duration": "400"}
        ]
    }
    result = amap_tools.parse_distance(test_data)
    assert isinstance(result, dict)
    assert "title" in result
    assert "content" in result
    assert "total_results" in result
    assert result["total_results"] == 2


def test_parse_around(amap_tools):
    """测试周边搜索数据解析功能"""
    test_data = {
        "pois": [
            {
                "name": "测试咖啡店",
                "address": "测试地址1号"
            },
            {
                "name": "测试餐厅",
                "address": "测试地址2号"
            }
        ]
    }
    result = amap_tools.parse_around(test_data)
    assert isinstance(result, dict)
    assert "title" in result
    assert "content" in result


def test_parse_weather(amap_tools):
    """测试天气数据解析功能"""
    test_data = {
        "city": "北京市",
        "forecasts": [
            {
                "date": "2024-01-15",
                "dayweather": "晴",
                "nightweather": "多云",
                "daytemp": "15",
                "nighttemp": "5",
                "daywind": "北",
                "daypower": "3",
                "nightwind": "南",
                "nightpower": "2"
            }
        ]
    }
    result = amap_tools.parse_weather(test_data)
    assert isinstance(result, dict)
    assert "title" in result
    assert "content" in result


def test_to_json(amap_tools):
    """测试JSON序列化功能"""
    test_data = {"key": "value", "number": 123}
    result = amap_tools.to_json(test_data)
    assert isinstance(result, str)
    assert '"key": "value"' in result
    assert '"number": 123' in result


def test_get_amap_route_uri(amap_tools):
    """测试高德地图URI生成功能"""
    from_location = "116.397428,39.90923"
    to_location = "116.397428,39.90923"
    
    # 测试驾车模式
    uri = amap_tools._AmapTools__get_amap_route_uri(from_location, to_location, mode="car")
    assert "uri.amap.com/navigation" in uri
    assert "mode=car" in uri
    
    # 测试步行模式
    uri = amap_tools._AmapTools__get_amap_route_uri(from_location, to_location, mode="walk")
    assert "mode=walk" in uri
    
    # 测试骑行模式
    uri = amap_tools._AmapTools__get_amap_route_uri(from_location, to_location, mode="ride")
    assert "mode=ride" in uri
    
    # 测试公交模式
    uri = amap_tools._AmapTools__get_amap_route_uri(from_location, to_location, mode="bus")
    assert "mode=bus" in uri


@pytest.mark.asyncio
async def test_agno_agent_with_amap_tool(amap_tools, jt_model):
    """测试 agno agent 能够触发 AmapTools 工具"""
    # 创建 agent
    ag = Agent(
        model=jt_model,
        tools=[amap_tools],
        instructions="你是一个地图助手，能够帮助用户查询地点和规划路线",
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
        "请帮我搜索一下北京天安门附近有什么景点",
        session_id=session_id,
        stream=True,
        yield_run_output=True,
    ):
        # 检查是否有工具调用完成的事件
        if isinstance(event, ToolCallCompletedEvent):
            tool_called = True
            print("Tool called successfully!")

    # 验证工具被调用
    assert tool_called, "工具未被触发"


