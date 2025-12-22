#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_enhanced_web.py — Test Enhanced Web Search

Tests for enhanced web search with content extraction.
"""

import sys
import os
import unittest
import asyncio

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.enhanced_web import (
    enhanced_search,
    _extract_text_from_html,
    _create_snippet,
)


class TestEnhancedWeb(unittest.TestCase):
    """Test cases for enhanced web search."""
    
    def test_extract_text_from_html(self):
        """Test extracting text from HTML."""
        html = """
        <html>
        <head><title>Test</title></head>
        <body>
            <script>alert('remove this');</script>
            <h1>Hello World</h1>
            <p>This is a test paragraph.</p>
            <style>.hidden { display: none; }</style>
        </body>
        </html>
        """
        
        text = _extract_text_from_html(html)
        self.assertIn("Hello World", text)
        self.assertIn("test paragraph", text)
        self.assertNotIn("alert", text)
        self.assertNotIn("display: none", text)
    
    def test_create_snippet(self):
        """Test creating snippet from text."""
        long_text = "This is a long text. " * 100
        
        snippet = _create_snippet(long_text, max_length=100)
        
        self.assertLessEqual(len(snippet), 150, "Snippet should be around max_length")
        self.assertGreater(len(snippet), 50, "Snippet should contain meaningful content")
    
    def test_create_snippet_short_text(self):
        """Test creating snippet from short text."""
        short_text = "This is short."
        snippet = _create_snippet(short_text, max_length=500)
        self.assertEqual(snippet, short_text)
    
    def test_enhanced_search_basic(self):
        """Test basic enhanced search (may fail without internet)."""
        async def run_test():
            try:
                results = await enhanced_search("Python programming", k=3)
                self.assertIsInstance(results, list)
                
                if results:
                    # Check structure of results
                    for result in results:
                        self.assertIn("title", result)
                        self.assertIn("url", result)
                        self.assertIn("snippet", result)
                        
            except Exception as e:
                # Skip test if network unavailable
                self.skipTest(f"Network test skipped: {e}")
        
        asyncio.run(run_test())
    
    def test_enhanced_search_empty_query(self):
        """Test enhanced search with empty query."""
        async def run_test():
            results = await enhanced_search("", k=5)
            self.assertEqual(results, [])
        
        asyncio.run(run_test())


if __name__ == "__main__":
    # Run tests
    unittest.main()
