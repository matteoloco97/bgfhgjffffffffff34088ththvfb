#!/usr/bin/env python3
"""
tests/test_intent_detection.py
==============================

Unit tests per il sistema di intent detection unificato.
Testa pattern matching, classificazione e routing.
"""

import sys
import os
import pytest
from typing import Dict, Any

# Add project root to path dynamically
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

# Import moduli da testare
try:
    from core.unified_web_handler import UnifiedIntentDetector
    from core.smart_intent_classifier import SmartIntentClassifier
    IMPORTS_OK = True
except ImportError as e:
    print(f"Warning: Import failed: {e}")
    IMPORTS_OK = False


@pytest.fixture
def unified_detector():
    """Fixture per UnifiedIntentDetector."""
    return UnifiedIntentDetector()


@pytest.fixture
def smart_classifier():
    """Fixture per SmartIntentClassifier."""
    return SmartIntentClassifier()


# ===================== WEATHER TESTS =====================

class TestWeatherIntent:
    """Test intent detection per query meteo."""
    
    weather_queries = [
        ("meteo roma", "weather"),
        ("che tempo fa a Milano", "weather"),
        ("previsioni meteo napoli", "weather"),
        ("weather in London", "weather"),
        ("temperatura oggi", "weather"),
        ("pioverà domani", "weather"),
    ]
    
    @pytest.mark.parametrize("query,expected_intent", weather_queries)
    def test_weather_detection(self, unified_detector, query, expected_intent):
        """Verifica che le query meteo siano classificate correttamente."""
        result = unified_detector.classify(query)
        assert result["intent"] == expected_intent, f"Query '{query}' should be {expected_intent}, got {result['intent']}"
        assert result["confidence"] >= 0.8, f"Confidence for '{query}' should be >= 0.8"


# ===================== PRICE TESTS =====================

class TestPriceIntent:
    """Test intent detection per query prezzi."""
    
    price_queries = [
        ("prezzo bitcoin", "price"),
        ("quanto vale ethereum", "price"),
        ("btc oggi", "price"),
        ("quotazione azioni apple", "price"),
        ("eur/usd cambio", "price"),
        ("oro prezzo corrente", "price"),
        ("nasdaq index", "price"),
        ("eth", "price"),  # Query breve con asset
    ]
    
    @pytest.mark.parametrize("query,expected_intent", price_queries)
    def test_price_detection(self, unified_detector, query, expected_intent):
        """Verifica che le query prezzi siano classificate correttamente."""
        result = unified_detector.classify(query)
        assert result["intent"] == expected_intent, f"Query '{query}' should be {expected_intent}, got {result['intent']}"


# ===================== SPORTS TESTS =====================

class TestSportsIntent:
    """Test intent detection per query sportive."""
    
    sports_queries = [
        ("risultato Milan", "sports"),
        ("classifica Serie A", "sports"),
        ("chi ha vinto Juventus", "sports"),
        ("partita Inter", "sports"),
        ("champions league risultati", "sports"),
    ]
    
    @pytest.mark.parametrize("query,expected_intent", sports_queries)
    def test_sports_detection(self, unified_detector, query, expected_intent):
        """Verifica che le query sportive siano classificate correttamente."""
        result = unified_detector.classify(query)
        assert result["intent"] == expected_intent, f"Query '{query}' should be {expected_intent}, got {result['intent']}"


# ===================== NEWS TESTS =====================

class TestNewsIntent:
    """Test intent detection per query news."""
    
    news_queries = [
        ("ultime notizie", "news"),
        ("breaking news", "news"),
        ("cosa è successo oggi", "news"),
        ("novità bitcoin", "news"),
    ]
    
    @pytest.mark.parametrize("query,expected_intent", news_queries)
    def test_news_detection(self, unified_detector, query, expected_intent):
        """Verifica che le query news siano classificate correttamente."""
        result = unified_detector.classify(query)
        assert result["intent"] == expected_intent, f"Query '{query}' should be {expected_intent}, got {result['intent']}"


# ===================== SCHEDULE TESTS =====================

