from typing import Optional, AsyncIterable

from agno.run.agent import RunContentEvent
from random import randint


def create_run_response_content_event(
        agent_id: str,
        name: str,
        session_id: str,
        run_id: str,
        model_provider_id: str,
        content: Optional[str] = None,
        reasoning_content: Optional[str] = None,
        **kwargs) -> RunContentEvent:
    """
    创建一个RunResponseContentEvent对象
    """
    return RunContentEvent(
        content=content,
        reasoning_content=reasoning_content,
        agent_id=agent_id,
        agent_name=name,
        session_id=session_id,
        run_id=run_id,
        model_provider_data={"id": model_provider_id},
        **kwargs
    )


# 基于上面的函数写一个流式的方案，大概就是把 content 取 n =randint(0,5)个字符往出推,yield
async def create_run_response_content_event_stream(
        agent_id: str,
        name: str,
        session_id: str,
        run_id: str,
        model_provider_id: str,
        content: Optional[str] = None,
        reasoning_content: Optional[str] = None,
        **kwargs) -> AsyncIterable[RunContentEvent]:
    '''
    顺序取n 个字符并推送，模拟流式推送
    '''

    while reasoning_content:
        n = randint(0, 5)
        yield create_run_response_content_event(
            agent_id=agent_id,
            name=name,
            session_id=session_id,
            run_id=run_id,
            model_provider_id=model_provider_id,
            content=None,
            reasoning_content=reasoning_content[:n],
            **kwargs
        )
        reasoning_content = reasoning_content[n:]

    while content:
        n = randint(0, 5)
        yield create_run_response_content_event(
            agent_id=agent_id,
            name=name,
            session_id=session_id,
            run_id=run_id,
            model_provider_id=model_provider_id,
            content=content[:n],
            reasoning_content=None,
            **kwargs
        )
        content = content[n:]
