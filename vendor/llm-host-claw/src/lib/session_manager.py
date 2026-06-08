from agno.session.summary import SessionSummaryManager
from dataclasses import dataclass

from configs.common import SessionManagerConfig
from datetime import datetime
from textwrap import dedent
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type, Union, override

from pydantic import BaseModel, Field

from agno.models.base import Model
from agno.models.message import Message
from agno.models.utils import get_model

if TYPE_CHECKING:
    from agno.metrics import RunMetrics
    from agno.session import Session
    from agno.session.agent import AgentSession
    from agno.session.team import TeamSession

from lib import get_agno_agent_context_str


@dataclass
class CustomSessionManager(SessionSummaryManager):
    """
    会话管理器
    """

    num_context_windows: Optional[int] = None

    # 从config初始化
    @classmethod
    def from_config(
        cls,
        cfg: SessionManagerConfig,
        api_key: Optional[str],
        num_context_windows: Optional[int] = None,
    ) -> "CustomSessionManager":
        return cls(
            model=cfg.model.get_model(
                api_key=api_key,
            ),
            num_context_windows=num_context_windows,
            last_n_runs=cfg.last_n_runs,
            conversation_limit=cfg.conversation_limit,
        )

    @override
    def _prepare_summary_messages(
        self,
        session: Optional["Session"] = None,
    ) -> Optional[List[Message]]:
        """Prepare messages for session summary generation. Returns None if no meaningful messages to summarize."""
        if not session:
            return None

        self.model = get_model(self.model)
        if self.model is None:
            return None

        response_format = self.get_response_format(self.model)

        system_message = self.get_system_message(
            response_format=response_format,
        )
        all = session.get_messages(
            last_n_runs=self.last_n_runs, limit=self.conversation_limit
        )
        over_run = all[
            : len(all) - len(session.get_messages(last_n_runs=self.num_context_windows))
        ]

        if system_message is None or not over_run:
            return None
        return [
            system_message,
            Message(
                role="user",
                content=get_agno_agent_context_str(over_run),
            ),
        ]

    @override
    def get_system_message(  # type: ignore
        self,
        response_format: Union[Dict[str, Any], Type[BaseModel]],
    ) -> Message:
        if self.session_summary_prompt is not None:
            system_prompt = self.session_summary_prompt
        else:
            system_prompt = dedent("""\
            分析以下用户与助手之间的对话，并提取以下详细信息：
            - summary (str): 提供会话的简明摘要，重点关注对未来交互有帮助的重要信息。
            - topics (Optional[List[str]]): 列出会话中讨论的主题。
            保持摘要简洁明了。仅包含相关信息。
            """)

        if response_format == {"type": "json_object"}:
            from agno.utils.prompts import get_json_output_prompt

            system_prompt += "\n" + get_json_output_prompt(SessionSummaryResponse)  # type: ignore

        return Message(role="system", content=system_prompt)