class TestScheduleIntent:
    """Test intent detection per query calendario."""
    
    schedule_queries = [
        ("quando gioca la Juve", "schedule"),
        ("a che ora inizia la partita", "schedule"),
        ("calendario F1", "schedule"),
        ("prossimo gp formula 1", "schedule"),
    ]
    
    @pytest.mark.parametrize("query,expected_intent", schedule_queries)
    def test_schedule_detection(self, unified_detector, query, expected_intent):
        """Verifica che le query calendario siano classificate correttamente."""
        result = unified_detector.classify(query)
        assert result["intent"] == expected_intent, f"Query '{query}' should be {expected_intent}, got {result['intent']}"


# ===================== CODE TESTS =====================

class TestCodeIntent:
    """Test intent detection per query codice."""
    
    code_queries = [
        ("scrivi codice python", "code"),
        ("genera uno script bash", "code"),
        ("implementa funzione sorting", "code"),
        ("debug questo errore", "code"),
        ("fixa questo bug", "code"),
    ]
    
    @pytest.mark.parametrize("query,expected_intent", code_queries)
    def test_code_detection(self, unified_detector, query, expected_intent):
        """Verifica che le query codice siano classificate correttamente."""
        result = unified_detector.classify(query)
        assert result["intent"] == expected_intent, f"Query '{query}' should be {expected_intent}, got {result['intent']}"


# ===================== BETTING TESTS =====================

class TestBettingIntent:
    """Test intent detection per query betting."""
    
    betting_queries = [
        ("calcola ev scommessa", "betting"),
        ("kelly criterion quota 2.5", "betting"),
        ("è una value bet?", "betting"),
        ("quote partita milan", "betting"),
    ]
    
    @pytest.mark.parametrize("query,expected_intent", betting_queries)
    def test_betting_detection(self, unified_detector, query, expected_intent):
        """Verifica che le query betting siano classificate correttamente."""
        result = unified_detector.classify(query)
        assert result["intent"] == expected_intent, f"Query '{query}' should be {expected_intent}, got {result['intent']}"


# ===================== TRADING TESTS =====================

class TestTradingIntent:
    """Test intent detection per query trading."""
    
    trading_queries = [
        ("position size account 10000", "trading"),
        ("calcola risk reward", "trading"),
        ("stop loss 95 take profit 110", "trading"),
        ("leva 10x su btc", "trading"),
    ]
    
    @pytest.mark.parametrize("query,expected_intent", trading_queries)
    def test_trading_detection(self, unified_detector, query, expected_intent):
        """Verifica che le query trading siano classificate correttamente."""
        result = unified_detector.classify(query)
        assert result["intent"] == expected_intent, f"Query '{query}' should be {expected_intent}, got {result['intent']}"


# ===================== EDGE CASES =====================

class TestEdgeCases:
    """Test per casi limite e ambiguità."""
    
    def test_empty_query(self, unified_detector):
        """Query vuota deve restituire direct_llm."""
        result = unified_detector.classify("")
        assert result["intent"] == "direct_llm"
        assert result["confidence"] == 0.0
    
    def test_travel_vs_sports(self, unified_detector):
        """'volo roma' deve essere travel, non sports (Roma squadra)."""
        result = unified_detector.classify("volo roma parigi")
        assert result["intent"] == "general_web", f"Expected general_web (travel), got {result['intent']}"
        assert result.get("live_type") == "travel"
    
    def test_general_knowledge(self, unified_detector):
        """Query generale deve andare a direct_llm."""
        result = unified_detector.classify("chi era Napoleone")
        assert result["intent"] == "direct_llm"
    
    def test_deep_research_explicit(self, unified_detector):
        """Trigger esplicito per deep research."""
        result = unified_detector.classify("ricerca approfondita su AI")
        assert result["intent"] == "deep_research"
        assert result["confidence"] >= 0.9


# ===================== INPUT CLEANING TESTS =====================

