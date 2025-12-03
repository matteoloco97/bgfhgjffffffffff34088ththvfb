#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_user_profile_memory.py — Test User Profile Memory System

Tests for user profile fact storage, retrieval, and "remember" detection.
"""

import sys
import os
import unittest
from typing import List, Dict, Any

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.user_profile_memory import (
    detect_remember_statement,
    classify_category,
    save_user_profile_fact,
    query_user_profile,
    get_all_user_facts,
    delete_user_fact,
)


class TestUserProfileMemory(unittest.TestCase):
    """Test cases for user profile memory functionality."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        cls.test_user_id = "test_user_memory"
        cls.saved_fact_ids = []
    
    def test_detect_remember_italian(self):
        """Test detection of Italian 'remember' statements."""
        # Italian patterns
        tests = [
            ("ricorda che ho 30 anni", "ho 30 anni"),
            ("Da ora in poi ricordati che preferisco il tono diretto", "preferisco il tono diretto"),
            ("memorizza che abito a Roma", "abito a Roma"),
            ("Ricordati di questo fatto importante", "questo fatto importante"),
        ]
        
        for text, expected_fact in tests:
            result = detect_remember_statement(text)
            self.assertIsNotNone(result, f"Should detect remember in: {text}")
            self.assertIn(expected_fact.lower(), result.lower(), 
                         f"Extracted fact should contain: {expected_fact}")
    
    def test_detect_remember_english(self):
        """Test detection of English 'remember' statements."""
        tests = [
            ("remember that I'm 30 years old", "i'm 30 years old"),
            ("From now on, assume that I prefer direct tone", "i prefer direct tone"),
            ("Please remember my favorite color is blue", "my favorite color is blue"),
            ("keep in mind that I work on AI projects", "i work on ai projects"),
        ]
        
        for text, expected_fact in tests:
            result = detect_remember_statement(text)
            self.assertIsNotNone(result, f"Should detect remember in: {text}")
            self.assertIn(expected_fact.lower(), result.lower(),
                         f"Extracted fact should contain: {expected_fact}")
    
    def test_no_remember_statement(self):
        """Test that normal messages don't trigger detection."""
        normal_messages = [
            "Ciao come stai?",
            "Che tempo fa oggi?",
            "Can you help me with this code?",
            "I'm working on a project",
        ]
        
        for msg in normal_messages:
            result = detect_remember_statement(msg)
            self.assertIsNone(result, f"Should not detect remember in: {msg}")
    
    def test_classify_category_bio(self):
        """Test bio category classification."""
        bio_facts = [
            "ho 30 anni",
            "sono nato nel 1994",
            "abito a Milano",
            "I'm 25 years old",
            "I live in Rome",
        ]
        
        for fact in bio_facts:
            category = classify_category(fact)
            self.assertEqual(category, "bio", f"Should classify as bio: {fact}")
    
    def test_classify_category_goal(self):
        """Test goal category classification."""
        goal_facts = [
            "voglio imparare Python",
            "il mio obiettivo è ridurre il debito",
            "devo finire il progetto entro fine mese",
            "my goal is to learn AI",
            "I want to build a startup",
        ]
        
        for fact in goal_facts:
            category = classify_category(fact)
            self.assertEqual(category, "goal", f"Should classify as goal: {fact}")
    
    def test_classify_category_preference(self):
        """Test preference category classification."""
        pref_facts = [
            "preferisco il tono diretto",
            "mi piace il caffè forte",
            "I prefer concise answers",
            "my style is minimalist",
        ]
        
        for fact in pref_facts:
            category = classify_category(fact)
            self.assertEqual(category, "preference", f"Should classify as preference: {fact}")
    
    def test_classify_category_project(self):
        """Test project category classification."""
        project_facts = [
            "sto lavorando su Jarvis",
            "sto costruendo un'app di AI",
            "I'm working on a chatbot project",
            "building a quantum computing app",
        ]
        
        for fact in project_facts:
            category = classify_category(fact)
            self.assertEqual(category, "project", f"Should classify as project: {fact}")
    
    def test_save_and_query_user_fact(self):
        """Test saving and querying user facts."""
        # Save a fact
        fact_text = "Il mio colore preferito è blu"
        fact_id = save_user_profile_fact(
            user_id=self.test_user_id,
            fact_text=fact_text
        )
        
        if fact_id:
            self.saved_fact_ids.append(fact_id)
            self.assertIsNotNone(fact_id, "Should save fact successfully")
            
            # Query the fact
            results = query_user_profile(
                user_id=self.test_user_id,
                query_text="qual è il mio colore preferito?",
                top_k=5
            )
            
            self.assertGreater(len(results), 0, "Should find saved fact")
            # Check if our fact is in results
            found = any("blu" in r.get("text", "").lower() for r in results)
            self.assertTrue(found, "Should find fact about blue color")
    
    def test_save_fact_with_category(self):
        """Test saving fact with explicit category."""
        fact_text = "Lavoro nel settore AI"
        fact_id = save_user_profile_fact(
            user_id=self.test_user_id,
            fact_text=fact_text,
            category="project"
        )
        
        if fact_id:
            self.saved_fact_ids.append(fact_id)
            self.assertIsNotNone(fact_id, "Should save fact with category")
    
    def test_get_all_user_facts(self):
        """Test retrieving all facts for a user."""
        # Save multiple facts
        facts_to_save = [
            "Amo la pizza",
            "Studio machine learning",
            "Vivo a Roma",
        ]
        
        for fact in facts_to_save:
            fact_id = save_user_profile_fact(self.test_user_id, fact)
            if fact_id:
                self.saved_fact_ids.append(fact_id)
        
        # Get all facts
        all_facts = get_all_user_facts(self.test_user_id, limit=100)
        
        self.assertIsInstance(all_facts, list, "Should return a list")
        self.assertGreater(len(all_facts), 0, "Should have saved facts")
    
    def test_query_with_category_filter(self):
        """Test querying facts with category filter."""
        # Save facts in different categories
        save_user_profile_fact(
            self.test_user_id, 
            "Il mio obiettivo principale è completare Jarvis",
            category="goal"
        )
        
        save_user_profile_fact(
            self.test_user_id,
            "Preferisco risposte concise",
            category="preference"
        )
        
        # Query only goals
        goal_results = query_user_profile(
            user_id=self.test_user_id,
            query_text="obiettivo",
            top_k=5,
            category="goal"
        )
        
        # Verify results are from goal category
        for result in goal_results:
            metadata = result.get("metadata", {})
            self.assertEqual(metadata.get("category"), "goal",
                           "Should only return goal category facts")
    
    def test_empty_fact_handling(self):
        """Test that empty facts are not saved."""
        result = save_user_profile_fact(self.test_user_id, "")
        self.assertIsNone(result, "Should not save empty fact")
        
        result = save_user_profile_fact(self.test_user_id, "   ")
        self.assertIsNone(result, "Should not save whitespace-only fact")
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test data."""
        # Delete all test facts
        for fact_id in cls.saved_fact_ids:
            try:
                delete_user_fact(fact_id)
            except:
                pass


if __name__ == "__main__":
    # Run tests
    unittest.main()
