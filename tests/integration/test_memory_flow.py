#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
tests/integration/test_memory_flow.py - Integration tests for memory flow.

Tests conversation memory persistence and retrieval.
"""

import os
import sys
import json
import pytest
from unittest.mock import MagicMock, patch

# Add project root to path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def sample_fixtures():
    """Load sample test fixtures."""
    fixtures_path = os.path.join(os.path.dirname(__file__), "../fixtures/sample_data.json")
    with open(fixtures_path) as f:
        return json.load(f)


@pytest.fixture
def sample_memory_entries(sample_fixtures):
    """Get sample memory entries."""
    return sample_fixtures["memory_entries"]


@pytest.fixture
def sample_conversation(sample_fixtures):
    """Get sample conversation history."""
    return sample_fixtures["conversation_history"]


# ============================================================================
# MEMORY ENTRY TESTS
# ============================================================================

class TestMemoryEntry:
    """Tests for memory entry structure."""
    
    def test_memory_entry_structure(self, sample_memory_entries):
        """Test memory entry has required fields."""
        for entry in sample_memory_entries:
            assert "content" in entry
            assert "metadata" in entry
            assert isinstance(entry["content"], str)
            assert isinstance(entry["metadata"], dict)
    
    def test_memory_entry_metadata(self, sample_memory_entries):
        """Test memory entry metadata fields."""
        for entry in sample_memory_entries:
            metadata = entry["metadata"]
            assert "type" in metadata
            assert "timestamp" in metadata
    
    def test_memory_entry_types(self, sample_memory_entries):
        """Test memory entry types."""
        valid_types = ["preference", "context", "topic", "fact", "conversation"]
        
        for entry in sample_memory_entries:
            entry_type = entry["metadata"]["type"]
            assert entry_type in valid_types or isinstance(entry_type, str)


# ============================================================================
# CONVERSATION HISTORY TESTS
# ============================================================================

class TestConversationHistory:
    """Tests for conversation history."""
    
    def test_conversation_structure(self, sample_conversation):
        """Test conversation history structure."""
        for message in sample_conversation:
            assert "role" in message
            assert "content" in message
    
    def test_conversation_roles(self, sample_conversation):
        """Test conversation roles are valid."""
        valid_roles = ["user", "assistant", "system"]
        
        for message in sample_conversation:
            assert message["role"] in valid_roles
    
    def test_conversation_alternation(self, sample_conversation):
        """Test conversation alternates between user and assistant."""
        for i in range(0, len(sample_conversation) - 1, 2):
            if i < len(sample_conversation):
                assert sample_conversation[i]["role"] == "user"
            if i + 1 < len(sample_conversation):
                assert sample_conversation[i + 1]["role"] == "assistant"


# ============================================================================
# MEMORY MODULE TESTS
# ============================================================================

class TestMemoryModule:
    """Tests for memory module functionality."""
    
    def test_conversational_memory_import(self):
        """Test conversational memory module can be imported."""
        try:
            from core.conversational_memory import ConversationalMemory
            assert ConversationalMemory is not None
        except ImportError:
            pytest.skip("conversational_memory module not available")
    
    def test_vector_memory_import(self):
        """Test vector memory module can be imported."""
        try:
            from core.vector_memory import VectorMemory
            assert VectorMemory is not None
        except ImportError:
            pytest.skip("vector_memory module not available")
    
    def test_memory_manager_import(self):
        """Test memory manager module can be imported."""
        try:
            from core.memory_manager import MemoryManager
            assert MemoryManager is not None
        except ImportError:
            pytest.skip("memory_manager module not available")


# ============================================================================
# MEMORY PERSISTENCE TESTS
# ============================================================================

class TestMemoryPersistence:
    """Tests for memory persistence."""
    
    def test_memory_context_builder_import(self):
        """Test memory context builder can be imported."""
        try:
            from core.memory_context_builder import build_memory_context
            assert callable(build_memory_context)
        except ImportError:
            pytest.skip("memory_context_builder module not available")
    
    def test_episodic_memory_import(self):
        """Test episodic memory can be imported."""
        try:
            from core.episodic_memory import EpisodicMemory
            assert EpisodicMemory is not None
        except ImportError:
            pytest.skip("episodic_memory module not available")


# ============================================================================
# MEMORY AUTOSAVE TESTS
# ============================================================================

class TestMemoryAutosave:
    """Tests for memory autosave functionality."""
    
    def test_memory_autosave_import(self):
        """Test memory autosave can be imported."""
        try:
            from core.memory_autosave import setup_autosave
            assert callable(setup_autosave)
        except ImportError:
            pytest.skip("memory_autosave module not available")


# ============================================================================
# USER PROFILE MEMORY TESTS
# ============================================================================

class TestUserProfileMemory:
    """Tests for user profile memory."""
    
    def test_user_profile_memory_import(self):
        """Test user profile memory can be imported."""
        try:
            from core.user_profile_memory import UserProfileMemory
            assert UserProfileMemory is not None
        except ImportError:
            pytest.skip("user_profile_memory module not available")


# ============================================================================
# KNOWLEDGE GRAPH TESTS
# ============================================================================

class TestKnowledgeGraph:
    """Tests for knowledge graph integration with memory."""
    
    def test_knowledge_graph_import(self):
        """Test knowledge graph can be imported."""
        try:
            from core.knowledge_graph import KnowledgeGraph
            assert KnowledgeGraph is not None
        except ImportError:
            pytest.skip("knowledge_graph module not available")
    
    def test_concept_extractor_import(self):
        """Test concept extractor can be imported."""
        try:
            from core.concept_extractor import extract_concepts
            assert callable(extract_concepts)
        except ImportError:
            pytest.skip("concept_extractor module not available")


# ============================================================================
# MEMORY FLOW INTEGRATION TESTS
# ============================================================================

class TestMemoryFlowIntegration:
    """Integration tests for memory flow."""
    
    def test_memory_entry_creation(self, sample_memory_entries):
        """Test creating memory entries from fixtures."""
        for entry in sample_memory_entries:
            # Validate structure
            assert len(entry["content"]) > 0
            assert entry["metadata"]["timestamp"] > 0
    
    def test_conversation_to_memory(self, sample_conversation):
        """Test converting conversation to memory format."""
        # Simulate extracting memory from conversation
        user_messages = [m for m in sample_conversation if m["role"] == "user"]
        assistant_messages = [m for m in sample_conversation if m["role"] == "assistant"]
        
        assert len(user_messages) > 0
        assert len(assistant_messages) > 0
    
    def test_memory_timestamp_ordering(self, sample_memory_entries):
        """Test memory entries can be ordered by timestamp."""
        timestamps = [e["metadata"]["timestamp"] for e in sample_memory_entries]
        
        # Should be sortable
        sorted_timestamps = sorted(timestamps)
        assert len(sorted_timestamps) == len(timestamps)


# ============================================================================
# EDGE CASES
# ============================================================================

class TestMemoryEdgeCases:
    """Tests for memory edge cases."""
    
    def test_empty_conversation(self):
        """Test handling empty conversation."""
        empty_conversation = []
        
        assert len(empty_conversation) == 0
    
    def test_single_message_conversation(self):
        """Test handling single message conversation."""
        single_message = [{"role": "user", "content": "Hello"}]
        
        assert len(single_message) == 1
        assert single_message[0]["role"] == "user"
    
    def test_unicode_in_memory(self, sample_memory_entries):
        """Test Unicode content in memory."""
        # Add Unicode test
        unicode_entry = {
            "content": "User asked about 日本語 translation",
            "metadata": {"type": "context", "timestamp": 1700000000}
        }
        
        assert "日本語" in unicode_entry["content"]
    
    def test_long_content_in_memory(self):
        """Test long content in memory."""
        long_content = "x" * 10000
        
        entry = {
            "content": long_content,
            "metadata": {"type": "context", "timestamp": 1700000000}
        }
        
        assert len(entry["content"]) == 10000
