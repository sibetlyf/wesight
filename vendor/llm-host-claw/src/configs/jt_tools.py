from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from .common import ToolkitConfigBase



class JtToolsConfig(ToolkitConfigBase):
    timeout: Optional[int] = 50
    # 搜索服务接口
    search_base_url: Optional[str] = "http://36.134.89.82:30053/v1/search/completions"
    source_type: Optional[str] = "plugin"
    summarize: Optional[bool] = False
    query_type_code_search: Optional[str] = "1-2"
    query_type_code_weather: Optional[str] = "1-1"
    query_type_code_date: Optional[str] = "1-6"

    # 调度接口
    scheduler_url: Optional[str] = "http://36.134.89.82:30518/scheduler/v2/completions"
    sourceType: Optional[str] = "klbase"
    chatType: Optional[int] = 2

    modelId_t2i: Optional[str] = "cntxt2image"
    modelId_i2t: Optional[str] = "LLMImage2Text"
    modelId_video: Optional[str] = "video_to_text"

    # 搜图服务
    client_ids: List[str] = Field(
        default=["1OyRwKBUKEOE8OcxR8Eu6X4xtbZIcN3oex3BsYhELVM", "5lziOgYaGTjeYyDfvt7q2GuoXwsaTQu6aQjUvw4txqM",
                 "ygx5wMcjqBVBLxcPz65zR8gSYVIYUmQkuDnTpX9Cwoc"])
    query_type_code_searchPicture: Optional[str] = "1-8"
    scheduler_url_v3: Optional[str] = "http://36.134.89.82:30507/scheduler/v3/chat/completions"
    modelId_searchPicture: Optional[str] = "qwen3-next-80b"
    max_url_cnt: Optional[int] = Field(default=10, description="查询最大数量")
    time_filter: Optional[int] = Field(default=10, description="")  # 补充解释参数含义

    target: Literal["core.tools.jt_tools.JtTools"] = "core.tools.jt_tools.JtTools" #type: ignore





