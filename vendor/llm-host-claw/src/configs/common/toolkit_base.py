from pydantic import BaseModel,Field,ConfigDict
from typing import Optional,List

class ToolkitConfigBase(BaseModel):
    model_config = ConfigDict(extra="allow")
    exclude_tools: Optional[List[str]] = Field(default=None, description="被排挤的工具，加入将不可用")
    timeout: Optional[int] = 60
    target:str=Field(description="必须配置的项目，用于实现工具的实例化，例如`tools.amap_tools.AmapTools`")