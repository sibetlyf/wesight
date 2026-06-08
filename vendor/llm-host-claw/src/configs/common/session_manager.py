from typing import Optional

from pydantic import BaseModel, Field

from .model import ModelConfig


class SessionManagerConfig(BaseModel):
    """
    会话管理器配置
    """

    model: ModelConfig = Field(
        default=ModelConfig(id="qwen3-next-80b"),
        description="The model configuration of the session manager.",
    )
    last_n_runs: Optional[int] = Field(
        default=None,
        description="The maximum number of runs to use for session summary generation.",
    )
    conversation_limit: Optional[int] = Field(
        default=None,
        description="The maximum number of messages to use for session summary generation.",
    )
