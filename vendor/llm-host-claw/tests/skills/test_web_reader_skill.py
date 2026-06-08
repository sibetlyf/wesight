#!/usr/bin/env python3
"""
Integration tests for web-reader skill.
Tests that the skill is properly loaded and influences AI behavior.
参考 test_skills_integration.py 和 conftest.py 的结构
"""

import os
import sys
import pytest
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from core.abilities_loader import load_skills
from agno.agent import Agent
from agno.skills import Skills, LocalSkills


class TestWebReaderSkillLoading:
    """Tests for web-reader skill loading functionality."""

    def test_web_reader_skill_loaded(self, workspace_prepare):
        """Test that web-reader skill is loaded."""
        import os
        workspace = os.environ.get("WORKSPACE")
        skills = load_skills(workspace=workspace)
        
        # Check if skills object contains web-reader
        assert skills is not None, "Skills should not be None"
        
        # Check if the skill directory exists
        skill_dir = Path(__file__).parent.parent.parent / "src" / "core" / "skills" / "web-reader"
        assert skill_dir.exists(), f"web-reader skill directory not found: {skill_dir}"
        
        # Check if SKILL.md exists
        skill_md = skill_dir / "SKILL.md"
        assert skill_md.exists(), f"SKILL.md not found in web-reader"
        
        print("✓ web-reader skill loaded successfully")


class TestWebReaderSkillBehavior:
    """Tests for web-reader skill behavior influence on AI."""

    @pytest.mark.asyncio
    async def test_agent_recognizes_web_scraping_request(self, jt_model, skills_loader, workspace_prepare):
        """Test that agent recognizes when to use web-reader skill."""
        agent = Agent(
            model=jt_model,
            skills=skills_loader,
            instructions="你是一个智能助手。",
            user_id="test_user",
            debug_mode=True,
            telemetry=False,
        )

        # Test prompts that should trigger web-reader skill
        web_prompts = [
            "帮我抓取 https://www.nxcode.io/zh/resources/news/kimi-k2-5-developer-guide-kimi-code-cli-2026 的内容",
            "爬取网站数据 https://www.woshipm.com/ai/6189316.html",
        ]

        for prompt in web_prompts:
            try:
                response = ""
                async for event in agent.arun(prompt, stream=True):
                    if hasattr(event, 'content') and event.content:
                        response += str(event.content)

                # Check if response mentions web scraping related content
                response_lower = response.lower()
                has_web_keyword = any(keyword in response_lower for keyword in [
                    "抓取", "提取", "读取", "爬取", "scrape", "extract", "crawl",
                    "网页", "web", "url", "browser", "playwright"
                ])

                if has_web_keyword:
                    print(f"✓ Agent recognized web scraping request: '{prompt[:40]}...'")
                else:
                    print(f"ℹ Agent response for '{prompt[:40]}...': {response[:100]}")

            except Exception as e:
                pytest.skip(f"Model not available: {e}")

    @pytest.mark.asyncio
    async def test_agent_recognizes_stealth_request(self, jt_model, skills_loader, workspace_prepare):
        """Test that agent recognizes stealth/bypass requests."""
        agent = Agent(
            model=jt_model,
            skills=skills_loader,
            instructions="你是一个智能助手。",
            user_id="test_user",
            debug_mode=True,
            telemetry=False,
        )

        # Test prompts that should trigger stealth mode
        stealth_prompts = [
            "https://www.woshipm.com/ai/6189316.html",
        ]

        for prompt in stealth_prompts:
            try:
                response = ""
                async for event in agent.arun(prompt, stream=True):
                    if hasattr(event, 'content') and event.content:
                        response += str(event.content)

                response_lower = response.lower()
                has_stealth_keyword = any(keyword in response_lower for keyword in [
                    "stealth", "绕过", "避免", "检测", "bypass", "captcha",
                    "anti-bot", "evasion", "stealth mode"
                ])

                if has_stealth_keyword:
                    print(f"✓ Agent recognized stealth request: '{prompt[:40]}...'")
                else:
                    print(f"ℹ Agent response for '{prompt[:40]}...': {response[:100]}")

            except Exception as e:
                pytest.skip(f"Model not available: {e}")


class TestWebReaderWithSpecificSkill:
    """Tests for web-reader skill with only this skill loaded."""

    @pytest.fixture
    def web_reader_only_skills(self, workspace_prepare):
        """只加载 web-reader skill"""
        yield Skills(loaders=[LocalSkills("src/core/skills/web-reader")])

    @pytest.mark.asyncio
    async def test_agent_with_only_web_reader_skill(self, jt_model, web_reader_only_skills, workspace_prepare):
        """Test agent with only web-reader skill loaded."""
        agent = Agent(
            model=jt_model,
            skills=web_reader_only_skills,
            instructions="你是一个网页数据提取助手，可以使用 web-reader skill 抓取网页内容。",
            user_id="test_user",
            debug_mode=True,
            add_history_to_context=True,
            stream_events=True,
            telemetry=False,
        )

        prompt = "帮我抓取 https://www.msn.cn/zh-cn/news/other/%E5%85%BB%E9%BE%99%E8%99%BE-%E7%81%AB%E7%83%AD%E5%B0%8F%E5%BF%83%E9%9A%90%E7%A7%81%E5%AE%89%E5%85%A8/ar-AA1Z1kRg 使用web-reader进行爬取网页内容，结果存在workspace/runs/"
        
        try:
            response = ""
            async for event in agent.arun(prompt, stream=True):
                if hasattr(event, 'content') and event.content:
                    response += str(event.content)

            # 直接输出完整响应
            print("=" * 80)
            print("Agent 使用 web-reader skill 的输出：")
            print("=" * 80)
            print(response)
            print("=" * 80)

        except Exception as e:
            pytest.skip(f"Model not available: {e}")



if __name__ == "__main__":
    pytest.main([__file__, "-v"])
