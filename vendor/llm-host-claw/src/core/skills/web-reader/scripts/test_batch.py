#!/usr/bin/env python3
"""Batch processing test for web-reader skill."""

import asyncio
import json
import sys
import os
import importlib.util

# Load web_reader module dynamically
spec = importlib.util.spec_from_file_location("web_reader", os.path.join(os.path.dirname(__file__), "web-reader.py"))
web_reader_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web_reader_module)
WebReader = web_reader_module.WebReader

async def test_batch():
    """Test batch processing of multiple URLs."""
    urls = [
        "https://example.com",
        "https://httpbin.org/html",
        "https://news.ycombinator.com"
    ]
    
    results = []
    
    async with WebReader(stealth=True) as reader:
        for url in urls:
            print(f"Processing: {url}")
            result = await reader.read(url)
            results.append({
                "url": result.url,
                "title": result.title,
                "success": result.error is None,
                "text_length": len(result.text)
            })
            print(f"  -> {result.title[:50]}...")
    
    # Save results
    output_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "test-workspace/iteration-1/eval-4/with_skill/outputs/batch_result.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\nBatch test complete! Processed {len(results)} URLs.")
    print(f"Results saved to {output_path}")
    
    return results

if __name__ == "__main__":
    results = asyncio.run(test_batch())
    print("\nSummary:")
    for r in results:
        status = "✓" if r["success"] else "✗"
        print(f"  {status} {r['url']} - {r['title'][:30]}...")
