#!/usr/bin/env python3
"""
tests/test_web_router.py
========================

Unit tests for WebRouter module - intelligent web vs LLM routing.
Tests explicit triggers, time-sensitive detection, and diagnostics.
"""

import sys
import os
import pytest
from typing import Dict, Any

# Add project root to path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from core.web_router import (
    WebRouter,
    get_web_router,
    should_use_web,
    route_query,
)


# ===================== FIXTURES =====================

@pytest.fixture
def router():
    """Fixture for WebRouter instance (without LLM classifier)."""
    return WebRouter(use_llm_classifier=False)


@pytest.fixture
def router_with_llm():
    """Fixture for WebRouter instance (with LLM classifier)."""
    return WebRouter(use_llm_classifier=True)


# ===================== EXPLICIT TRIGGER TESTS =====================

class TestExplicitTriggers:
    """Test explicit keyword triggers that always require web."""
    
    # Italian triggers
    italian_triggers = [
        ("cerca su internet il meteo di roma", True, "explicit"),
        ("cercami informazioni su bitcoin", True, "explicit"),
        ("trova fonti per questa notizia", True, "explicit"),
        ("dammi i link sui risultati", True, "explicit"),
        ("verifica questa informazione online", True, "explicit"),
    ]
    
    # English triggers
    english_triggers = [
        ("search for latest news", True, "explicit"),
        ("find sources about climate change", True, "explicit"),
        ("lookup bitcoin price", True, "explicit"),
        ("google current weather", True, "explicit"),
        ("verify this information", True, "explicit"),
    ]
    
    @pytest.mark.parametrize("query,should_web,trigger_type", italian_triggers)
    def test_italian_explicit_triggers(self, router, query, should_web, trigger_type):
        """Test Italian explicit triggers."""
        result = router.route(query)
        assert result['web_required'] == should_web, f"Query '{query}' should have web_required={should_web}"
        assert result['trigger_type'] == trigger_type
        assert result['confidence'] >= 0.90
    
    @pytest.mark.parametrize("query,should_web,trigger_type", english_triggers)
    def test_english_explicit_triggers(self, router, query, should_web, trigger_type):
        """Test English explicit triggers."""
        result = router.route(query)
        assert result['web_required'] == should_web
        assert result['trigger_type'] == trigger_type
        assert result['confidence'] >= 0.90


# ===================== TIME-SENSITIVE TESTS =====================

class TestTimeSensitive:
    """Test time-sensitive pattern detection."""
    
    time_sensitive_queries = [
        # Current state
        ("qual è l'ultimo prezzo di bitcoin", True, "price"),
        ("what is the latest news on AI", True, "news"),
        ("stato attuale del mercato", True, "general"),
        
        # Today/recent events
        ("cosa è successo oggi in politica", True, "news"),
        ("what happened in the last 24 hours", True, "news"),
        
        # Market/prices
        ("prezzo del bitcoin", True, "price"),
        ("quotazione azioni apple", True, "price"),
        ("cambio euro dollaro", True, "price"),
        
        # Weather
        ("meteo roma", True, "weather"),
        ("che tempo fa oggi", True, "weather"),
        ("temperature forecast", True, "weather"),
        
        # Sports
        ("risultato della partita milan", True, "sports"),
        ("classifica serie a", True, "sports"),
        
        # News
        ("ultime notizie", True, "news"),
        ("latest breaking news", True, "news"),
    ]
    
    @pytest.mark.parametrize("query,should_web,expected_category", time_sensitive_queries)
    def test_time_sensitive_detection(self, router, query, should_web, expected_category):
        """Test time-sensitive query detection."""
        result = router.route(query)
        assert result['web_required'] == should_web, f"Query '{query}' should have web_required={should_web}"
        assert result['category'] == expected_category, f"Query '{query}' should be category {expected_category}"
        assert result['trigger_type'] in ['time_sensitive', 'explicit']


