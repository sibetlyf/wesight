from typing import Union, Any, Optional, AsyncGenerator, cast
import os
from agno.agent import Agent
from agno.agent import Message


from protocol import ExtraInfo, EnVar
from protocol.normalizer import ResponseEventNormalizer, create_response_id
from protocol.response_events import ResponseEventEnvelope, ResponseProtocolContext
from configs.orchestrator import OrchestratorConfig

from core.abilities_loader import load_skills, load_tools
from core.prompt import PromptFactory
from lib.session_manager import CustomSessionManager
from lib.compression_manager import CustomCompressionManager
from protocol.envar import EnVar


class Orchestrator:
    def __init__(
        self,
        *,
        cfg: Optional[OrchestratorConfig] = None,
        envar: Optional[EnVar] = None,
    ):

        self.envar = envar or EnVar.from_env()
        self.cfg = cfg or OrchestratorConfig.from_env()
        cfg_model = cast(Any, self.cfg.model)
        envar_api_key = cast(Any, self.envar).api_key
        self.model = cfg_model.get_model(
            api_key=envar_api_key,
        )

        # 构建 prompt
        self.prompt_factory = PromptFactory(envar=self.envar)

        # 构建上下文管理器
        session_summary_manager = CustomSessionManager.from_config(
            cfg=self.cfg.session_manager,
            api_key=envar_api_key,
            num_context_windows=self.cfg.num_history_runs,
        )
        # 构建压缩管理器
        compression_manager = CustomCompressionManager.from_config(
            cfg=self.cfg.compression_manager,
            api_key=envar_api_key,
        )

        self.agent = Agent(
            user_id=self.envar.user_id,
            name="Orchestrator",
            id=f"orchestrator-{self.envar.record_id}",
            session_id=f"session-{self.envar.record_id}",
            # cfg
            model=self.model,
            db=self.cfg.db.get_async_db(),
            description=self.prompt_factory.get_description(),
            instructions=self.prompt_factory.get_introduction(),
            additional_context=self.prompt_factory.get_subagent_system_prompt(),
            # 上下文压缩管理选项
            session_summary_manager=session_summary_manager,
            add_session_summary_to_context=cast(Any, self.cfg).add_session_summary_to_context,
            max_tool_calls_from_history=self.cfg.max_tool_calls_from_history,
            num_history_runs=self.cfg.num_history_runs,
            compression_manager=compression_manager,
            # 其他内容
            add_history_to_context=True,
            skills=load_skills(envar=self.envar),
            tools=load_tools(envar=self.envar, cfgs=self.cfg.toolkits),  # type: ignore
            telemetry=False,
        )

    async def run(
        self, message: Union[str, Message], extra: Optional[ExtraInfo] = None
    ) -> AsyncGenerator[ResponseEventEnvelope, Any]:

        if isinstance(message, str):
            message = Message(role="user", content=message)
        if extra:
            message.content = f"""
{message.content}\n
<additional_info>{extra.dump_json()}</additional_info>"""

        response_id = create_response_id()
        normalizer = ResponseEventNormalizer(
            ResponseProtocolContext(
                response_id=response_id,
                session_id=self.agent.session_id or f"session-{self.envar.record_id}",
                root_agent_id=self.agent.id,
                root_agent_name=self.agent.name,
            )
        )

        async for response in self.agent.arun(
            input=message, stream=True, stream_events=True, yield_run_output=True
        ):
            for normalized_event in normalizer.normalize(response):
                yield normalized_event
