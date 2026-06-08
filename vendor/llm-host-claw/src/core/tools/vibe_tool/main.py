#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import os
import sys
from protocol.envar import EnVar
from agno.agent import Agent
from agno.models.litellm import LiteLLM

# 添加 src 目录到 module path
sys.path.append(str(__import__('pathlib').Path(__file__).resolve().parents[3]))
from vibe_toolkit import VibeCodingToolkit
from configs.vibe_toolkit import VibeCodingToolkitConfig

async def main():
    # Keep the local demo runnable without embedding real credentials.
    model = LiteLLM(
        api_base=os.getenv("VIBE_TOOL_DEMO_BASE_URL", "https://example.com/v1"),
        api_key=os.getenv("VIBE_TOOL_DEMO_API_KEY", "EMPTY"),
        id=os.getenv("VIBE_TOOL_DEMO_MODEL", "openai/qwen3.5-plus"),
    )
    toolkit = VibeCodingToolkit(cfg=VibeCodingToolkitConfig(agent_type="opencode"), envar=EnVar.from_env())
    agent = Agent(model=model, tools=[toolkit], debug_mode=True)
    # await agent.aprint_response("你好")
    while True:
        query = str(input())
        if query == "exit":
            break
        else:
            resp = agent.arun(query, stream=True)
            async for chunk in resp:
                content = chunk.content if hasattr(chunk, 'content') else str(chunk)
                if content:
                    content = content.strip()
                    if content:
                        sys.stdout.write(content)
                        sys.stdout.flush()
            print()

if __name__ == "__main__":
    asyncio.run(main())
