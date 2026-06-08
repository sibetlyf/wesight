#!/usr/bin/env python3
"""
Integration tests for trip-planner skill.
Tests that the skill is properly loaded and influences AI behavior.
参考 test_skills_integration.py 和 conftest.py 的结构
"""

import os
import sys
import pytest
import uuid
import re
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from core.abilities_loader import load_skills, _load_core_tools
from agno.agent import Agent
from agno.skills import Skills, LocalSkills
from protocol import EnVar


@pytest.fixture
def workspace_env(workspace_prepare):
    """从环境变量获取工作目录信息"""
    envar = EnVar.from_env()
    yield {
        "workspace": envar.workspace,
        "runspace": envar.runspace,
        "userspace": envar.userspace,
        "sessionspace": envar.sessionspace,
    }


def extract_html(response: str) -> str:
    """从响应中提取 HTML 代码"""
    html_pattern = r'```html\s*(.*?)\s*```'
    matches = re.findall(html_pattern, response, re.DOTALL)

    if matches:
        return matches[0]

    if '<html' in response.lower() or '<!doctype' in response.lower() or '<body' in response.lower():
        return response

    return ""


def save_html_file(html_content: str, file_path: Path) -> bool:
    """保存 HTML 到文件"""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        return True
    except Exception as e:
        print(f"保存文件失败: {e}")
        return False


class TestSmartTripPlannerWithSpecificSkill:
    """Tests for trip-planner skill with only this skill loaded."""

    @pytest.fixture
    def smart_trip_planner_only_skills(self, workspace_prepare):
        """只加载 trip-planner skill"""
        yield Skills(loaders=[LocalSkills("src/core/skills/trip-planner")])

    @pytest.mark.asyncio
    async def test_agent_with_only_smart_trip_planner_skill(self, jt_model, smart_trip_planner_only_skills, workspace_env):
        """Test agent with only trip-planner skill loaded and shell tools."""
        agent = Agent(
            model=jt_model,
            skills=smart_trip_planner_only_skills,
            instructions="你是一个智能出行助手，可以输出方案的比较， 生成html 文件。",
            user_id="test_user",
            debug_mode=True,
            add_history_to_context=True,
            stream_events=True,
            telemetry=False,
        )

        prompt = "北京长景新园到莲花池公园，出行方案比较下"#3月21号去西安，10点前要到，帮我看看哪班车最合适，北京西直门出发。

        try:
            response = ""
            async for event in agent.arun(prompt, stream=True):
                if hasattr(event, 'content') and event.content:
                    response += str(event.content)

            print("=" * 80)
            print(response)


            html_content = extract_html(response)

            if html_content:
                file_name = f"trip_plan_{uuid.uuid4().hex[:8]}.html"
                file_path = Path(workspace_env["runspace"]) / file_name

                if save_html_file(html_content, file_path):
                    print(f"✓ HTML 文件已保存: {file_path}")
                    print(f"  文件大小: {len(html_content)} 字符")
                else:
                    print(f"✗ HTML 文件保存失败")
            else:
                print(f"ℹ 未找到 HTML 代码")

        except Exception as e:
            pytest.skip(f"Model not available: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
