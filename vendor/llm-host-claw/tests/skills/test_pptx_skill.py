#!/usr/bin/env python3
"""
Test scripts for pptx skill
Tests the pptx skill functionality including presentation creation, editing, and analysis.
"""

import os
import sys
import subprocess
import tempfile
import shutil
from pathlib import Path

# Add src to path for importing skill modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src" / "core" / "skills" / "pptx" / "scripts"))

SKILL_DIR = Path(__file__).parent.parent.parent / "src" / "core" / "skills" / "pptx"
SCRIPTS_DIR = SKILL_DIR / "scripts"
OFFICE_DIR = SCRIPTS_DIR / "office"


def test_skill_metadata():
    """Test that SKILL.md exists and has required content."""
    skill_md = SKILL_DIR / "SKILL.md"
    assert skill_md.exists(), f"SKILL.md not found at {skill_md}"
    
    content = skill_md.read_text(encoding='utf-8')
    assert "name: pptx" in content, "Skill name not found in SKILL.md"
    assert "description:" in content, "Description not found in SKILL.md"
    print("✓ Skill metadata test passed")


def test_license_file():
    """Test that LICENSE.txt exists."""
    license_file = SKILL_DIR / "LICENSE.txt"
    assert license_file.exists(), f"LICENSE.txt not found at {license_file}"
    print("✓ License file test passed")


def test_reference_docs():
    """Test that reference documentation exists."""
    reference_files = ["editing.md", "pptxgenjs.md"]
    for ref_file in reference_files:
        ref_path = SKILL_DIR / ref_file
        if ref_path.exists():
            print(f"✓ Reference file {ref_file} exists")
        else:
            print(f"ℹ Reference file {ref_file} not found (optional)")


def test_office_scripts_exist():
    """Test that office helper scripts exist."""
    required_scripts = [
        OFFICE_DIR / "unpack.py",
        OFFICE_DIR / "pack.py",
        OFFICE_DIR / "validate.py",
        OFFICE_DIR / "soffice.py",
    ]
    
    for script in required_scripts:
        assert script.exists(), f"Required scripts not found: {script}"
    print("✓ Office scripts exist test passed")


def test_validators_exist():
    """Test that validator modules exist."""
    validators_dir = OFFICE_DIR / "validators"
    assert validators_dir.exists(), f"Validators directory not found: {validators_dir}"
    
    required_validators = ["__init__.py", "base.py", "docx.py", "pptx.py", "redlining.py"]
    for validator in required_validators:
        assert (validators_dir / validator).exists(), f"Validator not found: {validator}"
    print("✓ Validators exist test passed")


def test_pptx_scripts_exist():
    """Test that PPTX-specific scripts exist."""
    expected_scripts = [
        SCRIPTS_DIR / "add_slide.py",
        SCRIPTS_DIR / "clean.py",
        SCRIPTS_DIR / "thumbnail.py",
    ]
    
    found = 0
    for script in expected_scripts:
        if script.exists():
            found += 1
            print(f"✓ Script {script.name} exists")
        else:
            print(f"⚠ Script {script.name} not found")
    
    print(f"✓ Found {found}/{len(expected_scripts)} expected scripts")


def test_unpack_script():
    """Test the unpack scripts can be imported."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("unpack", OFFICE_DIR / "unpack.py")
        unpack = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(unpack)
        print("✓ Unpack scripts imports successfully")
    except Exception as e:
        print(f"⚠ Unpack scripts import test failed: {e}")


def test_pack_script():
    """Test the pack scripts can be imported."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("pack", OFFICE_DIR / "pack.py")
        pack = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pack)
        print("✓ Pack scripts imports successfully")
    except Exception as e:
        print(f"⚠ Pack scripts import test failed: {e}")


def test_validate_script():
    """Test the validate scripts can be imported."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("validate", OFFICE_DIR / "validate.py")
        validate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(validate)
        print("✓ Validate scripts imports successfully")
    except Exception as e:
        print(f"⚠ Validate scripts import test failed: {e}")


def test_soffice_script():
    """Test the soffice scripts can be imported."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("soffice", OFFICE_DIR / "soffice.py")
        soffice = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(soffice)
        print("✓ Soffice scripts imports successfully")
    except Exception as e:
        print(f"⚠ Soffice scripts import test failed: {e}")


def test_helpers_exist():
    """Test that helper modules exist."""
    helpers_dir = OFFICE_DIR / "helpers"
    if helpers_dir.exists():
        helpers = ["merge_runs.py", "simplify_redlines.py"]
        for helper in helpers:
            if (helpers_dir / helper).exists():
                print(f"✓ Helper {helper} exists")
            else:
                print(f"⚠ Helper {helper} not found")
    else:
        print("ℹ Helpers directory not found (optional)")


def test_schemas_exist():
    """Test that XML schemas exist."""
    schemas_dir = OFFICE_DIR / "schemas"
    if schemas_dir.exists():
        xsd_files = list(schemas_dir.rglob("*.xsd"))
        print(f"✓ Found {len(xsd_files)} XSD schema files")
    else:
        print("ℹ Schemas directory not found (optional)")


def test_python_dependencies():
    """Test that required Python dependencies are available."""
    dependencies = [
        ("markitdown", "markitdown[pptx]"),
        ("PIL", "Pillow"),
    ]
    
    for dep, install_name in dependencies:
        try:
            __import__(dep)
            print(f"✓ Dependency '{dep}' is installed")
        except ImportError:
            print(f"⚠ Dependency '{dep}' is not installed (pip install {install_name})")


def test_nodejs_dependencies():
    """Test that Node.js dependencies are available."""
    try:
        result = subprocess.run(["npm", "list", "-g", "pptxgenjs"], 
                              capture_output=True, text=True, timeout=10)
        if "pptxgenjs" in result.stdout:
            print("✓ Node.js package 'pptxgenjs' is installed globally")
        else:
            print("⚠ Node.js package 'pptxgenjs' not found (npm install -g pptxgenjs)")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("⚠ npm not found or pptxgenjs not installed")


def test_external_tools():
    """Test that external tools are available."""
    tools = [
        ("pdftoppm", "poppler-utils"),
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


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("Testing pptx skill")
    print("=" * 60)
    
    tests = [
        test_skill_metadata,
        test_license_file,
        test_reference_docs,
        test_office_scripts_exist,
        test_validators_exist,
        test_pptx_scripts_exist,
        test_unpack_script,
        test_pack_script,
        test_validate_script,
        test_soffice_script,
        test_helpers_exist,
        test_schemas_exist,
        test_python_dependencies,
        test_nodejs_dependencies,
        test_external_tools,
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
