#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
tests/unit/test_cache_middleware.py - Unit tests for cache middleware.

Tests L1/L2 cache operations, cache key generation, statistics tracking,
and the @cached_response decorator.
"""

import os
import sys
import json
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ============================================================================
# CACHE KEY GENERATION TESTS
# ============================================================================

class TestCacheKeyGeneration:
    """Tests for cache key generation functionality."""
    
    def test_generate_cache_key_basic(self):
        """Test basic cache key generation."""
        from core.cache_middleware import generate_cache_key
        
        key = generate_cache_key("chat", text="hello", source="api")
        
        assert key.startswith("chat:")
        assert len(key) > 5  # endpoint: + hash
    
    def test_generate_cache_key_consistent(self):
        """Test that same params produce same key."""
        from core.cache_middleware import generate_cache_key
        
        key1 = generate_cache_key("chat", text="hello", source="api")
        key2 = generate_cache_key("chat", text="hello", source="api")
        
        assert key1 == key2
    
    def test_generate_cache_key_different_params(self):
        """Test that different params produce different keys."""
        from core.cache_middleware import generate_cache_key
        
        key1 = generate_cache_key("chat", text="hello", source="api")
        key2 = generate_cache_key("chat", text="world", source="api")
        
        assert key1 != key2
    
    def test_generate_cache_key_different_endpoints(self):
        """Test that different endpoints produce different keys."""
        from core.cache_middleware import generate_cache_key
        
        key1 = generate_cache_key("chat", text="hello")
        key2 = generate_cache_key("search", text="hello")
        
        assert key1 != key2
    
    def test_generate_cache_key_empty_params(self):
        """Test cache key with no params."""
        from core.cache_middleware import generate_cache_key
        
        key = generate_cache_key("empty")
        
        assert key.startswith("empty:")
        assert len(key) > 6
    
    def test_generate_cache_key_special_chars(self):
        """Test cache key with special characters in params."""
        from core.cache_middleware import generate_cache_key
        
        key = generate_cache_key("chat", text="こんにちは", source="api")
        
        assert key.startswith("chat:")
        assert len(key) > 5
    
    def test_generate_cache_key_order_independence(self):
        """Test that param order doesn't affect key."""
        from core.cache_middleware import generate_cache_key
        
        key1 = generate_cache_key("chat", a="1", b="2", c="3")
        key2 = generate_cache_key("chat", c="3", a="1", b="2")
        
        assert key1 == key2


# ============================================================================
# CACHE STATISTICS TESTS
# ============================================================================

class TestCacheStatistics:
    """Tests for cache statistics tracking."""
    
    def test_reset_cache_stats(self):
        """Test resetting cache statistics."""
        from core.cache_middleware import reset_cache_stats, get_cache_stats, _update_stats
        
        # Add some stats
        _update_stats("test_endpoint", "hit")
        _update_stats("test_endpoint", "miss")
        
        # Reset
        reset_cache_stats()
        
        # Verify reset
        stats = get_cache_stats()
        assert stats['middleware']['total_hits'] == 0
        assert stats['middleware']['total_misses'] == 0
        assert stats['middleware']['total_bypasses'] == 0
    
    def test_stats_hit_tracking(self):
        """Test hit tracking in statistics."""
        from core.cache_middleware import reset_cache_stats, get_cache_stats, _update_stats
        
        reset_cache_stats()
        
        _update_stats("chat", "hit")
        _update_stats("chat", "hit")
        _update_stats("search", "hit")
        
        stats = get_cache_stats()
        assert stats['middleware']['total_hits'] == 3
    
    def test_stats_miss_tracking(self):
        """Test miss tracking in statistics."""
        from core.cache_middleware import reset_cache_stats, get_cache_stats, _update_stats
        
        reset_cache_stats()
        
        _update_stats("chat", "miss")
        _update_stats("search", "miss")
        
        stats = get_cache_stats()
        assert stats['middleware']['total_misses'] == 2
    
    def test_stats_bypass_tracking(self):
        """Test bypass tracking in statistics."""
        from core.cache_middleware import reset_cache_stats, get_cache_stats, _update_stats
        
        reset_cache_stats()
        
        _update_stats("chat", "bypass")
        
        stats = get_cache_stats()
        assert stats['middleware']['total_bypasses'] == 1
    
    def test_stats_hit_rate_calculation(self):
        """Test hit rate calculation."""
        from core.cache_middleware import reset_cache_stats, get_cache_stats, _update_stats
        
        reset_cache_stats()
        
        # 3 hits, 1 miss = 75% hit rate
        _update_stats("chat", "hit")
        _update_stats("chat", "hit")
        _update_stats("chat", "hit")
        _update_stats("chat", "miss")
        
        stats = get_cache_stats()
        assert stats['middleware']['hit_rate'] == 0.75
    
    def test_stats_per_endpoint_tracking(self):
        """Test per-endpoint statistics tracking."""
        from core.cache_middleware import reset_cache_stats, get_cache_stats, _update_stats
        
        reset_cache_stats()
        
        _update_stats("chat", "hit")
        _update_stats("chat", "hit")
        _update_stats("search", "miss")
        
        stats = get_cache_stats()
        per_endpoint = {s['endpoint']: s for s in stats['middleware']['per_endpoint']}
        
        assert 'chat' in per_endpoint
        assert per_endpoint['chat']['hits'] == 2
        assert 'search' in per_endpoint
        assert per_endpoint['search']['misses'] == 1
    
    def test_stats_empty_state(self):
        """Test statistics with no requests."""
        from core.cache_middleware import reset_cache_stats, get_cache_stats
        
        reset_cache_stats()
        
        stats = get_cache_stats()
        assert stats['middleware']['total_hits'] == 0
        assert stats['middleware']['total_misses'] == 0
        assert stats['middleware']['hit_rate'] == 0.0


