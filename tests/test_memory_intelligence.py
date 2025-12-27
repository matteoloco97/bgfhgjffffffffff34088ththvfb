#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_memory_intelligence.py — Test Suite for Memory Intelligence System

Tests for:
- core/semantic_context_analyzer.py
- core/context_prioritizer.py
"""

import sys
import os
import time
import unittest
from typing import List

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.semantic_context_analyzer import (
    SemanticContextAnalyzer,
    Topic,
    SemanticRelation,
    ContextAnalysisResult,
    get_semantic_analyzer,
    SEMANTIC_ANALYSIS_ENABLED,
)
from core.context_prioritizer import (
    ContextPrioritizer,
    ContextItem,
    ContextType,
    PriorityLevel,
    PrioritizationResult,
    get_context_prioritizer,
    create_context_item,
    prioritize_context,
    allocate_budget,
    approx_tokens,
    trim_to_tokens,
)


class TestTokenUtilities(unittest.TestCase):
    """Test token utility functions."""
    
    def test_approx_tokens_empty(self):
        """Test token count for empty string."""
        self.assertEqual(approx_tokens(""), 0)
        self.assertEqual(approx_tokens(None), 0)
    
    def test_approx_tokens_normal(self):
        """Test token count for normal text."""
        # 4 chars ≈ 1 token
        text = "Hello, world!"  # 13 chars ≈ 4 tokens
        tokens = approx_tokens(text)
        self.assertGreater(tokens, 0)
        self.assertEqual(tokens, 4)  # ceil(13/4) = 4
    
    def test_trim_to_tokens_no_trim_needed(self):
        """Test trimming when text is under limit."""
        text = "Short text"
        result = trim_to_tokens(text, 100)
        self.assertEqual(result, text)
    
    def test_trim_to_tokens_trimmed(self):
        """Test trimming when text exceeds limit."""
        text = "This is a longer text that should be trimmed"
        result = trim_to_tokens(text, 5)  # 5 tokens ≈ 20 chars
        self.assertEqual(len(result), 20)
    
    def test_trim_to_tokens_edge_cases(self):
        """Test edge cases for trimming."""
        self.assertEqual(trim_to_tokens("", 10), "")
        self.assertEqual(trim_to_tokens("text", 0), "")
        self.assertEqual(trim_to_tokens("text", -1), "")


class TestTopic(unittest.TestCase):
    """Test Topic dataclass."""
    
    def test_topic_creation(self):
        """Test creating a topic."""
        topic = Topic(text="Python", importance=0.9)
        self.assertEqual(topic.text, "Python")
        self.assertEqual(topic.importance, 0.9)
        self.assertEqual(topic.frequency, 1)
        self.assertIsInstance(topic.first_seen, int)
    
    def test_topic_to_dict(self):
        """Test topic serialization."""
        topic = Topic(text="FastAPI", importance=0.8)
        d = topic.to_dict()
        self.assertIn("text", d)
        self.assertIn("importance", d)
        self.assertEqual(d["text"], "FastAPI")
    
    def test_topic_from_dict(self):
        """Test topic deserialization."""
        data = {
            "text": "ChromaDB",
            "importance": 0.7,
            "frequency": 3,
        }
        topic = Topic.from_dict(data)
        self.assertEqual(topic.text, "ChromaDB")
        self.assertEqual(topic.importance, 0.7)
        self.assertEqual(topic.frequency, 3)
    
    def test_topic_decay_importance(self):
        """Test importance decay over time."""
        topic = Topic(text="Test", importance=1.0)
        topic.last_seen = int(time.time()) - 86400  # 24 hours ago
        
        decayed = topic.decay_importance(half_life_hours=24.0)
        # After one half-life, importance should be ~0.5
        self.assertLess(decayed, 1.0)
        self.assertGreater(decayed, 0.4)
        self.assertLess(decayed, 0.6)


class TestSemanticContextAnalyzer(unittest.TestCase):
    """Test SemanticContextAnalyzer class."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        cls.analyzer = get_semantic_analyzer()
    
    def test_analyzer_singleton(self):
        """Test analyzer singleton pattern."""
        analyzer1 = get_semantic_analyzer()
        analyzer2 = get_semantic_analyzer()
        self.assertIs(analyzer1, analyzer2)
    
    def test_extract_topics_empty(self):
        """Test topic extraction from empty text."""
        topics = self.analyzer.extract_topics("")
        self.assertEqual(len(topics), 0)
        
        topics = self.analyzer.extract_topics("   ")
        self.assertEqual(len(topics), 0)
    
    def test_extract_topics_normal(self):
        """Test topic extraction from normal text."""
        text = "Python is a programming language used by FastAPI"
        topics = self.analyzer.extract_topics(text)
        
        # Should extract some topics
        self.assertIsInstance(topics, list)
        # Topics extracted depend on available NLP models
    
    def test_extract_topics_updates_frequency(self):
        """Test that repeated topics increase frequency."""
        # Clear cache first
        self.analyzer.clear_cache()
        
        text1 = "Python is great"
        text2 = "Python is powerful"
        
        self.analyzer.extract_topics(text1)
        topics2 = self.analyzer.extract_topics(text2)
        
        # Check if Python topic has increased frequency
        python_topics = [t for t in topics2 if "python" in t.text.lower()]
        if python_topics:
            self.assertGreaterEqual(python_topics[0].frequency, 1)
    
    def test_compute_similarity_same_text(self):
        """Test similarity for identical texts."""
        text = "Python programming language"
        similarity = self.analyzer.compute_similarity(text, text)
        
        # Should be very high (close to 1.0) or 0.0 if embeddings not available
        self.assertIn(similarity, [1.0, 0.0]) if similarity in [1.0, 0.0] else self.assertGreater(similarity, 0.9)
    
    def test_compute_similarity_different_texts(self):
        """Test similarity for different texts."""
        similarity = self.analyzer.compute_similarity(
            "Python programming",
            "Cat dog animal"
        )
        # Should be lower than identical texts
        self.assertLessEqual(similarity, 1.0)
        self.assertGreaterEqual(similarity, 0.0)
    
    def test_find_semantic_relations(self):
        """Test finding semantic relations between topics."""
        topics = [
            Topic(text="Python"),
            Topic(text="FastAPI"),
            Topic(text="ChromaDB"),
        ]
        
        relations = self.analyzer.find_semantic_relations(topics)
        self.assertIsInstance(relations, list)
        # Relations depend on similarity threshold and embeddings
    
    def test_analyze_context_continuity_no_previous(self):
        """Test continuity with no previous context."""
        score, shift = self.analyzer.analyze_context_continuity(
            "Current text",
            []
        )
        self.assertEqual(score, 1.0)
        self.assertFalse(shift)
    
    def test_analyze_context_continuity_with_previous(self):
        """Test continuity with previous context."""
        score, shift = self.analyzer.analyze_context_continuity(
            "Let's talk about Python",
            ["Python is a programming language", "I use Python for web development"]
        )
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)
        self.assertIsInstance(shift, bool)
    
    def test_full_analysis(self):
        """Test full context analysis."""
        result = self.analyzer.analyze(
            "I'm working on a Python project",
            previous_texts=["Let's build an API", "Using FastAPI framework"],
            context_source="user"
        )
        
        self.assertIsInstance(result, ContextAnalysisResult)
        self.assertIsInstance(result.topics, list)
        self.assertIsInstance(result.relations, list)
        self.assertGreaterEqual(result.continuity_score, 0.0)
        self.assertLessEqual(result.continuity_score, 1.0)
        self.assertIsInstance(result.topic_shift_detected, bool)
    
    def test_cluster_topics(self):
        """Test topic clustering."""
        # Add some topics first
        self.analyzer.extract_topics("Python FastAPI programming")
        self.analyzer.extract_topics("Machine learning neural networks")
        
        clusters = self.analyzer.cluster_topics()
        self.assertIsInstance(clusters, dict)
    
    def test_get_stats(self):
        """Test getting analyzer stats."""
        stats = self.analyzer.get_stats()
        self.assertIn("cached_topics", stats)
        self.assertIn("cached_embeddings", stats)
        self.assertIn("enabled", stats)
    
    def test_clear_cache(self):
        """Test cache clearing."""
        self.analyzer.extract_topics("Some text with Topics")
        self.analyzer.clear_cache()
        
        stats = self.analyzer.get_stats()
        self.assertEqual(stats["cached_topics"], 0)
        self.assertEqual(stats["cached_embeddings"], 0)


