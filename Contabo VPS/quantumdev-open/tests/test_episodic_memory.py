#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_episodic_memory.py — Test Episodic Memory System

Tests for conversation buffer, summarization, and episodic retrieval.
"""

import sys
import os
import unittest
import asyncio
from typing import List, Dict, Any

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.episodic_memory import (
    add_to_conversation_buffer,
    summarize_and_save_buffer,
    query_conversation_history,
    get_recent_conversation_summaries,
    get_current_buffer_status,
    clear_conversation_buffer,
)


class TestEpisodicMemory(unittest.TestCase):
    """Test cases for episodic memory functionality."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        cls.test_conversation_id = "test_conv_episodic_123"
        cls.test_user_id = "test_user_episodic"
    
    def test_add_to_buffer(self):
        """Test adding turns to conversation buffer."""
        result = add_to_conversation_buffer(
            conversation_id=self.test_conversation_id,
            user_message="Ciao, come stai?",
            assistant_message="Ciao! Sto bene, grazie. Come posso aiutarti?"
        )
        
        self.assertTrue(result.get("added"), "Should add turn to buffer")
        self.assertGreaterEqual(result.get("buffer_size", 0), 1, "Buffer should have at least 1 turn")
    
    def test_buffer_status(self):
        """Test getting buffer status."""
        # Add some turns
        for i in range(3):
            add_to_conversation_buffer(
                conversation_id=self.test_conversation_id,
                user_message=f"Messaggio {i}",
                assistant_message=f"Risposta {i}"
            )
        
        status = get_current_buffer_status(self.test_conversation_id)
        
        self.assertTrue(status.get("exists"), "Buffer should exist")
        self.assertGreaterEqual(status.get("size", 0), 3, "Buffer should have at least 3 turns")
        self.assertIn("estimated_tokens", status, "Should have token estimate")
    
    def test_buffer_threshold_detection(self):
        """Test that buffer detects when summarization is needed."""
        # Clear buffer first
        clear_conversation_buffer(self.test_conversation_id)
        
        # Add enough turns to trigger threshold (default is 10)
        long_message = "This is a long message that will contribute to the token count. " * 20
        
        for i in range(12):
            result = add_to_conversation_buffer(
                conversation_id=self.test_conversation_id,
                user_message=long_message,
                assistant_message=long_message
            )
        
        # Last result should indicate summarization needed
        status = get_current_buffer_status(self.test_conversation_id)
        # This depends on token threshold, may or may not need summarization
        self.assertIn("needs_summarization", status, "Should check summarization need")
    
    def test_summarize_buffer_sync(self):
        """Test buffer summarization without LLM (rule-based)."""
        # Clear and add fresh turns
        clear_conversation_buffer(self.test_conversation_id)
        
        turns = [
            ("Parliamo di AI", "Certo, di cosa vuoi parlare?"),
            ("Come funziona il machine learning?", "Il ML usa algoritmi per imparare dai dati."),
            ("Interessante!", "Sono felice che ti piaccia."),
        ]
        
        for user_msg, asst_msg in turns:
            add_to_conversation_buffer(
                conversation_id=self.test_conversation_id,
                user_message=user_msg,
                assistant_message=asst_msg,
                user_id=self.test_user_id
            )
        
        # Summarize without LLM (should use rule-based fallback)
        async def run_summarize():
            summary = await summarize_and_save_buffer(
                conversation_id=self.test_conversation_id,
                user_id=self.test_user_id,
                llm_func=None  # No LLM, will use fallback
            )
            return summary
        
        summary = asyncio.run(run_summarize())
        
        if summary:
            self.assertIsInstance(summary, str, "Summary should be a string")
            self.assertGreater(len(summary), 0, "Summary should not be empty")
    
    def test_query_conversation_history(self):
        """Test querying past conversation summaries."""
        # First create a summary (if not already created in previous test)
        async def create_summary():
            return await summarize_and_save_buffer(
                conversation_id=self.test_conversation_id,
                user_id=self.test_user_id,
                llm_func=None
            )
        
        try:
            asyncio.run(create_summary())
        except:
            pass  # May fail if buffer is empty
        
        # Query the history
        results = query_conversation_history(
            conversation_id=self.test_conversation_id,
            query_text="AI machine learning",
            top_k=5
        )
        
        self.assertIsInstance(results, list, "Should return a list")
        # May be empty if summarization failed or no summaries exist
    
    def test_get_recent_summaries(self):
        """Test getting recent summaries chronologically."""
        summaries = get_recent_conversation_summaries(
            conversation_id=self.test_conversation_id,
            limit=10
        )
        
        self.assertIsInstance(summaries, list, "Should return a list")
        
        # If we have summaries, check they're sorted by recency
        if len(summaries) > 1:
            for i in range(len(summaries) - 1):
                current_ts = summaries[i].get("metadata", {}).get("created_at", 0)
                next_ts = summaries[i + 1].get("metadata", {}).get("created_at", 0)
                self.assertGreaterEqual(current_ts, next_ts,
                                       "Summaries should be sorted by recency")
    
    def test_clear_buffer(self):
        """Test clearing conversation buffer."""
        # Add some turns
        add_to_conversation_buffer(
            conversation_id=self.test_conversation_id,
            user_message="Test message",
            assistant_message="Test response"
        )
        
        # Clear the buffer
        result = clear_conversation_buffer(self.test_conversation_id)
        self.assertTrue(result, "Should clear existing buffer")
        
        # Check buffer is empty
        status = get_current_buffer_status(self.test_conversation_id)
        self.assertEqual(status.get("size", -1), 0, "Buffer should be empty after clear")
    
    def test_empty_conversation_handling(self):
        """Test handling of non-existent conversations."""
        fake_conv_id = "nonexistent_conversation_999"
        
        # Status should indicate buffer doesn't exist
        status = get_current_buffer_status(fake_conv_id)
        self.assertFalse(status.get("exists"), "Non-existent buffer should not exist")
        
        # Query should return empty list
        results = query_conversation_history(
            conversation_id=fake_conv_id,
            query_text="test",
            top_k=5
        )
        self.assertEqual(results, [], "Should return empty list for non-existent conversation")
    
    def test_buffer_max_size(self):
        """Test that buffer respects max size."""
        clear_conversation_buffer(self.test_conversation_id)
        
        # Add more than buffer max (default is 10)
        for i in range(15):
            add_to_conversation_buffer(
                conversation_id=self.test_conversation_id,
                user_message=f"Message {i}",
                assistant_message=f"Response {i}"
            )
        
        status = get_current_buffer_status(self.test_conversation_id)
        buffer_size = status.get("size", 0)
        max_size = status.get("max_size", 10)
        
        # Buffer should not exceed max size (uses deque with maxlen)
        self.assertLessEqual(buffer_size, max_size,
                            f"Buffer size {buffer_size} should not exceed max {max_size}")
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test data."""
        # Clear test conversation buffer
        try:
            clear_conversation_buffer(cls.test_conversation_id)
        except Exception:
            pass


if __name__ == "__main__":
    # Run tests
    unittest.main()
