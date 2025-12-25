#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
tests/integration/test_web_search_flow.py - Integration tests for web search flow.

Tests web search → synthesis → response flow.
"""

import os
import sys
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def sample_fixtures():
    """Load sample test fixtures."""
    fixtures_path = os.path.join(os.path.dirname(__file__), "../fixtures/sample_data.json")
    with open(fixtures_path) as f:
        return json.load(f)


@pytest.fixture
def mock_search_results(sample_fixtures):
    """Get mock search results from fixtures."""
    return sample_fixtures["web_search_results"]


@pytest.fixture
def mock_synthesis_response(sample_fixtures):
    """Get mock synthesis response from fixtures."""
    return sample_fixtures["llm_responses"]["synthesis"]


# ============================================================================
# WEB SEARCH REQUEST TESTS
# ============================================================================

class TestWebSearchFlow:
    """Integration tests for web search flow."""
    
    def test_web_search_request_creation(self):
        """Test creating a web search request."""
        from backend.models import WebSearchRequest, SourceEnum
        
        request = WebSearchRequest(
            q="Python 3.12 features",
            k=5,
            summarize_top=2,
            source=SourceEnum.API,
            source_id="test_user"
        )
        
        assert request.q == "Python 3.12 features"
        assert request.k == 5
        assert request.summarize_top == 2
    
    def test_web_search_request_defaults(self):
        """Test web search request default values."""
        from backend.models import WebSearchRequest
        
        request = WebSearchRequest(q="test query")
        
        assert request.k == 6
        assert request.summarize_top == 2
    
    @pytest.mark.asyncio
    async def test_search_to_synthesis_flow(self, mock_search_results, mock_synthesis_response):
        """Test complete search to synthesis flow."""
        from core.parallel_synthesis import parallel_synthesize_documents
        
        # Mock the LLM for synthesis by patching where it's imported
        with patch('core.chat_engine.reply_with_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_synthesis_response
            
            with patch('backend.synthesis_prompt_v2.build_aggressive_synthesis_prompt', return_value="prompt"):
                synthesis, stats = await parallel_synthesize_documents(
                    query="Python features",
                    documents=mock_search_results,
                    max_concurrent=2,
                    timeout=5.0,
                )
                
                assert isinstance(synthesis, str)
                assert "total_documents" in stats


# ============================================================================
# SEARCH RESULT PROCESSING TESTS
# ============================================================================

class TestSearchResultProcessing:
    """Tests for processing search results."""
    
    def test_search_result_structure(self, mock_search_results):
        """Test search result structure."""
        for result in mock_search_results:
            assert "idx" in result
            assert "title" in result
            assert "url" in result
            assert "text" in result
    
    def test_search_result_urls_valid(self, mock_search_results):
        """Test search result URLs are valid."""
        import re
        
        url_pattern = re.compile(r'^https?://')
        
        for result in mock_search_results:
            assert url_pattern.match(result["url"]), f"Invalid URL: {result['url']}"
    
    def test_search_result_text_not_empty(self, mock_search_results):
        """Test search results have text content."""
        for result in mock_search_results:
            assert len(result["text"]) > 0


# ============================================================================
# SYNTHESIS TESTS
# ============================================================================

class TestSynthesisFlow:
    """Tests for synthesis functionality."""
    
    @pytest.mark.asyncio
    async def test_synthesis_with_empty_documents(self):
        """Test synthesis with empty document list."""
        from core.parallel_synthesis import parallel_synthesize_documents
        
        synthesis, stats = await parallel_synthesize_documents(
            query="test",
            documents=[],
        )
        
        assert synthesis == ""
        assert stats["total_documents"] == 0
    
    @pytest.mark.asyncio
    async def test_synthesis_merging(self):
        """Test synthesis merging functionality."""
        from core.parallel_synthesis import _merge_syntheses
        
        syntheses = [
            "First point about Python",
            "Second point about features",
        ]
        
        merged = _merge_syntheses(syntheses)
        
        assert "First point" in merged
        assert "Second point" in merged
    
    def test_synthesis_config(self):
        """Test synthesis configuration."""
        from core.parallel_synthesis import get_parallel_synthesis_config
        
        config = get_parallel_synthesis_config()
        
        assert "enabled" in config
        assert "max_concurrent" in config
        assert "timeout" in config


# ============================================================================
# WEB SUMMARIZE TESTS
# ============================================================================

class TestWebSummarizeFlow:
    """Tests for web summarize functionality."""
    
    def test_web_summarize_request_with_url(self):
        """Test web summarize request with URL."""
        from backend.models import WebSummarizeRequest
        
        request = WebSummarizeRequest(
            url="https://example.com/article",
            return_sources=True
        )
        
        assert request.url == "https://example.com/article"
        assert request.q is None
    
    def test_web_summarize_request_with_query(self):
        """Test web summarize request with query."""
        from backend.models import WebSummarizeRequest
        
        request = WebSummarizeRequest(
            q="Python asyncio tutorial",
            return_sources=True
        )
        
        assert request.q == "Python asyncio tutorial"
        assert request.url is None


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

class TestWebSearchErrorHandling:
    """Tests for web search error handling."""
    
    def test_query_validation_error(self):
        """Test query validation error."""
        from backend.models import WebSearchRequest
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError):
            WebSearchRequest(q="")
    
    def test_k_out_of_range(self):
        """Test k parameter out of range."""
        from backend.models import WebSearchRequest
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError):
            WebSearchRequest(q="test", k=100)
    
    @pytest.mark.asyncio
    async def test_synthesis_timeout_handling(self):
        """Test synthesis handles timeout gracefully."""
        from core.parallel_synthesis import parallel_synthesize_documents
        
        documents = [
            {"idx": 1, "title": "Test", "url": "http://test.com", "text": "Content"}
        ]
        
        # Very short timeout should not crash
        synthesis, stats = await parallel_synthesize_documents(
            query="test",
            documents=documents,
            timeout=0.001,
            retry_attempts=0,
        )
        
        assert isinstance(stats, dict)


# ============================================================================
# CACHING TESTS
# ============================================================================

class TestWebSearchCaching:
    """Tests for web search caching."""
    
    def test_cache_key_generation(self):
        """Test cache key generation for search."""
        from core.cache_middleware import generate_cache_key
        
        key1 = generate_cache_key("web_search", q="Python", k=5)
        key2 = generate_cache_key("web_search", q="Python", k=5)
        key3 = generate_cache_key("web_search", q="JavaScript", k=5)
        
        assert key1 == key2
        assert key1 != key3
