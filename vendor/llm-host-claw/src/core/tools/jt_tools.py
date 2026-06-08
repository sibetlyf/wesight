import httpx
from loguru import logger
from agno.run.agent import RunContentEvent
from agno.models.message import Citations
from typing import Optional, List, override
import json
from agno.run.base import RunContext
import asyncio

from configs.jt_tools import JtToolsConfig
import uuid
from agno.tools.toolkit import Toolkit
from protocol.external_agent_run_response_event import (
    ExternalAgentRunResponseContentEvent,
)
from protocol import EnVar
import re
import os
import random
import base64

# 全局锁，用于控制 get_search 的并发
_search_semaphore = None  # 将在 __init__ 中初始化


class JtTools(Toolkit):
    """
    工具
    """

    @override
    def __init__(
        self,
        *,
        cfg: JtToolsConfig,
        envar: EnVar,
        include_tools: Optional[List[str]] = None,
    ):
        self.workspace = envar.workspace
        self.user = envar.user_id
        self.record_id = envar.record_id
        self.authorization = envar.authorization

        self.cfg = cfg

        # 初始化全局信号量（限制并发数为1，确保串行执行）
        global _search_semaphore
        if _search_semaphore is None:
            _search_semaphore = asyncio.Semaphore(1)

        super().__init__(
            include_tools=include_tools,
            exclude_tools=self.cfg.exclude_tools,
            tools=[
                self.get_search,
                self.get_weather,
                self.generate_image,
                self.image_text,
                self.search_picture,
            ],
        )  #

    async def _parse_sse_stream(self, response: httpx.Response) -> str:
        """
        解析SSE流数据 - 收集所有事件，返回包含 finished: "Stop" 的最终事件
        Args:
            response (httpx.Response): 异步响应对象
        Returns:
            str: 解析后的事件数据字符串（最终结果）
        Raises:
            Exception: 当无法获取有效数据时抛出
        """
        data_buffer = []
        last_finish_event = None
        response.encoding = "utf-8"

        async for line in response.aiter_lines():
            line = line.strip()
            if line.startswith("data:"):
                data_value = line[5:].strip()
                data_buffer.append(data_value)
            elif line == "":  # 空行表示事件结束
                if data_buffer:
                    event_data = "\n".join(data_buffer)
                    data_buffer = []
                    # 检查是否是最终事件（必须包含 finished: "Stop"）
                    try:
                        event_json = json.loads(event_data)
                        # 检查 event_json 是否为 None 或不是字典类型
                        if not isinstance(event_json, dict):
                            continue
                        if event_json.get("finished") == "Stop":
                            # 这是最终事件，立即返回
                            return event_data
                        elif event_json.get("status") == "finish":
                            # 这是 finish 状态事件，保存但继续等待最终事件
                            last_finish_event = event_data
                    except json.JSONDecodeError:
                        pass

        # 处理最后一个事件（如果没有空行结尾）
        if data_buffer:
            event_data = "\n".join(data_buffer)
            try:
                event_json = json.loads(event_data)
                # 检查 event_json 是否为 None 或不是字典类型
                if isinstance(event_json, dict):
                    if event_json.get("finished") == "Stop":
                        return event_data
                    elif event_json.get("status") == "finish":
                        last_finish_event = event_data
            except json.JSONDecodeError:
                pass

        # 如果没有找到 finished: "Stop" 事件，返回最后一个 finish 事件
        if last_finish_event:
            return last_finish_event

        raise Exception(f"服务请求返回信息为空: {response.status_code}")

    def _extract_uid_from_path(self, path: str):
        """
        从文件路径中提取UID（用于与headers中的UID校验）
        规则:
        1. 如果路径以 'public' 开头（第一个有效目录名），返回 'public' 表示放行
        2. 否则提取第一个出现的 '/upload' 前的最后一个目录名作为UID
        3. 路径无效或无法提取时返回 None
        参数:
            path: 文件路径字符串
        返回:
            str:
                'public' - 表示public路径需放行
                uid字符串 - 成功提取的UID
                None - 路径无效或提取失败
        """
        if not path:
            return None
        # 标准化路径：合并连续斜杠
        normalized_path = re.sub(r"/+", "/", path)
        # 提取第一个有效目录名（忽略开头/结尾的斜杠）
        stripped_path = normalized_path.strip("/")
        if not stripped_path:
            return None
        first_dir = stripped_path.split("/", 1)[0]
        # 检查是否public路径
        if first_dir == "public":
            return "public"
        # 查找第一个 '/upload' 位置
        upload_index = normalized_path.find("/upload")
        if upload_index == -1:
            return None
        # 提取 '/upload' 前的部分并移除末尾斜杠
        prefix = normalized_path[:upload_index].rstrip("/")
        if not prefix:
            return None
        # 取最后一段作为UID
        return prefix.split("/")[-1]

    def _remove_prefix(self, file_path):
        prefix = "/largemodel/llmstudio/fs/"
        if file_path.startswith(prefix):
            # 截取前缀之后的部分
            return file_path[len(prefix) :]
        return file_path  # 如果不匹配前缀，返回原始路径

    async def _do_search_request(
        self, client: httpx.AsyncClient, query_sentence: str
    ) -> dict:
        """执行实际的搜索请求"""
        headers = {"Content-Type": "application/json"}
        json_parameter = {
            "query_sentence": query_sentence,
            "query_type_code": self.cfg.query_type_code_search,
            "user_id": self.user,
            "source_type": self.cfg.source_type,
            "summarize": self.cfg.summarize,
        }

        async with client.stream(
            "POST",
            self.cfg.search_base_url,  # type: ignore
            headers=headers,
            json=json_parameter,
        ) as response:
            if response.status_code != 200:
                error_msg = f"搜索接口请求异常: {response.status_code}"
                logger.bind(uid=self.record_id).error(str(error_msg))
                raise Exception(error_msg)

            event_data = await self._parse_sse_stream(response)
            return json.loads(event_data)

    async def get_search(self, run_context: RunContext, keywords: str):
        """
        联网检索，用于获取新闻、政策、天气、科技进展、冷门知识、文化趋势、节假日查询等信息。

        Args:
            keywords (str): 检索关键词，抽取关键词时必须言简意赅，不能超过 3 个，例如：
                - *月*日 国内新闻
                - 北京 热门景点
                - 北京上海 高铁 时间表

        Returns:
            str: A JSON formatted string containing the search results.
        """
        global _search_semaphore

        max_retries = 3
        retry_delay = 0.5  # 重试间隔（秒）

        for attempt in range(max_retries):
            try:
                # 使用信号量控制并发（确保串行执行）
                async with _search_semaphore:  # type: ignore
                    logger.bind(uid=self.record_id).info(
                        f"get_search 开始查询 (attempt {attempt + 1}/{max_retries}): {keywords}"
                    )

                    with logger.bind(uid=self.record_id).catch(
                        reraise=True, message="解析异常!"
                    ):
                        # 设置详细的超时参数：连接5秒，读取使用配置超时
                        timeout_config = httpx.Timeout(
                            connect=5.0,  # 连接超时
                            read=self.cfg.timeout or 50,  # 读取超时
                            write=10.0,  # 写入超时
                            pool=5.0,  # 连接池获取超时
                        )
                        async with httpx.AsyncClient(timeout=timeout_config) as client:
                            data_content = await asyncio.wait_for(
                                self._do_search_request(client, keywords),
                                timeout=(self.cfg.timeout or 50) + 10,  # 额外10秒缓冲
                            )

                # 检查搜索结果
                # print(f"get_search 结果：{data_content}")
                result_list = data_content.get("response", {}).get("result", [])

                # 如果结果为空，可能是并发问题，重试
                if len(result_list) == 0:
                    logger.bind(uid=self.record_id).warning(
                        f"get_search 返回空结果 (attempt {attempt + 1}/{max_retries}): {keywords}"
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)  # 固定延迟
                        continue
                    else:
                        # 最后一次尝试仍然失败
                        yield json.dumps(
                            {"content": "未查询到相关数据"}, ensure_ascii=False
                        )
                        return

                # 处理搜索结果
                res_content = ""
                citations = []
                for i in range(min(5, len(result_list))):
                    if "text" in result_list[i]:
                        res_content += result_list[i]["text"]
                        if result_list[i].get("file_info"):
                            citations.append(result_list[i].get("file_info"))

                meta_data = RunContentEvent(
                    agent_id=f"get_search_toolkit",
                    agent_name="get_search_toolkit",
                    citations=Citations(raw=citations),
                )

                yield ExternalAgentRunResponseContentEvent(
                    type="citation",
                    agent_id=run_context.session_id,
                    run_id=run_context.run_id,
                    agent_name=run_context.session_id,
                    session_id=run_context.session_id,
                    content="",
                    metadata=meta_data,
                )
                yield json.dumps(
                    {"content": res_content, "citations": citations}, ensure_ascii=False
                )
                return

            except Exception as e:
                logger.bind(uid=self.record_id).error(
                    f"get_search 异常 (attempt {attempt + 1}/{max_retries}): {keywords}, error: {str(e)}"
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    yield json.dumps(
                        {"content": f"搜索失败: {str(e)}"}, ensure_ascii=False
                    )
                    return

    async def get_weather(self, query_sentence: Optional[str]):
        """
        查询目标城市近7天的天气信息并返回查询结果,需要给出具体时间和地点

        Args:
            query_sentence (Optional[str]): 用户请求的查询内容,例如`北京今天的天气`

        Returns:
            查询结果
        """
        headers = {"Content-Type": "application/json"}
        json_parameter = {
            "query_sentence": query_sentence,
            "query_type_code": self.cfg.query_type_code_weather,
            "user_id": self.user,
            "source_type": self.cfg.source_type,
        }
        with logger.bind(uid=self.record_id).catch(reraise=True, message="解析异常!"):
            async with httpx.AsyncClient(timeout=self.cfg.timeout) as client:
                # 发起异步POST请求（流式）
                async with client.stream(
                    "POST",
                    self.cfg.search_base_url,  # type: ignore
                    headers=headers,
                    json=json_parameter,
                ) as response:
                    # 检查HTTP状态码
                    if response.status_code != 200:
                        error_msg = f"搜索接口请求异常: {response.status_code}"
                        raise Exception(error_msg)
                    # 调用SSE流解析函数
                    event_data = await self._parse_sse_stream(response)
                    # 解析结果
                    data_content = json.loads(event_data)
                    if len(data_content.get("response", {}).get("result", [])) == 0:
                        return json.dumps(
                            {"content": "未查询到相关数据"}, ensure_ascii=False
                        )

                    content = data_content["response"]["result"][0]["text"]
                    return json.dumps({"content": content}, ensure_ascii=False)

    async def generate_image(
        self,
        prompt: Optional[str],
        height: Optional[int] = 1024,
        width: Optional[int] = 1024,
        style_tag: Optional[int] = 0,
        n: Optional[int] = 1,
        txt2ImgRatio: Optional[str] = "1:1",
        enhance: Optional[int] = 1,
        watermark: Optional[int] = 1,
    ):
        """
        根据用户需求进行绘画创作(漫画、水彩、油画等多种风格的图像。请注意，本工具专注于艺术创作，无法生成数据图表、表格等信息图),支持生成1-4张图片。结果图会直接返回给用户，你可以直接回答“以上是为您生成的***”

        Args:
            prompt (Optional[str]): 用户请求生成的图片描述
            height(Optional[int]): 生成图片高，默认是1024
            width(Optional[int]): 生成图片宽，默认是1024
            style_tag(Optional[int]): 生成风格，默认是0，base model，可选1,2,3。1表示油画风格；2表示素描风格；3表示水彩风格
            n(Optional[int]): 生成图片数量，默认是1，可选1,2,3,4
            txt2ImgRatio(Optional[str]): 生成图片比例，默认是1:1，可选3:4、4:3、16:9、9:16
            enhance(Optional[int]): 是否扩写，0:不扩写 1:扩写。默认1
            watermark(Optional[int]): 是否添加水印，0:无水印 1:有水印 2: AI水印。默认1

        Returns:
            str: A JSON formatted string containing the search results.
        """
        headers = {
            "content-type": "application/json",
            "Authorization": self.authorization,
        }
        json_parameter = {
            "modelId": self.cfg.modelId_t2i,  # cntxt2image
            "input": prompt,
            "height": height,
            "width": width,
            "style_tag": style_tag,
            "n": n,
            "txt2ImgRatio": txt2ImgRatio,
            "imgReturnType": "base64",
            "enhance": enhance,
            "watermark": watermark,
            "recordId": self.record_id,
            "sourceType": self.cfg.sourceType,
            "chatType": self.cfg.chatType,
            "userId": self.user,
        }

        async with httpx.AsyncClient(timeout=self.cfg.timeout) as client:
            # 发起异步POST请求（流式）
            async with client.stream(
                "POST",
                self.cfg.scheduler_url,  # type: ignore
                headers=headers,  # type: ignore
                json=json_parameter,
            ) as response:

                # 检查HTTP状态码
                if response.status_code != 200:
                    error_msg = f"模型服务请求异常: {response.status_code}"
                    raise Exception(error_msg)
                    # return json.dumps({"content": error_msg}, ensure_ascii=False)

                # 调用SSE流解析函数
                event_data = await self._parse_sse_stream(response)
                # 解析结果
                # 目标是 文图输出base64，落到workspace/runs/下
                with logger.bind(uid=self.record_id).catch(
                    reraise=True, message="解析异常!"
                ):
                    imgs = []
                    data_dict = json.loads(event_data)
                    if "finished" in data_dict and data_dict["finished"] == "Stop":
                        # 安全地获取数据，处理可能的 None 值
                        parts = data_dict.get("parts", [])
                        if not parts:
                            return json.dumps(
                                {
                                    "content": "图像生成失败：返回数据格式异常（无parts）"
                                },
                                ensure_ascii=False,
                            )

                        content = parts[0].get("content", {}) if parts else {}
                        if content is None:
                            return json.dumps(
                                {
                                    "content": "图像生成失败：返回数据格式异常（content为空）"
                                },
                                ensure_ascii=False,
                            )

                        text_value = content.get("text", "")
                        image_data = content.get("data", [])

                        if not image_data:
                            return json.dumps(
                                {
                                    "content": text_value
                                    or "图像生成失败：未返回图片数据"
                                },
                                ensure_ascii=False,
                            )

                        for item in image_data:
                            if item and item.get("type") == "b64_json":
                                # 从image_data中提取type='b64_json'时的url（存储的是图片base64字符串）
                                base64_str = item.get("url", "")
                                if not base64_str:
                                    continue
                                # 创建runs目录
                                runs_dir = os.path.join(self.workspace, "runs")  # type: ignore
                                os.makedirs(runs_dir, exist_ok=True)
                                # 生成唯一文件名
                                img_name = f"{uuid.uuid4()}.jpg"
                                img_path = os.path.join(runs_dir, img_name)
                                # 解码base64并保存
                                with open(img_path, "wb") as f:
                                    f.write(base64.b64decode(base64_str))
                                # 构建相对路径
                                # relative_path = os.path.join('runs', img_name)
                                imgs.append(img_path)
                        # 构建返回结果
                        if imgs:
                            return json.dumps(
                                {"content": text_value, "images": imgs},
                                ensure_ascii=False,
                            )
                        else:
                            return json.dumps(
                                {
                                    "content": text_value
                                    or "图像生成失败：未能提取图片数据"
                                },
                                ensure_ascii=False,
                            )

    async def image_text(self, prompt: Optional[str], imagePath: Optional[str]):
        """
        通用的图像识别助手，分析用户提供的图像（上传的图片地址或图片base64编码），输出基于图片的内容描述/问答/创意解读。不得用于水果或工艺品识别。该工具专注于图片分析与理解，生成与图像内容相关的文本输出，而非图像生成。

        Args:
            prompt (Optional[str]): 用户请求的问题
            imagePath:(Optional[str]): 用户上传的图片地址或图片base64编码（字符串长度大于800时，认为是base64编码）

        Returns:
            str: A JSON formatted string containing the search results.
        """
        # 处理 imagePath：如果是文件路径则读取并转为 base64，如果已经是 base64（长度>800）则直接使用
        processed_image_path = imagePath
        if imagePath and len(imagePath) <= 800:
            # 可能是文件路径，尝试读取并转为 base64
            try:
                # 尝试多种路径解析方式
                possible_paths = [
                    imagePath,  # 原始路径
                    os.path.join(self.workspace, imagePath),  # 相对于 workspace
                    os.path.join(self.workspace, "runs", imagePath),  # 相对于 runs 目录
                    os.path.abspath(imagePath),  # 绝对路径
                ]
                image_data = None
                for path in possible_paths:
                    if os.path.exists(path) and os.path.isfile(path):
                        with open(path, "rb") as f:
                            image_data = f.read()
                        logger.bind(uid=self.record_id).info(
                            f"成功读取图片文件: {path}"
                        )
                        break
                if image_data:
                    # 转为 base64 编码
                    processed_image_path = base64.b64encode(image_data).decode("utf-8")
                    logger.bind(uid=self.record_id).info(
                        f"图片已转为 base64，长度: {len(processed_image_path)}"
                    )
                else:
                    logger.bind(uid=self.record_id).warning(
                        f"无法找到图片文件: {imagePath}，将原样传递"
                    )
            except Exception as e:
                logger.bind(uid=self.record_id).error(
                    f"读取图片文件失败: {imagePath}, error: {str(e)}"
                )
                # 出错时仍使用原始值，让下游服务处理

        headers = {
            "content-type": "application/json",
            "Authorization": self.authorization,
        }
        json_parameter = {
            "modelId": self.cfg.modelId_i2t,
            "input": prompt,
            "params": {"top_p": 0.2, "max_gen_len": 256, "temperature": 0},
            "imagePath": processed_image_path,
            "recordId": self.record_id,
            "sourceType": self.cfg.sourceType,
            "chatType": self.cfg.chatType,
            "userId": self.user,
        }
        async with httpx.AsyncClient(timeout=self.cfg.timeout) as client:
            # 发起异步POST请求（流式）
            async with client.stream(
                "POST",
                self.cfg.scheduler_url,  # type: ignore
                headers=headers,  # type: ignore
                json=json_parameter,
            ) as response:
                # 检查HTTP状态码
                if response.status_code != 200:
                    error_msg = f"模型服务请求异常: {response.status_code}"
                    raise Exception(error_msg)
                # 调用SSE流解析函数
                event_data = await self._parse_sse_stream(response)
                # 解析结果
                with logger.bind(uid=self.record_id).catch(
                    reraise=True, message="解析异常!"
                ):
                    data_dict = json.loads(event_data)
                    if "finished" in data_dict and data_dict["finished"] == "Stop":
                        text_value = data_dict["parts"][0]["content"]["text"]
                    return json.dumps({"content": text_value}, ensure_ascii=False)  # type: ignore

    async def _filter_pictures(self, query: str, results: str):
        """
        将搜图结果中的描述与query进行对比，筛选相关性高的图片。

        Args:
            query (str): 用户请求的问题
            results:(str): 搜图返回结果

        Returns:
            筛选出来的结果
        """

        system_prompt = f"""
                    你是一个专业的图片筛选助手，负责根据用户查询从图片搜索结果中筛选最相关的图片。

                    任务要求：
                    1. 仔细分析用户查询："{query}"、"{query}"的语义含义、"{query}"对应的英文
                    2. 从以下搜索结果中，根据每张图片的description文本描述，筛选出与第1条任务中最相关的图片
                    3. 请返回一个完整的JSON对象，格式与原始搜索结果完全一致
                    4. 确保保留所有原始字段，特别是URL链接必须完整保留，不得截断或修改
                    5. 只保留真正相关的图片，不相关的图片应被过滤掉
                    6. 请思考图片的语义相关性，而不仅仅是关键词匹配

                    原始搜索结果：
                    {results}

                    请直接返回筛选后的JSON对象，不要添加任何额外的文本说明或解释。
                    """

        headers = {
            "content-type": "application/json",
            "Authorization": self.authorization,
        }
        json_parameter = {
            "model": self.cfg.modelId_searchPicture,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": system_prompt},
            ],
            "recordId": self.record_id,
            "sourceType": self.cfg.sourceType,
            "user": self.user,
            "stream": False,
        }
        try:
            async with httpx.AsyncClient(timeout=self.cfg.timeout) as client:
                # 发起异步POST请求（非流式）
                response = await client.post(
                    url=self.cfg.scheduler_url_v3, headers=headers, json=json_parameter
                )
                content = json.loads(response.text)
                try:
                    data_str = content["choices"][0]["message"]["content"]
                    return data_str
                except Exception as e:
                    return json.dumps(
                        {"content": "过滤图片结果解析失败"}, ensure_ascii=False
                    )
        except httpx.TimeoutException:
            logger.error("tool timeout:筛选图片模型服务请求超时")
            return json.dumps(
                {"content": "tool timeout:筛选图片服务请求超时"}, ensure_ascii=False
            )

    async def search_picture(self, query: str):
        """
        用于根据关键词搜索与网页内容匹配的图片，返回可用的图片链接和描述，仅在网页需要插入图片时调用，无图片需求时不调用。
        搜索图片使用的关键词，通过“剔除修饰词、锁定核心主体”确定，例如：咖啡、游乐园。另外，可以从多维度衍生、改写关键词：
                 1）通用化：包含具体地名（例如中国、北京）的内容可以去掉地名，搜索通用的主体词，例如北京环球影城，可以只搜索环球影城。
                 2）语义关联法：可以挖掘核心词的同义词、近义词、上下位词，扩大检索范围；
                 3）元素拆解法：拆分主体涉及的核心元素，比如场景中的物品、人物、动作等；
        Args:
           query  (str): 搜索图片使用的关键词，仅搜索主体词或通用词。
        Returns:
            搜索出来的图像
        """
        _url = f"https://api.unsplash.com/search/photos?client_id={random.choice(self.cfg.client_ids)}&query={query}&content_filter=high&lang=zh-Hans&orientation=landscape"
        headers = {"Content-Type": "application/json"}
        json_parameter = {
            "query_sentence": _url,
            "query_type_code": self.cfg.query_type_code_searchPicture,
            "user_id": self.user,
            "source_type": self.cfg.source_type,
        }
        async with httpx.AsyncClient(timeout=self.cfg.timeout) as client:
            # 发起异步POST请求（流式）
            async with client.stream(
                "POST", self.cfg.search_base_url, headers=headers, json=json_parameter
            ) as response:
                # 检查HTTP状态码
                if response.status_code != 200:
                    error_msg = f"搜索接口请求异常: {response.status_code}"
                    raise RuntimeError(error_msg)
                # 调用SSE流解析函数
                event_data = await self._parse_sse_stream(response)  #
                # 解析结果
                with logger.bind(uid=self.record_id).catch(
                    reraise=True, message="解析异常!"
                ):
                    data_content = json.loads(event_data)
                    result_list = data_content.get("response", {}).get("result", [])
                    # 条件1：result 本身是空列表
                    # 条件2：result 有元素且第一个元素的 text 等于 '[]'
                    if not result_list or (
                        len(result_list) > 0 and result_list[0].get("text") == "[]"
                    ):
                        return json.dumps(
                            {"content": "未查询到相关数据"}, ensure_ascii=False
                        )
                        # return
                    content = data_content["response"]["result"][0][
                        "text"
                    ]  # 解析后的json
                    # 选择相关性高的
                    result = await self._filter_pictures(query, content)  # 输出是列表
                    result_dict = {"key_words": query, "image": result}
                    return json.dumps(result_dict, ensure_ascii=False)
