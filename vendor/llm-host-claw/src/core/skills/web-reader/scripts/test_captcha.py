#!/usr/bin/env python3
"""CAPTCHA detection test for web-reader skill."""

import asyncio
import sys
import os
import importlib.util

# Load web_reader module dynamically
spec = importlib.util.spec_from_file_location("web_reader", os.path.join(os.path.dirname(__file__), "web-reader.py"))
web_reader_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web_reader_module)
WebReader = web_reader_module.WebReader

async def test_captcha_detection():
    """Test CAPTCHA detection on a page with captcha keywords."""
    test_cases = [
        ("https://example.com", False, "Normal page"),
        ("https://news.ycombinator.com", False, "Normal site (should not detect CAPTCHA)"),
    ]
    
    print("CAPTCHA Detection Test Results:\n")
    results = []
    
    async with WebReader(stealth=True) as reader:
        for url, expected_captcha, description in test_cases:
            result = await reader.read(url)
            detected = result.captcha_detected
            
            status = "PASS" if detected == expected_captcha else "FAIL"
            results.append({
                "url": url,
                "description": description,
                "expected_captcha": expected_captcha,
                "detected": detected,
                "status": status
            })
            
            print(f"[{status}] {description}")
            print(f"  URL: {url}")
            print(f"  CAPTCHA detected: {detected} (expected: {expected_captcha})")
            print()
    
    # Save results
    output_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "test-workspace/iteration-1/eval-5/with_skill/outputs/captcha_result.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        import json
        json.dump(results, f, indent=2)
    
    passed = sum(1 for r in results if r["status"] == "PASS")
    print(f"\nTest Summary: {passed}/{len(results)} passed")
    
    return results

if __name__ == "__main__":
    asyncio.run(test_captcha_detection())
