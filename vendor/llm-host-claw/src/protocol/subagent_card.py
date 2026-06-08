from typing import Optional
from pydantic import BaseModel, Field
from typing import List, Dict, Any
from protocol.agent_mode import AgentMode


class SubAgentCard(BaseModel):
    """
    name (str): 子智能体的名称。
    description (str): 子智能体的简要描述。
    instructions (str): 子智能体的指令。
    tools (List[str]): 子智能体可使用的工具列表。
    skills (List[str]): 子智能体具备的技能列表。
    """

    name: str = Field(..., description="子智能体的名称。")
    description: str = Field(..., description="子智能体的简要描述。")

    instructions: str = Field(..., description="子智能体的指令。")
    tools: List[str] = Field(..., description="子智能体可使用的工具列表。")
    skills: List[str] = Field(..., description="子智能体具备的技能列表。")

    # router模式下Agent相关参数
    agent_mode: Optional[AgentMode] = Field(
        default=None, description="Agent的运行模式，默认为agent模式。"
    )
    stop_after_agent_run: Optional[str] = Field(
        default=None, description="当前Agent任务结束后直接停止，不再将结果返回给上层Agent。"
    )
    model: Optional[str] = Field(default=None, description="Agent使用的模型。")
    entrypoint: Optional[str] = Field(default=None, description="内置函数的调用路径，例如 'core.my_module.my_function'")
    entrypoint_params: Optional[Dict[str, str]] = Field(default=None, description="当作为router entrypoint时，大模型应当提供的JSON参数列表及其描述")
    extra: Optional[Dict[str, Any]] = Field(default=None, description="Agent的额外信息。")
