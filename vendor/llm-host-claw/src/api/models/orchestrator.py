from pydantic import BaseModel, Field
from typing import Optional
from protocol.extra_info import ExtraInfo


class OrchestratorRunRequest(BaseModel):
    """Orchestrator 运行请求模型"""
    message: str = Field(..., description="用户消息")
    session_id: Optional[str] = Field(None, description="会话 ID")
    userspace: Optional[str] = Field(None, description="用户空间根目录")
    extra: Optional[ExtraInfo] = Field(None, description="额外信息")
