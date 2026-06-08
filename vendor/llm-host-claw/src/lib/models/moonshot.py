from agno.models.moonshot import MoonShot
from agno.agent import Message

from typing import List, Dict, Any, override


class FixMoonShot(MoonShot):
    """
    修复版MoonShot，call_id 变化可能导致模型输出漏掉 tool_call
    """

    @override
    def _format_all_messages(
        self, messages: List[Message], compress_tool_results: bool = False
    ) -> List[Dict[str, Any]]:
        """Format all messages, remapping foreign tool call IDs to call_ prefix first."""
        from agno.utils.message import normalize_tool_messages, reformat_tool_call_ids

        # Backwards compat: expand old Gemini combined tool messages into individual canonical messages
        messages = normalize_tool_messages(messages)
        normalized = reformat_tool_call_ids(messages, provider="other")
        return [self._format_message(m, compress_tool_results) for m in normalized]
