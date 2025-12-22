#!/usr/bin/env python3
"""
tests/test_web_synthesis_optimization.py
=========================================

Test suite for web synthesis optimization features:
- LLM config presets
- Smart extract trimming
- Pre-compiled regex patterns
- Optimized LLM parameters
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
from core.llm_config import get_preset, to_payload_params, list_presets, get_preset_info
from core.web_response_formatter import (
    smart_trim_extracts,
    _clean_extract,
    _approx_tokens,
    _extract_keywords,
    _score_extract_relevance,
)


class TestLLMConfig(unittest.TestCase):
    """Test LLM configuration presets."""
    
    def test_get_preset_web_synthesis(self):
        """Test web_synthesis preset retrieval."""
        preset = get_preset("web_synthesis")
        self.assertIsNotNone(preset)
        self.assertEqual(preset.temperature, 0.2)
        self.assertEqual(preset.max_tokens, 120)
        self.assertIn("---", preset.stop_sequences)
    
    def test_get_preset_fallback(self):
        """Test fallback to chat preset for unknown names."""
        preset = get_preset("nonexistent_preset")
        self.assertIsNotNone(preset)
        self.assertEqual(preset.temperature, 0.7)  # chat default
    
    def test_list_presets(self):
        """Test listing all available presets."""
        presets = list_presets()
        self.assertIn("web_synthesis", presets)
        self.assertIn("chat", presets)
        self.assertIn("code_generation", presets)
    
    def test_to_payload_params(self):
        """Test conversion to payload parameters."""
        preset = get_preset("web_synthesis")
        params = to_payload_params(preset)
        
        self.assertEqual(params["temperature"], 0.2)
        self.assertEqual(params["max_tokens"], 120)
        self.assertEqual(params["top_p"], 0.9)
        self.assertIn("stop", params)
    
    def test_get_preset_info(self):
        """Test getting preset information."""
        info = get_preset_info("web_synthesis")
        self.assertIsNotNone(info)
        self.assertIn("description", info)
        self.assertIn("temperature", info)


class TestSmartTrimExtracts(unittest.TestCase):
    """Test smart extract trimming functionality."""
    
    def setUp(self):
        """Set up test data."""
        self.sample_extracts = [
            {
                "url": "https://example.com/1",
                "title": "Bitcoin Price Analysis",
                "text": "Bitcoin is currently trading at $45000. " * 50
            },
            {
                "url": "https://example.com/2",
                "title": "Cryptocurrency News",
                "text": "Latest crypto market updates and analysis. " * 50
            },
            {
                "url": "https://example.com/3",
                "title": "Investment Guide",
                "text": "How to invest in digital currencies. " * 50
            },
        ]
    
    def test_smart_trim_limits_sources(self):
        """Test that smart_trim_extracts limits number of sources."""
        result = smart_trim_extracts(
            self.sample_extracts * 3,  # 9 extracts
            query="Bitcoin price",
            max_sources=3
        )
        self.assertLessEqual(len(result), 3)
    
    def test_smart_trim_reduces_tokens(self):
        """Test that smart trimming reduces total tokens."""
        result = smart_trim_extracts(
            self.sample_extracts,
            query="Bitcoin price",
            max_total_tokens=200
        )
        
        total_tokens = sum(ext.get("tokens", 0) for ext in result)
        self.assertLessEqual(total_tokens, 200)
    
    def test_smart_trim_prioritizes_relevant(self):
        """Test that relevant extracts are prioritized."""
        result = smart_trim_extracts(
            self.sample_extracts,
            query="Bitcoin price analysis",
            max_sources=2
        )
        
        # First result should be most relevant (contains "Bitcoin" and "Price")
        self.assertGreater(result[0].get("relevance_score", 0), 0)
    
    def test_smart_trim_empty_input(self):
        """Test handling of empty input."""
        result = smart_trim_extracts([], query="test")
        self.assertEqual(len(result), 0)


class TestCleanExtract(unittest.TestCase):
    """Test HTML cleaning and duplicate removal."""
    
    def test_clean_html_tags(self):
        """Test removal of HTML tags."""
        dirty = "This is <b>bold</b> and <i>italic</i> text."
        clean = _clean_extract(dirty)
        self.assertNotIn("<b>", clean)
        self.assertNotIn("</b>", clean)
        self.assertIn("bold", clean)
    
    def test_clean_html_entities(self):
        """Test removal of HTML entities."""
        dirty = "Price is &pound;100 or &#8364;120"
        clean = _clean_extract(dirty)
        self.assertNotIn("&pound;", clean)
        self.assertNotIn("&#8364;", clean)
    
    def test_clean_whitespace_normalization(self):
        """Test whitespace normalization."""
        dirty = "Too    many     spaces"
        clean = _clean_extract(dirty)
        self.assertEqual(clean, "Too many spaces")
    
    def test_clean_empty_input(self):
        """Test handling of empty input."""
        self.assertEqual(_clean_extract(""), "")
        self.assertEqual(_clean_extract(None), "")


class TestTokenUtils(unittest.TestCase):
    """Test token approximation utilities."""
    
    def test_approx_tokens_basic(self):
        """Test basic token approximation (1 token ≈ 4 chars)."""
        text = "a" * 400  # 400 chars
        tokens = _approx_tokens(text)
        self.assertEqual(tokens, 100)  # 400/4 = 100
    
    def test_approx_tokens_empty(self):
        """Test token approximation with empty string."""
        self.assertEqual(_approx_tokens(""), 0)
        self.assertEqual(_approx_tokens(None), 0)
    
    def test_extract_keywords(self):
        """Test keyword extraction from query."""
        query = "What is the price of Bitcoin today?"
        keywords = _extract_keywords(query)
        
        # Should extract meaningful words, not stopwords
        self.assertIn("price", keywords)
        self.assertIn("bitcoin", [k.lower() for k in keywords])
        self.assertNotIn("is", keywords)
        self.assertNotIn("the", keywords)
    
    def test_score_relevance(self):
        """Test relevance scoring."""
        text = "Bitcoin price is currently $45000"
        keywords = ["bitcoin", "price"]
        
        score = _score_extract_relevance(text, keywords)
        self.assertGreater(score, 0)
        self.assertLessEqual(score, 1.0)
    
    def test_score_relevance_no_match(self):
        """Test relevance scoring with no matches."""
        text = "Ethereum network statistics"
        keywords = ["bitcoin", "price"]
        
        score = _score_extract_relevance(text, keywords)
        self.assertEqual(score, 0.0)


class TestBackwardCompatibility(unittest.TestCase):
    """Test backward compatibility of modified functions."""
    
    def test_smart_trim_with_minimal_params(self):
        """Test smart_trim_extracts works with minimal parameters."""
        extracts = [{"url": "test", "title": "Test", "text": "Test text"}]
        result = smart_trim_extracts(extracts, "test query")
        self.assertIsNotNone(result)
        self.assertIsInstance(result, list)


if __name__ == "__main__":
    # Run tests with verbose output
    unittest.main(verbosity=2)
