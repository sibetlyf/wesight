#!/usr/bin/env python3
"""
Main test runner for all skills.
Runs all skill test scripts and reports the overall results.
"""

import os
import sys
import subprocess
from pathlib import Path

# Basic structure tests (no model required)
BASIC_TESTS = [
    "test_docx_skill.py",
    "test_pdf_skill.py",
    "test_pptx_skill.py",
    "test_xlsx_skill.py",
    "test_drawio_skill.py",
    "test_doc_coauthoring_skill.py",
    "test_content_research_writer_skill.py",
]

# Integration tests (require model, run with pytest)
INTEGRATION_TESTS = [
    "test_skills_integration.py",
    "test_drawio_skill_integration.py",
]


def run_test(test_script: str) -> bool:
    """Run a single test scripts and return True if it passes."""
    test_path = Path(__file__).parent / test_script
    
    if not test_path.exists():
        print(f"⚠ Test scripts not found: {test_script}")
        return False
    
    print(f"\n{'='*60}")
    print(f"Running: {test_script}")
    print('='*60)
    
    try:
        result = subprocess.run(
            [sys.executable, str(test_path)],
            capture_output=False,
            text=True,
            timeout=120
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"✗ {test_script} timed out")
        return False
    except Exception as e:
        print(f"✗ {test_script} failed with error: {e}")
        return False


def run_pytest_test(test_script: str) -> bool:
    """Run a pytest test scripts and return True if it passes."""
    test_path = Path(__file__).parent / test_script
    
    if not test_path.exists():
        print(f"⚠ Test scripts not found: {test_script}")
        return False
    
    print(f"\n{'='*60}")
    print(f"Running: {test_script} (pytest)")
    print('='*60)
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(test_path), "-v", "--tb=short"],
            capture_output=False,
            text=True,
            timeout=300
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"✗ {test_script} timed out")
        return False
    except Exception as e:
        print(f"✗ {test_script} failed with error: {e}")
        return False


def main():
    """Run all skill tests."""
    print("="*60)
    print("Running All Skill Tests")
    print("="*60)
    
    results = {}
    
    # Run basic tests
    print("\n" + "-"*60)
    print("PHASE 1: Basic Structure Tests")
    print("-"*60)
    for test in BASIC_TESTS:
        results[test] = run_test(test)
    
    # Run integration tests (optional, require model)
    print("\n" + "-"*60)
    print("PHASE 2: Integration Tests (require model)")
    print("-"*60)
    for test in INTEGRATION_TESTS:
        results[test] = run_pytest_test(test)
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = 0
    failed = 0
    
    for test, success in results.items():
        status = "✓ PASSED" if success else "✗ FAILED"
        print(f"{status}: {test}")
        if success:
            passed += 1
        else:
            failed += 1
    
    total_tests = len(BASIC_TESTS) + len(INTEGRATION_TESTS)
    print("="*60)
    print(f"Total: {passed} passed, {failed} failed out of {total_tests} tests")
    print(f"  - Basic tests: {len(BASIC_TESTS)}")
    print(f"  - Integration tests: {len(INTEGRATION_TESTS)}")
    print("="*60)
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