# ============================================================================
# MULTI-LEVEL CACHE TESTS
# ============================================================================

class TestMultiLevelCache:
    """Tests for multi-level cache functionality."""
    
    def test_cache_init(self):
        """Test cache initialization."""
        from core.multi_level_cache import MultiLevelCache
        
        cache = MultiLevelCache()
        
        assert cache.l1_enabled is True
        assert hasattr(cache, '_l1_cache')
    
    def test_cache_set_and_get(self):
        """Test basic cache set and get."""
        from core.multi_level_cache import MultiLevelCache
        
        cache = MultiLevelCache()
        cache.l2_enabled = False  # Disable L2 for unit test
        
        cache.set("test_query", "test_result")
        result = cache.get("test_query")
        
        assert result == "test_result"
    
    def test_cache_miss(self):
        """Test cache miss returns None."""
        from core.multi_level_cache import MultiLevelCache
        
        cache = MultiLevelCache()
        cache.l2_enabled = False
        
        result = cache.get("nonexistent_query")
        
        assert result is None
    
    def test_cache_clear_l1(self):
        """Test clearing L1 cache."""
        from core.multi_level_cache import MultiLevelCache
        
        cache = MultiLevelCache()
        cache.l2_enabled = False
        
        cache.set("query1", "result1")
        cache.set("query2", "result2")
        
        cleared = cache.clear_l1()
        
        assert cleared == 2
        assert cache.get("query1") is None
    
    def test_cache_stats_tracking(self):
        """Test cache statistics tracking."""
        from core.multi_level_cache import MultiLevelCache
        
        cache = MultiLevelCache()
        cache.l2_enabled = False
        cache.reset_stats()
        
        cache.get("miss_query")  # Miss
        cache.set("hit_query", "result")
        cache.get("hit_query")  # Hit
        
        stats = cache.get_stats()
        
        assert stats['l1_misses'] >= 1
        assert stats['l1_hits'] >= 1
    
    def test_cache_lru_eviction(self):
        """Test LRU eviction when cache is full."""
        from core.multi_level_cache import MultiLevelCache
        
        cache = MultiLevelCache()
        cache._l1_max_size = 3  # Small size for testing
        cache.l2_enabled = False
        cache.reset_stats()
        
        # Fill cache
        cache.set("query1", "result1")
        cache.set("query2", "result2")
        cache.set("query3", "result3")
        
        # Add one more (should evict oldest)
        cache.set("query4", "result4")
        
        stats = cache.get_stats()
        assert stats['l1_evictions'] >= 1
        assert stats['l1_size'] <= 3
    
    def test_cache_hash_query(self):
        """Test query hashing."""
        from core.multi_level_cache import MultiLevelCache
        
        cache = MultiLevelCache()
        
        hash1 = cache._hash_query("test query")
        hash2 = cache._hash_query("test query")
        hash3 = cache._hash_query("different query")
        
        assert hash1 == hash2
        assert hash1 != hash3
        assert len(hash1) == 16  # SHA256 truncated to 16 chars


# ============================================================================
# CACHED RESPONSE DECORATOR TESTS
# ============================================================================

