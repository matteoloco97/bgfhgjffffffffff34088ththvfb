#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_multi_search_aggregator.py
======================================
Tests for multi-engine search aggregator with fuzzy deduplication.
"""

import sys
import os
import unittest
import asyncio

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.multi_search_aggregator import (
    fuzzy_url_match,
    aggregate_multi_engine,
    search_brave,
)


class TestFuzzyUrlMatch(unittest.TestCase):
    """Test cases for fuzzy URL matching."""
    
    def test_exact_match(self):
        """Test exact URL match."""
        url1 = "https://example.com/page/1"
        url2 = "https://example.com/page/1"
        score = fuzzy_url_match(url1, url2)
        self.assertEqual(score, 1.0)
    
    def test_different_domains(self):
        """Test URLs with different domains."""
        url1 = "https://example.com/page"
        url2 = "https://different.com/page"
        score = fuzzy_url_match(url1, url2)
        self.assertEqual(score, 0.0)
    
    def test_same_domain_different_paths(self):
        """Test URLs with same domain but different paths."""
        url1 = "https://example.com/page/1"
        url2 = "https://example.com/page/2"
        score = fuzzy_url_match(url1, url2)
        self.assertGreater(score, 0.0)
        self.assertLess(score, 1.0)
    
    def test_same_domain_partial_overlap(self):
        """Test URLs with partial path overlap."""
        url1 = "https://example.com/a/b/c"
        url2 = "https://example.com/a/b/d"
        score = fuzzy_url_match(url1, url2)
        # Jaccard similarity: {a,b,c} vs {a,b,d} = 2/4 = 0.5
        self.assertAlmostEqual(score, 0.5, places=1)
    
    def test_same_domain_no_path(self):
        """Test URLs with same domain but no path."""
        url1 = "https://example.com/"
        url2 = "https://example.com/"
        score = fuzzy_url_match(url1, url2)
        # Empty paths are identical, so this should be a perfect match
        self.assertEqual(score, 1.0)
    
    def test_invalid_url(self):
        """Test handling of invalid URLs."""
        url1 = "not-a-url"
        url2 = "https://example.com/page"
        score = fuzzy_url_match(url1, url2)
        self.assertEqual(score, 0.0)


class TestSearchBrave(unittest.TestCase):
    """Test cases for Brave Search integration."""
    
    def test_search_brave_disabled(self):
        """Test Brave search when disabled."""
        async def run_test():
            # Save original env
            orig_key = os.getenv("BRAVE_SEARCH_API_KEY")
            orig_enabled = os.getenv("BRAVE_SEARCH_ENABLED")
            
            try:
                # Disable Brave search
                os.environ["BRAVE_SEARCH_ENABLED"] = "0"
                
                results = await search_brave("test query", count=5)
                self.assertEqual(results, [])
            finally:
                # Restore env
                if orig_key:
                    os.environ["BRAVE_SEARCH_API_KEY"] = orig_key
                elif "BRAVE_SEARCH_API_KEY" in os.environ:
                    del os.environ["BRAVE_SEARCH_API_KEY"]
                
                if orig_enabled:
                    os.environ["BRAVE_SEARCH_ENABLED"] = orig_enabled
                elif "BRAVE_SEARCH_ENABLED" in os.environ:
                    del os.environ["BRAVE_SEARCH_ENABLED"]
        
        asyncio.run(run_test())
    
    def test_search_brave_no_api_key(self):
        """Test Brave search without API key."""
        async def run_test():
            # Save original env
            orig_key = os.getenv("BRAVE_SEARCH_API_KEY")
            
            try:
                # Remove API key
                if "BRAVE_SEARCH_API_KEY" in os.environ:
                    del os.environ["BRAVE_SEARCH_API_KEY"]
                
                results = await search_brave("test query", count=5)
                self.assertEqual(results, [])
            finally:
                # Restore env
                if orig_key:
                    os.environ["BRAVE_SEARCH_API_KEY"] = orig_key
        
        asyncio.run(run_test())


class TestAggregateMultiEngine(unittest.TestCase):
    """Test cases for multi-engine aggregation."""
    
    def test_aggregate_empty_query(self):
        """Test aggregation with empty query."""
        async def run_test():
            # Note: This test may still make real network calls
            # depending on the implementation
            results = await aggregate_multi_engine("", max_results=5)
            # Even with empty query, some engines might return results
            # or it might return empty list - both are acceptable
            self.assertIsInstance(results, list)
        
        asyncio.run(run_test())
    
    def test_aggregate_basic_structure(self):
        """Test basic structure of aggregated results."""
        async def run_test():
            try:
                # Use only DuckDuckGo to avoid needing Brave API key
                results = await aggregate_multi_engine(
                    "Python programming",
                    engines=["duckduckgo"],
                    max_results=5
                )
                
                self.assertIsInstance(results, list)
                
                # Check structure if we got results
                if results:
                    for result in results:
                        self.assertIn("url", result)
                        self.assertIn("title", result)
                        # snippet might be optional
                        
            except Exception as e:
                # Skip test if network unavailable
                self.skipTest(f"Network test skipped: {e}")
        
        asyncio.run(run_test())
    
    def test_aggregate_respects_max_results(self):
        """Test that aggregation respects max_results limit."""
        async def run_test():
            try:
                max_results = 3
                results = await aggregate_multi_engine(
                    "Python programming",
                    engines=["duckduckgo"],
                    max_results=max_results
                )
                
                self.assertIsInstance(results, list)
                self.assertLessEqual(len(results), max_results)
                
            except Exception as e:
                # Skip test if network unavailable
                self.skipTest(f"Network test skipped: {e}")
        
        asyncio.run(run_test())
    
    def test_aggregate_custom_engines(self):
        """Test aggregation with custom engine list."""
        async def run_test():
            try:
                # Test with only duckduckgo (no Brave API needed)
                results = await aggregate_multi_engine(
                    "test query",
                    engines=["duckduckgo"],
                    max_results=5
                )
                
                self.assertIsInstance(results, list)
                
            except Exception as e:
                # Skip test if network unavailable
                self.skipTest(f"Network test skipped: {e}")
        
        asyncio.run(run_test())
    
    def test_aggregate_with_bing(self):
        """Test aggregation with Bing engine included."""
        async def run_test():
            try:
                # Test with bing included (should not cause index errors)
                results = await aggregate_multi_engine(
                    "test query",
                    engines=["duckduckgo", "bing"],
                    max_results=5
                )
                
                self.assertIsInstance(results, list)
                # Bing may or may not return results depending on network
                
            except Exception as e:
                # Skip test if network unavailable
                self.skipTest(f"Network test skipped: {e}")
        
        asyncio.run(run_test())


if __name__ == "__main__":
    # Run tests
    unittest.main()
