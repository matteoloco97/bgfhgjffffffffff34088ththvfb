#!/usr/bin/env python3
"""
tests/test_weather_agent.py
===========================

Unit tests per il Weather Agent (agents/weather_open_meteo.py).
Testa parsing query con punteggiatura, estrazione città, e formatting.
"""

import sys
import os
import pytest
from typing import Optional

# Add project root to path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

# Import moduli da testare
try:
    from agents.weather_open_meteo import (
        extract_city_from_query,
        is_weather_query,
        _clean_city_name,
    )
    IMPORTS_OK = True
except ImportError as e:
    print(f"Warning: Import failed: {e}")
    IMPORTS_OK = False


# ===================== CITY NAME CLEANING TESTS =====================

class TestCleanCityName:
    """Test per la pulizia dei nomi città."""
    
    @pytest.mark.skipif(not IMPORTS_OK, reason="Import failed")
    @pytest.mark.parametrize("input_city,expected", [
        ("roma?", "roma"),
        ("roma??", "roma"),
        ("milano!", "milano"),
        ("milano!!", "milano"),
        ("napoli...", "napoli"),
        ("firenze.", "firenze"),
        ("torino;", "torino"),
        ("bologna:", "bologna"),
        ("  roma  ", "roma"),
        ("reggio emilia", "reggio emilia"),
        ("new york", "new york"),
        ("", ""),
        ("???", ""),
    ])
    def test_clean_city_name(self, input_city: str, expected: str):
        """Verifica che la punteggiatura venga rimossa correttamente."""
        result = _clean_city_name(input_city)
        assert result == expected, f"Expected '{expected}' for input '{input_city}', got '{result}'"


# ===================== CITY EXTRACTION TESTS =====================

class TestExtractCity:
    """Test per l'estrazione della città dalla query."""
    
    # Test cases per il bug fix principale (punteggiatura)
    punctuation_cases = [
        ("meteo roma?", "roma"),
        ("meteo roma??", "roma"),
        ("meteo milano!", "milano"),
        ("meteo napoli...", "napoli"),
        ("che tempo fa a firenze?", "firenze"),
        ("previsioni torino!!", "torino"),
        ("weather london?", "london"),
    ]
    
    # Test cases standard (senza punteggiatura)
    standard_cases = [
        ("meteo roma", "roma"),
        ("meteo milano", "milano"),
        ("che tempo fa a napoli", "napoli"),
        ("che tempo fa firenze", "firenze"),
        ("previsioni meteo torino", "torino"),
        ("weather in london", "london"),
        ("tempo a venezia", "venezia"),
    ]
    
    # Test casi con parole temporali
    temporal_cases = [
        ("meteo roma oggi", "roma"),
        ("meteo milano domani", "milano"),
        ("previsioni napoli settimana", "napoli"),
        ("che tempo fa a firenze oggi?", "firenze"),
    ]
    
    @pytest.mark.skipif(not IMPORTS_OK, reason="Import failed")
    @pytest.mark.parametrize("query,expected_city", punctuation_cases)
    def test_extract_city_with_punctuation(self, query: str, expected_city: str):
        """Verifica estrazione città con punteggiatura finale."""
        result = extract_city_from_query(query)
        assert result == expected_city, f"Query '{query}' should extract '{expected_city}', got '{result}'"
    
    @pytest.mark.skipif(not IMPORTS_OK, reason="Import failed")
    @pytest.mark.parametrize("query,expected_city", standard_cases)
    def test_extract_city_standard(self, query: str, expected_city: str):
        """Verifica estrazione città standard."""
        result = extract_city_from_query(query)
        assert result == expected_city, f"Query '{query}' should extract '{expected_city}', got '{result}'"
    
    @pytest.mark.skipif(not IMPORTS_OK, reason="Import failed")
    @pytest.mark.parametrize("query,expected_city", temporal_cases)
    def test_extract_city_with_temporal_words(self, query: str, expected_city: str):
        """Verifica estrazione città con parole temporali."""
        result = extract_city_from_query(query)
        assert result == expected_city, f"Query '{query}' should extract '{expected_city}', got '{result}'"
    
    @pytest.mark.skipif(not IMPORTS_OK, reason="Import failed")
    def test_extract_city_fallback_common_city(self):
        """Verifica fallback su città comune nel testo."""
        result = extract_city_from_query("che ne dici di roma?")
        assert result == "roma", f"Should find 'roma' in fallback, got '{result}'"
    
    @pytest.mark.skipif(not IMPORTS_OK, reason="Import failed")
    def test_extract_city_no_match(self):
        """Verifica None quando non trova città."""
        result = extract_city_from_query("meteo")
        assert result is None, f"Expected None for bare 'meteo', got '{result}'"


# ===================== WEATHER QUERY DETECTION TESTS =====================

class TestIsWeatherQuery:
    """Test per il riconoscimento di query meteo."""
    
    weather_queries = [
        "meteo roma",
        "meteo roma?",
        "che tempo fa a milano",
        "previsioni napoli",
        "weather london",
        "temperatura oggi",
        "pioggia domani",
        "neve a torino",
        "temporale in arrivo",
    ]
    
    non_weather_queries = [
        "ciao",
        "prezzo bitcoin",
        "risultato milan",
        "chi era napoleone",
        "calcola 2+2",
    ]
    
    @pytest.mark.skipif(not IMPORTS_OK, reason="Import failed")
    @pytest.mark.parametrize("query", weather_queries)
    def test_is_weather_query_true(self, query: str):
        """Verifica che query meteo siano riconosciute."""
        assert is_weather_query(query), f"Query '{query}' should be recognized as weather query"
    
    @pytest.mark.skipif(not IMPORTS_OK, reason="Import failed")
    @pytest.mark.parametrize("query", non_weather_queries)
    def test_is_weather_query_false(self, query: str):
        """Verifica che query non-meteo non siano riconosciute."""
        assert not is_weather_query(query), f"Query '{query}' should NOT be recognized as weather query"


# ===================== RUN TESTS =====================

if __name__ == "__main__":
    if not IMPORTS_OK:
        print("❌ Cannot run tests: imports failed")
        sys.exit(1)
    
    # Run with pytest
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
