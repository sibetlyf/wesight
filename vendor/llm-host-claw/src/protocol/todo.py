from pydantic import BaseModel, Field
from enum import Enum
import uuid
import importlib
from typing import Optional, List, Sequence, Union, Dict, Literal, Any, Callable
from agno.models.message import Message
from agno.tools.mcp import MCPTools
from agno.tools import Toolkit, Function


class Step(BaseModel):
    title: str = Field(description="步骤标题")
    content: str = Field(description="任务内容和依赖信息")
    tools: Optional[List[str]] = Field(description="相关工具名称列表")
    dependencies: Optional[List[str]] = Field(default=None, description="本步骤依赖的步骤列表")

    def format(self):
        return f'''{self.title}:{self.content}'''


class StepWithStatus(Step):
    step_id: int = Field(description="步骤ID")
    status: Literal["pending", "completed", "failed", "running"] = Field(default="pending", description="步骤状态")

class Plan(BaseModel):
    mission_id: int = Field(description="计划ID")
    title: str = Field(description="任务标题")
    steps: List[StepWithStatus] = Field(description="步骤列表")
    tools: List[str] = Field(default=[],exclude=True)
    def model_post_init(self, context: Any, /) -> None:
        self.tools = self.tools or []
        # 为每个 step 分配 id

    
    @property
    def done(self) -> bool:
        return all([i.status in ["completed", "failed"] for i in self.steps])



    @classmethod
    def from_step(cls, mission_id: int, title: str, steps: List[Step], tools: Optional[List[str]] = None) -> "Plan":
        steps_with_id: list[StepWithStatus]=[]
        for i, step in enumerate(steps):
            if isinstance(step, Step):
                steps_with_id.append(StepWithStatus(step_id=i+1,**step.model_dump()))
            else:
                steps_with_id.append(step)
        return cls(mission_id=mission_id, title=title, steps=steps_with_id, tools=tools or []) 



    def model_dump_yaml(self) -> str:
        content = self.model_dump()
        import yaml
        return yaml.dump(content, default_flow_style=False, allow_unicode=True)


    

        
