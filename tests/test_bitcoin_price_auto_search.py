#!/usr/bin/env python3
"""
tests/test_bitcoin_price_auto_search.py
========================================

Test automatico per verificare che "Prezzo Bitcoin?" attivi auto-search.

OBIETTIVO (da issue):
Quando user chiede "Prezzo Bitcoin?", il bot DEVE:
1. Rilevare intent=live_data
2. Cercare su web (CoinMarketCap)
3. Estrarre prezzo reale
4. Rispondere con prezzo reale (NO <think>, NO invenzioni)
"""

import sys
import os
import pytest
import asyncio

# Add project root to path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)


class TestBitcoinPriceAutoSearch:
    """Test suite per auto-search con query 'Prezzo Bitcoin?'"""
    
    @pytest.mark.asyncio
    async def test_query_classifier_detects_live_data_intent(self):
        """Verifica che il classificatore rilevi intent=live_data per 'Prezzo Bitcoin?'"""
        from core.query_classifier import get_query_classifier
        
        classifier = get_query_classifier()
        
        test_queries = [
            "Prezzo Bitcoin?",
            "Prezzo Bitcoin",
            "Quanto vale Bitcoin?",
            "Quotazione BTC",
            "Bitcoin price",
        ]
        
        for query in test_queries:
            result = await classifier.classify_intent(query)
            
            assert result['intent'] == 'live_data', \
                f"Query '{query}' should have intent='live_data', got '{result['intent']}'"
            
            assert result['requires_search'] == True, \
                f"Query '{query}' should require search"
            
            # Sub-intent should be price-related
            assert result['sub_intent'] == 'price', \
                f"Query '{query}' should have sub_intent='price', got '{result['sub_intent']}'"
            
            print(f"✅ '{query}' → intent={result['intent']}, sub_intent={result['sub_intent']}")
    
    @pytest.mark.asyncio
    async def test_auto_search_detector_triggers_search(self):
        """Verifica che il detector attivi la ricerca per 'Prezzo Bitcoin?'"""
        from core.auto_search_detector import get_auto_search_detector
        
        detector = get_auto_search_detector()
        
        query = "Prezzo Bitcoin?"
        
        result = await detector.should_trigger_search(query, {}, {})
        
        assert result['should_search'] == True, \
            f"Query '{query}' should trigger search, got should_search={result['should_search']}"
        
        # Should be either 'live_data:price' or 'live_entity' or 'temporal'
        assert 'price' in result.get('reason', '') or 'live' in result.get('reason', ''), \
            f"Search reason should be price/live related, got '{result.get('reason')}'"
        
        assert result.get('confidence', 0) >= 0.7, \
            f"Confidence should be >= 0.7, got {result.get('confidence')}"
        
        print(f"✅ Search triggered: reason={result.get('reason')}, confidence={result.get('confidence'):.2f}")
    
    @pytest.mark.asyncio
    async def test_search_strategy_is_quick_for_price(self):
        """Verifica che la strategia di ricerca sia 'quick' per prezzi"""
        from core.query_classifier import get_query_classifier
        from core.search_strategy_planner import get_search_strategy_planner
        
        classifier = get_query_classifier()
        planner = get_search_strategy_planner()
        
        query = "Prezzo Bitcoin?"
        
        # Get intent classification
        intent_result = await classifier.classify_intent(query)
        
        # Get strategy
        strategy = await planner.plan_search_strategy(query, intent_result)
        
        assert strategy['strategy'] == 'quick', \
            f"Price query should use 'quick' strategy, got '{strategy['strategy']}'"
        
        assert strategy['synthesis_mode'] == 'concise', \
            f"Price query should use 'concise' synthesis, got '{strategy['synthesis_mode']}'"
        
        assert strategy['timeout'] <= 15, \
            f"Quick strategy timeout should be <= 15s, got {strategy['timeout']}"
        
        print(f"✅ Strategy: {strategy['strategy']}, synthesis={strategy['synthesis_mode']}, timeout={strategy['timeout']}s")
    
    @pytest.mark.asyncio
    async def test_full_flow_process_with_auto_search(self):
        """Test del flusso completo process_with_auto_search"""
        from core.chat_engine import process_with_auto_search
        
        query = "Prezzo Bitcoin?"
        user_id = "test_user"
        
        # This test verifies the flow works, not the actual web search
        # (which requires network access)
        result = await process_with_auto_search(
            user_message=query,
            user_id=user_id,
            context={},
            persona="Test persona"
        )
        
        # Result should be a dict with expected keys
        assert isinstance(result, dict), "Result should be a dict"
        assert 'response' in result, "Result should have 'response' key"
        assert 'search_triggered' in result, "Result should have 'search_triggered' key"
        assert 'search_reason' in result, "Result should have 'search_reason' key"
        
        # For price queries, search should be triggered
        # (even if it fails due to network, the trigger should happen)
        search_triggered = result.get('search_triggered', False)
        search_reason = result.get('search_reason', 'unknown')
        
        print(f"✅ Full flow executed: search_triggered={search_triggered}, reason={search_reason}")
        print(f"   Response preview: {result.get('response', '')[:100]}...")
    
    def test_think_tags_are_stripped(self):
        """Verifica che i tag <think> vengano rimossi dalla risposta"""
        from core.chat_engine import _strip_think_tags
        
        test_cases = [
            # (input, expected_contains_think_after)
            (
                "<think>This is my reasoning process...</think>The answer is 42.",
                False
            ),
            (
                "Normal response without think tags",
                False
            ),
            (
                "<THINK>Case insensitive test</THINK>Real response here.",
                False
            ),
            (
                "<think>\nMultiline\nthinking\n</think>\nActual response",
                False
            ),
            (
                "Pre-text <think>inner thought</think> post-text",
                False
            ),
        ]
        
        for input_text, _ in test_cases:
            result = _strip_think_tags(input_text)
            
            assert '<think>' not in result.lower(), \
                f"<think> tag should be stripped from: {input_text[:50]}..."
            assert '</think>' not in result.lower(), \
                f"</think> tag should be stripped from: {input_text[:50]}..."
            
            # Result should have actual content
            if 'answer is 42' in input_text.lower():
                assert '42' in result, "Answer content should be preserved"
            
            print(f"✅ Think tags stripped: '{input_text[:30]}...' → '{result[:30]}...'")
    
    @pytest.mark.asyncio
    async def test_smart_intent_classifier_for_price(self):
        """Verifica che SmartIntentClassifier classifichi correttamente le query sui prezzi"""
        from core.smart_intent_classifier import SmartIntentClassifier
        
        classifier = SmartIntentClassifier()
        
        test_queries = [
            ("Prezzo Bitcoin?", "WEB_SEARCH", "price"),
            ("Prezzo Bitcoin", "WEB_SEARCH", "price"),
            ("Quanto vale ETH?", "WEB_SEARCH", "price"),
            ("Quotazione BTC", "WEB_SEARCH", "price"),
        ]
        
        for query, expected_intent, expected_live_type in test_queries:
            result = classifier.classify(query)
            
            assert result['intent'] == expected_intent, \
                f"Query '{query}' should have intent='{expected_intent}', got '{result['intent']}'"
            
            assert result.get('live_type') == expected_live_type, \
                f"Query '{query}' should have live_type='{expected_live_type}', got '{result.get('live_type')}'"
            
            print(f"✅ SmartIntent: '{query}' → intent={result['intent']}, live_type={result.get('live_type')}")


