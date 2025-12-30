#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_renderer_integration.py

Unit tests for renderer integration (Issue 3B).
Tests the logic without requiring network access or a running renderer service.
"""

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.web_tools import (
    fetch_and_extract_async,
    fetch_and_extract_with_renderer,
    _is_js_heavy,
    ExtractedContent,
    FetchLog,
    RENDERER_ENABLED,
)


class TestRendererIntegration(unittest.TestCase):
    """Test renderer integration without network calls."""
    
    def test_js_heavy_detection_short_text(self):
        """Test that short extracted text triggers JS-heavy detection."""
        html = "<html><body><p>Short</p></body></html>"
        extracted_text = "Short"
        
        result = _is_js_heavy(html, extracted_text)
        self.assertTrue(result, "Short text should trigger JS-heavy detection")
    
    def test_js_heavy_detection_react(self):
        """Test that React markers trigger JS-heavy detection."""
        html = """
        <html>
        <body>
            <div id="react-root"></div>
            <script>__NEXT_DATA__</script>
        </body>
        </html>
        """
        extracted_text = "Some reasonable amount of text here to not trigger length check."
        
        result = _is_js_heavy(html, extracted_text)
        self.assertTrue(result, "React markers should trigger JS-heavy detection")
    
    def test_js_heavy_detection_sufficient_content(self):
        """Test that sufficient static content doesn't trigger JS-heavy detection."""
        html = "<html><body><p>" + ("Long content " * 200) + "</p></body></html>"
        extracted_text = "Long content " * 200
        
        result = _is_js_heavy(html, extracted_text)
        self.assertFalse(result, "Sufficient content should not trigger JS-heavy detection")
    
    def test_extracted_content_dataclass(self):
        """Test ExtractedContent dataclass."""
        content = ExtractedContent(
            text="Test content",
            title="Test Title",
            meta_description="Test description",
            og_image="https://example.com/image.jpg"
        )
        
        self.assertEqual(content.text, "Test content")
        self.assertEqual(content.title, "Test Title")
        self.assertEqual(content.content_length, len("Test content"))
        self.assertEqual(content.og_image, "https://example.com/image.jpg")
    
    def test_fetch_log_dataclass(self):
        """Test FetchLog dataclass and JSON serialization."""
        log = FetchLog(
            url="https://example.com",
            fetch_ok=True,
            status_code=200,
            extract_chars=1234,
            used_renderer=True,
            renderer_ok=True,
        )
        
        self.assertEqual(log.url, "https://example.com")
        self.assertTrue(log.fetch_ok)
        self.assertTrue(log.used_renderer)
        self.assertTrue(log.renderer_ok)
        
        # Test JSON serialization
        json_str = log.to_json()
        self.assertIn("https://example.com", json_str)
        self.assertIn('"fetch_ok": true', json_str.lower())
    
    @patch('core.web_tools.fetch_url')
    @patch('core.web_tools.extract_text')
    @patch('core.web_tools._is_js_heavy')
    async def test_fetch_with_renderer_no_js(self, mock_is_js_heavy, mock_extract_text, mock_fetch_url):
        """Test fetch_and_extract_with_renderer when page is not JS-heavy."""
        # Mock responses
        mock_fetch_url.return_value = (
            b"<html><body>Test content</body></html>",
            "https://example.com",
            200,
            {"Content-Type": "text/html"}
        )
        
        mock_extract_text.return_value = ExtractedContent(
            text="Test content extracted",
            title="Test",
            content_length=23
        )
        
        mock_is_js_heavy.return_value = False
        
        # Call function
        extracted, fetch_log = await fetch_and_extract_with_renderer("https://example.com")
        
        # Assertions
        self.assertTrue(fetch_log.fetch_ok)
        self.assertFalse(fetch_log.used_renderer)
        self.assertEqual(extracted.text, "Test content extracted")
    
    @patch('core.web_tools.fetch_url')
    @patch('core.web_tools.extract_text')
    @patch('core.web_tools._is_js_heavy')
    @patch('core.web_tools._call_renderer')
    async def test_fetch_with_renderer_js_heavy(
        self, 
        mock_call_renderer, 
        mock_is_js_heavy, 
        mock_extract_text, 
        mock_fetch_url
    ):
        """Test fetch_and_extract_with_renderer when page is JS-heavy."""
        # Mock initial fetch
        mock_fetch_url.return_value = (
            b"<html><body><div id='react-root'></div></body></html>",
            "https://example.com",
            200,
            {"Content-Type": "text/html"}
        )
        
        # Mock initial extraction (insufficient)
        mock_extract_text.side_effect = [
            ExtractedContent(text="Short", content_length=5),
            ExtractedContent(text="Full rendered content", content_length=21)
        ]
        
        # Trigger JS-heavy detection
        mock_is_js_heavy.return_value = True
        
        # Mock renderer success
        mock_call_renderer.return_value = {
            "ok": True,
            "html": "<html><body>Rendered content</body></html>",
            "final_url": "https://example.com",
            "status_code": 200,
        }
        
        # Call function
        extracted, fetch_log = await fetch_and_extract_with_renderer("https://example.com")
        
        # Assertions
        self.assertTrue(fetch_log.fetch_ok)
        self.assertTrue(fetch_log.used_renderer)
        self.assertTrue(fetch_log.renderer_ok)
        self.assertEqual(extracted.text, "Full rendered content")
        mock_call_renderer.assert_called_once()
    
    @patch('core.web_tools.RENDERER_ENABLED', True)
    @patch('core.web_tools.fetch_and_extract_with_renderer')
    async def test_fetch_async_uses_renderer_when_enabled(self, mock_fetch_with_renderer):
        """Test that fetch_and_extract_async uses renderer when enabled."""
        # Mock the renderer response
        mock_fetch_with_renderer.return_value = (
            ExtractedContent(text="Rendered text", og_image="https://example.com/img.jpg"),
            FetchLog(url="https://example.com", fetch_ok=True, extract_chars=13)
        )
        
        # Call function
        text, og_image = await fetch_and_extract_async("https://example.com")
        
        # Assertions
        self.assertEqual(text, "Rendered text")
        self.assertEqual(og_image, "https://example.com/img.jpg")
        mock_fetch_with_renderer.assert_called_once()


def run_async_test(coro):
    """Helper to run async tests."""
    return asyncio.run(coro)


if __name__ == "__main__":
    # For now, run only the sync tests
    # Async tests can be run with pytest-asyncio in a full environment
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add only sync tests
    suite.addTest(TestRendererIntegration('test_js_heavy_detection_short_text'))
    suite.addTest(TestRendererIntegration('test_js_heavy_detection_react'))
    suite.addTest(TestRendererIntegration('test_js_heavy_detection_sufficient_content'))
    suite.addTest(TestRendererIntegration('test_extracted_content_dataclass'))
    suite.addTest(TestRendererIntegration('test_fetch_log_dataclass'))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "="*80)
    print("NOTE: Async tests require pytest-asyncio and are skipped in this environment.")
    print("Run with: pytest tests/test_renderer_integration.py")
    print("="*80)
    
    sys.exit(0 if result.wasSuccessful() else 1)
