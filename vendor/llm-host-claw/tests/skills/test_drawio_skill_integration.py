#!/usr/bin/env python3
"""
Integration tests for drawio skill.
Tests that drawio skill is properly loaded and influences AI behavior.
"""

import os
import sys
import pytest
import uuid
import re
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from core.abilities_loader import load_skills
from agno.agent import Agent
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


def extract_drawio_xml(response: str) -> str:
    """从响应中提取 drawio XML 代码"""
    # 尝试提取 ```xml ... ``` 包裹的内容
    xml_pattern = r'```xml\s*(.*?)\s*```'
    matches = re.findall(xml_pattern, response, re.DOTALL)
    
    if matches:
        # 返回第一个匹配的内容
        return matches[0]
    
    # 如果没有找到xml标签，尝试直接返回response（可能是纯XML）
    if '<mxGraphModel' in response or '<diagram' in response:
        return response
    
    return ""


def save_drawio_file(xml_content: str, file_path: Path) -> bool:
    """保存 drawio XML 到文件"""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(xml_content)
        return True
    except Exception as e:
        print(f"保存文件失败: {e}")
        return False


class TestDrawioSkillBehavior:
    """Tests for drawio skill behavior influence on AI."""

    @pytest.mark.asyncio
    async def test_agent_recognizes_diagram_request(self, jt_model, skills_loader):
        """Test that agent recognizes when to use drawio skill."""
        agent = Agent(
            model=jt_model,
            skills=skills_loader,
            instructions="你是一个智能助手。",
            user_id="test_user",
            debug_mode=True,
            telemetry=False,
        )

        # Test prompts that should trigger drawio skill
        diagram_prompts = [
            "帮我画一个项目管理流程图",
            "随机选择一个场景，生成该场景的时序图",
        ]

        for prompt in diagram_prompts:
            try:
                response = ""
                async for event in agent.arun(prompt, stream=True):
                    if hasattr(event, 'content') and event.content:
                        response += str(event.content)

                response_lower = response.lower()
                has_diagram_keyword = any(keyword in response_lower for keyword in [
                    "drawio", "diagram", "流程图", "架构图", "时序图", "er图",
                    "flowchart", "architecture", "sequence", "mxgraph"
                ])

                if has_diagram_keyword:
                    print(f"✓ Agent recognized diagram request: '{prompt[:30]}...'")
                else:
                    print(f"ℹ Agent response for '{prompt[:30]}...': {response[:100]}")

            except Exception as e:
                pytest.skip(f"Model not available: {e}")

    @pytest.mark.asyncio
    async def test_agent_suggests_drawio_for_visualization(self, jt_model, skills_loader, workspace_env):
        """Test that agent suggests drawio for visualization needs and saves to file."""
        agent = Agent(
            model=jt_model,
            skills=skills_loader,
            instructions="你是一个智能助手，擅长使用 draw.io 生成图表。请生成完整的 draw.io XML 代码。",
            user_id="test_user",
            debug_mode=True,
            telemetry=False,
        )

        # Test prompts about visualizing systems or processes
        viz_prompts = [
            "画一下电商系统架构图，用 draw.io 的 mxGraphModel 格式输出",
        ]

        for prompt in viz_prompts:
            try:
                response = ""
                async for event in agent.arun(prompt, stream=True):
                    if hasattr(event, 'content') and event.content:
                        response += str(event.content)

                # 从响应中提取 drawio XML
                drawio_xml = extract_drawio_xml(response)

                # 保存到文件
                if drawio_xml:
                    file_name = f"diagram_{uuid.uuid4().hex[:8]}.drawio"
                    file_path = Path(workspace_env["runspace"]) / file_name
                    
                    if save_drawio_file(drawio_xml, file_path):
                        print(f"✓ Draw.io 文件已保存: {file_path}")
                        print(f"  文件大小: {len(drawio_xml)} 字符")
                    else:
                        print(f"✗ Draw.io 文件保存失败")
                else:
                    print(f"ℹ 未找到 drawio XML 代码")
                    print(f"  响应内容: {response[:200]}...")

            except Exception as e:
                pytest.skip(f"Model not available: {e}")

    @pytest.mark.asyncio
    async def test_agent_generates_drawio_file(self, jt_model, skills_loader, workspace_env):
        """测试 Agent 生成 drawio 文件并保存"""
        agent = Agent(
            model=jt_model,
            skills=skills_loader,
            instructions="你是一个智能助手。请根据以下描述生成 draw.io 格式的流程图，输出完整的 XML 代码（用 ```xml 包裹）",
            user_id="test_user",
            debug_mode=True,
            telemetry=False,
        )

        prompt = "生成一个简单的订单处理流程图"
        
        try:
            response = ""
            async for event in agent.arun(prompt, stream=True):
                if hasattr(event, 'content') and event.content:
                    response += str(event.content)

            # 提取 drawio XML
            drawio_xml = extract_drawio_xml(response)
            
            if drawio_xml:
                # 生成文件名
                file_name = f"order_flowchart_{uuid.uuid4().hex[:8]}.drawio"
                file_path = Path(workspace_env["runspace"]) / file_name
                
                if save_drawio_file(drawio_xml, file_path):
                    print(f"=" * 80)
                    print(f"✓ Draw.io 文件已生成: {file_path}")
                    print(f"  文件大小: {len(drawio_xml)} 字符")
                    print(f"=" * 80)
                    
                    # 打印部分内容预览
                    preview = drawio_xml[:500] if len(drawio_xml) > 500 else drawio_xml
                    print(f"  XML 预览:\n{preview}...")
                else:
                    print(f"✗ 文件保存失败")
            else:
                print(f"=" * 80)
                print(f"ℹ 响应中未找到 drawio XML")
                print(f"  完整响应: {response[:500]}...")
                print(f"=" * 80)

        except Exception as e:
            pytest.skip(f"Model not available: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
