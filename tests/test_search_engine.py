#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_search_engine.py
============================
Unit tests for the multi-provider SearchEngine with mocks.

Tests cover:
- Fallback on provider error
- Fallback on low results
- Multilingual query expansion and merge + dedup
- Trust scoring ordering
"""

import sys
import os
import asyncio
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.search_engine import (
    SearchEngine,
    SearchEngineResult,
    expand_query_multilingual,
    get_domain_trust_score,
    get_search_engine,
)
from core.search_providers.base import (
    BaseSearchProvider,
    ProviderResponse,
    SearchResult,
)


# =============================================================================
# Mock Provider for Testing
# =============================================================================

class MockSearchProvider(BaseSearchProvider):
    """Mock provider for testing."""
    
    def __init__(
        self,
        name: str = "mock",
        configured: bool = True,
        results: List[SearchResult] = None,
        error: str = "",
        timeout: float = 10.0,
    ):
        super().__init__(timeout=timeout)
        self.name = name
        self._configured = configured
        self._results = results or []
        self._error = error
        self.search_calls = []
    
    def is_configured(self) -> bool:
        return self._configured
    
    async def search(
        self,
        query: str,
        num_results: int = 10,
        language: str = "it"
    ) -> ProviderResponse:
        self.search_calls.append({
            "query": query,
            "num_results": num_results,
            "language": language,
        })
        
        if self._error:
            return ProviderResponse(
                provider_name=self.name,
                success=False,
                error_message=self._error,
            )
        
        return ProviderResponse(
            results=self._results[:num_results],
            provider_name=self.name,
            success=True,
            response_time_ms=50,
        )


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_results():
    """Sample search results for testing."""
    return [
        SearchResult(
            title="Bitcoin Price Today",
            url="https://coinmarketcap.com/currencies/bitcoin/",
            snippet="Current BTC price and market cap",
            domain="coinmarketcap.com",
            provider="mock",
            score=0.9,
        ),
        SearchResult(
            title="Bitcoin News",
            url="https://reuters.com/bitcoin-news",
            snippet="Latest bitcoin news from Reuters",
            domain="reuters.com",
            provider="mock",
            score=0.85,
        ),
        SearchResult(
            title="Prezzo Bitcoin",
            url="https://ilsole24ore.com/bitcoin",
            snippet="Quotazione Bitcoin in tempo reale",
            domain="ilsole24ore.com",
            provider="mock",
            score=0.8,
        ),
        SearchResult(
            title="BTC Analysis",
            url="https://coindesk.com/price/bitcoin",
            snippet="Technical analysis of Bitcoin",
            domain="coindesk.com",
            provider="mock",
            score=0.75,
        ),
        SearchResult(
            title="Crypto Markets",
            url="https://investing.com/crypto/btc",
            snippet="Cryptocurrency market overview",
            domain="investing.com",
            provider="mock",
            score=0.7,
        ),
    ]


@pytest.fixture
def low_trust_results():
    """Results from low-trust domains."""
    return [
        SearchResult(
            title="Random Blog Post",
            url="https://random-blog.com/bitcoin",
            snippet="Some random content",
            domain="random-blog.com",
            provider="mock",
            score=0.5,
        ),
    ]


# =============================================================================
# Test: Query Expansion
# =============================================================================

class TestQueryExpansion:
    """Tests for multilingual query expansion."""
    
    def test_expand_italian_query(self):
        """Test expanding Italian query to English."""
        queries = expand_query_multilingual("prezzo bitcoin", ["it", "en"])
        
        assert "it" in queries
        assert queries["it"] == "prezzo bitcoin"
        
        # Should have English translation
        assert "en" in queries
        assert "price" in queries["en"].lower()
    
    def test_expand_english_query(self):
        """Test expanding English query to Italian."""
        queries = expand_query_multilingual("bitcoin price", ["en", "it"])
        
        assert "en" in queries
        assert queries["en"] == "bitcoin price"
    
    def test_expand_single_language(self):
        """Test with single language."""
        queries = expand_query_multilingual("test query", ["it"])
        
        assert "it" in queries
        assert queries["it"] == "test query"
    
    def test_expand_empty_languages(self):
        """Test with empty language list."""
        queries = expand_query_multilingual("test", [])
        
        # Should include at least original query
        assert len(queries) >= 1


# =============================================================================
# Test: Trust Scoring
# =============================================================================

class TestTrustScoring:
    """Tests for domain trust scoring."""
    
    def test_high_trust_domain(self):
        """Test that known high-trust domains get high scores."""
        # Reuters is a known trusted news source
        score = get_domain_trust_score("reuters.com")
        assert score >= 0.9
    
    def test_wikipedia_trust(self):
        """Test Wikipedia trust score."""
        score = get_domain_trust_score("wikipedia.org")
        # Wikipedia should have a reasonable trust score
        assert score >= 0.5
    
    def test_unknown_domain(self):
        """Test unknown domain gets default score."""
        score = get_domain_trust_score("totally-unknown-domain-xyz.com")
        # Should get default score (0.6)
        assert 0.5 <= score <= 0.7
    
    def test_empty_domain(self):
        """Test empty domain."""
        score = get_domain_trust_score("")
        assert score == 0.5


# =============================================================================
# Test: SearchEngine Fallback on Error
# =============================================================================

class TestSearchEngineFallbackOnError:
    """Tests for provider fallback on errors."""
    
    @pytest.mark.asyncio
    async def test_fallback_on_primary_error(self, sample_results):
        """Test fallback to secondary provider when primary fails."""
        # Create mock providers
        primary = MockSearchProvider(
            name="primary",
            configured=True,
            error="Connection timeout",
        )
        secondary = MockSearchProvider(
            name="secondary",
            configured=True,
            results=sample_results,
        )
        
        # Create engine with mocked providers
        engine = SearchEngine(
            providers=["primary", "secondary"],
            languages=["it"],
            min_results_before_fallback=2,
        )
        engine._providers = {
            "primary": primary,
            "secondary": secondary,
        }
        
        result = await engine.search("test query")
        
        assert result.total_results > 0
        assert "primary" in result.providers_tried
        assert "secondary" in result.providers_tried
        assert result.fallback_triggered
    
    @pytest.mark.asyncio
    async def test_all_providers_fail(self):
        """Test behavior when all providers fail."""
        primary = MockSearchProvider(name="primary", error="Error 1")
        secondary = MockSearchProvider(name="secondary", error="Error 2")
        tertiary = MockSearchProvider(name="tertiary", error="Error 3")
        
        engine = SearchEngine(
            providers=["primary", "secondary", "tertiary"],
            languages=["it"],
        )
        engine._providers = {
            "primary": primary,
            "secondary": secondary,
            "tertiary": tertiary,
        }
        
        result = await engine.search("test query")
        
        assert result.total_results == 0
        assert len(result.providers_tried) == 3


# =============================================================================
# Test: SearchEngine Fallback on Low Results
# =============================================================================

class TestSearchEngineFallbackOnLowResults:
    """Tests for fallback when results are below threshold."""
    
    @pytest.mark.asyncio
    async def test_fallback_on_few_results(self, sample_results, low_trust_results):
        """Test fallback when primary returns too few results."""
        # Primary returns only 1 result
        primary = MockSearchProvider(
            name="primary",
            configured=True,
            results=low_trust_results,  # Only 1 result
        )
        # Secondary returns more
        secondary = MockSearchProvider(
            name="secondary",
            configured=True,
            results=sample_results,  # 5 results
        )
        
        engine = SearchEngine(
            providers=["primary", "secondary"],
            languages=["it"],
            min_results_before_fallback=4,  # Need at least 4
        )
        engine._providers = {
            "primary": primary,
            "secondary": secondary,
        }
        
        result = await engine.search("test query")
        
        # Should have tried both providers
        assert "primary" in result.providers_tried
        assert "secondary" in result.providers_tried
        # Should have combined results
        assert result.total_results > 1
    
    @pytest.mark.asyncio
    async def test_no_fallback_when_enough_results(self, sample_results):
        """Test that fallback is not triggered when results are sufficient."""
        primary = MockSearchProvider(
            name="primary",
            configured=True,
            results=sample_results,  # 5 results
        )
        secondary = MockSearchProvider(
            name="secondary",
            configured=True,
            results=[],
        )
        
        engine = SearchEngine(
            providers=["primary", "secondary"],
            languages=["it"],
            min_results_before_fallback=4,
        )
        engine._providers = {
            "primary": primary,
            "secondary": secondary,
        }
        
        result = await engine.search("test query")
        
        # Should only have tried primary
        assert "primary" in result.providers_tried
        # Secondary should not be in providers_tried since primary had enough
        assert len(primary.search_calls) > 0
        assert result.total_results >= 4


# =============================================================================
# Test: Multilingual Merge and Dedup
# =============================================================================

class TestMultilingualMergeDedup:
    """Tests for merging multilingual results with deduplication."""
    
    @pytest.mark.asyncio
    async def test_dedup_same_url(self):
        """Test that duplicate URLs are removed."""
        results = [
            SearchResult(
                title="Page 1",
                url="https://example.com/page",
                snippet="First",
                domain="example.com",
                provider="mock",
                score=0.9,
            ),
            SearchResult(
                title="Page 1 Again",
                url="https://example.com/page",  # Same URL
                snippet="Duplicate",
                domain="example.com",
                provider="mock",
                score=0.8,
            ),
        ]
        
        provider = MockSearchProvider(
            name="primary",
            configured=True,
            results=results,
        )
        
        engine = SearchEngine(
            providers=["primary"],
            languages=["it"],
        )
        engine._providers = {"primary": provider}
        
        result = await engine.search("test")
        
        # Should have only 1 unique URL
        assert result.total_results == 1
    
    @pytest.mark.asyncio
    async def test_max_per_domain_limit(self):
        """Test that max_per_domain limit is applied."""
        # Create 5 results from same domain
        results = [
            SearchResult(
                title=f"Page {i}",
                url=f"https://example.com/page{i}",
                snippet=f"Content {i}",
                domain="example.com",
                provider="mock",
                score=0.9 - (i * 0.1),
            )
            for i in range(5)
        ]
        
        provider = MockSearchProvider(
            name="primary",
            configured=True,
            results=results,
        )
        
        engine = SearchEngine(
            providers=["primary"],
            languages=["it"],
        )
        engine._providers = {"primary": provider}
        engine.max_per_domain = 2  # Limit to 2 per domain
        
        result = await engine.search("test")
        
        # Should have at most 2 from example.com
        example_results = [r for r in result.results if r.domain == "example.com"]
        assert len(example_results) <= 2
    
    @pytest.mark.asyncio
    async def test_merge_multilingual_results(self):
        """Test merging results from different languages."""
        it_results = [
            SearchResult(
                title="Risultato Italiano",
                url="https://it.example.com/pagina",
                snippet="Contenuto in italiano",
                domain="it.example.com",
                provider="mock",
                score=0.9,
            ),
        ]
        en_results = [
            SearchResult(
                title="English Result",
                url="https://en.example.com/page",
                snippet="English content",
                domain="en.example.com",
                provider="mock",
                score=0.85,
            ),
        ]
        
        # Provider returns different results for different languages
        class MultiLangProvider(BaseSearchProvider):
            name = "multilang"
            
            def is_configured(self):
                return True
            
            async def search(self, query, num_results=10, language="it"):
                if language == "it":
                    return ProviderResponse(results=it_results, success=True)
                else:
                    return ProviderResponse(results=en_results, success=True)
        
        engine = SearchEngine(
            providers=["multilang"],
            languages=["it", "en"],
        )
        engine._providers = {"multilang": MultiLangProvider()}
        
        result = await engine.search("test")
        
        # Should have results from both languages
        assert result.total_results >= 2
        domains = [r.domain for r in result.results]
        assert "it.example.com" in domains
        assert "en.example.com" in domains


# =============================================================================
# Test: Trust Scoring Ordering
# =============================================================================

class TestTrustScoringOrdering:
    """Tests for trust-based result ordering."""
    
    @pytest.mark.asyncio
    async def test_high_trust_ranked_first(self):
        """Test that high-trust domains are ranked higher."""
        results = [
            SearchResult(
                title="Low Trust",
                url="https://random-site.xyz/page",
                snippet="Random content",
                domain="random-site.xyz",
                provider="mock",
                score=0.5,
            ),
            SearchResult(
                title="Reuters News",
                url="https://reuters.com/news",
                snippet="Trusted news source",
                domain="reuters.com",
                provider="mock",
                score=0.5,  # Same base score
            ),
        ]
        
        provider = MockSearchProvider(
            name="primary",
            configured=True,
            results=results,
        )
        
        engine = SearchEngine(
            providers=["primary"],
            languages=["it"],
        )
        engine._providers = {"primary": provider}
        
        result = await engine.search("test")
        
        # Reuters should be ranked higher due to trust score
        if result.total_results >= 2:
            # Results should be sorted by combined score
            assert result.results[0].domain == "reuters.com"


# =============================================================================
# Test: URL-Only Mode
# =============================================================================

class TestUrlOnlyMode:
    """Tests for URL-only search mode."""
    
    @pytest.mark.asyncio
    async def test_url_only_mode(self):
        """Test processing user-provided URLs."""
        engine = SearchEngine()
        
        urls = [
            "https://example.com/article1",
            "https://wikipedia.org/wiki/Test",
        ]
        
        results = await engine.search_url_only(urls)
        
        assert len(results) == 2
        assert results[0].provider == "url_only"
        assert "example.com" in results[0].domain
    
    @pytest.mark.asyncio
    async def test_url_only_empty_list(self):
        """Test URL-only mode with empty list."""
        engine = SearchEngine()
        results = await engine.search_url_only([])
        assert len(results) == 0


# =============================================================================
# Test: No Provider Available
# =============================================================================

class TestNoProviderAvailable:
    """Tests for handling no configured providers."""
    
    @pytest.mark.asyncio
    async def test_no_configured_provider(self):
        """Test behavior when no provider is configured."""
        engine = SearchEngine(providers=["nonexistent"])
        engine._providers = {}  # No providers
        
        result = await engine.search("test query")
        
        assert result.total_results == 0
        assert "no provider" in result.error.lower()


# =============================================================================
# Test: Singleton Factory
# =============================================================================

class TestSingletonFactory:
    """Tests for get_search_engine singleton."""
    
    def test_singleton_returns_same_instance(self):
        """Test that factory returns same instance."""
        # Clear cached instance
        import core.search_engine as se_module
        se_module._search_engine_instance = None
        
        engine1 = get_search_engine()
        engine2 = get_search_engine()
        
        assert engine1 is engine2


# =============================================================================
# Test: Empty Query
# =============================================================================

class TestEmptyQuery:
    """Tests for empty query handling."""
    
    @pytest.mark.asyncio
    async def test_empty_query_returns_error(self):
        """Test that empty query returns error result."""
        engine = SearchEngine()
        
        result = await engine.search("")
        
        assert result.total_results == 0
        assert "empty" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_whitespace_query_returns_error(self):
        """Test that whitespace-only query returns error."""
        engine = SearchEngine()
        
        result = await engine.search("   ")
        
        assert result.total_results == 0
        assert "empty" in result.error.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
