from typing import List, Optional

from pydantic import BaseModel, Field

from .model import ModelConfig


class CompressionManagerConfig(BaseModel):
    """
    工具上下文压缩管理器配置
    """

    compress_tool_results_limit: Optional[int] = Field(
        default=None,
        description="The maximum number of tool results to compress.",
    )
    compress_token_limit: Optional[int] = Field(
        default=None,
        description="超过多少 token 的时候开始压缩",
    )

    model: ModelConfig = Field(
        default=ModelConfig(id="qwen3-next-80b"),
        description="The model configuration of the compression manager.",
    )
    tool_keep_last: List[List[str]] = Field(
        default=[["write_todo", "update_todo", "modify_todo"]],
        description="出现在这个列表意味着压缩时只保留最后一个工具调用结果，前面的直接 cut",
    )
    tool_not_compress: List[str] = Field(
        default=["assign_task", "read_file"],
        description="出现在这个列表意味着不压缩这个工具调用结果",
    )
