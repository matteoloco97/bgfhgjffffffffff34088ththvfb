#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_adaptive_token_allocation.py - Unit tests for adaptive token allocation

Tests for:
- TokenAllocationStrategy (complexity analysis and token budgets)
- AdvancedQueryAnalyzer (multi-dimensional analysis and strategy recommendation)
"""

import sys
import os
import unittest

# Add parent directory to path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.adaptive_token_allocator import (
    get_token_allocator,
    TokenAllocationStrategy,
    QueryComplexity
)
from core.query_analyzer_v2 import (
    get_query_analyzer,
    AdvancedQueryAnalyzer,
    UncertaintyLevel,
    TimeSensitivity
)


class TestTokenAllocationStrategy(unittest.TestCase):
    """Test cases for TokenAllocationStrategy."""
    
    def setUp(self):
        self.allocator = TokenAllocationStrategy()
    
    def test_trivial_queries(self):
        """Test trivial query detection."""
        test_cases = [
            "ciao",
            "hi",
            "hello",
            "grazie",
            "thanks",
            "ok",
            "sì",
            "no",
        ]
        
        for query in test_cases:
            complexity = self.allocator.analyze_complexity(query)
            self.assertEqual(
                complexity,
                QueryComplexity.TRIVIAL,
                f"Expected TRIVIAL for '{query}', got {complexity}"
            )
            
            budget, _, _ = self.allocator.allocate_tokens(query)
            self.assertEqual(
                budget,
                100,
                f"Expected 100 tokens for '{query}', got {budget}"
            )
    
    def test_simple_queries(self):
        """Test simple query detection."""
        test_cases = [
            "cos'è Python",
            "what is Python",
            "chi è Einstein",
            "who is Einstein",
        ]
        
        for query in test_cases:
            complexity = self.allocator.analyze_complexity(query)
            self.assertEqual(
                complexity,
                QueryComplexity.SIMPLE,
                f"Expected SIMPLE for '{query}', got {complexity}"
            )
            
            budget, _, _ = self.allocator.allocate_tokens(query)
            self.assertEqual(
                budget,
                300,
                f"Expected 300 tokens for '{query}', got {budget}"
            )
    
    def test_complex_queries(self):
        """Test complex query detection."""
        test_cases = [
            "analizza in dettaglio Python",
            "analyze Python in detail",
            "confronta Python e Java",
            "compare Python and Java",
            "spiegami dettagliato come funziona",
        ]
        
        for query in test_cases:
            complexity = self.allocator.analyze_complexity(query)
            self.assertEqual(
                complexity,
                QueryComplexity.COMPLEX,
                f"Expected COMPLEX for '{query}', got {complexity}"
            )
            
            budget, _, _ = self.allocator.allocate_tokens(query)
            self.assertEqual(
                budget,
                1200,
                f"Expected 1200 tokens for '{query}', got {budget}"
            )
    
    def test_very_complex_queries(self):
        """Test very complex query detection."""
        test_cases = [
            "ricerca dettagliata su Python",
            "research Python thoroughly",
            "implementa un sistema complesso",
            "implement a complex system",
            "step by step guida completa",
            "passo dopo passo spiega tutto",
        ]
        
        for query in test_cases:
            complexity = self.allocator.analyze_complexity(query)
            self.assertEqual(
                complexity,
                QueryComplexity.VERY_COMPLEX,
                f"Expected VERY_COMPLEX for '{query}', got {complexity}"
            )
            
            budget, _, _ = self.allocator.allocate_tokens(query)
            self.assertEqual(
                budget,
                2048,
                f"Expected 2048 tokens for '{query}', got {budget}"
            )
    
    def test_moderate_default(self):
        """Test moderate complexity as default."""
        test_cases = [
            "spiegami come funziona il sistema di memoria",
            "tell me about programming languages and their features",
            "cosa ne pensi di questo approccio per gestire i token",
        ]
        
        for query in test_cases:
            complexity = self.allocator.analyze_complexity(query)
            self.assertEqual(
                complexity,
                QueryComplexity.MODERATE,
                f"Expected MODERATE for '{query}', got {complexity}"
            )
            
            budget, _, _ = self.allocator.allocate_tokens(query)
            self.assertEqual(
                budget,
                600,
                f"Expected 600 tokens for '{query}', got {budget}"
            )
    
    def test_singleton_instance(self):
        """Test that get_token_allocator returns singleton."""
        allocator1 = get_token_allocator()
        allocator2 = get_token_allocator()
        self.assertIs(allocator1, allocator2)


class TestAdvancedQueryAnalyzer(unittest.TestCase):
    """Test cases for AdvancedQueryAnalyzer."""
    
    def setUp(self):
        self.analyzer = AdvancedQueryAnalyzer()
    
    def test_uncertainty_analysis(self):
        """Test uncertainty level detection."""
        # Confident queries
        confident_queries = ["ciao", "what is Python"]
        for query in confident_queries:
            uncertainty = self.analyzer.analyze_uncertainty(query)
            self.assertEqual(
                uncertainty,
                UncertaintyLevel.CONFIDENT,
                f"Expected CONFIDENT for '{query}'"
            )
        
        # Uncertain queries
        uncertain_queries = ["cosa ne pensi", "forse dovrei", "opinione su questo"]
        for query in uncertain_queries:
            uncertainty = self.analyzer.analyze_uncertainty(query)
            self.assertEqual(
                uncertainty,
                UncertaintyLevel.UNCERTAIN,
                f"Expected UNCERTAIN for '{query}'"
            )
        
        # Research queries
        research_queries = ["ricerca su Python", "trova informazioni", "chi ha vinto"]
        for query in research_queries:
            uncertainty = self.analyzer.analyze_uncertainty(query)
            self.assertEqual(
                uncertainty,
                UncertaintyLevel.REQUIRES_RESEARCH,
                f"Expected REQUIRES_RESEARCH for '{query}'"
            )
    
    def test_time_sensitivity_analysis(self):
        """Test time sensitivity detection."""
        # Evergreen queries
        evergreen_queries = ["cos'è Python", "spiegami la storia"]
        for query in evergreen_queries:
            time_sens = self.analyzer.analyze_time_sensitivity(query)
            self.assertEqual(
                time_sens,
                TimeSensitivity.EVERGREEN,
                f"Expected EVERGREEN for '{query}'"
            )
        
        # Dynamic queries
        dynamic_queries = ["meteo Roma oggi", "weather today", "prezzo Bitcoin"]
        for query in dynamic_queries:
            time_sens = self.analyzer.analyze_time_sensitivity(query)
            self.assertEqual(
                time_sens,
                TimeSensitivity.DYNAMIC,
                f"Expected DYNAMIC for '{query}'"
            )
        
        # Real-time queries
        realtime_queries = ["notizie ora", "live news", "breaking news adesso"]
        for query in realtime_queries:
            time_sens = self.analyzer.analyze_time_sensitivity(query)
            self.assertEqual(
                time_sens,
                TimeSensitivity.REAL_TIME,
                f"Expected REAL_TIME for '{query}'"
            )
    
    def test_strategy_recommendation(self):
        """Test strategy recommendation logic."""
        # Real-time → web_search
        strategy, conf = self.analyzer.recommend_strategy(
            "simple",
            UncertaintyLevel.CONFIDENT,
            TimeSensitivity.REAL_TIME
        )
        self.assertEqual(strategy, "web_search")
        self.assertEqual(conf, 0.95)
        
        # Research → web_search
        strategy, conf = self.analyzer.recommend_strategy(
            "simple",
            UncertaintyLevel.REQUIRES_RESEARCH,
            TimeSensitivity.EVERGREEN
        )
        self.assertEqual(strategy, "web_search")
        self.assertEqual(conf, 0.90)
        
        # Dynamic + uncertain → hybrid
        strategy, conf = self.analyzer.recommend_strategy(
            "simple",
            UncertaintyLevel.UNCERTAIN,
            TimeSensitivity.DYNAMIC
        )
        self.assertEqual(strategy, "hybrid")
        self.assertEqual(conf, 0.85)
        
        # Complex → hybrid
        strategy, conf = self.analyzer.recommend_strategy(
            "complex",
            UncertaintyLevel.CONFIDENT,
            TimeSensitivity.EVERGREEN
        )
        self.assertEqual(strategy, "hybrid")
        self.assertEqual(conf, 0.75)
        
        # Default → direct_llm
        strategy, conf = self.analyzer.recommend_strategy(
            "simple",
            UncertaintyLevel.CONFIDENT,
            TimeSensitivity.EVERGREEN
        )
        self.assertEqual(strategy, "direct_llm")
        self.assertEqual(conf, 0.70)
    
    def test_complete_analysis(self):
        """Test complete query analysis."""
        # Test case 1: "Ciao" → trivial, 100 tokens
        score = self.analyzer.analyze("Ciao")
        self.assertEqual(score.complexity, "trivial")
        self.assertEqual(score.metadata["token_budget"], 100)
        
        # Test case 2: "Analizza..." → complex, 1200 tokens
        score = self.analyzer.analyze("Analizza in dettaglio Python")
        self.assertEqual(score.complexity, "complex")
        self.assertEqual(score.metadata["token_budget"], 1200)
        
        # Test case 3: "Meteo Roma?" → simple/moderate + dynamic → hybrid
        score = self.analyzer.analyze("Meteo Roma oggi?")
        self.assertEqual(score.time_sensitivity, TimeSensitivity.DYNAMIC)
        # Token budget should be reasonable (300-600)
        self.assertIn(score.metadata["token_budget"], [300, 600])
    
    def test_singleton_instance(self):
        """Test that get_query_analyzer returns singleton."""
        analyzer1 = get_query_analyzer()
        analyzer2 = get_query_analyzer()
        self.assertIs(analyzer1, analyzer2)


if __name__ == "__main__":
    print("🧪 Running Adaptive Token Allocation Tests\n" + "=" * 60)
    unittest.main(verbosity=2)