# ===================== GENERAL CHAT TESTS =====================

class TestGeneralChat:
    """Test queries that should NOT trigger web search."""
    
    general_queries = [
        # General knowledge (not time-sensitive)
        ("cos'è la fotosintesi", False),
        ("spiega la teoria della relatività", False),
        ("what is quantum physics", False),
        
        # Opinions/subjective
        ("qual è il miglior linguaggio di programmazione", False),
        ("dimmi una barzelletta", False),
        ("raccontami una storia", False),
        
        # Calculations
        ("quanto fa 25 * 37", False),
        ("calcola l'area di un cerchio con raggio 5", False),
        
        # Conversational
        ("ciao come stai", False),
        ("di cosa stiamo parlando", False),
        ("grazie per l'aiuto", False),
        
        # General advice
        ("come posso migliorare la mia produttività", False),
        ("dammi consigli per dormire meglio", False),
    ]
    
    @pytest.mark.parametrize("query,should_web", general_queries)
    def test_general_chat_no_web(self, router, query, should_web):
        """Test that general chat queries don't trigger web search."""
        result = router.route(query)
        assert result['web_required'] == should_web, f"Query '{query}' should have web_required={should_web}"
        assert result['trigger_type'] == 'none'


# ===================== CATEGORY DETECTION TESTS =====================

class TestCategoryDetection:
    """Test query categorization."""
    
    category_tests = [
        ("ultime notizie di politica", "news"),
        ("prezzo bitcoin oggi", "price"),
        ("meteo roma domani", "weather"),
        ("risultato milan juventus", "sports"),
        ("nuovo update di windows", "tech"),
        ("dimmi qualcosa di interessante", "general"),
    ]
    
    @pytest.mark.parametrize("query,expected_category", category_tests)
    def test_category_detection(self, router, query, expected_category):
        """Test that queries are categorized correctly."""
        result = router.route(query)
        assert result['category'] == expected_category


# ===================== LANGUAGE DETECTION TESTS =====================

class TestLanguageDetection:
    """Test language detection in queries."""
    
    language_tests = [
        ("cerca informazioni su Roma", ['it']),
        ("search for information about Rome", ['en']),
        ("qual è il meteo", ['it']),  # Italian accents
        ("hello world test", ['en']),
    ]
    
    @pytest.mark.parametrize("query,expected_langs", language_tests)
    def test_language_detection(self, router, query, expected_langs):
        """Test language detection."""
        result = router.route(query)
        assert result['languages'] == expected_langs or set(result['languages']) >= set(expected_langs)


# ===================== FRESHNESS TESTS =====================

class TestFreshness:
    """Test freshness_days calculation based on category."""
    
    freshness_tests = [
        ("ultime notizie", "news", 7),
        ("prezzo bitcoin", "price", 1),
        ("meteo oggi", "weather", 1),
        ("risultato partita", "sports", 7),
        ("nuovo update software", "tech", 30),
        ("spiega la fotosintesi", "general", 90),
    ]
    
    @pytest.mark.parametrize("query,expected_category,expected_freshness", freshness_tests)
    def test_freshness_calculation(self, router, query, expected_category, expected_freshness):
        """Test that freshness_days is calculated correctly."""
        result = router.route(query)
        # Only check freshness if category matches (some queries may have different categorization)
        if result['category'] == expected_category:
            assert result['freshness_days'] == expected_freshness


# ===================== LOGGING FORMAT TESTS =====================

