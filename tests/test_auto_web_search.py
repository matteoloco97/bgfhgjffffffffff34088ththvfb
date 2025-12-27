#!/usr/bin/env python3
"""
tests/test_auto_web_search.py
==============================

Comprehensive test suite for STEP 2 - Auto Web Search Intelligence

Tests:
- Temporal detection
- Live data detection
- Knowledge gap detection
- Intent classification
- Strategy planning
- End-to-end integration
- Performance tests
"""

import sys
import os
import pytest
import asyncio
from typing import Dict, Any

# Add project root to path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)


# ===================== AUTO SEARCH DETECTOR TESTS =====================

class TestAutoSearchDetector:
    """Tests for AutoSearchDetector class."""
    
    def test_import(self):
        """Verify AutoSearchDetector can be imported."""
        from core.auto_search_detector import AutoSearchDetector, get_auto_search_detector
        assert AutoSearchDetector is not None
        assert get_auto_search_detector is not None
    
    @pytest.mark.asyncio
    async def test_temporal_keyword_detection(self):
        """Test temporal keyword detection."""
        from core.auto_search_detector import AutoSearchDetector
        
        detector = AutoSearchDetector()
        
        temporal_queries = [
            ("Quanto costa Bitcoin adesso?", True),
            ("Ultime notizie su AI", True),
            ("Prezzo ETH oggi", True),
            ("Notizie recenti Italia", True),
            ("Aggiornamenti domani", True),
        ]
        
        for query, expected in temporal_queries:
            result = await detector.detect_temporal_intent(query)
            assert result == expected, f"Query '{query}' should have temporal={expected}, got {result}"
    
    @pytest.mark.asyncio
    async def test_temporal_with_dates(self):
        """Test temporal detection with specific dates."""
        from core.auto_search_detector import AutoSearchDetector
        
        detector = AutoSearchDetector()
        
        date_queries = [
            ("Prezzo Bitcoin 27 dicembre 2024", True),
            ("Eventi 2024-12-27", True),
        ]
        
        for query, expected in date_queries:
            result = await detector.detect_temporal_intent(query)
            assert result == expected, f"Date query '{query}' should have temporal={expected}"
    
    @pytest.mark.asyncio
    async def test_no_false_temporal(self):
        """Test that non-temporal queries don't trigger false positives."""
        from core.auto_search_detector import AutoSearchDetector
        
        detector = AutoSearchDetector()
        
        non_temporal_queries = [
            "Chi ha inventato Bitcoin?",
            "Cos'è Python?",
            "Come funziona un motore?",
            "Storia della Francia",
        ]
        
        for query in non_temporal_queries:
            result = await detector.detect_temporal_intent(query)
            assert result == False, f"Non-temporal query '{query}' should not trigger temporal detection"


class TestLiveDataDetection:
    """Tests for live data detection."""
    
    @pytest.mark.asyncio
    async def test_price_detection(self):
        """Test price data detection."""
        from core.auto_search_detector import AutoSearchDetector
        
        detector = AutoSearchDetector()
        
        price_queries = [
            "Prezzo Ethereum",
            "Quotazione Bitcoin",
            "Quanto vale BTC",
            "Price of SOL",
        ]
        
        for query in price_queries:
            needs_live, data_type = await detector.detect_live_data_need(query)
            assert needs_live == True, f"Price query '{query}' should trigger live data"
            assert data_type == "price", f"Query '{query}' should be type 'price', got '{data_type}'"
    
    @pytest.mark.asyncio
    async def test_weather_detection(self):
        """Test weather data detection."""
        from core.auto_search_detector import AutoSearchDetector
        
        detector = AutoSearchDetector()
        
        weather_queries = [
            "Che tempo fa a Roma?",
            "Meteo Milano",
            "Previsioni Napoli domani",
            "Temperatura Firenze",
        ]
        
        for query in weather_queries:
            needs_live, data_type = await detector.detect_live_data_need(query)
            assert needs_live == True, f"Weather query '{query}' should trigger live data"
            assert data_type == "weather", f"Query '{query}' should be type 'weather', got '{data_type}'"
    
    @pytest.mark.asyncio
    async def test_news_detection(self):
        """Test news data detection."""
        from core.auto_search_detector import AutoSearchDetector
        
        detector = AutoSearchDetector()
        
        news_queries = [
            "Ultime notizie Italia",
            "Breaking news tech",
            "Novità Apple",
        ]
        
        for query in news_queries:
            needs_live, data_type = await detector.detect_live_data_need(query)
            assert needs_live == True, f"News query '{query}' should trigger live data"
            assert data_type == "news", f"Query '{query}' should be type 'news', got '{data_type}'"
    
    @pytest.mark.asyncio
    async def test_sports_detection(self):
        """Test sports data detection."""
        from core.auto_search_detector import AutoSearchDetector
        
        detector = AutoSearchDetector()
        
        sports_queries = [
            "Risultati Serie A oggi",
            "Classifica Champions League",
            "Chi ha vinto Milan",
        ]
        
        for query in sports_queries:
            needs_live, data_type = await detector.detect_live_data_need(query)
            assert needs_live == True, f"Sports query '{query}' should trigger live data"
            assert data_type == "sports", f"Query '{query}' should be type 'sports', got '{data_type}'"


