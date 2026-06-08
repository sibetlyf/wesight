from agno.tools.mcp import MCPTools
from agno.tools.mcp.params import SSEClientParams, StreamableHTTPClientParams
from pydantic import BaseModel, Field
from typing import Optional, Literal, Union, Dict, Any


class MCPCard(BaseModel):
    name: Optional[str] = None
    url: str
    transport: Literal["sse", "streamable-http"] = Field(default="sse", description="MCP服务传输方式")
    headers: Optional[Dict[str, Any]] = None
    timeout: float = 30
    sse_read_timeout: Optional[float] = None

    def model_post_init(self, context: Any, /) -> None:
        #sse_read_time_out 是 timeout*5
        self.sse_read_timeout = self.timeout * 5 if self.sse_read_timeout is None else self.sse_read_timeout

    @property
    def agno_server_params(self) -> Optional[Union[SSEClientParams, StreamableHTTPClientParams]]:
        if self.transport == "streamable-http":
            return StreamableHTTPClientParams(**self.model_dump(include={"url", "headers"}))
        else:
            return SSEClientParams(**self.model_dump(include={"url", "headers", "timeout", "sse_read_timeout"}))
