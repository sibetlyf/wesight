from typing import Literal, Optional
from pydantic import BaseModel, Field


class AgentMode(BaseModel):
    mode: Literal["subagent", "router", "all"] = Field(
        default="router",
        description="智能体的运行模式，router模式下当前Agent运行结束后会直接退出该Agent的任务",
    )
    permission: Optional[Literal["Plan", "Execute"]] = Field(
        default=None, description="智能体的权限，Ask模式只能进行对话，无法操作本地文件"
    )
