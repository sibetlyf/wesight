from agno.compression.manager import CompressionManager
from dataclasses import dataclass, field
from typing import Optional, override
import asyncio
from textwrap import dedent
from typing import List, Optional

from agno.metrics import RunMetrics


from agno.models.base import Model
from agno.models.message import Message
from agno.models.utils import get_model
from agno.utils.log import log_error, log_warning


from configs.common import CompressionManagerConfig

DEFAULT_COMPRESSION_PROMPT_WITH_QUERY = dedent("""你是用于压缩工具调用结果的工具。

目标：
基于“工具输入参数”，提取并压缩工具输出中的关键信息，仅保留与参数直接相关的内容。

---

规则：

1. 相关性
• 在工具输入清晰明确的场景下，仅保留与工具输入参数直接相关的信息  
• 在工具输入不清晰或不明确的场景下，保留所有信息，仅进行长度压缩

2. 抗幻觉（强约束）
• 只能使用工具输出中明确存在的信息  
• 禁止补充、推测、改写为更具体内容  
• 禁止新增任何实体、数字、时间、结论  

3. 保留要素（若相关）
• 数字、价格、数量、统计  
• 时间（格式："2025年10月21日"）  
• 实体（人/公司/产品/地点）  
• 标识符（URL / ID / 版本等）  

4. 压缩方式
• 保留关键内容，概括其他内容
• 列表裁剪为最相关项  
• 不做解释、不加背景  

5. 异常处理
• 无相关信息 → 输出内容概要  
• 信息不完整 → 保留原始片段，不补全  

---

示例：


Tool: search(query="OpenAI 产品发布")
Tool Result: OpenAI 在近期发布了多个产品。2025 年 10 月 21 日推出 ChatGPT Atlas（AI 浏览器，支持 macOS）；2025 年 10 月 6 日推出 Apps in ChatGPT（包含 SDK）。此外还宣布与 Spotify、Zillow、Canva 建立合作关系，并计划扩展企业市场。

压缩后的输出：
OpenAI - 2025年10月21日推出ChatGPT Atlas（macOS）；2025年10月6日：Apps in ChatGPT + SDK

---

核心原则：

只提取，不创造；只压缩，不推理；所有内容必须可在工具输出中定位。
""")


