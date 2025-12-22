#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_async_web_tools_unit.py — Unit Tests for Async Web Tools
 
Unit tests that don't require network access.
"""

import sys
import os
import unittest
import asyncio
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.web_tools import DomainRateLimiter


class TestDomainRateLimiter(unittest.TestCase):
    """Unit tests for DomainRateLimiter class."""
    
    def test_rate_limiter_initialization(self):
        """Test rate limiter can be initialized."""
        limiter = DomainRateLimiter(rate_per_second=5.0)
        self.assertEqual(limiter.rate_per_second, 5.0)
        self.assertAlmostEqual(limiter.min_interval, 0.2, places=2)
    
    def test_rate_limiter_zero_rate(self):
        """Test rate limiter with zero rate (no limiting)."""
        limiter = DomainRateLimiter(rate_per_second=0.0)
        self.assertEqual(limiter.min_interval, 0)
    
    def test_extract_domain(self):
        """Test domain extraction from URL."""
        limiter = DomainRateLimiter()
        
        domain = limiter._extract_domain("https://www.example.com/path")
        self.assertEqual(domain, "www.example.com")
        
        domain = limiter._extract_domain("http://subdomain.example.com:8080/page")
        self.assertEqual(domain, "subdomain.example.com:8080")
        
        domain = limiter._extract_domain("invalid-url")
        self.assertEqual(domain, "")
    
    def test_rate_limiting_same_domain(self):
        """Test that same domain requests are rate limited."""
        async def run_test():
            limiter = DomainRateLimiter(rate_per_second=5.0)  # 0.2s between requests
            
            # First request - should be immediate
            t0 = time.time()
            await limiter.acquire("https://example.com/page1")
            t1 = time.time()
            elapsed1 = t1 - t0
            self.assertLess(elapsed1, 0.1, "First request should be immediate")
            
            # Second request to same domain - should be delayed
            t2 = time.time()
            await limiter.acquire("https://example.com/page2")
            t3 = time.time()
            elapsed2 = t3 - t2
            
            # Should wait at least min_interval (0.2s)
            self.assertGreater(
                elapsed2, 
                0.15,  # Allow some slack for timing
                "Second request to same domain should be rate limited"
            )
        
        asyncio.run(run_test())
    
    def test_rate_limiting_different_domains(self):
        """Test that different domain requests are not rate limited."""
        async def run_test():
            limiter = DomainRateLimiter(rate_per_second=5.0)
            
            # First domain
            await limiter.acquire("https://example.com/page1")
            
            # Different domain - should not be delayed
            t0 = time.time()
            await limiter.acquire("https://other.com/page1")
            elapsed = time.time() - t0
            
            self.assertLess(
                elapsed, 
                0.1,
                "Different domain should not be rate limited"
            )
        
        asyncio.run(run_test())
    
    def test_rate_limiting_concurrent_different_domains(self):
        """Test concurrent requests to different domains."""
        async def run_test():
            limiter = DomainRateLimiter(rate_per_second=5.0)
            
            # Concurrent requests to different domains should complete quickly
            tasks = [
                limiter.acquire("https://example1.com/page"),
                limiter.acquire("https://example2.com/page"),
                limiter.acquire("https://example3.com/page"),
            ]
            
            t0 = time.time()
            await asyncio.gather(*tasks)
            elapsed = time.time() - t0
            
            # Should be fast since all different domains
            self.assertLess(
                elapsed,
                0.5,
                "Concurrent requests to different domains should be fast"
            )
        
        asyncio.run(run_test())
    
    def test_rate_limiting_concurrent_same_domain(self):
        """Test concurrent requests to same domain."""
        async def run_test():
            limiter = DomainRateLimiter(rate_per_second=5.0)  # 0.2s interval
            
            # Concurrent requests to same domain should be serialized
            tasks = [
                limiter.acquire("https://example.com/page1"),
                limiter.acquire("https://example.com/page2"),
                limiter.acquire("https://example.com/page3"),
            ]
            
            t0 = time.time()
            await asyncio.gather(*tasks)
            elapsed = time.time() - t0
            
            # Should take at least 0.4s (3 requests * 0.2s interval - first is immediate)
            self.assertGreater(
                elapsed,
                0.3,  # Allow some slack
                "Concurrent requests to same domain should be serialized"
            )
        
        asyncio.run(run_test())


class TestAsyncWebToolsConfig(unittest.TestCase):
    """Test configuration and initialization."""
    
    def test_config_defaults(self):
        """Test that configuration defaults are sensible."""
        from core.web_tools import (
            HTTP_MAX_CONCURRENT,
            HTTP_RATE_LIMIT_PER_DOMAIN,
            MAX_RETRIES_ASYNC,
            BACKOFF_BASE,
            BACKOFF_MAX,
        )
        
        self.assertEqual(HTTP_MAX_CONCURRENT, 6)
        self.assertEqual(HTTP_RATE_LIMIT_PER_DOMAIN, 2.0)
        self.assertEqual(MAX_RETRIES_ASYNC, 3)
        self.assertEqual(BACKOFF_BASE, 0.5)
        self.assertEqual(BACKOFF_MAX, 10.0)


if __name__ == "__main__":
    # Run tests
    unittest.main(verbosity=2)