class TestKnowledgeGapDetection:
    """Tests for knowledge gap detection."""
    
    @pytest.mark.asyncio
    async def test_knowledge_gap_new_entity(self):
        """Test detection of new entities not in memory."""
        from core.auto_search_detector import AutoSearchDetector
        
        detector = AutoSearchDetector()
        
        # Empty memory - should detect gap for factual queries
        empty_memory = {}
        
        query = "Cos'è il quantum computing?"
        has_gap = await detector.detect_knowledge_gap(query, empty_memory)
        assert has_gap == True, "Should detect gap for new entity with empty memory"
    
    @pytest.mark.asyncio
    async def test_no_gap_known_entity(self):
        """Test no gap when entity is in memory."""
        from core.auto_search_detector import AutoSearchDetector
        
        detector = AutoSearchDetector()
        
        # Memory with quantum computing discussed
        memory = {
            'topics': ['quantum computing', 'AI'],
            'entities': ['Quantum', 'Computing']
        }
        
        query = "Dimmi ancora del quantum computing"
        has_gap = await detector.detect_knowledge_gap(query, memory)
        # With memory containing the topic, should not detect gap
        assert has_gap == False, "Should not detect gap for known entity"


# ===================== QUERY CLASSIFIER TESTS =====================

class TestQueryClassifier:
    """Tests for QueryClassifier class."""
    
    def test_import(self):
        """Verify QueryClassifier can be imported."""
        from core.query_classifier import QueryClassifier, get_query_classifier
        assert QueryClassifier is not None
        assert get_query_classifier is not None
    
    @pytest.mark.asyncio
    async def test_conversational_intent(self):
        """Test conversational intent detection."""
        from core.query_classifier import QueryClassifier
        
        classifier = QueryClassifier()
        
        conversational_queries = [
            "Ciao come stai?",
            "Grazie mille!",
            "Ok perfetto",
            "Buongiorno",
        ]
        
        for query in conversational_queries:
            result = await classifier.classify_intent(query)
            assert result['intent'] == 'conversational', f"'{query}' should be conversational"
            assert result['requires_search'] == False, f"'{query}' should not require search"
    
    @pytest.mark.asyncio
    async def test_factual_intent(self):
        """Test factual intent detection."""
        from core.query_classifier import QueryClassifier
        
        classifier = QueryClassifier()
        
        factual_queries = [
            "Cos'è Python?",
            "Chi era Einstein?",
            "Come funziona un motore?",
        ]
        
        for query in factual_queries:
            result = await classifier.classify_intent(query)
            assert result['intent'] == 'factual', f"'{query}' should be factual, got {result['intent']}"
    
    @pytest.mark.asyncio
    async def test_live_data_intent(self):
        """Test live data intent detection."""
        from core.query_classifier import QueryClassifier
        
        classifier = QueryClassifier()
        
        live_queries = [
            ("Prezzo Bitcoin", "price"),
            ("Che tempo fa a Roma?", "weather"),
            ("Ultime notizie su AI", "news"),
            ("Risultati Serie A", "sports"),
        ]
        
        for query, expected_sub in live_queries:
            result = await classifier.classify_intent(query)
            assert result['intent'] == 'live_data', f"'{query}' should be live_data, got {result['intent']}"
            assert result['requires_search'] == True, f"'{query}' should require search"
    
    @pytest.mark.asyncio
    async def test_calculation_intent(self):
        """Test calculation intent detection."""
        from core.query_classifier import QueryClassifier
        
        classifier = QueryClassifier()
        
        calc_queries = [
            "Calcola 234 * 567",
            "Quanto fa 10 + 5?",
            "15 più 20",
        ]
        
        for query in calc_queries:
            result = await classifier.classify_intent(query)
            assert result['intent'] == 'calculation', f"'{query}' should be calculation"
            assert result['requires_search'] == False, f"'{query}' should not require search"


# ===================== SEARCH STRATEGY PLANNER TESTS =====================