@dataclass
class CustomCompressionManager(CompressionManager):
    """
    工具上下文压缩管理器
    """

    # 只保留最后一个工具调用结果，前面的直接 cut
    tool_keep_last: List[List[str]] = field(
        default_factory=lambda: [["write_todo", "update_todo"]]
    )
    tool_not_compress: List[str] = field(default_factory=list)

    @classmethod
    def from_config(
        cls,
        cfg: CompressionManagerConfig,
        api_key: Optional[str],
    ) -> "CustomCompressionManager":
        return cls(
            compress_tool_results_limit=cfg.compress_tool_results_limit,
            compress_token_limit=cfg.compress_token_limit,
            tool_keep_last=cfg.tool_keep_last,
            tool_not_compress=cfg.tool_not_compress,
            model=cfg.model.get_model(
                api_key=api_key,
            ),
        )

    async def _acompress_tool_result_by_model(
        self,
        query: Optional[Message],
        tool_result: Message,
        run_metrics: Optional["RunMetrics"] = None,
    ) -> Optional[str]:
        """Async compress a single tool result"""
        if not tool_result:
            return None

        if tool_result.content and len(str(tool_result.content)) <= 2000:
            return str(tool_result.content)  # type: ignore
        # 不再使用 query 导向压缩
        if tool_result.tool_args:
            args = ",".join([f"{k}={v}" for k, v in tool_result.tool_args.items()])
        else:
            args = "*"
        tool_content = f"Tool: {tool_result.tool_name or 'unknown'}({args})\nTool Result: {tool_result.content}"

        self.model = get_model(self.model)
        if not self.model:
            log_warning("No compression model available")
            return None

        compression_prompt = (
            self.compress_tool_call_instructions
            or DEFAULT_COMPRESSION_PROMPT_WITH_QUERY
        )
        compression_message = tool_content

        try:
            response = await self.model.aresponse(
                messages=[
                    Message(role="system", content=compression_prompt),
                    Message(role="user", content=compression_message),
                ]
            )

            # Accumulate compression model metrics
            if run_metrics is not None:
                from agno.metrics import ModelType, accumulate_model_metrics

                accumulate_model_metrics(
                    response, self.model, ModelType.COMPRESSION_MODEL, run_metrics
                )

            return f"[压缩后的工具执行结果]\n{response.content}"
        except Exception as e:
            log_error(f"Error compressing tool result: {e}")
            return tool_content

    async def _acompress_tool_result_by_cut(
        self,
        tool_result: Message,
        run_metrics: Optional["RunMetrics"] = None,
    ) -> Optional[str]:
        """Async compress a single tool result by cut off"""
        if not tool_result:
            return None
        # 保留前5个字符和后5个字符,中间采用占位符标识
        return "\n".join([tool_result.content[:5], "...", "[工具执行结果已折叠，你可以再次调用该工具获取完整结果]", "...", tool_result.content[-5:]])  # type: ignore

    async def _no_compress(
        self, tool_result: Message, run_metrics: Optional["RunMetrics"] = None
    ) -> Optional[str]:
        """Async compress a single tool result by no compress"""
        return tool_result.content  # type: ignore

    def __in_which_tool_keep_last(self, tool_name: Optional[str]) -> int:
        """判断工具是否在压缩列表中"""
        if not tool_name:
            return -1
        elif tool_name in self.tool_not_compress:
            return -2
        for idx, keep_last_one in enumerate(self.tool_keep_last):
            if tool_name in keep_last_one:
                return idx
        return -1

    @override
    async def acompress(
        self,
        messages: List[Message],
        run_metrics: Optional["RunMetrics"] = None,
    ) -> None:
        """Async compress uncompressed tool results"""
        if not self.compress_tool_results:
            return

        uncompressed_tools = [
            msg
            for msg in messages
            if msg.role == "tool" and msg.compressed_content is None
        ]

        if not uncompressed_tools:
            return

        # 尝试获取最后的用户输入
        last_user = next((msg for msg in messages if msg.role == "user"), None)

        # Track original sizes before compression
        original_sizes = [
            len(str(msg.content)) if msg.content else 0 for msg in uncompressed_tools
        ]

        # 采用不同压缩方式,-1采用模型压缩，其他数字应当考虑压缩前面相同数字的，并保留最后一个
        tasks = []
        squeeze_way = [
            self.__in_which_tool_keep_last(msg.tool_name) for msg in uncompressed_tools
        ]
        for idx, way in enumerate(squeeze_way):
            if way == -1:
                tasks.append(
                    self._acompress_tool_result_by_model(
                        last_user, uncompressed_tools[idx], run_metrics=run_metrics
                    )
                )

            elif way in squeeze_way[idx + 1 :]:  # 保留最后一个
                tasks.append(
                    self._acompress_tool_result_by_cut(
                        uncompressed_tools[idx], run_metrics=run_metrics
                    )
                )
            elif way == -2:
                tasks.append(
                    self._no_compress(uncompressed_tools[idx], run_metrics=run_metrics)
                )
            else:
                tasks.append(
                    self._no_compress(uncompressed_tools[idx], run_metrics=run_metrics)
                )

        # Parallel compression using asyncio.gather
        results = await asyncio.gather(*tasks)

        # Apply results and track stats
        for msg, compressed, original_len in zip(
            uncompressed_tools, results, original_sizes
        ):
            if compressed:
                msg.compressed_content = compressed
                # Count actual tool results (Gemini combines multiple in one message)
                tool_results_count = len(msg.tool_calls) if msg.tool_calls else 1
                self.stats["tool_results_compressed"] = (
                    self.stats.get("tool_results_compressed", 0) + tool_results_count
                )
                self.stats["original_size"] = (
                    self.stats.get("original_size", 0) + original_len
                )
                self.stats["compressed_size"] = self.stats.get(
                    "compressed_size", 0
                ) + len(compressed)
            else:
                log_warning(f"Compression failed for {msg.tool_name}")