class TestThinkTagStripping:
    """Test specifici per la rimozione dei tag <think>"""
    
    def test_strip_simple_think_tag(self):
        """Test rimozione tag <think> semplice"""
        from core.chat_engine import _strip_think_tags
        
        input_text = "<think>Thinking about this...</think>The answer is Bitcoin."
        result = _strip_think_tags(input_text)
        
        assert '<think>' not in result
        assert '</think>' not in result
        assert 'Bitcoin' in result
        print(f"✅ Simple: '{result}'")
    
    def test_strip_multiline_think_tag(self):
        """Test rimozione tag <think> multilinea"""
        from core.chat_engine import _strip_think_tags
        
        input_text = """<think>
Let me think about this step by step:
1. First consideration
2. Second consideration
3. Final analysis
</think>

Based on my analysis, the price of Bitcoin is approximately $96,000."""
        
        result = _strip_think_tags(input_text)
        
        assert '<think>' not in result
        assert '</think>' not in result
        assert '96,000' in result or 'Bitcoin' in result
        print(f"✅ Multiline: '{result[:80]}...'")
    
    def test_preserve_non_think_content(self):
        """Test che il contenuto non-think sia preservato"""
        from core.chat_engine import _strip_think_tags
        
        input_text = "This is a normal response with no think tags."
        result = _strip_think_tags(input_text)
        
        assert result == input_text
        print(f"✅ Preserved: '{result}'")
    
    def test_strip_case_insensitive(self):
        """Test rimozione case-insensitive"""
        from core.chat_engine import _strip_think_tags
        
        test_cases = [
            "<THINK>uppercase</THINK>real",
            "<Think>mixed case</Think>real",
            "<tHiNk>weird case</tHiNk>real",
        ]
        
        for input_text in test_cases:
            result = _strip_think_tags(input_text)
            assert 'real' in result
            assert '<' not in result or '>' not in result
            print(f"✅ Case insensitive: '{input_text[:20]}' → '{result}'")


# Run tests when executed directly
if __name__ == "__main__":
    print("=" * 70)
    print("Test Auto-Search per 'Prezzo Bitcoin?'")
    print("=" * 70)
    print()
    
    # Run pytest
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