class TestSearchStrategyPlanner:
    """Tests for SearchStrategyPlanner class."""
    
    def test_import(self):
        """Verify SearchStrategyPlanner can be imported."""
        from core.search_strategy_planner import SearchStrategyPlanner, get_search_strategy_planner
        assert SearchStrategyPlanner is not None
        assert get_search_strategy_planner is not None
    
    @pytest.mark.asyncio
    async def test_quick_strategy_for_price(self):
        """Test quick strategy for price queries."""
        from core.search_strategy_planner import SearchStrategyPlanner
        
        planner = SearchStrategyPlanner()
        
        intent_result = {
            'intent': 'live_data',
            'sub_intent': 'price',
            'search_urgency': 'high'
        }
        
        strategy = await planner.plan_search_strategy("Prezzo Bitcoin", intent_result)
        
        assert strategy['strategy'] == 'quick', "Price query should use quick strategy"
        assert strategy['synthesis_mode'] == 'concise', "Price query should use concise synthesis"
        assert strategy['timeout'] <= 15, "Quick strategy should have short timeout"
    
    @pytest.mark.asyncio
    async def test_deep_strategy_for_research(self):
        """Test deep strategy for research queries."""
        from core.search_strategy_planner import SearchStrategyPlanner
        
        planner = SearchStrategyPlanner()
        
        intent_result = {
            'intent': 'research',
            'sub_intent': 'deep_research',
            'search_urgency': 'medium'
        }
        
        strategy = await planner.plan_search_strategy("Approfondimento AI", intent_result)
        
        assert strategy['strategy'] == 'research', "Research query should use research strategy"
        assert strategy['synthesis_mode'] == 'comprehensive', "Research should use comprehensive synthesis"
    
    @pytest.mark.asyncio
    async def test_cache_policy_application(self):
        """Test cache policy based on data type."""
        from core.search_strategy_planner import SearchStrategyPlanner
        
        planner = SearchStrategyPlanner()
        
        # Price - should have short cache TTL
        should_use_price = await planner.should_use_cache("btc price", "price", 30)
        assert should_use_price == True, "30s old price data should be cacheable"
        
        should_use_old_price = await planner.should_use_cache("btc price", "price", 120)
        assert should_use_old_price == False, "120s old price data should be stale"
        
        # Weather - should have longer cache TTL
        should_use_weather = await planner.should_use_cache("meteo roma", "weather", 1000)
        assert should_use_weather == True, "1000s old weather data should be cacheable"


# ===================== INTEGRATION TESTS =====================

class TestAutoSearchIntegration:
    """End-to-end integration tests."""
    
    @pytest.mark.asyncio
    async def test_e2e_price_query(self):
        """Test end-to-end price query flow."""
        from core.auto_search_detector import get_auto_search_detector
        from core.query_classifier import get_query_classifier
        from core.search_strategy_planner import get_search_strategy_planner
        
        detector = get_auto_search_detector()
        classifier = get_query_classifier()
        planner = get_search_strategy_planner()
        
        query = "Quanto costa Bitcoin?"
        
        # Step 1: Detect if search needed
        search_decision = await detector.should_trigger_search(query, {}, {})
        assert search_decision['should_search'] == True
        
        # Step 2: Classify intent
        intent_result = await classifier.classify_intent(query)
        assert intent_result['intent'] == 'live_data'
        
        # Step 3: Plan strategy
        strategy = await planner.plan_search_strategy(query, intent_result)
        assert strategy['strategy'] in ['quick', 'parallel']
    
    @pytest.mark.asyncio
    async def test_e2e_weather_query(self):
        """Test end-to-end weather query flow."""
        from core.auto_search_detector import get_auto_search_detector
        from core.query_classifier import get_query_classifier
        
        detector = get_auto_search_detector()
        classifier = get_query_classifier()
        
        query = "Che tempo fa a Milano?"
        
        search_decision = await detector.should_trigger_search(query, {}, {})
        assert search_decision['should_search'] == True
        
        intent_result = await classifier.classify_intent(query)
        assert intent_result['intent'] == 'live_data'
        assert intent_result['sub_intent'] == 'weather'
    
    @pytest.mark.asyncio
    async def test_e2e_news_query(self):
        """Test end-to-end news query flow."""
        from core.auto_search_detector import get_auto_search_detector
        from core.query_classifier import get_query_classifier
        
        detector = get_auto_search_detector()
        classifier = get_query_classifier()
        
        query = "Ultime notizie su Tesla"
        
        search_decision = await detector.should_trigger_search(query, {}, {})
        assert search_decision['should_search'] == True
        
        intent_result = await classifier.classify_intent(query)
        assert intent_result['intent'] == 'live_data'
    
    @pytest.mark.asyncio
    async def test_e2e_no_trigger_conversational(self):
        """Test that conversational queries don't trigger search."""
        from core.auto_search_detector import get_auto_search_detector
        from core.query_classifier import get_query_classifier
        
        detector = get_auto_search_detector()
        classifier = get_query_classifier()
        
        queries = [
            "Ciao come stai?",
            "Grazie!",
            "Ok perfetto",
        ]
        
        for query in queries:
            search_decision = await detector.should_trigger_search(query, {}, {})
            assert search_decision['should_search'] == False, f"'{query}' should not trigger search"


