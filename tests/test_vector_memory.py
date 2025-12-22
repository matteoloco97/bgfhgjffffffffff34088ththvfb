#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_vector_memory.py — Test Vector Memory System

Tests for ChromaDB integration and semantic search functionality.
"""

import sys
import os
import unittest
import asyncio
from typing import List, Dict, Any

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.vector_memory import (
    add_document,
    query_documents,
    delete_session_documents,
    get_collection_stats,
)


class TestVectorMemory(unittest.TestCase):
    """Test cases for vector memory functionality."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        cls.test_session_id = "test_session_123"
        
    def test_add_document(self):
        """Test adding a document to vector memory."""
        result = add_document(
            self.test_session_id,
            "This is a test document about quantum computing.",
            {"topic": "quantum", "source": "test"}
        )
        self.assertTrue(result, "Failed to add document")
    
    def test_add_multiple_documents(self):
        """Test adding multiple documents."""
        documents = [
            ("Python is a programming language.", {"topic": "programming"}),
            ("Machine learning is a subset of AI.", {"topic": "ai"}),
            ("Quantum computers use qubits.", {"topic": "quantum"}),
        ]
        
        for text, metadata in documents:
            result = add_document(self.test_session_id, text, metadata)
            self.assertTrue(result, f"Failed to add document: {text}")
    
    def test_query_documents(self):
        """Test querying documents with semantic search."""
        # Add some documents first
        add_document(
            self.test_session_id,
            "Artificial intelligence and machine learning are transforming technology.",
            {"topic": "ai"}
        )
        add_document(
            self.test_session_id,
            "Python is widely used for data science and AI applications.",
            {"topic": "programming"}
        )
        
        # Query
        results = query_documents(
            self.test_session_id,
            "What is AI?",
            top_k=2
        )
        
        self.assertIsInstance(results, list, "Results should be a list")
        if results:
            self.assertIn("text", results[0], "Result should contain 'text' field")
            self.assertIn("metadata", results[0], "Result should contain 'metadata' field")
    
    def test_query_empty_session(self):
        """Test querying a session with no documents."""
        results = query_documents("nonexistent_session", "test query", top_k=5)
        self.assertEqual(results, [], "Empty session should return empty list")
    
    def test_delete_session_documents(self):
        """Test deleting all documents for a session."""
        # Add a document
        add_document(
            "delete_test_session",
            "This document will be deleted.",
            {"test": True}
        )
        
        # Delete
        result = delete_session_documents("delete_test_session")
        self.assertTrue(result, "Failed to delete session documents")
    
    def test_collection_stats(self):
        """Test getting collection statistics."""
        stats = get_collection_stats()
        self.assertIsInstance(stats, dict, "Stats should be a dictionary")
        self.assertIn("collection_name", stats, "Stats should contain collection_name")
    
    def test_add_empty_document(self):
        """Test adding empty document (should fail gracefully)."""
        result = add_document(self.test_session_id, "", {})
        self.assertFalse(result, "Empty document should not be added")
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test data."""
        try:
            delete_session_documents(cls.test_session_id)
        except:
            pass


if __name__ == "__main__":
    # Run tests
    unittest.main()
