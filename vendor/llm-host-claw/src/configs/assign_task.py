from typing import Literal, List
from pydantic import Field
from configs.common import CompressionManagerConfig, ToolkitConfigBase, ModelConfig


class AssignTaskConfig(ToolkitConfigBase):
    target: Literal["core.tools.assign_task.AssignTaskTools"] = "core.tools.assign_task.AssignTaskTools"  # type: ignore
    unauthorize_tools: List[str] = [
        "write_todo",
        "update_todo",
        "modify_todo",
        "create_subagent",
        "assign_task",
        "publish_artifact",
    ]

    model: ModelConfig = Field(
        default=ModelConfig(id="glm-5.1"),
        description="The model configuration used for the subagent in assign_task tool.",
    )
    compression_manager: CompressionManagerConfig = Field(
        default=CompressionManagerConfig(),
        description="The configuration of the compression manager used in assign_task tool.",
    )
