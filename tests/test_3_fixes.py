#!/usr/bin/env python3
"""
tests/test_3_fixes.py
=====================

Test suite for the 3 QuantumDev fixes:
1. Autoweb parsing with punctuation
2. Concise web response formatter
3. Conversational web context
"""

import sys
import os
import pytest
from typing import Dict, Any

# Add project root to path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

# ===================== PROBLEMA 1: Autoweb Parsing Tests =====================

class TestAutowebPunctuationFix:
    """Test that punctuation doesn't interfere with pattern matching."""
    
    def test_clean_query_for_matching(self):
        """Test the _clean_query_for_matching method."""
        from core.smart_intent_classifier import SmartIntentClassifier
        
        # Test punctuation removal
        assert SmartIntentClassifier._clean_query_for_matching("Meteo Roma?") == "Meteo Roma"
        assert SmartIntentClassifier._clean_query_for_matching("Prezzo Bitcoin!") == "Prezzo Bitcoin"
        assert SmartIntentClassifier._clean_query_for_matching("Chi è Einstein?!") == "Chi è Einstein"
        assert SmartIntentClassifier._clean_query_for_matching("Risultato Milan.") == "Risultato Milan"
        
        # Test multiple punctuation
        assert SmartIntentClassifier._clean_query_for_matching("Meteo Roma???") == "Meteo Roma"
        assert SmartIntentClassifier._clean_query_for_matching("Bitcoin!!!") == "Bitcoin"
        
        # Test whitespace normalization
        assert SmartIntentClassifier._clean_query_for_matching("Meteo   Roma") == "Meteo Roma"
        assert SmartIntentClassifier._clean_query_for_matching("  Prezzo  Bitcoin  ") == "Prezzo Bitcoin"
    
    def test_classify_with_punctuation(self):
        """Test that classification works correctly with punctuation."""
        from core.smart_intent_classifier import SmartIntentClassifier
        
        classifier = SmartIntentClassifier()
        
        # Weather queries with punctuation
        result1 = classifier.classify("Meteo Roma?")
        assert result1["intent"] == "WEB_SEARCH"
        assert result1.get("live_type") == "weather"
        
        result2 = classifier.classify("Che tempo fa a Milano?!")
        assert result2["intent"] == "WEB_SEARCH"
        assert result2.get("live_type") == "weather"
        
        # Price queries with punctuation
        result3 = classifier.classify("Prezzo Bitcoin!")
        assert result3["intent"] == "WEB_SEARCH"
        assert result3.get("live_type") == "price"
        
        result4 = classifier.classify("Quanto vale Ethereum?")
        assert result4["intent"] == "WEB_SEARCH"
        
        # Sports queries with punctuation
        result5 = classifier.classify("Risultato Milan?")
        assert result5["intent"] == "WEB_SEARCH"
        assert result5.get("live_type") == "sports"
    
    def test_single_word_with_punctuation(self):
        """Test single-word queries with punctuation."""
        from core.smart_intent_classifier import SmartIntentClassifier
        
        classifier = SmartIntentClassifier()
        
        # Single word with punctuation should still be detected as single word
        result = classifier.classify("Roma?")
        assert result["intent"] == "WEB_SEARCH"
        assert result["reason"] == "single_token_general_knowledge"


# ===================== PROBLEMA 2: Concise Formatter Tests =====================