class TestInputCleaning:
    """Test per la pulizia dell'input (punteggiatura, spazi, ecc.)."""
    
    def test_weather_with_question_mark(self, unified_detector):
        """'meteo roma?' deve essere classificato come weather."""
        result = unified_detector.classify("meteo roma?")
        assert result["intent"] == "weather", f"'meteo roma?' should be weather, got {result['intent']}"
    
    def test_weather_with_exclamation(self, unified_detector):
        """'meteo milano!' deve essere classificato come weather."""
        result = unified_detector.classify("meteo milano!")
        assert result["intent"] == "weather"
    
    def test_weather_with_trailing_spaces(self, unified_detector):
        """'  meteo napoli  ' deve essere classificato come weather."""
        result = unified_detector.classify("  meteo napoli  ")
        assert result["intent"] == "weather"
    
    def test_price_with_punctuation(self, unified_detector):
        """'prezzo bitcoin?' deve essere classificato come price."""
        result = unified_detector.classify("prezzo bitcoin?")
        assert result["intent"] == "price"
    
    def test_news_with_punctuation(self, unified_detector):
        """'ultime notizie?' deve essere classificato come news."""
        result = unified_detector.classify("ultime notizie?")
        assert result["intent"] == "news"


# ===================== CLEAN QUERY FUNCTION TESTS =====================

class TestCleanQueryFunction:
    """Test per la funzione clean_query_input."""
    
    def test_clean_query_basic(self):
        """Test pulizia base."""
        from core.unified_web_handler import clean_query_input
        
        assert clean_query_input("meteo roma?") == "meteo roma"
        assert clean_query_input("prezzo btc!") == "prezzo btc"
        assert clean_query_input("  query  ") == "query"
    
    def test_clean_query_multiple_punctuation(self):
        """Test con punteggiatura multipla."""
        from core.unified_web_handler import clean_query_input
        
        assert clean_query_input("test???") == "test"
        assert clean_query_input("test!!") == "test"
        assert clean_query_input("test..,;:") == "test"
    
    def test_clean_query_empty(self):
        """Test query vuota."""
        from core.unified_web_handler import clean_query_input
        
        assert clean_query_input("") == ""
        assert clean_query_input("   ") == ""


# ===================== RETROCOMPATIBILITY TESTS =====================

class TestRetrocompatibility:
    """Test per retrocompatibilità con SmartIntentClassifier."""
    
    def test_to_smart_intent_format(self, unified_detector):
        """Verifica conversione a formato SmartIntentClassifier."""
        # Weather → WEB_SEARCH
        result = unified_detector.classify("meteo roma")
        converted = unified_detector.to_smart_intent_format(result)
        
        assert converted["intent"] == "WEB_SEARCH"
        assert converted.get("live_type") == "weather"
    
    def test_code_format_conversion(self, unified_detector):
        """Code deve mappare a DIRECT_LLM."""
        result = unified_detector.classify("scrivi codice python")
        converted = unified_detector.to_smart_intent_format(result)
        
        assert converted["intent"] == "DIRECT_LLM"
        assert converted.get("live_type") == "code"


# ===================== WEATHER AGENT TESTS =====================

class TestWeatherAgentCleaning:
    """Test per la pulizia input nel weather agent."""
    
    def test_clean_city_name(self):
        """Test funzione clean_city_name."""
        from agents.weather_open_meteo import clean_city_name
        
        assert clean_city_name("roma?") == "roma"
        assert clean_city_name("Milano!") == "milano"
        assert clean_city_name("  Napoli  ") == "napoli"
        assert clean_city_name("Roma,") == "roma"
        assert clean_city_name("torino...") == "torino"
    
    def test_extract_city_with_punctuation(self):
        """Test estrazione città con punteggiatura."""
        from agents.weather_open_meteo import extract_city_from_query
        
        # Query con punteggiatura
        assert extract_city_from_query("meteo roma?") == "roma"
        assert extract_city_from_query("meteo milano!") == "milano"
        assert extract_city_from_query("che tempo fa a napoli?") == "napoli"


# ===================== RUN TESTS =====================

if __name__ == "__main__":
    if not IMPORTS_OK:
        print("❌ Cannot run tests: imports failed")
        sys.exit(1)
    
    # Run with pytest
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