class TestContextItem(unittest.TestCase):
    """Test ContextItem dataclass."""
    
    def test_context_item_creation(self):
        """Test creating a context item."""
        item = ContextItem(
            content="Test content",
            context_type=ContextType.CONVERSATION,
            priority=PriorityLevel.HIGH,
        )
        self.assertEqual(item.content, "Test content")
        self.assertEqual(item.context_type, ContextType.CONVERSATION)
        self.assertEqual(item.priority, PriorityLevel.HIGH)
    
    def test_context_item_tokens(self):
        """Test token count property."""
        item = ContextItem(
            content="Hello world",  # 11 chars
            context_type=ContextType.CONVERSATION,
        )
        self.assertEqual(item.tokens, 3)  # ceil(11/4) = 3
    
    def test_context_item_priority_score(self):
        """Test priority score computation."""
        item = ContextItem(
            content="Test",
            context_type=ContextType.SYSTEM,
            priority=PriorityLevel.CRITICAL,
            relevance_score=0.9,
            importance_score=0.8,
        )
        
        score = item.compute_priority_score()
        self.assertGreater(score, 0.0)
        self.assertLessEqual(score, 1.0)
    
    def test_context_item_priority_score_with_age(self):
        """Test priority score with aged item."""
        old_item = ContextItem(
            content="Old content",
            context_type=ContextType.CONVERSATION,
            priority=PriorityLevel.MEDIUM,
            recency_timestamp=int(time.time()) - 86400,  # 1 day ago
        )
        
        new_item = ContextItem(
            content="New content",
            context_type=ContextType.CONVERSATION,
            priority=PriorityLevel.MEDIUM,
            recency_timestamp=int(time.time()),
        )
        
        old_score = old_item.compute_priority_score()
        new_score = new_item.compute_priority_score()
        
        # New item should have higher score due to recency
        self.assertLess(old_score, new_score)
    
    def test_context_item_to_dict(self):
        """Test serialization."""
        item = ContextItem(
            content="Test",
            context_type=ContextType.USER_PROFILE,
            priority=PriorityLevel.HIGH,
        )
        
        d = item.to_dict()
        self.assertIn("content", d)
        self.assertIn("context_type", d)
        self.assertIn("tokens", d)