# ===================== PERFORMANCE TESTS =====================

class TestPerformance:
    """Performance tests for auto-search detection."""
    
    @pytest.mark.asyncio
    async def test_detection_latency(self):
        """Test that detection is fast (<100ms)."""
        import time
        from core.auto_search_detector import get_auto_search_detector
        
        detector = get_auto_search_detector()
        
        queries = [
            "Prezzo Bitcoin adesso",
            "Che tempo fa a Roma?",
            "Ultime notizie su AI",
            "Ciao come stai?",
            "Calcola 10 + 5",
        ]
        
        for query in queries:
            start = time.perf_counter()
            await detector.should_trigger_search(query, {}, {})
            elapsed_ms = (time.perf_counter() - start) * 1000
            
            assert elapsed_ms < 100, f"Detection for '{query}' took {elapsed_ms:.1f}ms (max 100ms)"
    
    @pytest.mark.asyncio
    async def test_classifier_latency(self):
        """Test that classification is fast (<50ms)."""
        import time
        from core.query_classifier import get_query_classifier
        
        classifier = get_query_classifier()
        
        queries = [
            "Prezzo Bitcoin",
            "Cos'è Python?",
            "Ciao",
        ]
        
        for query in queries:
            start = time.perf_counter()
            await classifier.classify_intent(query)
            elapsed_ms = (time.perf_counter() - start) * 1000
            
            assert elapsed_ms < 50, f"Classification for '{query}' took {elapsed_ms:.1f}ms (max 50ms)"


# ===================== SEARCH QUERY GENERATION TESTS =====================

class TestSearchQueryGeneration:
    """Tests for search query optimization."""
    
    @pytest.mark.asyncio
    async def test_generate_price_queries(self):
        """Test price query optimization."""
        from core.auto_search_detector import get_auto_search_detector
        
        detector = get_auto_search_detector()
        
        queries = await detector.generate_search_queries("Quanto costa Bitcoin adesso?", "quick")
        
        assert len(queries) > 0, "Should generate at least one query"
        # Check for price-related terms
        queries_lower = [q.lower() for q in queries]
        has_price_term = any('price' in q or 'bitcoin' in q or 'btc' in q for q in queries_lower)
        assert has_price_term, "Generated queries should include price terms"
    
    @pytest.mark.asyncio
    async def test_generate_weather_queries(self):
        """Test weather query optimization."""
        from core.auto_search_detector import get_auto_search_detector
        
        detector = get_auto_search_detector()
        
        queries = await detector.generate_search_queries("Che tempo fa a Roma domani?", "quick")
        
        assert len(queries) > 0, "Should generate at least one query"
        queries_lower = [q.lower() for q in queries]
        has_weather_term = any('weather' in q or 'meteo' in q or 'roma' in q for q in queries_lower)
        assert has_weather_term, "Generated queries should include weather/city terms"


# ===================== WEB SEARCH METHODS TESTS =====================

class TestWebSearchMethods:
    """Tests for new web_search.py methods."""
    
    def test_import_new_methods(self):
        """Verify new methods can be imported."""
        from core.web_search import (
            smart_search,
            parallel_multi_source_search,
            adaptive_synthesis,
            get_web_search
        )
        
        assert smart_search is not None
        assert parallel_multi_source_search is not None
        assert adaptive_synthesis is not None
        assert get_web_search is not None
    
    def test_adaptive_synthesis_modes(self):
        """Test adaptive synthesis with different modes."""
        from core.web_search import adaptive_synthesis
        
        sample_results = [
            {'title': 'Test 1', 'url': 'https://example.com/1', 'snippet': 'This is test snippet 1 with some content.'},
            {'title': 'Test 2', 'url': 'https://example.com/2', 'snippet': 'This is test snippet 2 with more content.'},
            {'title': 'Test 3', 'url': 'https://example.com/3', 'snippet': 'This is test snippet 3 with extra content.'},
        ]
        
        # Test concise mode
        concise = adaptive_synthesis(sample_results, 'concise')
        assert len(concise) > 0, "Concise synthesis should produce output"
        assert len(concise) <= 250, "Concise should be short"
        
        # Test detailed mode
        detailed = adaptive_synthesis(sample_results, 'detailed')
        assert len(detailed) > len(concise), "Detailed should be longer than concise"
        
        # Test comprehensive mode
        comprehensive = adaptive_synthesis(sample_results, 'comprehensive')
        assert 'Fonti:' in comprehensive, "Comprehensive should include sources"


# ===================== RUN TESTS =====================

if __name__ == "__main__":
    # Run with pytest
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
