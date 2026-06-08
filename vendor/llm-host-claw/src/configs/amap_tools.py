from typing import Optional, Literal

from .common import ToolkitConfigBase



class AmapToolConfig(ToolkitConfigBase):
    # 高德地图key
    timeout: Optional[int] = 50
    amap_key: Optional[str] = "cc9fc33cfcf43f1c84efec7db3aed7c6"
    target: Literal["core.tools.amap_tools.AmapTools"] = "core.tools.amap_tools.AmapTools" #type: ignore
