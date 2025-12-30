#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/test_fetch_extract.py

Test script for Issue 3: Fetch & Extract functionality.

Tests the crawler-grade fetch and extraction pipeline including:
- Basic HTML fetch and extraction
- JS-heavy detection heuristics  
- Renderer fallback (if available)
- Structured logging

Usage:
    python scripts/test_fetch_extract.py [--urls URL1,URL2,...]
    python scripts/test_fetch_extract.py --file urls.txt
    
Example:
    python scripts/test_fetch_extract.py --urls https://example.com,https://react.dev
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from typing import List, Dict, Any

# Add project root to path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Default test URLs (mix of static and JS-heavy)
DEFAULT_TEST_URLS = [
    # Static sites (should work without renderer)
    "https://www.example.com",
    "https://www.wikipedia.org",
    "https://httpbin.org/html",
    
    # News/Content sites
    "https://www.python.org",
    "https://docs.python.org/3/",
    
    # Potentially JS-heavy sites (may trigger renderer)
    "https://github.com",
    "https://www.google.com",
    
    # Italian sites (original use case)
    "https://www.ansa.it",
    "https://www.ilmeteo.it",
    
    # SPA/JS-heavy (likely need renderer)
    "https://react.dev",
]


def print_table(results: List[Dict[str, Any]]) -> None:
    """Print results as a formatted table."""
    # Calculate column widths
    url_width = max(40, max(len(r.get("url", "")[:50]) for r in results))
    
    # Header
    print("\n" + "=" * 100)
    print(f"{'URL':<{url_width}} | {'Chars':>7} | {'Renderer':>8} | {'OK':>4} | {'Time':>8} | Notes")
    print("-" * 100)
    
    # Rows
    for r in results:
        url = r.get("url", "")[:url_width]
        chars = r.get("extract_chars", 0)
        used_renderer = "Yes" if r.get("used_renderer", False) else "No"
        renderer_ok = ""
        if r.get("used_renderer"):
            renderer_ok = " ✓" if r.get("renderer_ok", False) else " ✗"
        ok = "✓" if r.get("ok", False) else "✗"
        time_ms = r.get("time_ms", 0)
        notes = r.get("notes", "")
        
        print(f"{url:<{url_width}} | {chars:>7} | {used_renderer:>6}{renderer_ok:>2} | {ok:>4} | {time_ms:>6.0f}ms | {notes}")
    
    print("=" * 100)
    
    # Summary
    total = len(results)
    successful = sum(1 for r in results if r.get("ok", False))
    used_renderer_count = sum(1 for r in results if r.get("used_renderer", False))
    renderer_ok_count = sum(1 for r in results if r.get("renderer_ok", False))
    
    print(f"\nSummary: {successful}/{total} successful ({100*successful/total:.1f}%)")
    print(f"Renderer used: {used_renderer_count}, Renderer OK: {renderer_ok_count}")
    
    # Check acceptance criteria
    min_chars = int(os.getenv("EXTRACT_MIN_CHARS", "800"))
    readable_count = sum(1 for r in results if r.get("extract_chars", 0) >= min_chars)
    readable_pct = 100 * readable_count / total
    
    print(f"\nAcceptance Criteria:")
    print(f"  - Pages with >= {min_chars} chars: {readable_count}/{total} ({readable_pct:.1f}%)")
    print(f"  - Target: >= 80%")
    print(f"  - Status: {'✓ PASS' if readable_pct >= 80 else '✗ FAIL'}")


async def test_url(url: str) -> Dict[str, Any]:
    """Test fetch and extract for a single URL."""
    from core.web_tools import (
        fetch_and_extract_with_renderer,
        EXTRACT_MIN_CHARS,
        RENDERER_ENABLED,
    )
    
    result = {
        "url": url,
        "ok": False,
        "extract_chars": 0,
        "used_renderer": False,
        "renderer_ok": False,
        "time_ms": 0,
        "notes": "",
    }
    
    try:
        t0 = time.time()
        extracted, fetch_log = await fetch_and_extract_with_renderer(url)
        elapsed = time.time() - t0
        
        result["time_ms"] = elapsed * 1000
        result["extract_chars"] = extracted.content_length
        result["used_renderer"] = fetch_log.used_renderer
        result["renderer_ok"] = fetch_log.renderer_ok
        result["ok"] = fetch_log.fetch_ok and extracted.content_length > 0
        
        # Add notes
        notes = []
        if extracted.title:
            notes.append(f"title={len(extracted.title)}c")
        if fetch_log.used_renderer and not fetch_log.renderer_ok:
            notes.append("renderer_failed")
        if not fetch_log.fetch_ok:
            notes.append(f"fetch_failed: {fetch_log.error}")
        if extracted.content_length < EXTRACT_MIN_CHARS:
            notes.append(f"short(<{EXTRACT_MIN_CHARS})")
        
        result["notes"] = ", ".join(notes)
        
    except Exception as e:
        result["notes"] = f"error: {str(e)[:50]}"
    
    return result


async def run_tests(urls: List[str]) -> List[Dict[str, Any]]:
    """Run tests for all URLs."""
    print(f"\nTesting {len(urls)} URLs...")
    print(f"Renderer enabled: {os.getenv('RENDERER_ENABLED', '1')}")
    print(f"Min chars threshold: {os.getenv('EXTRACT_MIN_CHARS', '800')}")
    print("-" * 50)
    
    results = []
    
    for i, url in enumerate(urls):
        print(f"[{i+1}/{len(urls)}] Testing: {url[:60]}...", end=" ", flush=True)
        result = await test_url(url)
        
        status = "✓" if result["ok"] else "✗"
        chars = result["extract_chars"]
        time_ms = result["time_ms"]
        print(f"{status} {chars} chars in {time_ms:.0f}ms")
        
        results.append(result)
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Test fetch & extract pipeline for Issue 3"
    )
    parser.add_argument(
        "--urls",
        type=str,
        help="Comma-separated list of URLs to test",
    )
    parser.add_argument(
        "--file",
        type=str,
        help="File containing URLs (one per line)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    
    args = parser.parse_args()
    
    # Determine URLs to test
    urls = DEFAULT_TEST_URLS
    
    if args.urls:
        urls = [u.strip() for u in args.urls.split(",") if u.strip()]
    elif args.file:
        try:
            with open(args.file, "r") as f:
                urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        except Exception as e:
            print(f"Error reading file: {e}")
            sys.exit(1)
    
    if not urls:
        print("No URLs to test")
        sys.exit(1)
    
    # Run tests
    results = asyncio.run(run_tests(urls))
    
    # Output
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print_table(results)


if __name__ == "__main__":
    main()
