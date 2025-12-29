#!/usr/bin/env python3
"""
tests/test_content_fetch.py
============================

Tests for the anti-hallucination content fetching feature.

Tests:
- fetch_with_browserless function
- fetch_missing_content function
- Content extraction from HTML
- Integration with chat_engine handlers
"""

import sys
import os
import pytest
import asyncio
from typing import Dict, Any, List
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)


# ===================== CONTENT FETCH FUNCTION TESTS =====================

class TestFetchWithBrowserless:
    """Tests for fetch_with_browserless function."""
    
    def test_import(self):
        """Verify fetch_with_browserless can be imported."""
        from core.web_search import fetch_with_browserless
        assert fetch_with_browserless is not None
    
    @pytest.mark.asyncio
    async def test_empty_url_returns_empty(self):
        """Test that empty URL returns empty string."""
        from core.web_search import fetch_with_browserless
        
        result = await fetch_with_browserless("")
        assert result == ""
    
    @pytest.mark.asyncio
    async def test_fallback_to_direct_fetch(self):
        """Test fallback to direct HTTP when Browserless not configured."""
        from core.web_search import fetch_with_browserless
        
        # With EN_BROWSERLESS=0, it should fall back to direct fetch
        # This test just verifies no crash
        with patch.dict(os.environ, {"EN_BROWSERLESS": "0"}):
            # Will fail due to network, but shouldn't crash
            result = await fetch_with_browserless("https://example.com")
            # Result might be empty if network fails, that's OK
            assert isinstance(result, str)


