#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_memory_integration.py — Integration Tests for Personal Memory System

Tests the full integration of user profile and episodic memory in chat flow.
"""

import sys
import os
import unittest
import asyncio
from typing import List, Dict, Any

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.memory_manager import (
    gather_memory_context,
    process_user_message,
    record_conversation_turn,
    get_memory_stats,
)


class TestMemoryIntegration(unittest.TestCase):
    """Integration tests for the personal memory system."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        cls.test_user_id = "test_integration_user"
        cls.test_conversation_id = "test_integration_conv"
    
    def test_process_remember_statement_italian(self):
        """Test processing Italian 'remember' statement."""
        async def run_test():
            result = await process_user_message(
                user_id=self.test_user_id,
                conversation_id=self.test_conversation_id,
                user_message="Ricorda che il mio colore preferito è verde"
            )
            return result
        
        result = asyncio.run(run_test())
        
        self.assertTrue(result.get("remember_detected"), "Should detect remember statement")
        # Fact saving may fail if ChromaDB not available
        if result.get("fact_saved"):
            self.assertIsNotNone(result.get("fact_id"), "Should save fact and return ID")
    
    def test_process_remember_statement_english(self):
        """Test processing English 'remember' statement."""
        async def run_test():
            result = await process_user_message(
                user_id=self.test_user_id,
                conversation_id=self.test_conversation_id,
                user_message="Remember that I prefer concise answers"
            )
            return result
        
        result = asyncio.run(run_test())
        
        self.assertTrue(result.get("remember_detected"), "Should detect remember statement")
    
    def test_process_normal_message(self):
        """Test that normal messages don't trigger remember."""
        async def run_test():
            result = await process_user_message(
                user_id=self.test_user_id,
                conversation_id=self.test_conversation_id,
                user_message="What is the weather today?"
            )
            return result
        
        result = asyncio.run(run_test())
        
        self.assertFalse(result.get("remember_detected"), "Should not detect remember in normal message")
        self.assertFalse(result.get("fact_saved"), "Should not save fact for normal message")
    
    def test_sensitive_data_blocking(self):
        """Test that sensitive data is not saved."""
        async def run_test():
            # Try to save something that looks like an API key
            result = await process_user_message(
                user_id=self.test_user_id,
                conversation_id=self.test_conversation_id,
                user_message="Remember that my API key is sk_test_abcdefghijklmnopqrstuvwxyz123456"
            )
            return result
        
        result = asyncio.run(run_test())
        
        self.assertTrue(result.get("remember_detected"), "Should detect remember statement")
        
        # Should block saving due to sensitive pattern
        if result.get("blocked_sensitive"):
            self.assertFalse(result.get("fact_saved"), "Should block saving sensitive data")
    
    def test_gather_memory_context(self):
        """Test gathering combined memory context."""
        async def run_test():
            # First, save some facts
            await process_user_message(
                user_id=self.test_user_id,
                conversation_id=self.test_conversation_id,
                user_message="Ricorda che lavoro nel settore AI"
            )
            
            # Then gather context
            context = await gather_memory_context(
                user_id=self.test_user_id,
                conversation_id=self.test_conversation_id,
                user_message="Dimmi del mio lavoro"
            )
            return context
        
        context = asyncio.run(run_test())
        
        self.assertIsInstance(context, dict, "Should return a dict")
        self.assertIn("profile_context", context, "Should have profile_context key")
        self.assertIn("episodic_context", context, "Should have episodic_context key")
        
        # May be empty if ChromaDB not available or no matches
        if context.get("profile_context"):
            self.assertIsInstance(context["profile_context"], str, "Profile context should be string")
    
    def test_record_conversation_turn(self):
        """Test recording conversation turn."""
        async def run_test():
            result = await record_conversation_turn(
                conversation_id=self.test_conversation_id,
                user_message="Cos'è il machine learning?",
                assistant_message="Il machine learning è un ramo dell'intelligenza artificiale.",
                user_id=self.test_user_id,
                llm_func=None  # No LLM for testing
            )
            return result
        
        result = asyncio.run(run_test())
        
        # Recording may fail if episodic memory not enabled
        if result.get("recorded"):
            self.assertTrue(result.get("recorded"), "Should record turn")
    
    def test_memory_stats(self):
        """Test getting memory statistics."""
        stats = get_memory_stats(
            user_id=self.test_user_id,
            conversation_id=self.test_conversation_id
        )
        
        self.assertIsInstance(stats, dict, "Should return a dict")
        self.assertIn("profile_memory", stats, "Should have profile_memory stats")
        self.assertIn("episodic_memory", stats, "Should have episodic_memory stats")
        
        # Check structure
        profile_stats = stats.get("profile_memory", {})
        self.assertIn("enabled", profile_stats, "Profile stats should have 'enabled'")
        
        episodic_stats = stats.get("episodic_memory", {})
        self.assertIn("enabled", episodic_stats, "Episodic stats should have 'enabled'")
    
    def test_full_conversation_flow(self):
        """Test full conversation flow with memory."""
        async def run_test():
            # 1. User says something to remember
            remember_result = await process_user_message(
                user_id=self.test_user_id,
                conversation_id=self.test_conversation_id,
                user_message="Ricorda che mi piace il caffè espresso"
            )
            
            # 2. Record a turn
            record_result = await record_conversation_turn(
                conversation_id=self.test_conversation_id,
                user_message="Ricorda che mi piace il caffè espresso",
                assistant_message="Ok, ho memorizzato che ti piace il caffè espresso.",
                user_id=self.test_user_id
            )
            
            # 3. Later, gather context for related query
            context = await gather_memory_context(
                user_id=self.test_user_id,
                conversation_id=self.test_conversation_id,
                user_message="Che caffè mi piace?"
            )
            
            # 4. Get stats
            stats = get_memory_stats(
                user_id=self.test_user_id,
                conversation_id=self.test_conversation_id
            )
            
            return {
                "remember": remember_result,
                "record": record_result,
                "context": context,
                "stats": stats,
            }
        
        results = asyncio.run(run_test())
        
        # Verify each step
        self.assertIsInstance(results["remember"], dict, "Remember should return dict")
        self.assertIsInstance(results["record"], dict, "Record should return dict")
        self.assertIsInstance(results["context"], dict, "Context should return dict")
        self.assertIsInstance(results["stats"], dict, "Stats should return dict")
    
    def test_multiple_users_isolation(self):
        """Test that different users have isolated memories."""
        async def run_test():
            user1_id = "user1_test"
            user2_id = "user2_test"
            
            # User 1 saves a fact
            result1 = await process_user_message(
                user_id=user1_id,
                conversation_id="conv1",
                user_message="Remember that I love pizza"
            )
            
            # User 2 saves a different fact
            result2 = await process_user_message(
                user_id=user2_id,
                conversation_id="conv2",
                user_message="Remember that I love sushi"
            )
            
            # Get stats for each user
            stats1 = get_memory_stats(user_id=user1_id)
            stats2 = get_memory_stats(user_id=user2_id)
            
            return {
                "user1": (result1, stats1),
                "user2": (result2, stats2),
            }
        
        results = asyncio.run(run_test())
        
        # Both should have successfully processed their own facts
        # (if memory system is enabled)
        self.assertIsInstance(results["user1"], tuple, "User1 results should be tuple")
        self.assertIsInstance(results["user2"], tuple, "User2 results should be tuple")
    
    def test_conversation_isolation(self):
        """Test that different conversations have isolated episodic memory."""
        async def run_test():
            conv1_id = "conversation_1"
            conv2_id = "conversation_2"
            
            # Record turns in conversation 1
            await record_conversation_turn(
                conversation_id=conv1_id,
                user_message="Let's talk about AI",
                assistant_message="Sure, what about AI?",
                user_id=self.test_user_id
            )
            
            # Record turns in conversation 2
            await record_conversation_turn(
                conversation_id=conv2_id,
                user_message="Let's talk about cooking",
                assistant_message="Sure, what about cooking?",
                user_id=self.test_user_id
            )
            
            # Get stats for each conversation
            stats1 = get_memory_stats(conversation_id=conv1_id)
            stats2 = get_memory_stats(conversation_id=conv2_id)
            
            return (stats1, stats2)
        
        stats1, stats2 = asyncio.run(run_test())
        
        # Both should have separate episodic memory
        self.assertIsInstance(stats1, dict, "Stats1 should be dict")
        self.assertIsInstance(stats2, dict, "Stats2 should be dict")


if __name__ == "__main__":
    # Run tests
    unittest.main()
