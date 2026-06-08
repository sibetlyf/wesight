from dataclasses import dataclass
from typing import Optional, Any, Dict
from typing import Literal
from agno.run.agent import RunOutputEvent, CustomEvent, RunOutput


@dataclass
class ExternalAgentRunResponseContentEvent(CustomEvent):
    # type:
    #   - content: 出现在正文，delta
    #   - document: 第三方智能体输出，侧边栏，delta
    #   - citation: 引用，取citation中的内容
    event: str = "ExternalAgentRunResponseContentEvent"
    type: Literal["content", "citation", "document"] = "document"
    metadata: Optional[Any] = None
    mode: Optional[Literal["subagent", "router"]] = "subagent"

    @property
    def call_id(self) -> Optional[str]:
        return self.tool_call_id

    def __post_init__(self):
        valid_types = {"content", "citation", "document"}
        if self.type not in valid_types:
            raise ValueError(
                f"Invalid type: '{self.type}'. Must be one of {valid_types}"
            )

    def __str__(self):
        if self.content:
            return self.content
        else:
            return ""

    def to_dict(self) -> Dict[str, Any]:
        raw = super().to_dict()
        raw["metadata"] = self.metadata.to_dict() if self.metadata else None
        return raw