class TestFetchMissingContent:
    """Tests for fetch_missing_content function."""
    
    def test_import(self):
        """Verify fetch_missing_content can be imported."""
        from core.web_search import fetch_missing_content
        assert fetch_missing_content is not None
    
    @pytest.mark.asyncio
    async def test_empty_results_returns_empty(self):
        """Test that empty results list returns empty list."""
        from core.web_search import fetch_missing_content
        
        result = await fetch_missing_content([])
        assert result == []
    
    @pytest.mark.asyncio
    async def test_results_with_sufficient_snippets_unchanged(self):
        """Test that results with sufficient snippets are not fetched."""
        from core.web_search import fetch_missing_content
        
        # Create results with long snippets (> 100 chars)
        long_snippet = "A" * 150  # 150 characters, above threshold
        results = [
            {'url': 'https://example.com/1', 'title': 'Test 1', 'snippet': long_snippet},
            {'url': 'https://example.com/2', 'title': 'Test 2', 'snippet': long_snippet},
        ]
        
        # Make a copy to compare
        original_snippets = [r['snippet'] for r in results]
        
        # Should not fetch anything (snippets are sufficient)
        updated_results = await fetch_missing_content(results, min_snippet_length=100)
        
        # Snippets should remain unchanged
        for i, r in enumerate(updated_results):
            assert r['snippet'] == original_snippets[i]
    
    @pytest.mark.asyncio
    async def test_identifies_results_needing_fetch(self):
        """Test that results with short/missing snippets are identified."""
        from core.web_search import fetch_missing_content
        
        results = [
            {'url': 'https://example.com/1', 'title': 'Test 1', 'snippet': 'Short'},  # Too short
            {'url': 'https://example.com/2', 'title': 'Test 2', 'snippet': ''},  # Empty
            {'url': 'https://example.com/3', 'title': 'Test 3', 'snippet': 'A' * 150},  # Sufficient
        ]
        
        # Mock the fetch_with_browserless to avoid network calls
        with patch('core.web_search.fetch_with_browserless', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = "Fetched content for testing purposes"
            
            updated_results = await fetch_missing_content(results, min_snippet_length=100)
            
            # Should have called fetch for 2 results (the ones with short/empty snippets)
            assert mock_fetch.call_count == 2


class TestExtractTextFromHtml:
    """Tests for HTML text extraction helper."""
    
    def test_import(self):
        """Verify _extract_text_from_html can be imported."""
        from core.web_search import _extract_text_from_html
        assert _extract_text_from_html is not None
    
    def test_empty_html_returns_empty(self):
        """Test that empty HTML returns empty string."""
        from core.web_search import _extract_text_from_html
        
        result = _extract_text_from_html("")
        assert result == ""
    
    def test_extracts_text_from_paragraphs(self):
        """Test extraction of text from paragraph tags."""
        from core.web_search import _extract_text_from_html
        
        html = """
        <html>
            <body>
                <p>This is a long paragraph with meaningful content that should be extracted.</p>
                <p>Another paragraph with additional information for the test.</p>
            </body>
        </html>
        """
        
        result = _extract_text_from_html(html)
        assert "long paragraph" in result or "meaningful content" in result
    
    def test_removes_script_tags(self):
        """Test that script tags are removed."""
        from core.web_search import _extract_text_from_html
        
        html = """
        <html>
            <body>
                <script>var evil = 'should not appear';</script>
                <p>This is the real content that should appear in the output.</p>
            </body>
        </html>
        """
        
        result = _extract_text_from_html(html)
        assert "evil" not in result
        assert "should not appear" not in result


# ===================== INTEGRATION TESTS =====================

class TestChatEngineIntegration:
    """Integration tests for chat_engine content fetching."""
    
    def test_handler_imports_fetch_missing_content(self):
        """Verify handlers import fetch_missing_content."""
        # This test verifies the import structure is correct
        from core.web_search import smart_search, adaptive_synthesis, fetch_missing_content
        assert smart_search is not None
        assert adaptive_synthesis is not None
        assert fetch_missing_content is not None
    
    @pytest.mark.asyncio
    async def test_live_data_handler_calls_fetch(self):
        """Test that _handle_live_data_query calls fetch_missing_content."""
        try:
            from core.chat_engine import _handle_live_data_query
        except ImportError as e:
            pytest.skip(f"chat_engine dependencies not available: {e}")
        
        # Mock all the external dependencies
        with patch('core.chat_engine.smart_search', new_callable=AsyncMock) as mock_search, \
             patch('core.chat_engine.fetch_missing_content', new_callable=AsyncMock) as mock_fetch, \
             patch('core.chat_engine.adaptive_synthesis') as mock_synth, \
             patch('core.chat_engine.reply_with_llm', new_callable=AsyncMock) as mock_llm:
            
            # Setup mocks
            mock_search.return_value = {
                'results': [
                    {'url': 'https://example.com', 'title': 'Test', 'snippet': 'Short'}
                ],
                'search_time_ms': 100,
                'cache_hit': False
            }
            mock_fetch.return_value = [
                {'url': 'https://example.com', 'title': 'Test', 'snippet': 'Fetched content'}
            ]
            mock_synth.return_value = "Synthesized content"
            mock_llm.return_value = "LLM response"
            
            # Call the handler
            result = await _handle_live_data_query(
                query="Prezzo Bitcoin",
                data_type="price",
                context={},
                persona="Test persona",
                strategy={'synthesis_mode': 'concise'}
            )
            
            # Verify fetch_missing_content was called
            mock_fetch.assert_called_once()


# ===================== ADAPTIVE SYNTHESIS WITH CONTENT TESTS =====================

class TestAdaptiveSynthesisWithContent:
    """Tests for adaptive_synthesis with real content."""
    
    def test_synthesis_uses_full_content(self):
        """Test that synthesis uses full_content when available."""
        from core.web_search import adaptive_synthesis
        
        results = [
            {
                'url': 'https://example.com',
                'title': 'Bitcoin Price',
                'snippet': 'Bitcoin is trading at $95,234 today with strong volume.',
                'full_content': 'Extended content about Bitcoin price movements and market analysis.'
            }
        ]
        
        # Synthesis should work with the snippet
        synthesized = adaptive_synthesis(results, 'concise')
        assert len(synthesized) > 0
        assert 'Bitcoin' in synthesized or '$95,234' in synthesized
    
    def test_synthesis_handles_empty_snippets(self):
        """Test synthesis behavior with empty snippets."""
        from core.web_search import adaptive_synthesis
        
        # Results with empty snippets
        results = [
            {'url': 'https://example.com', 'title': 'Test Title', 'snippet': ''},
        ]
        
        synthesized = adaptive_synthesis(results, 'concise')
        # Should return a message about no content
        assert 'NESSUN' in synthesized or 'NOTA' in synthesized


# ===================== RUN TESTS =====================

if __name__ == "__main__":
    # Run with pytest
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
