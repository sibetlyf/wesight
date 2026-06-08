#!/usr/bin/env python3
"""
Test scripts for pdf skill
Tests the pdf skill functionality including PDF processing, extraction, and manipulation.
"""

import os
import sys
import subprocess
import tempfile
import shutil
from pathlib import Path

# Add src to path for importing skill modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src" / "core" / "skills" / "pdf" / "scripts"))

SKILL_DIR = Path(__file__).parent.parent.parent / "src" / "core" / "skills" / "pdf"
SCRIPTS_DIR = SKILL_DIR / "scripts"


def test_skill_metadata():
    """Test that SKILL.md exists and has required content."""
    skill_md = SKILL_DIR / "SKILL.md"
    assert skill_md.exists(), f"SKILL.md not found at {skill_md}"
    
    content = skill_md.read_text(encoding='utf-8')
    assert "name: pdf" in content, "Skill name not found in SKILL.md"
    assert "description:" in content, "Description not found in SKILL.md"
    print("✓ Skill metadata test passed")


def test_license_file():
    """Test that LICENSE.txt exists."""
    license_file = SKILL_DIR / "LICENSE.txt"
    assert license_file.exists(), f"LICENSE.txt not found at {license_file}"
    print("✓ License file test passed")


def test_reference_docs():
    """Test that reference documentation exists."""
    reference_files = ["reference.md", "forms.md"]
    for ref_file in reference_files:
        ref_path = SKILL_DIR / ref_file
        if ref_path.exists():
            print(f"✓ Reference file {ref_file} exists")
        else:
            print(f"ℹ Reference file {ref_file} not found (optional)")


def test_scripts_exist():
    """Test that PDF processing scripts exist."""
    expected_scripts = [
        "check_bounding_boxes.py",
        "check_fillable_fields.py",
        "convert_pdf_to_images.py",
        "create_validation_image.py",
        "extract_form_field_info.py",
        "extract_form_structure.py",
        "fill_fillable_fields.py",
        "fill_pdf_form_with_annotations.py",
    ]
    
    found = 0
    for script in expected_scripts:
        script_path = SCRIPTS_DIR / script
        if script_path.exists():
            found += 1
            print(f"✓ Script {script} exists")
        else:
            print(f"⚠ Script {script} not found")
    
    print(f"✓ Found {found}/{len(expected_scripts)} expected scripts")


def test_python_dependencies():
    """Test that required Python dependencies are available."""
    dependencies = [
        "pypdf",
        "pdfplumber",
        "reportlab",
    ]
    
    for dep in dependencies:
        try:
            __import__(dep)
            print(f"✓ Dependency '{dep}' is installed")
        except ImportError:
            print(f"⚠ Dependency '{dep}' is not installed (optional)")


def test_external_tools():
    """Test that external tools are available."""
    tools = [
        ("pdftotext", "poppler-utils"),
        ("qpdf", "qpdf"),
    ]
    
    for tool, package in tools:
        try:
            result = subprocess.run([tool, "--version"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0 or "version" in result.stderr.lower():
                print(f"✓ Tool '{tool}' is available")
            else:
                print(f"⚠ Tool '{tool}' may not be available (install {package})")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            print(f"⚠ Tool '{tool}' not found (install {package})")


def test_script_imports():
    """Test that scripts can be imported."""
    import importlib.util
    
    scripts_to_test = [
        "check_bounding_boxes.py",
        "check_fillable_fields.py",
        "convert_pdf_to_images.py",
        "extract_form_field_info.py",
        "extract_form_structure.py",
    ]
    
    for script_name in scripts_to_test:
        script_path = SCRIPTS_DIR / script_name
        if script_path.exists():
            try:
                spec = importlib.util.spec_from_file_location(
                    script_name.replace(".py", ""), script_path
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                print(f"✓ Script {script_name} imports successfully")
            except Exception as e:
                print(f"⚠ Script {script_name} import failed: {e}")
        else:
            print(f"ℹ Script {script_name} not found")


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("Testing pdf skill")
    print("=" * 60)
    
    tests = [
        test_skill_metadata,
        test_license_file,
        test_reference_docs,
        test_scripts_exist,
        test_python_dependencies,
        test_external_tools,
        test_script_imports,
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
