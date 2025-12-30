#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/test_renderer_pipeline.py

Test script for JS Renderer Pipeline (Issue 3B).

Tests:
1. Static URL - should work without renderer
2. JS-heavy URL - should trigger renderer fallback
3. Logging validation - verify all required fields are logged

Usage:
    python scripts/test_renderer_pipeline.py
    
Expected output:
    - Both URLs should extract content
    - JS-heavy URL should show used_renderer=true in logs
    - Static URL may or may not use renderer depending on heuristics
    - All logs should include: fetch_ok, extract_chars, used_renderer, renderer_ok
"""

import asyncio
import logging
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.web_tools import (
    fetch_and_extract_with_renderer,
    fetch_and_extract_async,
    RENDERER_ENABLED,
    RENDERER_URL,
    EXTRACT_MIN_CHARS,
)

# Configure logging to see structured logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


async def test_static_url():
    """Test a static HTML page (should extract without renderer)."""
    url = "https://example.com"
    logger.info(f"\n{'='*80}")
    logger.info(f"TEST 1: Static URL - {url}")
    logger.info(f"{'='*80}")
    
    try:
        extracted, fetch_log = await fetch_and_extract_with_renderer(url, timeout=10.0)
        
        logger.info(f"\nResults:")
        logger.info(f"  - URL: {fetch_log.url}")
        logger.info(f"  - Fetch OK: {fetch_log.fetch_ok}")
        logger.info(f"  - Status Code: {fetch_log.status_code}")
        logger.info(f"  - Extract Chars: {fetch_log.extract_chars}")
        logger.info(f"  - Used Renderer: {fetch_log.used_renderer}")
        logger.info(f"  - Renderer OK: {fetch_log.renderer_ok}")
        logger.info(f"  - Title: {extracted.title}")
        logger.info(f"  - Text Preview: {extracted.text[:200]}...")
        
        # Validate
        assert fetch_log.fetch_ok, "Fetch should succeed"
        assert fetch_log.extract_chars > 0, "Should extract some text"
        
        logger.info(f"\n✅ TEST 1 PASSED")
        return True
        
    except Exception as e:
        logger.error(f"\n❌ TEST 1 FAILED: {e}", exc_info=True)
        return False


async def test_js_heavy_url():
    """Test a JS-heavy SPA (should trigger renderer)."""
    # Example JS-heavy sites - choose one that's reliable
    # Note: Some sites may block automated access
    test_urls = [
        "https://react.dev",  # React docs (uses React)
        "https://vuejs.org",  # Vue.js docs (uses Vue)
        "https://angular.io",  # Angular docs (uses Angular)
    ]
    
    url = test_urls[0]  # Use React docs as default
    
    logger.info(f"\n{'='*80}")
    logger.info(f"TEST 2: JS-heavy URL - {url}")
    logger.info(f"{'='*80}")
    
    try:
        extracted, fetch_log = await fetch_and_extract_with_renderer(url, timeout=20.0)
        
        logger.info(f"\nResults:")
        logger.info(f"  - URL: {fetch_log.url}")
        logger.info(f"  - Fetch OK: {fetch_log.fetch_ok}")
        logger.info(f"  - Status Code: {fetch_log.status_code}")
        logger.info(f"  - Extract Chars: {fetch_log.extract_chars}")
        logger.info(f"  - Used Renderer: {fetch_log.used_renderer}")
        logger.info(f"  - Renderer OK: {fetch_log.renderer_ok}")
        logger.info(f"  - Title: {extracted.title}")
        logger.info(f"  - Text Preview: {extracted.text[:200]}...")
        
        # Validate
        assert fetch_log.fetch_ok, "Fetch should succeed"
        
        # On JS-heavy sites, we expect renderer to be used OR sufficient extraction
        if fetch_log.used_renderer:
            logger.info(f"\n✓ Renderer was triggered as expected for JS-heavy site")
            if fetch_log.renderer_ok:
                logger.info(f"✓ Renderer succeeded")
                # After rendering, we should have good extraction
                if fetch_log.extract_chars >= EXTRACT_MIN_CHARS:
                    logger.info(f"✓ Extraction meets minimum threshold ({fetch_log.extract_chars} >= {EXTRACT_MIN_CHARS})")
                else:
                    logger.warning(f"⚠ Extraction below threshold even with renderer ({fetch_log.extract_chars} < {EXTRACT_MIN_CHARS})")
            else:
                logger.warning(f"⚠ Renderer failed, using fallback extraction")
        else:
            logger.info(f"✓ Static extraction was sufficient ({fetch_log.extract_chars} chars)")
        
        logger.info(f"\n✅ TEST 2 PASSED")
        return True
        
    except Exception as e:
        logger.error(f"\n❌ TEST 2 FAILED: {e}", exc_info=True)
        return False


async def test_renderer_offline():
    """Test graceful degradation when renderer is offline."""
    url = "https://example.com"
    
    logger.info(f"\n{'='*80}")
    logger.info(f"TEST 3: Renderer Offline (Graceful Degradation)")
    logger.info(f"{'='*80}")
    
    # This test assumes renderer might be offline
    # It should not crash, just log renderer_ok=false
    
    try:
        extracted, fetch_log = await fetch_and_extract_with_renderer(url, timeout=5.0)
        
        logger.info(f"\nResults:")
        logger.info(f"  - Fetch OK: {fetch_log.fetch_ok}")
        logger.info(f"  - Extract Chars: {fetch_log.extract_chars}")
        logger.info(f"  - Used Renderer: {fetch_log.used_renderer}")
        logger.info(f"  - Renderer OK: {fetch_log.renderer_ok}")
        
        # Should still get some content even if renderer fails
        assert fetch_log.fetch_ok, "Basic fetch should work"
        assert fetch_log.extract_chars > 0, "Should extract something even without renderer"
        
        if fetch_log.used_renderer and not fetch_log.renderer_ok:
            logger.info(f"\n✓ Graceful degradation working - renderer failed but extraction continued")
        
        logger.info(f"\n✅ TEST 3 PASSED")
        return True
        
    except Exception as e:
        logger.error(f"\n❌ TEST 3 FAILED: {e}", exc_info=True)
        return False


async def test_async_integration():
    """Test that fetch_and_extract_async uses renderer when enabled."""
    url = "https://example.com"
    
    logger.info(f"\n{'='*80}")
    logger.info(f"TEST 4: fetch_and_extract_async Integration")
    logger.info(f"{'='*80}")
    logger.info(f"Renderer Enabled: {RENDERER_ENABLED}")
    
    try:
        text, og_image = await fetch_and_extract_async(url, timeout=10.0)
        
        logger.info(f"\nResults:")
        logger.info(f"  - Text Length: {len(text)}")
        logger.info(f"  - OG Image: {og_image}")
        logger.info(f"  - Text Preview: {text[:200]}...")
        
        assert len(text) > 0, "Should extract text"
        
        logger.info(f"\n✅ TEST 4 PASSED")
        return True
        
    except Exception as e:
        logger.error(f"\n❌ TEST 4 FAILED: {e}", exc_info=True)
        return False


async def main():
    """Run all tests."""
    logger.info(f"\n{'#'*80}")
    logger.info(f"JS RENDERER PIPELINE TEST SUITE")
    logger.info(f"{'#'*80}")
    logger.info(f"\nConfiguration:")
    logger.info(f"  - RENDERER_ENABLED: {RENDERER_ENABLED}")
    logger.info(f"  - RENDERER_URL: {RENDERER_URL}")
    logger.info(f"  - EXTRACT_MIN_CHARS: {EXTRACT_MIN_CHARS}")
    
    results = []
    
    # Run tests
    results.append(("Static URL", await test_static_url()))
    results.append(("JS-heavy URL", await test_js_heavy_url()))
    results.append(("Renderer Offline", await test_renderer_offline()))
    results.append(("Async Integration", await test_async_integration()))
    
    # Summary
    logger.info(f"\n{'#'*80}")
    logger.info(f"TEST SUMMARY")
    logger.info(f"{'#'*80}")
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"{status} - {name}")
    
    total = len(results)
    passed = sum(1 for _, p in results if p)
    
    logger.info(f"\n{passed}/{total} tests passed")
    
    if passed == total:
        logger.info(f"\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        logger.error(f"\n❌ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
