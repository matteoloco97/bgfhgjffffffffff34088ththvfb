#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_smart_synthesis.py — Tests for Smart Synthesis Module

Tests intelligent content synthesis and summarization.
"""

import sys
import os
import unittest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.smart_synthesis import (
    SmartSynthesizer,
    get_smart_synthesizer,
    synthesize_content,
)


class TestSmartSynthesizer(unittest.TestCase):
    """Test cases for smart synthesizer."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.synthesizer = SmartSynthesizer()
    
    def test_extract_keywords(self):
        """Test keyword extraction."""
        text = "Bitcoin is a cryptocurrency. Bitcoin price is rising. Crypto market is bullish."
        keywords = self.synthesizer._extract_keywords(text, top_n=5)
        
        self.assertIsInstance(keywords, list)
        self.assertGreater(len(keywords), 0)
        # "bitcoin" and "crypto" should be in top keywords
        keywords_lower = [k.lower() for k in keywords]
        self.assertIn("bitcoin", keywords_lower)
    
    def test_split_sentences(self):
        """Test sentence splitting."""
        text = "This is sentence one. This is sentence two! Is this sentence three?"
        sentences = self.synthesizer._split_sentences(text)
        
        self.assertEqual(len(sentences), 3)
        self.assertIn("This is sentence one.", sentences)
        self.assertIn("This is sentence two!", sentences)
    
    def test_score_sentence(self):
        """Test sentence scoring."""
        sentence = "Bitcoin price reached $50,000 today."
        keywords = ["bitcoin", "price"]
        
        score = self.synthesizer._score_sentence(sentence, keywords, 0, 5)
        
        self.assertGreater(score, 0.0)
        self.assertLessEqual(score, 1.0)
    
    def test_extract_key_sentences_simple(self):
        """Test extracting key sentences from simple text."""
        text = """
        Bitcoin is a digital currency. It was created in 2009.
        The price of Bitcoin has increased significantly.
        Many people invest in Bitcoin today.
        Cryptocurrency market is growing rapidly.
        """
        
        key_sentences = self.synthesizer.extract_key_sentences(text, query="bitcoin price", top_n=3)
        
        self.assertIsInstance(key_sentences, list)
        self.assertGreater(len(key_sentences), 0)
        self.assertLessEqual(len(key_sentences), 3)
    
    def test_extract_key_sentences_with_query(self):
        """Test that query keywords boost sentence relevance."""
        text = """
        The weather today is sunny. Temperature is 25 degrees.
        Bitcoin reached a new high. Stock market is stable.
        It might rain tomorrow. Weather forecast shows clouds.
        """
        
        # Query about weather should prioritize weather sentences
        weather_sentences = self.synthesizer.extract_key_sentences(
            text, 
            query="weather today",
            top_n=2
        )
        
        self.assertGreater(len(weather_sentences), 0)
        # At least one sentence should be about weather
        has_weather = any("weather" in s.lower() or "temperature" in s.lower() 
                          for s in weather_sentences)
        self.assertTrue(has_weather, f"Expected weather in: {weather_sentences}")
    
    def test_deduplicate_sentences(self):
        """Test sentence deduplication."""
        sentences = [
            ("Bitcoin price is rising.", 0.9),
            ("Bitcoin price is increasing.", 0.8),  # Similar
            ("The weather is sunny.", 0.7),
            ("Bitcoin value is going up.", 0.6),  # Similar
        ]
        
        unique = self.synthesizer._deduplicate_sentences(sentences, similarity_threshold=0.5)
        
        # Should remove similar sentences
        self.assertLess(len(unique), len(sentences))
    
    def test_synthesize_multi_source_basic(self):
        """Test multi-source synthesis."""
        sources = [
            {
                "url": "https://example.com/1",
                "title": "Bitcoin News",
                "text": "Bitcoin price reached $50,000. The cryptocurrency market is bullish. Investors are optimistic."
            },
            {
                "url": "https://example.com/2", 
                "title": "Crypto Update",
                "text": "Ethereum also gained value. The crypto market shows strong momentum. Trading volume increased."
            }
        ]
        
        result = self.synthesizer.synthesize_multi_source(
            sources,
            query="crypto market",
            max_key_points=4
        )
        
        self.assertIsNotNone(result.summary)
        self.assertGreater(len(result.key_points), 0)
        self.assertLessEqual(len(result.key_points), 4)
        self.assertGreater(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)
        self.assertGreater(len(result.sources), 0)
    
    def test_synthesize_empty_sources(self):
        """Test synthesis with no sources."""
        result = self.synthesizer.synthesize_multi_source([], query="test")
        
        self.assertIsNotNone(result.summary)
        self.assertEqual(len(result.key_points), 0)
        self.assertEqual(result.confidence, 0.0)
    
    def test_synthesize_sources_no_text(self):
        """Test synthesis with sources lacking text."""
        sources = [
            {"url": "https://example.com/1", "title": "Test", "text": ""},
            {"url": "https://example.com/2", "title": "Test 2"},  # No text key
        ]
        
        result = self.synthesizer.synthesize_multi_source(sources, query="test")
        
        # Should handle gracefully
        self.assertIsNotNone(result)
    
    def test_singleton_instance(self):
        """Test singleton pattern for synthesizer."""
        synth1 = get_smart_synthesizer()
        synth2 = get_smart_synthesizer()
        
        self.assertIs(synth1, synth2)
    
    def test_utility_function(self):
        """Test utility synthesize_content function."""
        sources = [
            {
                "url": "https://example.com/1",
                "title": "Test Article",
                "text": "This is a test article. It contains useful information. The data is accurate."
            }
        ]
        
        result = synthesize_content(sources, query="test", max_key_points=3)
        
        self.assertIsInstance(result, dict)
        self.assertIn("summary", result)
        self.assertIn("key_points", result)
        self.assertIn("sources", result)
        self.assertIn("confidence", result)


