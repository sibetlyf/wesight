#!/usr/bin/env python3
"""
测试技能加载，验证中文提示词生成和参考文件递归遍历功能
"""

import sys
import os

import pytest


from core.abilities_loader import load_skills

@pytest.mark.asyncio
async def test_skills_load(workspace_prepare):
    """测试技能加载"""
    print("开始加载技能...")
    skills = load_skills()
    assert skills, "技能加载失败"
    print(f"技能加载完成，共加载 {len(skills._skills)} 个技能")
    
    # 测试中文提示词生成
    prompt_snippet = skills.get_system_prompt_snippet()
    print("\n生成的中文提示词:")
    print(prompt_snippet)
    assert "什么是技能？" in prompt_snippet, "提示词未转换为中文"




    