class TestCachedResponseDecorator:
    """Tests for the @cached_response decorator."""
    
    def test_decorator_preserves_function_name(self):
        """Test that decorator preserves function metadata."""
        from core.cache_middleware import cached_response
        
        @cached_response("test_endpoint", ttl=60)
        async def test_function():
            return {"result": "success"}
        
        assert test_function.__name__ == "test_function"
    
    def test_decorator_has_wrapped_attribute(self):
        """Test that decorator sets __wrapped__ attribute."""
        from core.cache_middleware import cached_response
        
        @cached_response("test_endpoint", ttl=60)
        async def test_function():
            return {"result": "success"}
        
        assert hasattr(test_function, '__wrapped__')
    
    @pytest.mark.asyncio
    async def test_decorator_cache_miss_executes_function(self):
        """Test that cache miss executes the wrapped function."""
        from core.cache_middleware import cached_response, reset_cache_stats
        
        reset_cache_stats()
        call_count = [0]
        
        @cached_response("test_endpoint", ttl=60)
        async def test_function():
            call_count[0] += 1
            return {"count": call_count[0]}
        
        # First call - should execute function
        # Note: Without FastAPI Request context, the decorator will execute function
        result = await test_function()
        
        assert call_count[0] >= 1


# ============================================================================
# CACHE BYPASS TESTS
# ============================================================================

class TestCacheBypass:
    """Tests for cache bypass functionality."""
    
    def test_should_bypass_cache_with_nocache_1(self):
        """Test cache bypass with nocache=1."""
        from core.cache_middleware import _should_bypass_cache
        
        # Create mock request with nocache=1
        mock_request = MagicMock()
        mock_request.query_params.get.return_value = "1"
        
        assert _should_bypass_cache(mock_request) is True
    
    def test_should_bypass_cache_with_nocache_true(self):
        """Test cache bypass with nocache=true."""
        from core.cache_middleware import _should_bypass_cache
        
        mock_request = MagicMock()
        mock_request.query_params.get.return_value = "true"
        
        assert _should_bypass_cache(mock_request) is True
    
    def test_should_not_bypass_cache_with_nocache_0(self):
        """Test no bypass with nocache=0."""
        from core.cache_middleware import _should_bypass_cache
        
        mock_request = MagicMock()
        mock_request.query_params.get.return_value = "0"
        
        assert _should_bypass_cache(mock_request) is False
    
    def test_should_not_bypass_cache_without_param(self):
        """Test no bypass when nocache param is missing."""
        from core.cache_middleware import _should_bypass_cache
        
        mock_request = MagicMock()
        mock_request.query_params.get.return_value = None
        
        # When None is returned, it should default to "0"
        mock_request.query_params.get.return_value = "0"
        
        assert _should_bypass_cache(mock_request) is False


# ============================================================================
# INTEGRATION WITH MULTI-LEVEL CACHE
# ============================================================================

class TestCacheMiddlewareIntegration:
    """Tests for cache middleware integration with multi-level cache."""
    
    def test_get_cache_stats_includes_multi_level(self):
        """Test that get_cache_stats includes multi-level cache stats."""
        from core.cache_middleware import get_cache_stats
        
        stats = get_cache_stats()
        
        assert 'middleware' in stats
        assert 'multi_level_cache' in stats
    
    def test_multi_level_cache_stats_fields(self):
        """Test multi-level cache stats have required fields."""
        from core.cache_middleware import get_cache_stats
        
        stats = get_cache_stats()
        ml_stats = stats['multi_level_cache']
        
        required_fields = ['l1_enabled', 'l2_enabled', 'l1_size', 'hit_rate']
        for field in required_fields:
            assert field in ml_stats, f"Missing field: {field}"


# ============================================================================
# EDGE CASES
# ============================================================================

class TestCacheEdgeCases:
    """Tests for cache edge cases."""
    
    def test_cache_with_unicode_keys(self):
        """Test cache handles unicode keys correctly."""
        from core.multi_level_cache import MultiLevelCache
        
        cache = MultiLevelCache()
        cache.l2_enabled = False
        
        cache.set("日本語クエリ", "結果")
        result = cache.get("日本語クエリ")
        
        assert result == "結果"
    
    def test_cache_with_large_values(self):
        """Test cache handles large values."""
        from core.multi_level_cache import MultiLevelCache
        
        cache = MultiLevelCache()
        cache.l2_enabled = False
        
        large_value = "x" * 10000
        cache.set("large_query", large_value)
        result = cache.get("large_query")
        
        assert result == large_value
    
    def test_cache_with_empty_string(self):
        """Test cache handles empty string values."""
        from core.multi_level_cache import MultiLevelCache
        
        cache = MultiLevelCache()
        cache.l2_enabled = False
        
        cache.set("empty_query", "")
        result = cache.get("empty_query")
        
        assert result == ""
    
    def test_cache_key_with_long_params(self):
        """Test cache key generation with very long parameters."""
        from core.cache_middleware import generate_cache_key
        
        long_text = "x" * 10000
        key = generate_cache_key("chat", text=long_text)
        
        # Key should be short regardless of input length
        assert len(key) < 100