class TestConciseWebResponseFormatter:
    """Test the ultra-concise web response formatter."""
    
    def test_remove_verbose_phrases(self):
        """Test that verbose phrases are removed."""
        from core.web_response_formatter import _remove_verbose_phrases
        
        # Test Italian verbose phrases
        text1 = "Basandomi sulle fonti, Bitcoin vale $45000."
        cleaned1 = _remove_verbose_phrases(text1)
        assert "basandomi sulle fonti" not in cleaned1.lower()
        assert "Bitcoin vale $45000" in cleaned1
        
        text2 = "Secondo le fonti, il meteo a Roma sarà soleggiato."
        cleaned2 = _remove_verbose_phrases(text2)
        assert "secondo le fonti" not in cleaned2.lower()
        assert "meteo a Roma sarà soleggiato" in cleaned2
        
        # Test English verbose phrases
        text3 = "Based on the sources, Bitcoin is at $45000."
        cleaned3 = _remove_verbose_phrases(text3)
        assert "based on the sources" not in cleaned3.lower()
        assert "Bitcoin is at $45000" in cleaned3
    
    def test_enforce_token_limit(self):
        """Test that token limit is enforced."""
        from core.web_response_formatter import _enforce_token_limit
        
        # Short text should be unchanged
        short_text = "Bitcoin vale $45000 oggi."
        result = _enforce_token_limit(short_text, max_tokens=120)
        assert result == short_text
        
        # Long text should be truncated
        long_text = " ".join(["word"] * 200)  # 200 words
        result = _enforce_token_limit(long_text, max_tokens=50)
        assert len(result) < len(long_text)
        # Token limit is approximate (4 chars per token), allow some margin
        # Result should be ~200 chars (50 tokens * 4) but may include ellipsis and sentence boundary
        assert len(result) <= 50 * 4 + 20  # Allow 20 char margin for sentence boundary
    
    def test_count_words(self):
        """Test word counting."""
        from core.web_response_formatter import _count_words
        
        assert _count_words("Bitcoin vale $45000") == 3
        assert _count_words("") == 0
        assert _count_words("Single") == 1
        assert _count_words("One two three four five") == 5
    
    def test_build_concise_prompt(self):
        """Test that concise prompt is built correctly."""
        from core.web_response_formatter import _build_concise_prompt
        
        query = "Prezzo Bitcoin"
        extracts = [
            {
                "url": "https://example.com",
                "title": "Bitcoin Price",
                "text": "Bitcoin is currently trading at $45000..."
            }
        ]
        
        prompt = _build_concise_prompt(query, extracts)
        
        # Check that prompt is concise
        assert "MAX 2-3 FRASI" in prompt or "MAX 50 PAROLE" in prompt
        assert "zero preamble" in prompt.lower() or "dritto al punto" in prompt.lower()
        assert query in prompt
        assert "Bitcoin Price" in prompt


# ===================== PROBLEMA 3: Conversational Context Tests =====================

