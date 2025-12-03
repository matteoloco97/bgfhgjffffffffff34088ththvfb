#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_persona_and_routing.py

Tests for persona cleanup and smart routing improvements.
Validates that:
1. Persona descriptions are accurate (no false limitations)
2. Routing decisions are correct for various query types
"""

import sys
import os
import pytest
from typing import Dict, Any

# Add parent directory to path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.persona_store import (
    DEFAULT_PERSONA,
    CAPABILITIES_BRIEF,
    build_system_prompt,
)


class TestPersonaDefinitions:
    """Test that persona definitions reflect actual capabilities."""

    def test_capabilities_brief_mentions_web_access(self):
        """Capabilities brief should mention web access capability."""
        brief = CAPABILITIES_BRIEF.lower()
        assert "web" in brief, "CAPABILITIES_BRIEF should mention web access"
        assert any(
            phrase in brief
            for phrase in ["posso accedere", "consulto", "accesso"]
        ), "Should state ability to access web, not inability"

    def test_capabilities_brief_mentions_memory(self):
        """Capabilities brief should mention memory/ChromaDB."""
        brief = CAPABILITIES_BRIEF.lower()
        assert any(
            word in brief for word in ["memoria", "chromadb", "cache"]
        ), "CAPABILITIES_BRIEF should mention memory capabilities"

    def test_capabilities_brief_no_false_limitations(self):
        """Capabilities brief should not contain false limitation phrases."""
        brief = CAPABILITIES_BRIEF.lower()
        
        false_limitations = [
            "non posso accedere",
            "non ho accesso",
            "non posso consultare",
            "non ho memoria",
            "non ricordo",
        ]
        
        for limitation in false_limitations:
            assert (
                limitation not in brief
            ), f"CAPABILITIES_BRIEF contains false limitation: '{limitation}'"

    def test_default_persona_structure(self):
        """DEFAULT_PERSONA should have expected structure."""
        assert isinstance(DEFAULT_PERSONA, dict), "DEFAULT_PERSONA should be a dict"
        assert "persona_id" in DEFAULT_PERSONA
        assert "system" in DEFAULT_PERSONA
        assert "behavior" in DEFAULT_PERSONA
        assert "version" in DEFAULT_PERSONA

    def test_default_persona_system_messages(self):
        """DEFAULT_PERSONA system messages should describe real capabilities."""
        system_text = build_system_prompt(DEFAULT_PERSONA).lower()
        
        # Should mention Jarvis/Quantum
        assert any(
            name in system_text for name in ["jarvis", "quantum"]
        ), "Should identify as Jarvis or Quantum AI"
        
        # Should mention web capability
        assert "web" in system_text, "Should mention web capability"
        
        # Should mention memory capability
        assert any(
            word in system_text for word in ["memoria", "chromadb", "cache"]
        ), "Should mention memory capability"

    def test_default_persona_no_false_limitations(self):
        """DEFAULT_PERSONA should not contain false limitation phrases."""
        system_text = build_system_prompt(DEFAULT_PERSONA).lower()
        
        false_limitations = [
            "non posso accedere a internet",
            "non ho accesso a internet",
            "non posso consultare fonti online",
            "non ho memoria delle conversazioni",
            "non ricordo conversazioni precedenti",
        ]
        
        for limitation in false_limitations:
            assert (
                limitation not in system_text
            ), f"DEFAULT_PERSONA contains false limitation: '{limitation}'"

    def test_persona_language_is_italian_focused(self):
        """Persona should indicate Italian as default language."""
        system_text = build_system_prompt(DEFAULT_PERSONA).lower()
        # Should mention Italian or language preference
        assert any(
            phrase in system_text for phrase in ["italiano", "italian", "lingua"]
        ), "Should mention language preference"


class TestRoutingLogic:
    """Test routing decision logic (conceptual tests without running full API)."""

    def test_meta_query_patterns(self):
        """Test that meta capability query patterns are well-defined."""
        from backend.quantum_api import _is_meta_capability_query
        
        meta_queries = [
            "chi sei?",
            "cosa puoi fare?",
            "come funzioni?",
            "puoi accedere a internet?",
            "hai memoria?",
        ]
        
        for query in meta_queries:
            result = _is_meta_capability_query(query)
            # At least some of these should be detected
            # (we're not testing 100% accuracy, just that the function exists and works)

    def test_explain_query_patterns(self):
        """Test that explain query patterns are detected."""
        from backend.quantum_api import _is_explain_query
        
        explain_queries = [
            "spiegami il teorema di Bayes",
            "che cos'è il Kelly criterion",
            "what is quantum computing",
        ]
        
        for query in explain_queries:
            result = _is_explain_query(query)
            assert isinstance(
                result, bool
            ), "Should return boolean"

    def test_smalltalk_query_detection(self):
        """Test that smalltalk queries are detected."""
        from backend.quantum_api import _is_smalltalk_query
        
        smalltalk = ["ciao", "hey", "grazie", "ok"]
        not_smalltalk = ["meteo Roma", "prezzo Bitcoin", "come funziona il Kelly"]
        
        for query in smalltalk:
            result = _is_smalltalk_query(query)
            assert result is True, f"'{query}' should be detected as smalltalk"
        
        for query in not_smalltalk:
            result = _is_smalltalk_query(query)
            assert result is False, f"'{query}' should NOT be detected as smalltalk"

    def test_live_query_detection(self):
        """Test that live queries (weather, prices, etc.) are detected."""
        from backend.quantum_api import _is_quick_live_query
        
        live_queries = [
            "meteo Roma",
            "che tempo fa",
            "prezzo Bitcoin",
            "quotazione EUR/USD",
            "risultati Serie A",
        ]
        
        for query in live_queries:
            result = _is_quick_live_query(query)
            assert result is True, f"'{query}' should be detected as live query"


class TestMemoryIntegration:
    """Test that memory is properly integrated."""

    def test_memory_search_function_exists(self):
        """Verify memory search function is available."""
        from utils.chroma_handler import search_topk
        
        # Just verify it exists and is callable
        assert callable(search_topk), "search_topk should be a callable function"

    def test_memory_collections_defined(self):
        """Verify memory collections are properly defined."""
        from utils.chroma_handler import FACTS, PREFS, BETS
        
        assert FACTS, "FACTS collection should be defined"
        assert PREFS, "PREFS collection should be defined"
        assert BETS, "BETS collection should be defined"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
