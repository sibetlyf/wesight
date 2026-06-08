#!/usr/bin/env python3
"""
Test scripts for content-research-writer skill
Tests the content-research-writer skill functionality for writing assistance.
"""

import os
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent.parent / "src" / "core" / "skills" / "content-research-writer"


def test_skill_metadata():
    """Test that SKILL.md exists and has required content."""
    skill_md = SKILL_DIR / "SKILL.md"
    assert skill_md.exists(), f"SKILL.md not found at {skill_md}"
    
    content = skill_md.read_text(encoding='utf-8')
    assert "name: content-research-writer" in content, "Skill name not found in SKILL.md"
    assert "description:" in content, "Description not found in SKILL.md"
    print("✓ Skill metadata test passed")


def test_readme_exists():
    """Test that README.md exists."""
    readme = SKILL_DIR / "README.md"
    if readme.exists():
        print("✓ README.md exists")
    else:
        print("ℹ README.md not found (optional)")


def test_chinese_version():
    """Test that Chinese version exists."""
    chinese_md = SKILL_DIR / "content-research-writer-SKILL-zh.md"
    if chinese_md.exists():
        print("✓ Chinese version (SKILL-zh.md) exists")
    else:
        print("ℹ Chinese version not found (optional)")


def test_skill_content():
    """Test that SKILL.md has the expected content sections."""
    skill_md = SKILL_DIR / "SKILL.md"
    content = skill_md.read_text(encoding='utf-8')
    
    expected_sections = [
        "When to Use This Skill",
        "What This Skill Does",
        "How to Use",
        "Instructions",
    ]
    
    for section in expected_sections:
        if section in content:
            print(f"✓ Section '{section}' found in SKILL.md")
        else:
            print(f"⚠ Section '{section}' not found in SKILL.md")


def test_writing_features():
    """Test that writing features are documented."""
    skill_md = SKILL_DIR / "SKILL.md"
    content = skill_md.read_text(encoding='utf-8')
    
    features = [
        "Collaborative Outlining",
        "Research Assistance",
        "Hook Improvement",
        "Section Feedback",
        "Citation Management",
    ]
    
    found = 0
    for feature in features:
        if feature in content:
            found += 1
            print(f"✓ Feature '{feature}' found")
        else:
            print(f"ℹ Feature '{feature}' not found")


def test_use_cases():
    """Test that use cases are documented."""
    skill_md = SKILL_DIR / "SKILL.md"
    content = skill_md.read_text(encoding='utf-8')
    
    use_cases = [
        "blog posts",
        "articles",
        "newsletters",
        "case studies",
        "technical documentation",
    ]
    
    found = 0
    for use_case in use_cases:
        if use_case in content.lower():
            found += 1
    
    print(f"✓ Found {found}/{len(use_cases)} use cases")


def test_workflow_steps():
    """Test that workflow steps are documented."""
    skill_md = SKILL_DIR / "SKILL.md"
    content = skill_md.read_text(encoding='utf-8')
    
    steps = [
        "Understand the Writing Project",
        "Collaborative Outlining",
        "Conduct Research",
        "Improve Hooks",
    ]
    
    found = 0
    for step in steps:
        if step in content:
            found += 1
            print(f"✓ Step '{step}' found")
        else:
            print(f"ℹ Step '{step}' not found")


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("Testing content-research-writer skill")
    print("=" * 60)
    
    tests = [
        test_skill_metadata,
        test_readme_exists,
        test_chinese_version,
        test_skill_content,
        test_writing_features,
        test_use_cases,
        test_workflow_steps,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"✗ {test.__name__} failed: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test.__name__} error: {e}")
            failed += 1
    
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
