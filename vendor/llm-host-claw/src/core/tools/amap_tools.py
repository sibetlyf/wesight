from agno.utils.log import logger
from typing import Optional, List, Dict, Any, Union, override
import json

from sqlalchemy import over
from configs.amap_tools import AmapToolConfig
from agno.tools.toolkit import Toolkit
from protocol import EnVar
import asyncio
import os
from mcp.client.sse import sse_client
from mcp import ClientSession
from contextlib import asynccontextmanager

# 全局信号量，用于控制所有高德地图工具的并发（限制为3）
_amap_tools_semaphore = None

# 方向转emoji映射
DIRECTION_EMOJI = {
    "东": "➡️",
    "西": "⬅️",
    "南": "⬇️",
    "北": "⬆️",
    "东北": "↗️",
    "东南": "↘️",
    "西北": "↖️",
    "西南": "↘️",
    "": "",  # 空方向不显示emoji
}


class AmapTools(Toolkit):
    """
    高德地图工具集，封装了地址解析、路径规划、周边搜索等功能
    自动处理地址到经纬度的转换，简化调用流程
    """

    @override
    def __init__(
        self,
        *,
        cfg: AmapToolConfig,
        envar: EnVar,
        include_tools: Optional[List[str]] = None,
    ):
        self.workspace = envar.workspace
        self.user = envar.user_id
        self.record_id = envar.record_id
        self.authorization = envar.authorization

        self.cfg = cfg
        self.api_key = self.cfg.amap_key or self._get_env_key()

        # 初始化全局信号量（限制所有高德地图工具并发数为3）
        global _amap_tools_semaphore
        if _amap_tools_semaphore is None:
            _amap_tools_semaphore = asyncio.Semaphore(3)

        # 定义支持的工具列表
        all_tools = [
            # 封装的工具（自动地址转经纬度）
            self.direction_bicycling,
            self.direction_driving,
            self.direction_transit_integrated,
            self.direction_walking,
            self.distance_calculation,
            # 直接集成的工具
            self.search_poi,
        ]

        super().__init__(
            include_tools=include_tools,
            exclude_tools=self.cfg.exclude_tools,
            tools=all_tools,
        )

    def _get_env_key(self) -> str:
        """从环境变量获取API密钥"""
        import os

        key = os.getenv("amap_key")
        if not key:
            raise ValueError("请设置amap_key环境变量或通过配置文件提供")
        return key

    @asynccontextmanager
    async def _init_session(self, use_semaphore: bool = True):
        """初始化SSE连接和客户端会话（使用正确的上下文管理）

        Args:
            use_semaphore: 是否使用信号量控制并发，默认为True
        """
        global _amap_tools_semaphore

        sse_url = f"https://mcp.amap.com/sse?key={self.api_key}"
        # SSE连接超时设置
        connect_timeout = 10.0  # 连接建立超时
        init_timeout = 5.0  # 初始化超时

        try:
            # 使用信号量控制并发（限制为3）
            if use_semaphore and _amap_tools_semaphore:
                async with _amap_tools_semaphore:
                    # 使用超时包装SSE连接
                    sse_context = sse_client(sse_url)
                    try:
                        read_stream, write_stream = await asyncio.wait_for(
                            sse_context.__aenter__(), timeout=connect_timeout
                        )
                    except asyncio.TimeoutError:
                        logger.error(f"SSE连接超时（{connect_timeout}秒）")
                        raise Exception(f"SSE连接超时，无法建立到高德地图服务的连接")

                    try:
                        async with ClientSession(read_stream, write_stream) as session:
                            # 初始化也设置超时
                            try:
                                await asyncio.wait_for(
                                    session.initialize(), timeout=init_timeout
                                )
                            except asyncio.TimeoutError:
                                logger.error(f"MCP会话初始化超时（{init_timeout}秒）")
                                raise Exception(f"MCP会话初始化超时")

                            await asyncio.sleep(0.5)
                            yield session
                    finally:
                        await sse_context.__aexit__(None, None, None)
            else:
                # 不使用信号量（用于内部调用如geocode_address）
                sse_context = sse_client(sse_url)
                try:
                    read_stream, write_stream = await asyncio.wait_for(
                        sse_context.__aenter__(), timeout=connect_timeout
                    )
                except asyncio.TimeoutError:
                    logger.error(f"SSE连接超时（{connect_timeout}秒）")
                    raise Exception(f"SSE连接超时，无法建立到高德地图服务的连接")

                try:
                    async with ClientSession(read_stream, write_stream) as session:
                        try:
                            await asyncio.wait_for(
                                session.initialize(), timeout=init_timeout
                            )
                        except asyncio.TimeoutError:
                            logger.error(f"MCP会话初始化超时（{init_timeout}秒）")
                            raise Exception(f"MCP会话初始化超时")

                        await asyncio.sleep(0.5)
                        yield session
                finally:
                    await sse_context.__aexit__(None, None, None)
        except Exception as e:
            logger.error(f"会话初始化失败: {str(e)}")
            raise e

    def meters_to_km(self, meters):
        """米转换为公里，保留一位小数"""
        if not meters or meters == "":
            return "0.0公里"
        # 小于1000米 不转换 直接返回；大于1000米的转成公里
        if int(meters) < 1000:
            return f"{int(meters)}米"
        if isinstance(meters, str):
            meters = float(meters.replace(",", ""))
        return f"{meters / 1000:.1f}公里"

    def seconds_to_minutes(self, seconds):
        """秒转换为分钟，取整"""
        if not seconds or seconds == "":
            return "0分钟"
        # 小于60秒 不转换 直接返回；大于60秒的转成分钟
        if int(seconds) < 60:
            return f"{int(seconds)}秒"
        if isinstance(seconds, str):
            seconds = float(seconds.replace(",", ""))
        return f"{int(seconds // 60)}分钟"

    def parse_bicycling(self, data):
        """解析骑行导航数据"""
        all_routes = []
        total_routes = len(data["paths"])
        for route_idx, path in enumerate(data["paths"], 1):
            total_distance = self.meters_to_km(path["distance"])
            total_duration = self.seconds_to_minutes(path["duration"])
            steps = []
            for i, step in enumerate(path["steps"], 1):
                direction = DIRECTION_EMOJI.get(step["orientation"], "")
                road = step["road"] if step["road"] else ""
                distance = self.meters_to_km(step["distance"])
                duration = self.seconds_to_minutes(step["duration"])
                steps.append(
                    f"{i}. {direction} **{step['instruction']}**\n | ⏱️ 耗时：{duration}"
                )

            all_routes.append(
                {
                    "title": f"🚲 骑行导航（路线{route_idx}/{total_routes}）",
                    "total": f"📏 总距离：{total_distance} | ⏱️ 总时长：{total_duration}",
                    "steps": "\n\n".join(steps),
                }
            )
        return all_routes

    def parse_walking(self, data):
        """解析步行导航数据"""
        logger.info("maps_direction_walking 原结果：", data)
        all_routes = []
        total_routes = len(data["route"]["paths"])
        for route_idx, path in enumerate(data["route"]["paths"], 1):
            total_distance = self.meters_to_km(path["distance"])
            total_duration = self.seconds_to_minutes(path["duration"])
            steps = []
            for i, step in enumerate(path["steps"], 1):
                direction = DIRECTION_EMOJI.get(step["orientation"], "")
                road = step["road"] if step["road"] else ""
                distance = self.meters_to_km(step["distance"])
                duration = self.seconds_to_minutes(step["duration"])
                steps.append(
                    f"{i}. {direction} **{step['instruction']}**\n  | ⏱️ 耗时：{duration}"
                )

            all_routes.append(
                {
                    "title": f"🚶 步行导航（路线{route_idx}/{total_routes}）",
                    "total": f"📏 总距离：{total_distance} | ⏱️ 总时长：{total_duration}",
                    "steps": "\n\n".join(steps),
                }
            )
        return all_routes

    def parse_driving(self, data):
        """解析驾车导航数据"""
        logger.info("maps_direction_driving 原结果：", data)
        all_routes = []
        total_routes = len(data["paths"])
        for route_idx, path in enumerate(data["paths"], 1):
            total_distance = self.meters_to_km(path["distance"])
            total_duration = self.seconds_to_minutes(path["duration"])
            steps = []
            for i, step in enumerate(path["steps"], 1):
                direction = DIRECTION_EMOJI.get(step["orientation"], "")
                road = step["road"] if step["road"] else ""
                distance = self.meters_to_km(step["distance"])
                duration = self.seconds_to_minutes(step["duration"])
                steps.append(
                    f"{i}. {direction} **{step['instruction']}**\n  | ⏱️ 耗时：{duration}"
                )

            all_routes.append(
                {
                    "title": f"🚗 驾车导航（路线{route_idx}/{total_routes}）",
                    "total": f"📏 总距离：{total_distance} | ⏱️ 总时长：{total_duration}",
                    "steps": "\n\n".join(steps),
                }
            )
        return all_routes

    def parse_transit(self, data):
        """解析公交导航数据"""
        logger.info("maps_direction_transit 原结果：", data)
        all_routes = []
        total_routes = len(data.get("transits", []))

        for route_idx, transit in enumerate(data.get("transits", []), 1):
            total_duration = self.seconds_to_minutes(transit.get("duration", ""))
            total_walking = self.meters_to_km(transit.get("walking_distance", ""))
            segments = []

            for seg in transit.get("segments", []):
                # 步行段处理
                if seg.get("walking"):
                    walk = seg["walking"]
                    steps = []
                    for i, step in enumerate(walk.get("steps", []), 1):
                        direction = DIRECTION_EMOJI.get(step.get("orientation", ""), "")
                        instruction = step.get("instruction", "无步行指引")
                        distance = self.meters_to_km(step.get("distance", ""))
                        steps.append(
                            f"{i}. {direction} **{instruction}**\n  📏 距离：{distance}"
                        )

                    walk_distance = self.meters_to_km(walk.get("distance", ""))
                    walk_duration = self.seconds_to_minutes(walk.get("duration", ""))
                    segments.append(
                        {
                            "type": "walking",
                            "content": "\n\n".join(steps) if steps else "🚶 无步行指引",
                            "total": f"🚶 步行段 | 📏 距离：{walk_distance} | ⏱️ 耗时：{walk_duration}",
                        }
                    )

                # 公交段处理（增加防御性判断）
                bus_info = seg.get("bus", {})
                buslines = bus_info.get("buslines", [])
                if buslines:
                    # 只取第一条公交线路，但确保不会因空数组报错
                    busline = buslines[0]
                    via_stops = busline.get("via_stops", [])
                    # 处理途经站点为空的情况
                    if via_stops:
                        via_stops_str = " → ".join(
                            [s.get("name", "未知站点") for s in via_stops]
                        )
                    else:
                        via_stops_str = "无途经站点"

                    # 确保关键字段存在
                    depart_name = busline.get("departure_stop", {}).get(
                        "name", "未知起点"
                    )
                    arrival_name = busline.get("arrival_stop", {}).get(
                        "name", "未知终点"
                    )
                    bus_distance = self.meters_to_km(busline.get("distance", ""))
                    bus_duration = self.seconds_to_minutes(busline.get("duration", ""))

                    segments.append(
                        {
                            "type": "bus",
                            "content": f"🚌 **{busline.get('name', '未知线路')}**\n  📍 途经站点：{depart_name} → {via_stops_str} → {arrival_name}\n  📏 距离：{bus_distance} | ⏱️ 耗时：{bus_duration}",
                            "total": f"🚌 公交段 | 线路：{busline.get('name', '未知线路')} | 📏 距离：{bus_distance}",
                        }
                    )

            # 构建单条公交路线内容
            segments_md = []
            for i, seg in enumerate(segments, 1):
                segments_md.append(f"### 第{i}段：{seg['total']}\n{seg['content']}")

            all_routes.append(
                {
                    "title": f"🚌 公交导航（路线{route_idx}/{total_routes}）",
                    "total": f"📏 总步行距离：{total_walking} | ⏱️ 总时长：{total_duration}",
                    "steps": "\n\n".join(segments_md) if segments_md else "无导航信息",
                }
            )

        return all_routes

    def parse_around(self, around_data):
        """解析周边搜索结果"""
        pois = around_data.get("pois", [])
        total_pois = len(pois)

        # 构建表格头部
        table_header = "| 序号 | 名称 | 地址 | 类型代码 | 图片 |\n|------|------|----------|------|\n"

        # 构建表格内容
        table_rows = []
        for poi_idx, poi in enumerate(pois, 1):
            idx = poi_idx
            name = poi.get("name", "未知名称")
            address = poi.get("address", "无地址信息")
            table_rows.append(f"| {idx} | {name} | {address} | ")

        # 组合表格
        table_content = table_header + "\n".join(table_rows)

        return {
            "title": f"🔍 周边搜索结果（共{total_pois}个）",
            "content": table_content,
        }

    def parse_distance(self, distance_data):
        """解析距离计算数据，简化格式"""
        results = distance_data.get("results", [])
        simplified_results = []

        for result in results:
            distance = self.meters_to_km(result.get("distance", ""))
            # 太近的时长是0，不太合理，不展示
            # duration = self.seconds_to_minutes(result.get('duration', ''))
            simplified_results.append(f"📏 距离：{distance} ")

        return {
            "title": "📏 距离计算结果",
            "content": (
                "\n\n".join(simplified_results)
                if simplified_results
                else "无距离计算数据"
            ),
            "total_results": len(simplified_results),
        }

    def parse_weather(self, weather_data):
        """解析天气数据并生成格式化结果"""
        # 天气状况与emoji映射
        weather_emoji = {
            "晴": "☀️",
            "晴朗": "☀️",
            "多云": "☁️",
            "阴": "☁️",
            "小雨": "🌧️",
            "中雨": "🌧️",
            "大雨": "🌧️",
            "暴雨": "🌧️",
            "雪": "❄️",
            "小雪": "❄️",
            "中雪": "❄️",
            "大雪": "❄️",
        }

        city = weather_data.get("city", "未知城市")
        forecasts = weather_data.get("forecasts", [])
        total_days = len(forecasts)

        # 构建天气卡片列表
        weather_cards = []
        for forecast in forecasts:
            # 日期格式化
            date_str = forecast["date"]
            month_day = f"{date_str.split('-')[1]}月{date_str.split('-')[2]}日"

            # 获取天气emoji
            day_weather = forecast["dayweather"]
            night_weather = forecast["nightweather"]  # 修正变量名
            day_emoji = next(
                (emoji for cond, emoji in weather_emoji.items() if cond in day_weather),
                "🌡️",
            )
            night_emoji = next(
                (
                    emoji
                    for cond, emoji in weather_emoji.items()
                    if cond in night_weather
                ),
                "🌡️",
            )

            # 温度和风力
            day_temp = f"{forecast['daytemp']}℃"
            night_temp = f"{forecast['nighttemp']}℃"
            day_wind = f"{forecast['daywind']}风 {forecast['daypower']}级"
            night_wind = f"{forecast['nightwind']}风 {forecast['nightpower']}级"

            # 天气卡片内容（修正nightweather变量名）
            card = f"""### 📅 {month_day}
    | 时段   | 天气状况       | 温度   | 风向风力     |
    |--------|----------------|--------|--------------|
    | 白天   | {day_emoji} {day_weather} | {day_temp} | {day_wind} |
    | 夜晚   | {night_emoji} {night_weather} | {night_temp} | {night_wind} |
    """
            weather_cards.append(card)

        return {
            "title": f"🌤️ {city}天气预报（{total_days}天）",
            "content": "\n\n".join(weather_cards),
        }

    def to_json(self, parsed_data, indent=2):
        """将解析结果序列化为JSON字符串"""
        return json.dumps(parsed_data, ensure_ascii=False, indent=indent)

    def __get_choices_message(self, address: List[str], is_origin: bool = True) -> str:
        return json.dumps(
            {
                "message": f"发现多个{"起点" if is_origin else "终点"}, 请选择",
                "address": address,
            },
            ensure_ascii=False,
        )

    def __get_amap_route_uri(
        self,
        from_location: str,
        to_location: str,
        mode: str = "car",
        policy: str = "0",
        src: str = "webapp",
        callnative: str = "0",
    ):
        """
        生成高德地图路径规划URI

        Args:
            from_location: 起点经纬度坐标，格式如"116.473168,39.993015"
            to_location: 终点经纬度坐标，格式如"116.403963,39.915119"
            mode: 出行方式，car（驾车）、bus（公交）、walk（步行）、ride（骑行）
            policy: 当mode=car(驾车):
                0:推荐策略,
                1:避免拥堵,
                2:避免收费,
                3:不走高速（仅限移动端）
                当mode=bus(公交):
                0:最佳路线,
                1:换乘少,
                2:步行少,
                3:不坐地铁
                缺省时是0
            src: 使用方来源信息，默认为"webapp"
            callnative: 是否尝试调起高德地图APP并在APP中查看，0表示不调起，1表示调起, 默认值为0

        Returns:
            高德地图路径规划URI字符串
        """
        # 根据出行方式设置参数
        base_url = "https://uri.amap.com/navigation"

        # 构建URI
        if mode == "car":
            # 驾车路径
            uri = f"{base_url}?from={from_location},startpoint&to={to_location},endpoint&mode={mode}&policy={policy}&src={src}&callnative={callnative}"
        elif mode == "bus":
            # 公交路径
            uri = f"{base_url}?from={from_location},startpoint&to={to_location},endpoint&mode={mode}&policy={policy}&src={src}&callnative={callnative}"
        elif mode == "walk":
            # 步行路径
            uri = f"{base_url}?from={from_location},startpoint&to={to_location},endpoint&mode={mode}&policy={policy}&src={src}&callnative={callnative}"
        elif mode == "ride":
            # 骑行路径
            uri = f"{base_url}?from={from_location},startpoint&to={to_location},endpoint&mode={mode}&policy={policy}&src={src}&callnative={callnative}"
        else:
            # 默认为驾车
            uri = f"{base_url}?from={from_location},startpoint&to={to_location},endpoint&mode={mode}&policy={policy}&src={src}&callnative={callnative}"

        return uri

    async def geocode_address(
        self, address: str, city: str
    ) -> Union[Dict[str, Any], List[str]]:
        """
        将地址转换为经纬度坐标

        Args:
            address (Optional[str]): 待解析的地址（如"南京夫子庙"）
            city (Optional[str]): 指定城市（如"南京市"）

        Returns:
            包含经纬度的字典，格式: {"location": "经度,纬度", "address": "匹配地址"}
        """
        # 增加重试机制
        max_retries = 3
        retry_delay = 1
        for attempt in range(max_retries):
            async with self._init_session() as session:

                try:
                    args = {"keywords": address}
                    if city:
                        args["city"] = city

                    # 修改为调用maps_text_search获取id，再调用maps_search_detail获取location
                    result = await asyncio.wait_for(
                        session.call_tool("maps_text_search", arguments=args),
                        timeout=self.cfg.timeout,
                    )
                    if result.isError:
                        error_text = result.content[0].text if result.content else "未知错误"  # type: ignore
                        logger.error(f"maps_text_search API调用失败: {error_text}")
                        if "CUQPS_HAS_EXCEEDED_THE_LIMIT" in error_text:
                            if attempt < max_retries - 1:
                                wait_time = retry_delay * (2**attempt)  # 指数退避
                                logger.warning(
                                    f"API调用频率超限，{wait_time}秒后进行第{attempt + 2}次重试"
                                )
                                await asyncio.sleep(wait_time)
                                continue
                            else:
                                error_msg = {
                                    "message": f"API调用频率超限，已重试{max_retries}次仍失败"
                                }
                                raise Exception(error_msg)
                        else:
                            error_msg = {"message": f"API调用失败: {error_text}"}
                            raise Exception(error_msg)

                    logger.info(f"maps_text_search result: {result}")
                    try:
                        result_data = json.loads(result.content[0].text)  # type: ignore
                        if not result_data.get("pois"):
                            return {"message": f"未找到地址'{address}'的POI数据"}
                        address_id = (
                            result_data["pois"][0]["id"]
                            if result_data.get("pois")
                            else {}
                        )

                        try:
                            result_detail = await asyncio.wait_for(
                                session.call_tool(
                                    "maps_search_detail", arguments={"id": address_id}
                                ),
                                timeout=self.cfg.timeout,
                            )
                            if result_detail.isError:
                                error_text = result_detail.content[0].text if result_detail.content else "未知错误"  # type: ignore
                                logger.error(
                                    f"maps_search_detail工具返回异常: {error_text}"
                                )
                                error_msg = {
                                    "message": f"详细信息获取失败: {error_text}"
                                }
                                raise Exception(error_msg)

                            logger.info(f"maps_search_detail result: {result_detail}")
                            result_data_detail = json.loads(result_detail.content[0].text)  # type: ignore
                            address = (
                                result_data_detail["name"]
                                if result_data_detail.get("name")
                                else ""
                            )
                            location = (
                                result_data_detail["location"]
                                if result_data_detail.get("location")
                                else ""
                            )
                            return {
                                "location": location,
                                "address": address,
                            }
                        except Exception as e:
                            logger.error(f"maps_search_detail工具返回异常: {e}")
                            error_msg = {"message": f"工具返回异常: {e}"}
                            raise Exception(error_msg)
                    except json.JSONDecodeError as e:
                        logger.error(f"返回非JSON格式数据: {result.content[0].text}")  # type: ignore
                        error_msg = {"message": f"返回非JSON格式数据: {result.content[0].text}"}  # type: ignore
                        raise Exception(error_msg)
                except Exception as e:
                    logger.error(f"地址解析失败: {str(e)}")
                    error_msg = {"message": f"地址解析失败: {str(e)}"}
                    raise Exception(error_msg)
        return {"message": f"地址经纬度解析失败，已重试{max_retries}次"}

    async def direction_bicycling(
        self, origin_address: str, destination_address: str, city: str, cityd: str
    ):
        """
        骑行路径规划。用于规划骑行方案，规划时会考虑天桥、单行线、封路等情况。

        Args:
            origin_address (Optional[str]): 起点地址（如"苏州虎丘区"）
            destination_address (Optional[str]): 终点地址（如"苏州相城区"）
            city (Optional[str]): 起点城市
            cityd (Optional[str]): 终点城市

        Returns:
            骑行路径信息，包含距离、时长、步骤等
        """
        try:
            # 解析起点和终点经纬度
            origin = await self.geocode_address(origin_address, city)
            if "message" in origin:
                logger.error(f"起点地址解析失败: {origin['message']}")  # type: ignore
                error_msg = {"message": f"起点地址解析失败: {origin['message']}"}  # type: ignore
                raise Exception(error_msg)
            dest = await self.geocode_address(destination_address, cityd)
            if "message" in dest:
                logger.error(f"终点地址解析失败: {dest['message']}")  # type: ignore
                error_msg = {"message": f"终点地址解析失败: {dest['message']}"}  # type: ignore
                raise Exception(error_msg)

            if not origin.get("location") or not dest.get("location"):  # type: ignore
                logger.error("起点或终点地址解析失败")
                error_msg = {"message": "起点或终点地址解析失败"}
                raise Exception(error_msg)

            async with self._init_session() as session:
                try:
                    result = await asyncio.wait_for(
                        session.call_tool(
                            "maps_direction_bicycling",
                            arguments={
                                "origin": origin["location"],  # type: ignore
                                "destination": dest["location"],  # type: ignore
                            },
                        ),
                        timeout=self.cfg.timeout,
                    )
                    data = json.loads(result.content[0].text)  # type: ignore
                    parse_data = self.parse_bicycling(data)
                    # 标注骑行路径 route_url
                    route_url = self.__get_amap_route_uri(origin["location"], dest["location"], "ride")  # type: ignore
                    if isinstance(parse_data, list):
                        for route in parse_data:
                            route["route_url"] = route_url
                    else:
                        parse_data["route_url"] = route_url
                    return self.to_json(parse_data)
                except Exception as e:
                    logger.error(f"骑行路径规划失败: {str(e)}")
                    error_msg = {"message": f"骑行路径规划失败: {str(e)}"}
                    raise Exception(error_msg)
        except asyncio.TimeoutError:
            logger.error("骑行路径规划请求超时")
            error_msg = {"message": "tool timeout: 骑行路径规划请求超时"}
            raise Exception(error_msg)
        except Exception as e:
            logger.error(f"骑行路径规划失败: {str(e)}")
            error_msg = {"message": f"骑行路径规划失败: {str(e)}"}
            raise Exception(error_msg)

    async def direction_driving(
        self, origin_address: str, destination_address: str, city: str, cityd: str
    ):
        """
        驾车路径规划。规划以小客车、轿车出行的方案，并且返回出行方案的数据。

        Args:
            origin_address (Optional[str]): 起点地址
            destination_address (Optional[str]): 终点地址
            city (Optional[str]): 起点城市
            cityd (Optional[str]): 终点城市

        Returns:
            驾车路径信息
        """
        try:
            origin = await self.geocode_address(origin_address, city)
            if "message" in origin:
                logger.error(f"起点地址解析失败: {origin['message']}")  # type: ignore
                error_msg = {"message": f"起点地址解析失败: {origin['message']}"}  # type: ignore
                raise Exception(error_msg)
            dest = await self.geocode_address(destination_address, cityd)
            if "message" in dest:
                logger.error(f"终点地址解析失败: {dest['message']}")  # type: ignore
                error_msg = {"message": f"终点地址解析失败: {dest['message']}"}  # type: ignore
                raise Exception(error_msg)

            if not origin.get("location") or not dest.get("location"):  # type: ignore
                logger.error("起点或终点地址解析失败")
                error_msg = {"message": "起点或终点地址解析失败"}
                raise Exception(error_msg)

            async with self._init_session() as session:
                try:
                    result = await asyncio.wait_for(
                        session.call_tool(
                            "maps_direction_driving",
                            arguments={
                                "origin": origin["location"],  # type: ignore
                                "destination": dest["location"],  # type: ignore
                                "city": city,
                                "cityd": cityd,
                            },
                        ),
                        timeout=self.cfg.timeout,
                    )
                    data = json.loads(result.content[0].text)  # type: ignore
                    parse_data = self.parse_driving(data)
                    # 标注驾车路径 route_url
                    route_url = self.__get_amap_route_uri(origin["location"], dest["location"], "car")  # type: ignore
                    if isinstance(parse_data, list):
                        for route in parse_data:
                            route["route_url"] = route_url
                    else:
                        parse_data["route_url"] = route_url
                    return self.to_json(parse_data)
                except Exception as e:
                    logger.error(f"驾车路径规划失败: {str(e)}")
                    error_msg = {"message": f"驾车路径规划失败: {str(e)}"}
                    raise Exception(error_msg)
        except asyncio.TimeoutError:
            logger.error("驾车路径规划请求超时")
            error_msg = {"message": "tool timeout: 驾车路径规划请求超时"}
            raise Exception(error_msg)
        except Exception as e:
            logger.error(f"驾车路径规划失败: {str(e)}")
            error_msg = {"message": f"驾车路径规划失败: {str(e)}"}
            raise Exception(error_msg)

    async def direction_transit_integrated(
        self, origin_address: str, destination_address: str, city: str, cityd: str
    ):
        """
        公交地铁路径规划。根据用户起终点规划综合各类公共公交、地铁交通方式的出行方案，并且返回出行方案的数据，不适合跨城场景中使用。

        Args:
            origin_address (Optional[str]): 起点地址
            destination_address (Optional[str]): 终点地址
            city (Optional[str]): 起点城市
            cityd (Optional[str]): 终点城市

        Returns:
            公共交通路径信息
        """
        try:
            origin = await self.geocode_address(origin_address, city)
            if "message" in origin:
                logger.error(f"起点地址解析失败: {origin['message']}")  # type: ignore
                error_msg = {"message": f"起点地址解析失败: {origin['message']}"}  # type: ignore
                raise Exception(error_msg)
            dest = await self.geocode_address(destination_address, cityd)
            if "message" in dest:
                logger.error(f"终点地址解析失败: {dest['message']}")  # type: ignore
                error_msg = {"message": f"终点地址解析失败: {dest['message']}"}  # type: ignore
                raise Exception(error_msg)

            if not origin.get("location") or not dest.get("location"):  # type: ignore
                logger.error("起点或终点地址解析失败")
                error_msg = {"message": "起点或终点地址解析失败"}
                raise Exception(error_msg)

            async with self._init_session() as session:
                try:
                    result = await asyncio.wait_for(
                        session.call_tool(
                            "maps_direction_transit_integrated",
                            arguments={
                                "origin": origin["location"],  # type: ignore
                                "destination": dest["location"],  # type: ignore
                                "city": city,
                                "cityd": cityd,
                            },
                        ),
                        timeout=self.cfg.timeout,
                    )
                    data = json.loads(result.content[0].text)  # type: ignore
                    parse_data = self.parse_transit(data)
                    # 标注公交路径 route_url
                    route_url = self.__get_amap_route_uri(origin["location"], dest["location"], "bus")  # type: ignore
                    if isinstance(parse_data, list):
                        for route in parse_data:
                            route["route_url"] = route_url
                    else:
                        parse_data["route_url"] = route_url
                    return self.to_json(parse_data)
                except Exception as e:
                    logger.error(f"公共交通路径规划失败: {str(e)}")
                    error_msg = {"message": f"公共交通路径规划失败: {str(e)}"}
                    raise Exception(error_msg)
        except asyncio.TimeoutError:
            logger.error("公共交通路径规划请求超时")
            error_msg = {"message": "tool timeout: 公共交通路径规划请求超时"}
            raise Exception(error_msg)
        except Exception as e:
            logger.error(f"公共交通路径规划失败: {str(e)}")
            error_msg = {"message": f"公共交通路径规划失败: {str(e)}"}
            raise Exception(error_msg)

    async def direction_walking(
        self, origin_address: str, destination_address: str, city: str, cityd: str
    ):
        """
        步行路径规划。根据输入起点终点规划100km以内的步行出行方案，并且返回出行方案的数据

        Args:
            origin_address (Optional[str]): 起点地址
            destination_address (Optional[str]): 终点地址
            city (Optional[str]): 指定城市
            cityd (Optional[str]): 终点城市

        Returns:
            步行路径信息
        """
        try:
            origin = await self.geocode_address(origin_address, city)
            if "message" in origin:
                logger.error(f"起点地址解析失败: {origin['message']}")  # type: ignore
                error_msg = {"message": f"起点地址解析失败: {origin['message']}"}  # type: ignore
                raise Exception(error_msg)
            dest = await self.geocode_address(destination_address, cityd)
            if "message" in dest:
                logger.error(f"终点地址解析失败: {dest['message']}")  # type: ignore
                error_msg = {"message": f"终点地址解析失败: {dest['message']}"}  # type: ignore
                raise Exception(error_msg)

            if not origin.get("location") or not dest.get("location"):  # type: ignore
                logger.error("起点或终点地址解析失败")
                error_msg = {"message": "起点或终点地址解析失败"}
                raise Exception(error_msg)

            async with self._init_session() as session:
                try:
                    result = await asyncio.wait_for(
                        session.call_tool(
                            "maps_direction_walking",
                            arguments={
                                "origin": origin["location"],  # type: ignore
                                "destination": dest["location"],  # type: ignore
                            },
                        ),
                        timeout=self.cfg.timeout,
                    )
                    data = json.loads(result.content[0].text)  # type: ignore
                    parse_data = self.parse_walking(data)
                    # 标注步行路径 route_url
                    route_url = self.__get_amap_route_uri(origin["location"], dest["location"], "walk")  # type: ignore
                    if isinstance(parse_data, list):
                        for route in parse_data:
                            route["route_url"] = route_url
                    else:
                        parse_data["route_url"] = route_url
                    return self.to_json(parse_data)
                except Exception as e:
                    logger.error(f"步行路径规划失败: {str(e)}")
                    error_msg = {"message": f"步行路径规划失败: {str(e)}"}
                    raise Exception(error_msg)
        except asyncio.TimeoutError:
            logger.error("步行路径规划请求超时")
            error_msg = {"message": "tool timeout: 步行路径规划请求超时"}
            raise Exception(error_msg)
        except Exception as e:
            logger.error(f"步行路径规划失败: {str(e)}")
            error_msg = {"message": f"步行路径规划失败: {str(e)}"}
            raise Exception(error_msg)

    async def distance_calculation(
        self,
        origins_addresses: str,
        destination_address: str,
        city: str,
        cityd: str,
        type: str = "0",
    ):
        """
        距离计算。测量两个地点之间的距离,支持驾车、直线、步行类型下的距离测量

        Args:
            origins_addresses (Optional[str]): 起点地址列表（用|分隔，如"地址1|地址2"）
            destination_address (Optional[str]): 终点地址
            city (Optional[str]): 指定城市
            cityd (Optional[str]): 终点城市
            type (str): 距离类型（1:驾车, 0:直线, 3:步行）

        Returns:
            距离计算结果
        """
        try:
            origin = await self.geocode_address(origins_addresses, city)
            if "message" in origin:
                logger.error(f"起点地址解析失败: {origin['message']}")  # type: ignore
                error_msg = {"message": f"起点地址解析失败: {origin['message']}"}  # type: ignore
                raise Exception(error_msg)
            dest = await self.geocode_address(destination_address, cityd)
            if "message" in dest:
                logger.error(f"终点地址解析失败: {dest['message']}")  # type: ignore
                error_msg = {"message": f"终点地址解析失败: {dest['message']}"}  # type: ignore
                raise Exception(error_msg)

            if not origin.get("location") or not dest.get("location"):  # type: ignore
                logger.error("起点或终点地址解析失败")
                error_msg = {"message": "起点或终点地址解析失败"}
                raise Exception(error_msg)

            async with self._init_session() as session:
                try:
                    result = await asyncio.wait_for(
                        session.call_tool(
                            "maps_distance",
                            arguments={
                                "origins": origin["location"],  # type: ignore
                                "destination": dest["location"],  # type: ignore
                                "type": type,
                            },
                        ),
                        timeout=self.cfg.timeout,
                    )
                    data = json.loads(result.content[0].text)  # type: ignore
                    parse_data = self.parse_distance(data)
                    return self.to_json(parse_data)
                except Exception as e:
                    logger.error(f"距离计算失败: {str(e)}")
                    error_msg = {"message": f"距离计算失败: {str(e)}"}
                    raise Exception(error_msg)
        except asyncio.TimeoutError:
            logger.error("距离计算请求超时")
            error_msg = {"message": "tool timeout: 距离计算请求超时"}
            raise Exception(error_msg)
        except Exception as e:
            logger.error(f"距离计算失败: {str(e)}")
            error_msg = {"message": f"距离计算失败: {str(e)}"}
            raise Exception(error_msg)

    async def around_search(
        self, keywords: str, location_address: str, city: str, radius: str = "1000"
    ):
        """
        周边搜,根据用户传入关键词以及坐标地址，搜索出radius半径范围的POI。更适合用于搜索已知中心点地址附近的特定类型的地点或物体。

        Args:
            keywords (Optional[str]): 搜索关键词（如"咖啡店"）
            location_address (Optional[str]): 中心点地址
            city (Optional[str]): 指定城市
            radius (Optional[str]): 搜索半径（米）

        Returns:
            周边POI搜索结果
        """
        try:
            # 解析中心点经纬度
            location = await self.geocode_address(location_address, city)
            if "message" in location:
                logger.error(f"中心点地址解析失败: {location['message']}")  # type: ignore
                error_msg = {"message": f"中心点地址解析失败: {location['message']}"}  # type: ignore
                raise Exception(error_msg)
            if not location.get("location"):  # type: ignore
                logger.error("中心点地址解析失败")
                error_msg = {"message": "中心点地址解析失败"}
                raise Exception(error_msg)

            async with self._init_session() as session:
                try:
                    result = await asyncio.wait_for(
                        session.call_tool(
                            "maps_around_search",
                            arguments={
                                "keywords": keywords,
                                "location": location["location"],  # type: ignore
                                "radius": radius,
                            },
                        ),
                        timeout=self.cfg.timeout,
                    )
                    data = json.loads(result.content[0].text)  # type: ignore
                    parse_data = self.parse_around(data)
                    return self.to_json(parse_data)
                except Exception as e:
                    logger.error(f"周边搜索失败: {str(e)}")
                    error_msg = {"message": f"周边搜索失败: {str(e)}"}
                    raise Exception(error_msg)
        except asyncio.TimeoutError:
            logger.error("周边搜索请求超时")
            error_msg = {"message": "tool timeout: 周边搜索请求超时"}
            raise Exception(error_msg)
        except Exception as e:
            logger.error(f"周边搜索失败: {str(e)}")
            error_msg = {"message": f"周边搜索失败: {str(e)}"}
            raise Exception(error_msg)

    async def search_poi(self, keywords: str, city: str, citylimit: bool = True):
        """
        根据用户输入的关键信息，搜索出周边相关的POI（兴趣点），并返回POI信息。

        Args:
            keywords (Optional[str]): 搜索关键词，用于查找地点、场所或地理位置相关的POI。
                           应包含具体的地名、商圈、景点、街道等地理位置信息，
                           例如："南京夫子庙"、"海淀区交大东路附近的公园"、"北京西站附近美食店"。
                           禁止使用包含价格查询、票务信息、服务咨询等非地理位置类的关键词。
            city (Optional[str]): 指定城市
            citylimit (bool): 是否限制在指定城市内搜索

        Returns:
            POI搜索结果
        """
        max_retries = 3
        retry_delay = 0.5  # 固定重试间隔
        # 设置超时时间（优先使用配置，默认30秒）
        request_timeout = self.cfg.timeout if self.cfg.timeout else 30

        for attempt in range(max_retries):
            try:
                logger.info(
                    f"search_poi 开始查询 (attempt {attempt + 1}/{max_retries}): keywords={keywords}, city={city}"
                )

                # _init_session 内部已经使用信号量控制并发
                async with self._init_session() as session:
                    args = {"keywords": keywords, "citylimit": citylimit}
                    if city:
                        args["city"] = city

                    # 使用更严格的超时控制
                    result = await asyncio.wait_for(
                        session.call_tool("maps_text_search", arguments=args),
                        timeout=request_timeout,
                    )

                    # 检查结果是否为空
                    if not result.content or len(result.content) == 0:
                        logger.warning(f"search_poi 返回空内容: keywords={keywords}")
                        return json.dumps(
                            {
                                "message": f"未找到'{keywords}'相关结果，建议更换更具体的地理位置信息关键词"
                            },
                            ensure_ascii=False,
                        )

                    result_text = result.content[0].text if result.content[0] else ""  # type: ignore

                    # result.content[0].text如果是空字符串，说明没有搜索到相关结果
                    if not result_text or result_text.strip() == "":
                        logger.warning(f"search_poi 返回空字符串: keywords={keywords}")
                        return json.dumps(
                            {
                                "message": f"未找到'{keywords}'相关结果，建议更换更具体的地理位置信息关键词"
                            },
                            ensure_ascii=False,
                        )

                    # 尝试解析JSON
                    try:
                        data = json.loads(result_text)
                    except json.JSONDecodeError as e:
                        logger.error(
                            f"search_poi JSON解析失败: {str(e)}, content={result_text[:200]}"
                        )
                        # 如果是空结果导致的解析失败，返回友好提示
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay)
                            continue
                        return json.dumps(
                            {
                                "message": f"搜索'{keywords}'时返回数据格式异常，建议更换关键词重试"
                            },
                            ensure_ascii=False,
                        )

                    # 检查是否有POI数据
                    pois = data.get("pois", [])
                    if not pois:
                        logger.info(f"search_poi 未找到POI数据: keywords={keywords}")
                        return json.dumps(
                            {
                                "message": f"未找到'{keywords}'相关地点，建议：\n1. 检查城市名称是否正确\n2. 使用更通用的关键词（如'餐厅'、'酒店'）\n3. 添加具体区域（如'朝阳区餐厅'）"
                            },
                            ensure_ascii=False,
                        )

                    parse_data = self.parse_around(data)
                    return self.to_json(parse_data)

            except asyncio.TimeoutError:
                logger.error(
                    f"search_poi 请求超时 (attempt {attempt + 1}/{max_retries}): keywords={keywords}"
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    continue
                return json.dumps(
                    {"message": f"搜索'{keywords}'超时，请稍后重试"}, ensure_ascii=False
                )

            except Exception as e:
                error_str = str(e)
                logger.error(
                    f"search_poi 异常 (attempt {attempt + 1}/{max_retries}): keywords={keywords}, error={error_str}"
                )

                # 检查是否是并发限制错误
                if "CUQPS_HAS_EXCEEDED_THE_LIMIT" in error_str:
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (attempt + 1)
                        logger.warning(f"search_poi API限流，等待{wait_time}s后重试")
                        await asyncio.sleep(wait_time)
                        continue

                # 其他错误，返回友好提示
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    continue

                return json.dumps(
                    {
                        "message": f"搜索'{keywords}'失败: {error_str}，建议更换关键词或稍后重试"
                    },
                    ensure_ascii=False,
                )