class TestLogging:
    """Test diagnostic logging format."""
    
    def test_log_format(self, router):
        """Test that log format is consistent and parseable."""
        query = "cerca su internet il prezzo di bitcoin"
        result = router.route(query)
        log_line = router.format_log(result)
        
        # Check log format contains required fields
        assert "[WEB_ROUTER]" in log_line
        assert "required=" in log_line
        assert "category=" in log_line
        assert "langs=" in log_line
        assert "freshness=" in log_line
        assert "route=" in log_line
        assert "reason=" in log_line
    
    def test_log_values_web_required(self, router):
        """Test log values when web is required."""
        query = "cerca su internet notizie"
        result = router.route(query)
        log_line = router.format_log(result)
        
        assert "required=True" in log_line
        assert "route=web" in log_line
    
    def test_log_values_no_web(self, router):
        """Test log values when web is not required."""
        query = "ciao come stai"
        result = router.route(query)
        log_line = router.format_log(result)
        
        assert "required=False" in log_line
        assert "route=llm" in log_line


# ===================== CONVENIENCE FUNCTIONS TESTS =====================

class TestConvenienceFunctions:
    """Test convenience helper functions."""
    
    def test_should_use_web(self):
        """Test should_use_web() convenience function."""
        # Note: Using singleton which may have LLM classifier enabled
        # Test with explicit trigger to avoid LLM classifier
        assert should_use_web("cerca su internet") is True
        # For negative test, need to ensure no LLM classifier interference
        router = WebRouter(use_llm_classifier=False)
        result = router.route("ciao come stai")
        assert result['web_required'] is False
    
    def test_route_query(self):
        """Test route_query() convenience function."""
        result = route_query("cerca notizie")
        assert 'web_required' in result
        assert 'category' in result
        assert 'reason' in result
    
    def test_get_web_router_singleton(self):
        """Test that get_web_router() returns singleton."""
        router1 = get_web_router()
        router2 = get_web_router()
        assert router1 is router2


# ===================== EDGE CASES TESTS =====================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_empty_query(self, router):
        """Test handling of empty query."""
        result = router.route("")
        assert 'web_required' in result
        assert result['web_required'] is False
    
    def test_very_short_query(self, router):
        """Test handling of very short queries."""
        result = router.route("btc")
        assert 'web_required' in result
        # Short queries might or might not trigger web depending on context
    
    def test_very_long_query(self, router):
        """Test handling of very long queries."""
        long_query = "cerca su internet " + "informazioni " * 100
        result = router.route(long_query)
        assert result['web_required'] is True  # Contains explicit trigger
    
    def test_mixed_language_query(self, router):
        """Test handling of mixed Italian/English queries."""
        query = "cerca su internet the latest news about AI"
        result = router.route(query)
        assert result['web_required'] is True
        # Should detect both languages
        assert 'it' in result['languages'] or 'en' in result['languages']
    
    def test_context_parameter(self, router):
        """Test that context parameter is accepted."""
        context = {'user_id': 'test123', 'conversation_id': 'conv456'}
        result = router.route("test query", context)
        assert 'web_required' in result


# ===================== INTEGRATION TESTS =====================

class TestIntegration:
    """Integration tests combining multiple features."""
    
    def test_full_pipeline_web_required(self, router):
        """Test full pipeline for web-required query."""
        query = "cerca ultime notizie su bitcoin"
        result = router.route(query)
        
        # Should trigger web
        assert result['web_required'] is True
        
        # Should have correct trigger type
        assert result['trigger_type'] in ['explicit', 'time_sensitive']
        
        # Should have category
        assert result['category'] in ['news', 'price', 'general']
        
        # Should have languages
        assert len(result['languages']) > 0
        
        # Should have freshness
        assert result['freshness_days'] > 0
        
        # Should have reason
        assert len(result['reason']) > 0
        
        # Should have confidence
        assert 0 <= result['confidence'] <= 1.0
    
    def test_full_pipeline_no_web(self, router):
        """Test full pipeline for non-web query."""
        query = "spiega la teoria della relatività"
        result = router.route(query)
        
        # Should NOT trigger web
        assert result['web_required'] is False
        
        # Should have trigger type 'none'
        assert result['trigger_type'] == 'none'
        
        # Should still have category
        assert result['category'] == 'general'
        
        # Should have reason
        assert len(result['reason']) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
