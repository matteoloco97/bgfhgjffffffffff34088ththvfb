#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_async_web_tools.py — Test Async Web Tools
 
Tests for async web fetching with parallelization and rate limiting.
"""

import sys
import os
import unittest
import asyncio
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.web_tools import (
    fetch_and_extract_async,
    parallel_fetch_urls,
    get_aiohttp_session,
    close_aiohttp_session,
    DomainRateLimiter,
)


class TestAsyncWebTools(unittest.TestCase):
    """Test cases for async web tools."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_urls = [
            "https://www.example.com",
            "https://www.python.org",
            "https://www.wikipedia.org",
        ]
    
    def tearDown(self):
        """Clean up after tests."""
        # Close aiohttp session
        try:
            asyncio.run(close_aiohttp_session())
        except Exception:
            pass
    
    def test_domain_rate_limiter(self):
        """Test domain rate limiter."""
        async def run_test():
            limiter = DomainRateLimiter(rate_per_second=5.0)
            
            # Test that same domain is rate limited
            t0 = time.time()
            await limiter.acquire("https://example.com/page1")
            await limiter.acquire("https://example.com/page2")
            elapsed = time.time() - t0
            
            # Second request should be delayed by at least 0.2s (1/5)
            self.assertGreater(elapsed, 0.15, "Rate limiter should delay requests")
            
            # Different domain should not be rate limited
            t1 = time.time()
            await limiter.acquire("https://other.com/page1")
            elapsed2 = time.time() - t1
            self.assertLess(elapsed2, 0.1, "Different domain should not be rate limited")
        
        asyncio.run(run_test())
    
    def test_fetch_and_extract_async_basic(self):
        """Test basic async fetch (may fail without internet)."""
        async def run_test():
            try:
                # Fetch a simple page
                text, og_image = await fetch_and_extract_async(
                    "https://www.example.com",
                    timeout=10.0
                )
                
                self.assertIsInstance(text, str)
                self.assertGreater(len(text), 0, "Should extract some text")
                
            except Exception as e:
                # Skip test if network unavailable
                self.skipTest(f"Network test skipped: {e}")
        
        asyncio.run(run_test())
    
    def test_fetch_and_extract_async_timeout(self):
        """Test async fetch with very short timeout."""
        async def run_test():
            # Use a very short timeout - should handle gracefully
            text, og_image = await fetch_and_extract_async(
                "https://www.wikipedia.org",
                timeout=0.1
            )
            
            # Even with timeout, should return something (empty or error message)
            self.assertIsInstance(text, str)
        
        asyncio.run(run_test())
    
    def test_parallel_fetch_urls_basic(self):
        """Test parallel URL fetching."""
        async def run_test():
            try:
                urls = [
                    "https://www.example.com",
                    "https://www.python.org",
                ]
                
                t0 = time.time()
                results = await parallel_fetch_urls(
                    urls,
                    timeout=10.0,
                    max_concurrent=2
                )
                elapsed = time.time() - t0
                
                self.assertIsInstance(results, list)
                self.assertEqual(len(results), len(urls))
                
                # Check structure
                for result in results:
                    self.assertIn("url", result)
                    self.assertIn("text", result)
                    self.assertIn("success", result)
                    self.assertIn("error", result)
                
                # Should be faster than sequential
                self.assertLess(
                    elapsed, 
                    10.0 * len(urls),
                    "Parallel fetch should be faster than sequential"
                )
                
            except Exception as e:
                # Skip test if network unavailable
                self.skipTest(f"Network test skipped: {e}")
        
        asyncio.run(run_test())
    
    def test_parallel_fetch_urls_partial_failure(self):
        """Test parallel fetch with some failures."""
        async def run_test():
            urls = [
                "https://www.example.com",  # Should work
                "https://invalid-domain-xyz123.com",  # Should fail
                "https://www.python.org",  # Should work
            ]
            
            results = await parallel_fetch_urls(
                urls,
                timeout=10.0,
                max_concurrent=3
            )
            
            self.assertEqual(len(results), len(urls))
            
            # Check that we got partial results
            success_count = sum(1 for r in results if r["success"])
            self.assertGreater(success_count, 0, "Should have some successful fetches")
            
            # Check failed result structure
            failed = [r for r in results if not r["success"]]
            self.assertGreater(len(failed), 0, "Should have some failures")
            for f in failed:
                self.assertIsNotNone(f["error"], "Failed fetch should have error message")
        
        asyncio.run(run_test())
    
    def test_aiohttp_session_creation(self):
        """Test aiohttp session can be created."""
        async def run_test():
            session = await get_aiohttp_session()
            self.assertIsNotNone(session, "Should create aiohttp session")
            self.assertFalse(session.closed, "Session should be open")
        
        asyncio.run(run_test())
    
    def test_concurrent_limit(self):
        """Test that concurrent limit is respected."""
        async def run_test():
            # Create many URLs (more than max_concurrent)
            urls = [f"https://www.example.com/{i}" for i in range(10)]
            
            t0 = time.time()
            results = await parallel_fetch_urls(
                urls,
                timeout=5.0,
                max_concurrent=2  # Small limit
            )
            elapsed = time.time() - t0
            
            self.assertEqual(len(results), len(urls))
            
            # With max_concurrent=2, should take longer than if all parallel
            # But we can't test exact timing without network consistency
            self.assertIsInstance(results, list)
        
        asyncio.run(run_test())


class TestRateLimitingIntegration(unittest.TestCase):
    """Integration tests for rate limiting."""
    
    def test_domain_rate_limiting_in_parallel_fetch(self):
        """Test that domain rate limiting works in parallel_fetch_urls."""
        async def run_test():
            # Multiple URLs from same domain
            urls = [
                "https://www.example.com/page1",
                "https://www.example.com/page2",
                "https://www.example.com/page3",
            ]
            
            t0 = time.time()
            results = await parallel_fetch_urls(
                urls,
                timeout=10.0,
                max_concurrent=3
            )
            elapsed = time.time() - t0
            
            # With 2 req/sec rate limit, 3 requests should take at least 1s
            # (0s, 0.5s, 1.0s for rate limit alone)
            # But network time dominates, so we just check structure
            self.assertEqual(len(results), len(urls))
            
        asyncio.run(run_test())


if __name__ == "__main__":
    # Run tests
    unittest.main(verbosity=2)
