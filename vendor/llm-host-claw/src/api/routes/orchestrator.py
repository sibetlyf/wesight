from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import json
from typing import AsyncGenerator

from api.models.orchestrator import OrchestratorRunRequest
from core.orchestrator import Orchestrator
from moma_cli.bootstrap import bootstrap_environment
from protocol.response_events import ResponseEventEnvelope

router = APIRouter()


@router.post("/run")
async def run_orchestrator(request: OrchestratorRunRequest):
    """运行 Orchestrator"""
    try:
        bootstrap_environment(
            config_path=None,
            mcp_config_path=None,
            workspace=request.userspace,
            session_id=request.session_id,
            user_id=None,
            api_key=None,
            authorization=None,
            sandbox=False,
            sandbox_root=None,
            require_orchestrator_config=False,
        )

        # 创建 Orchestrator 实例
        orchestrator = Orchestrator()

        # 定义流式响应的生成器
        async def event_generator() -> AsyncGenerator[str, None]:
            async for event in orchestrator.run(request.message, request.extra):
                event = event if isinstance(event, ResponseEventEnvelope) else ResponseEventEnvelope.model_validate(event)
                payload = json.dumps(event.model_dump(), ensure_ascii=False)
                yield f"event: {event.type}\n"
                yield f"data: {payload}\n\n"

        # 返回流式响应
        return StreamingResponse(event_generator(), media_type="text/event-stream")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_orchestrator_status():
    """获取 Orchestrator 状态"""
    return {"status": "running", "message": "Orchestrator is ready to process requests"}
