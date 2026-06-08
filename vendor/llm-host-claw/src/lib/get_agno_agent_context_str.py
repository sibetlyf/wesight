from agno.run.agent import ToolCallCompletedEvent
from typing import List, Optional, Union
from agno.agent import Message
import copy



def get_agno_agent_context_str(
    messages: List[Message],
    ignore_tool_list: Optional[List[str]] = None,
) -> Optional[str]:

    context_parts = []
    if messages:
        messages = copy.deepcopy(messages)
        ignore_tool_list = ignore_tool_list or []
        for msg in messages:
            if msg.role == "user":
                context_parts.append(f"- **user**: {msg.content}")
            elif msg.role == "assistant":
                if msg.tool_calls:
                # 处理 assistant 消息中的工具调用
                    for tool_call in msg.tool_calls:
                        function = tool_call.get("function", {})
                        tool_name = function.get("name")
                        if tool_name in ignore_tool_list:
                            continue
                        # 解析工具参数
                        tool_args = function.get("arguments", {})
                        if isinstance(tool_args, str):
                            import json
                            try:
                                tool_args = json.loads(tool_args)
                            except json.JSONDecodeError:
                                tool_args = {}
                        arguments = ", ".join([f"{k}={v}" for k, v in tool_args.items()])
                        _=f"- **assistant**: {tool_name}({arguments})"
                        if msg.content:
                            _=f"{_} | {msg.content}"
                        context_parts.append(_)
                elif msg.content:
                    context_parts.append(f"- **assistant**: {msg.content}")
            elif msg.role == "tool" and msg.tool_name:
                # 处理 tool 消息的执行结果
                if msg.tool_name in ignore_tool_list:
                    continue
                # 获取工具执行结果
                tool_result = msg.content or ""
                if isinstance(tool_result, list):
                    import json
                    tool_result = json.dumps(tool_result)
                escape = tool_result.replace("\n", "\\n")
                context_parts.append(f"- **Tool[{msg.tool_name}]**: {escape}")
    return "\n".join(context_parts)


