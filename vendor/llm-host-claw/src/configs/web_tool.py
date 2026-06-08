from pydantic import Field,BaseModel
from typing import Optional, Union, List, Callable, Any, Dict, Literal

from .common import ModelConfig, ToolkitConfigBase

class WebToolConfig(ToolkitConfigBase):
    description: str = Field(
        default="你是一名专业的网页设计师、前端开发专家，对现代Web设计趋势和最佳实践有深入理解，尤其擅长创造具有极高审美价值的用户界面。你的设计作品不仅功能完备，而且在视觉上令人惊叹，能够给用户带来强烈的'Aha-moment'体验。")
    instructions: str = Field(default='''
         请将用户提供的原始文本核心信息，分析其内容、并将其转化为清晰美观、内容丰富、易于阅读的可视化HTML网页代码。请充分发挥你的专业判断，选择最能体现内容精髓的设计风格、配色方案、排版和布局。代码格式必须正确，我希望可以直接复制这段代码生成网页。''')
    model: ModelConfig = Field(default=ModelConfig(id="qwen3-next-80b"))#
    add_external_tools: Optional[bool] = Field(default=True, description="是否添加外部工具")  #搜图工具打开
    tool_call_limit: int = Field(default=7, description="工具调用次数限制")
    add_skill: Optional[bool] = Field(default=True, description="是否添加skill")
    expected_output: Optional[str] = Field(default=None, description="预期输出")
    target: Literal["core.tools.web_tool.WebTool"] = "core.tools.web_tool.WebTool" #type: ignore
