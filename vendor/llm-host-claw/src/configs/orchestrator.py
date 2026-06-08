from pydantic import BaseModel, Field
import os
from typing import Union, List, Optional
from typing_extensions import Annotated
from configs.common import (
    CompressionManagerConfig,
    ModelConfig,
    MongoConfig,
    SQLiteConfig,
    SessionManagerConfig,
)

from configs.assign_task import AssignTaskConfig
from configs.shell import ShellConfig
from configs.amap_tools import AmapToolConfig
from configs.create_subagent import CreateSubagentConfig
from configs.web_tool import WebToolConfig
from configs.jt_tools import JtToolsConfig
from configs.publish_artifact import PublishArtifactConfig
from configs.vibe_toolkit import VibeCodingToolkitConfig
from configs.todo import TodoConfig
from configs.browse_use import BrowserUseConfig

KitUnion = Annotated[
    Union[
        AssignTaskConfig,
        ShellConfig,
        AmapToolConfig,
        CreateSubagentConfig,
        WebToolConfig,
        JtToolsConfig,
        PublishArtifactConfig,
        VibeCodingToolkitConfig,
        TodoConfig,
        BrowserUseConfig,
    ],
    Field(discriminator="target"),
]


class OrchestratorConfig(BaseModel):

    # 基础配置
    model: ModelConfig = Field(
        description="The model configuration of the orchestrator.",
    )
    db: SQLiteConfig | MongoConfig = Field(
        default=SQLiteConfig(),
        description="The database configuration of the orchestrator.",
    )

    # 上下文压缩管理选项
    session_manager: SessionManagerConfig = Field(
        default=SessionManagerConfig(),
        description="The session manager configuration of the orchestrator.",
    )
    add_session_summary_to_context: bool = Field(
        default=True,
        description="Whether to add session summary to context.",
    )
    max_tool_calls_from_history: Optional[int] = Field(
        default=None,
        description="The maximum number of tool calls from history to use.",
    )
    num_history_runs: Optional[int] = Field(
        default=None,
        description="The number of history runs to use.",
    )
    ## 工具输出压缩器
    compression_manager: CompressionManagerConfig = Field(
        default=CompressionManagerConfig(),
        description="The compression manager configuration of the orchestrator.",
    )

    # 工具集
    toolkits: List[KitUnion] = Field(
        description="The toolkits of the orchestrator.",
    )

    @classmethod
    def from_env(cls) -> "OrchestratorConfig":

        if not os.environ.get("ORCHESTRATOR_CONFIG"):
            raise ValueError("ORCHESTRATOR_CONFIG environment variable is not set")
        return cls.model_validate_json(os.environ.get("ORCHESTRATOR_CONFIG"))  # type: ignore

    def to_env(self):
        os.environ["ORCHESTRATOR_CONFIG"] = self.model_dump_json(ensure_ascii=False)