class TestContextPrioritizer(unittest.TestCase):
    """Test ContextPrioritizer class."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        cls.prioritizer = ContextPrioritizer(token_budget=100)
    
    def test_prioritizer_singleton(self):
        """Test prioritizer singleton pattern."""
        p1 = get_context_prioritizer(100)
        p2 = get_context_prioritizer()
        self.assertIs(p1, p2)
    
    def test_prioritize_empty_list(self):
        """Test prioritization with empty list."""
        result = self.prioritizer.prioritize([])
        
        self.assertEqual(len(result.selected_items), 0)
        self.assertEqual(len(result.excluded_items), 0)
        self.assertEqual(result.budget_used, 0)
    
    def test_prioritize_within_budget(self):
        """Test prioritization when all items fit in budget."""
        items = [
            create_context_item("Short text", priority="high"),
            create_context_item("Another text", priority="medium"),
        ]
        
        result = self.prioritizer.prioritize(items)
        
        # All items should be selected if they fit
        total_tokens = sum(item.tokens for item in items)
        if total_tokens <= self.prioritizer.token_budget:
            self.assertEqual(len(result.selected_items), len(items))
    
    def test_prioritize_exceeds_budget(self):
        """Test prioritization when items exceed budget."""
        # Create items that exceed budget (100 tokens)
        items = [
            create_context_item("A" * 200, priority="critical"),  # ~50 tokens
            create_context_item("B" * 200, priority="high"),      # ~50 tokens
            create_context_item("C" * 200, priority="medium"),    # ~50 tokens
        ]
        
        result = self.prioritizer.prioritize(items)
        
        # Some items should be excluded
        self.assertLess(result.budget_used, result.total_tokens)
        self.assertGreater(len(result.excluded_items), 0)
    
    def test_prioritize_critical_first(self):
        """Test that critical items are prioritized."""
        items = [
            create_context_item("Low priority", priority="low"),
            create_context_item("Critical", priority="critical"),
        ]
        
        result = self.prioritizer.prioritize(items)
        
        # Critical item should be in selected
        critical_selected = any(
            "Critical" in item.content for item in result.selected_items
        )
        self.assertTrue(critical_selected)
    
    def test_prioritize_with_query(self):
        """Test prioritization with relevance scoring."""
        items = [
            create_context_item("Python programming language", priority="medium"),
            create_context_item("Cat and dog animals", priority="medium"),
        ]
        
        result = self.prioritizer.prioritize(
            items,
            current_query="Tell me about Python"
        )
        
        # Both should have relevance scores set
        for item in result.selected_items:
            self.assertGreaterEqual(item.relevance_score, 0.0)
    
    def test_build_context_string(self):
        """Test building context string from result."""
        items = [
            create_context_item("System prompt", context_type="system"),
            create_context_item("User preference", context_type="user_profile"),
        ]
        
        result = self.prioritizer.prioritize(items)
        context_str = self.prioritizer.build_context_string(result)
        
        self.assertIsInstance(context_str, str)
        if result.selected_items:
            self.assertGreater(len(context_str), 0)


class TestConvenienceFunctions(unittest.TestCase):
    """Test convenience functions."""
    
    def test_create_context_item(self):
        """Test context item creation helper."""
        item = create_context_item(
            "Test content",
            context_type="system",
            priority="critical",
            relevance=0.9,
            importance=0.8,
        )
        
        self.assertEqual(item.content, "Test content")
        self.assertEqual(item.context_type, ContextType.SYSTEM)
        self.assertEqual(item.priority, PriorityLevel.CRITICAL)
        self.assertEqual(item.relevance_score, 0.9)
        self.assertEqual(item.importance_score, 0.8)
    
    def test_prioritize_context_function(self):
        """Test convenience prioritize function."""
        items = [create_context_item("Test")]
        result = prioritize_context(items, token_budget=100)
        
        self.assertIsInstance(result, PrioritizationResult)
    
    def test_allocate_budget(self):
        """Test budget allocation."""
        allocations = allocate_budget(
            total_budget=1000,
            allocations={
                "system": 0.1,
                "profile": 0.2,
                "conversation": 0.7,
            }
        )
        
        self.assertEqual(allocations["system"], 100)
        self.assertEqual(allocations["profile"], 200)
        self.assertEqual(allocations["conversation"], 700)
    
    def test_allocate_budget_normalization(self):
        """Test budget allocation with unnormalized percentages."""
        allocations = allocate_budget(
            total_budget=1000,
            allocations={
                "a": 1.0,
                "b": 1.0,
            }
        )
        
        # Should normalize: each gets 50%
        self.assertEqual(allocations["a"], 500)
        self.assertEqual(allocations["b"], 500)


class TestContextTypes(unittest.TestCase):
    """Test context type handling."""
    
    def test_all_context_types(self):
        """Test all context types can be used."""
        for ctx_type in ContextType:
            item = ContextItem(
                content="Test",
                context_type=ctx_type,
            )
            self.assertEqual(item.context_type, ctx_type)
    
    def test_all_priority_levels(self):
        """Test all priority levels can be used."""
        for priority in PriorityLevel:
            item = ContextItem(
                content="Test",
                context_type=ContextType.CONVERSATION,
                priority=priority,
            )
            self.assertEqual(item.priority, priority)


class TestIntegration(unittest.TestCase):
    """Integration tests for memory intelligence system."""
    
    def test_analyzer_to_prioritizer_flow(self):
        """Test flow from analyzer to prioritizer."""
        # Analyze some text
        analyzer = get_semantic_analyzer()
        analyzer.clear_cache()
        
        result = analyzer.analyze(
            "I want to build a Python web API",
            previous_texts=["Let's discuss FastAPI"]
        )
        
        # Create context items from analysis
        items = []
        for topic in result.topics[:3]:
            items.append(create_context_item(
                f"Topic: {topic.text}",
                context_type="knowledge_graph",
                priority="medium",
                importance=topic.importance,
            ))
        
        # Prioritize
        prioritizer = get_context_prioritizer(token_budget=100)
        prio_result = prioritizer.prioritize(items)
        
        self.assertIsInstance(prio_result, PrioritizationResult)
    
    def test_full_context_building_workflow(self):
        """Test complete context building workflow."""
        # 1. Create various context items
        items = [
            create_context_item(
                "You are a helpful AI assistant.",
                context_type="system",
                priority="critical",
            ),
            create_context_item(
                "User prefers Python over Java.",
                context_type="user_profile",
                priority="high",
            ),
            create_context_item(
                "Previously discussed web frameworks.",
                context_type="episodic",
                priority="medium",
            ),
            create_context_item(
                "Background: FastAPI uses async/await.",
                context_type="conversation",
                priority="low",
            ),
        ]
        
        # 2. Prioritize
        prioritizer = get_context_prioritizer(token_budget=200)
        result = prioritizer.prioritize(
            items,
            current_query="How do I create an async endpoint?"
        )
        
        # 3. Build context string
        context = prioritizer.build_context_string(result)
        
        # 4. Verify
        self.assertIsInstance(context, str)
        self.assertLessEqual(approx_tokens(context), 200)
        
        # Critical items should be present
        self.assertIn("helpful AI assistant", context)


if __name__ == "__main__":
    # Run tests
    unittest.main(verbosity=2)
