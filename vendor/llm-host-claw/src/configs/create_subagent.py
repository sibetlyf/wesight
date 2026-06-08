from pydantic import BaseModel, Field
from typing import Optional, Literal
from .common import ModelConfig, ToolkitConfigBase


class CreateSubagentConfig(ToolkitConfigBase):
    target: Literal["core.tools.create_subagent.CreateSubagentTools"] = "core.tools.create_subagent.CreateSubagentTools"  # type: ignore