class TestSynthesisQuality(unittest.TestCase):
    """Test synthesis quality and edge cases."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.synthesizer = SmartSynthesizer()
    
    def test_long_text_extraction(self):
        """Test extraction from long text."""
        # Create long text with repeated content
        text = " ".join([
            f"This is sentence {i} about Bitcoin and cryptocurrency market."
            for i in range(50)
        ])
        
        key_sentences = self.synthesizer.extract_key_sentences(
            text,
            query="bitcoin",
            top_n=5
        )
        
        self.assertLessEqual(len(key_sentences), 5)
        # Should deduplicate similar sentences
        self.assertLess(len(key_sentences), 50)
    
    def test_numbers_in_sentences(self):
        """Test that sentences with numbers get bonus scoring."""
        text = """
        Bitcoin is a cryptocurrency.
        The price reached $50,000 in 2024.
        Many people use it.
        Trading volume was 100 million.
        """
        
        key_sentences = self.synthesizer.extract_key_sentences(text, top_n=2)
        
        # Sentences with numbers should be preferred
        has_numbers = any(any(c.isdigit() for c in s) for s in key_sentences)
        self.assertTrue(has_numbers, f"Expected numbers in: {key_sentences}")
    
    def test_sentence_length_preference(self):
        """Test preference for medium-length sentences."""
        text = """
        Hi.
        Bitcoin is a cryptocurrency that enables peer-to-peer transactions.
        This is a very very very very very very very very very very very very very very very long sentence that goes on and on without much useful content but just keeps adding more and more words.
        The market is bullish today.
        """
        
        key_sentences = self.synthesizer.extract_key_sentences(text, top_n=2)
        
        # Should prefer medium-length sentences
        avg_length = sum(len(s.split()) for s in key_sentences) / len(key_sentences)
        self.assertGreater(avg_length, 3)  # Not too short
        self.assertLess(avg_length, 35)  # Not too long


if __name__ == "__main__":
    unittest.main()