class TestConversationalWebContext:
    """Test conversational web context manager."""
    
    def test_is_follow_up_detection(self):
        """Test follow-up query detection."""
        from core.conversational_web_context import ConversationalWebManager
        
        manager = ConversationalWebManager()
        
        # Conjunction patterns should be detected
        assert manager._is_follow_up("E domani?") == True
        assert manager._is_follow_up("e invece a Milano?") == True
        assert manager._is_follow_up("ma per Roma?") == True
        
        # Single words should be detected as potential follow-ups
        assert manager._is_follow_up("domani") == True
        assert manager._is_follow_up("Milano") == True
        
        # New queries should NOT be detected as follow-ups
        assert manager._is_follow_up("Chi è Einstein?") == False
        assert manager._is_follow_up("Che cos'è Bitcoin") == False
        assert manager._is_follow_up("Meteo Roma oggi") == False
    
    def test_extract_entities(self):
        """Test entity extraction."""
        from core.conversational_web_context import ConversationalWebManager
        
        manager = ConversationalWebManager()
        
        # Test capitalized words
        entities1 = manager._extract_entities("Meteo Roma")
        assert "Roma" in entities1
        
        entities2 = manager._extract_entities("Prezzo Bitcoin oggi")
        assert "bitcoin" in {e.lower() for e in entities2} or "Bitcoin" in entities2
        
        # Test multiple entities
        entities3 = manager._extract_entities("Volo da Roma a Milano")
        assert "Roma" in entities3
        assert "Milano" in entities3
    
    def test_detect_domain(self):
        """Test domain detection."""
        from core.conversational_web_context import ConversationalWebManager
        
        manager = ConversationalWebManager()
        
        assert manager._detect_domain("Meteo Roma") == "weather"
        assert manager._detect_domain("Prezzo Bitcoin") == "price"
        assert manager._detect_domain("Risultato Milan") == "sports"
        assert manager._detect_domain("Ultime notizie") == "news"
    
    def test_resolve_query_simple(self):
        """Test simple query resolution."""
        from core.conversational_web_context import ConversationalWebManager
        
        manager = ConversationalWebManager()
        
        # First query (no context)
        resolved1 = manager.resolve_query("Meteo Roma", session_id="test1")
        assert resolved1 == "Meteo Roma"  # Unchanged
        
        # Update context
        manager.update_context(
            query="Meteo Roma",
            entities={"Roma"},
            domain="weather",
            session_id="test1"
        )
        
        # Follow-up query
        resolved2 = manager.resolve_query("E domani?", session_id="test1")
        assert "Roma" in resolved2
        assert "domani" in resolved2.lower()
        assert "meteo" in resolved2.lower()
    
    def test_resolve_query_with_entity_change(self):
        """Test query resolution with entity change."""
        from core.conversational_web_context import ConversationalWebManager
        
        manager = ConversationalWebManager()
        
        # First query
        manager.update_context(
            query="Meteo Roma",
            entities={"Roma"},
            domain="weather",
            session_id="test2"
        )
        
        # Follow-up with new entity (single word)
        resolved = manager.resolve_query("Milano", session_id="test2")
        assert "Milano" in resolved
        assert "meteo" in resolved.lower()  # Inherits domain
    
    def test_session_isolation(self):
        """Test that different sessions are isolated."""
        from core.conversational_web_context import ConversationalWebManager
        
        manager = ConversationalWebManager()
        
        # Update context for session 1
        manager.update_context(
            query="Meteo Roma",
            entities={"Roma"},
            domain="weather",
            session_id="session1"
        )
        
        # Update context for session 2
        manager.update_context(
            query="Prezzo Bitcoin",
            entities={"Bitcoin"},
            domain="price",
            session_id="session2"
        )
        
        # Resolve in session 1 should use Roma context
        resolved1 = manager.resolve_query("E domani?", session_id="session1")
        assert "Roma" in resolved1
        assert "meteo" in resolved1.lower()
        
        # Resolve in session 2 should use Bitcoin context
        resolved2 = manager.resolve_query("E domani?", session_id="session2")
        assert "Bitcoin" in resolved2 or "bitcoin" in resolved2.lower()
    
    def test_context_expiry(self):
        """Test that context expires after TTL."""
        from core.conversational_web_context import ConversationalWebManager
        import time
        
        manager = ConversationalWebManager(context_ttl=1.0)  # 1 second TTL
        
        # Update context
        manager.update_context(
            query="Meteo Roma",
            entities={"Roma"},
            domain="weather",
            session_id="test_expiry"
        )
        
        # Immediate query should work
        resolved1 = manager.resolve_query("E domani?", session_id="test_expiry")
        assert "Roma" in resolved1
        
        # Wait for expiry
        time.sleep(1.5)
        
        # After expiry, should return original query
        resolved2 = manager.resolve_query("E domani?", session_id="test_expiry")
        assert resolved2 == "E domani?"  # Unchanged
    
    def test_clear_context(self):
        """Test clearing context."""
        from core.conversational_web_context import ConversationalWebManager
        
        manager = ConversationalWebManager()
        
        # Update context
        manager.update_context(
            query="Meteo Roma",
            entities={"Roma"},
            domain="weather",
            session_id="test_clear"
        )
        
        # Clear context
        manager.clear_context(session_id="test_clear")
        
        # Query after clearing should be unchanged
        resolved = manager.resolve_query("E domani?", session_id="test_clear")
        assert resolved == "E domani?"
    
    def test_get_stats(self):
        """Test getting manager stats."""
        from core.conversational_web_context import ConversationalWebManager
        
        manager = ConversationalWebManager()
        
        # Add some contexts
        manager.update_context("Query 1", session_id="s1")
        manager.update_context("Query 2", session_id="s2")
        
        stats = manager.get_stats()
        
        assert "total_sessions" in stats
        assert "active_contexts" in stats
        assert stats["total_sessions"] >= 2
        assert stats["active_contexts"] >= 2
    
    def test_singleton(self):
        """Test that get_web_context_manager returns singleton."""
        from core.conversational_web_context import get_web_context_manager
        
        manager1 = get_web_context_manager()
        manager2 = get_web_context_manager()
        
        assert manager1 is manager2  # Same instance


# ===================== Integration Tests =====================

class TestIntegration:
    """Integration tests combining multiple fixes."""
    
    def test_autoweb_with_context(self):
        """Test that autoweb parsing works with conversational context."""
        from core.smart_intent_classifier import SmartIntentClassifier
        from core.conversational_web_context import ConversationalWebManager
        
        classifier = SmartIntentClassifier()
        manager = ConversationalWebManager()
        
        # First query with punctuation
        query1 = "Meteo Roma?"
        result1 = classifier.classify(query1)
        assert result1["intent"] == "WEB_SEARCH"
        
        # Update context
        manager.update_context(query1, session_id="integration")
        
        # Follow-up with punctuation
        query2 = "E domani?"
        resolved = manager.resolve_query(query2, session_id="integration")
        assert "Roma" in resolved
        
        # Classify resolved query
        result2 = classifier.classify(resolved)
        assert result2["intent"] == "WEB_SEARCH"


# ===================== Run Tests =====================

if __name__ == "__main__":
    # Run with pytest
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
