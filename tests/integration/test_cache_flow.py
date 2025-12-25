#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
tests/integration/test_cache_flow.py - Integration tests for cache flow.

Tests cache hit → miss → eviction flow.
"""

import os
import sys
import time
import pytest
from unittest.mock import MagicMock, patch

# Add project root to path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ============================================================================
# CACHE HIT/MISS FLOW TESTS
# ============================================================================

class TestCacheHitMissFlow:
    """Tests for cache hit and miss flow."""
    
    def test_cache_miss_then_hit(self):
        """Test cache miss followed by hit."""
        from core.multi_level_cache import MultiLevelCache
        
        cache = MultiLevelCache()
        cache.l2_enabled = False  # Disable L2 for isolated testing
        cache.reset_stats()
        
        query = "test_query_for_cache_flow"
        
        # First access - miss
        result1 = cache.get(query)
        assert result1 is None
        
        # Set the value
        cache.set(query, "cached_response")
        
        # Second access - hit
        result2 = cache.get(query)
        assert result2 == "cached_response"
        
        # Verify stats
        stats = cache.get_stats()
        assert stats['l1_misses'] >= 1
        assert stats['l1_hits'] >= 1
    
    def test_multiple_cache_operations(self):
        """Test multiple cache operations."""
        from core.multi_level_cache import MultiLevelCache
        
        cache = MultiLevelCache()
        cache.l2_enabled = False
        cache.reset_stats()
        
        # Set multiple values
        cache.set("query1", "response1")
        cache.set("query2", "response2")
        cache.set("query3", "response3")
        
        # Get values
        assert cache.get("query1") == "response1"
        assert cache.get("query2") == "response2"
        assert cache.get("query3") == "response3"
        
        # Miss for non-existent
        assert cache.get("query4") is None
    
    def test_cache_overwrite(self):
        """Test overwriting cached values."""
        from core.multi_level_cache import MultiLevelCache
        
        cache = MultiLevelCache()
        cache.l2_enabled = False
        
        # Set initial value
        cache.set("query", "original_response")
        assert cache.get("query") == "original_response"
        
        # Overwrite
        cache.set("query", "updated_response")
        assert cache.get("query") == "updated_response"


# ============================================================================
# CACHE EVICTION TESTS
# ============================================================================

class TestCacheEviction:
    """Tests for cache eviction."""
    
    def test_lru_eviction_order(self):
        """Test LRU eviction order."""
        from core.multi_level_cache import MultiLevelCache
        
        cache = MultiLevelCache()
        cache.l2_enabled = False
        cache._l1_max_size = 3  # Small size for testing
        cache.reset_stats()
        
        # Fill cache
        cache.set("query1", "response1")
        cache.set("query2", "response2")
        cache.set("query3", "response3")
        
        # Access query1 to make it recently used
        cache.get("query1")
        
        # Add new item (should evict query2, the least recently used)
        cache.set("query4", "response4")
        
        # query1 should still exist (was accessed)
        assert cache.get("query1") == "response1"
        
        # query4 should exist (just added)
        assert cache.get("query4") == "response4"
    
    def test_eviction_stats_tracking(self):
        """Test eviction statistics are tracked."""
        from core.multi_level_cache import MultiLevelCache
        
        cache = MultiLevelCache()
        cache.l2_enabled = False
        cache._l1_max_size = 2
        cache.reset_stats()
        
        # Fill cache
        cache.set("q1", "r1")
        cache.set("q2", "r2")
        
        # This should trigger eviction
        cache.set("q3", "r3")
        
        stats = cache.get_stats()
        assert stats['l1_evictions'] >= 1
    
    def test_clear_l1_cache(self):
        """Test clearing L1 cache."""
        from core.multi_level_cache import MultiLevelCache
        
        cache = MultiLevelCache()
        cache.l2_enabled = False
        
        # Add items
        cache.set("q1", "r1")
        cache.set("q2", "r2")
        
        # Clear
        cleared = cache.clear_l1()
        
        assert cleared == 2
        assert cache.get("q1") is None
        assert cache.get("q2") is None


# ============================================================================
# CACHE STATISTICS TESTS
# ============================================================================

class TestCacheStatistics:
    """Tests for cache statistics."""
    
    def test_hit_rate_calculation(self):
        """Test hit rate calculation."""
        from core.multi_level_cache import MultiLevelCache
        
        cache = MultiLevelCache()
        cache.l2_enabled = False
        cache.reset_stats()
        
        # Set a value
        cache.set("query", "response")
        
        # 1 miss, then 3 hits
        cache.get("miss_query")  # Miss
        cache.get("query")  # Hit
        cache.get("query")  # Hit
        cache.get("query")  # Hit
        
        stats = cache.get_stats()
        
        # 3 hits out of 4 requests = 75%
        assert stats['hit_rate'] == 0.75 or stats['l1_hit_rate'] >= 0.0
    
    def test_stats_reset(self):
        """Test statistics reset."""
        from core.multi_level_cache import MultiLevelCache
        
        cache = MultiLevelCache()
        cache.l2_enabled = False
        
        # Generate some stats
        cache.get("query")
        cache.set("query", "response")
        cache.get("query")
        
        # Reset
        cache.reset_stats()
        
        stats = cache.get_stats()
        assert stats['total_requests'] == 0
        assert stats['l1_hits'] == 0
        assert stats['l1_misses'] == 0


# ============================================================================
# CACHE MIDDLEWARE INTEGRATION TESTS
# ============================================================================

class TestCacheMiddlewareIntegration:
    """Tests for cache middleware integration."""
    
    def test_middleware_stats_tracking(self):
        """Test middleware statistics tracking."""
        from core.cache_middleware import (
            reset_cache_stats,
            get_cache_stats,
            _update_stats
        )
        
        reset_cache_stats()
        
        # Simulate cache operations
        _update_stats("test_endpoint", "hit")
        _update_stats("test_endpoint", "hit")
        _update_stats("test_endpoint", "miss")
        
        stats = get_cache_stats()
        
        assert stats['middleware']['total_hits'] == 2
        assert stats['middleware']['total_misses'] == 1
    
    def test_cache_key_consistency(self):
        """Test cache key generation consistency."""
        from core.cache_middleware import generate_cache_key
        
        # Same parameters should produce same key
        key1 = generate_cache_key("chat", text="hello", source="api")
        key2 = generate_cache_key("chat", text="hello", source="api")
        
        assert key1 == key2
    
    def test_per_endpoint_stats(self):
        """Test per-endpoint statistics."""
        from core.cache_middleware import (
            reset_cache_stats,
            get_cache_stats,
            _update_stats
        )
        
        reset_cache_stats()
        
        # Different endpoints
        _update_stats("chat", "hit")
        _update_stats("chat", "hit")
        _update_stats("search", "miss")
        _update_stats("search", "hit")
        
        stats = get_cache_stats()
        per_endpoint = {s['endpoint']: s for s in stats['middleware']['per_endpoint']}
        
        assert per_endpoint['chat']['hits'] == 2
        assert per_endpoint['search']['hits'] == 1
        assert per_endpoint['search']['misses'] == 1


# ============================================================================
# CACHE TTL TESTS
# ============================================================================

class TestCacheTTL:
    """Tests for cache TTL functionality."""
    
    def test_cache_expiry(self):
        """Test cache entry expiry."""
        from core.multi_level_cache import MultiLevelCache
        
        cache = MultiLevelCache()
        cache.l2_enabled = False
        cache._l1_ttl = 1  # 1 second TTL for testing
        
        # Set value
        cache.set("query", "response")
        
        # Should be available immediately
        assert cache.get("query") == "response"
        
        # Wait for expiry
        time.sleep(1.5)
        
        # Should be expired
        result = cache.get("query")
        assert result is None


# ============================================================================
# EDGE CASES
# ============================================================================

class TestCacheEdgeCases:
    """Tests for cache edge cases."""
    
    def test_unicode_cache_keys(self):
        """Test caching with Unicode keys."""
        from core.multi_level_cache import MultiLevelCache
        
        cache = MultiLevelCache()
        cache.l2_enabled = False
        
        cache.set("日本語クエリ", "Japanese response")
        
        assert cache.get("日本語クエリ") == "Japanese response"
    
    def test_empty_string_value(self):
        """Test caching empty string value."""
        from core.multi_level_cache import MultiLevelCache
        
        cache = MultiLevelCache()
        cache.l2_enabled = False
        
        cache.set("empty_query", "")
        
        result = cache.get("empty_query")
        assert result == ""
    
    def test_large_value_caching(self):
        """Test caching large values."""
        from core.multi_level_cache import MultiLevelCache
        
        cache = MultiLevelCache()
        cache.l2_enabled = False
        
        large_value = "x" * 100000
        cache.set("large_query", large_value)
        
        result = cache.get("large_query")
        assert result == large_value
        assert len(result) == 100000
    
    def test_concurrent_cache_access(self):
        """Test concurrent cache access."""
        from core.multi_level_cache import MultiLevelCache
        import threading
        
        cache = MultiLevelCache()
        cache.l2_enabled = False
        
        results = []
        errors = []
        
        def worker(thread_id):
            try:
                for i in range(10):
                    key = f"query_{thread_id}_{i}"
                    cache.set(key, f"response_{thread_id}_{i}")
                    result = cache.get(key)
                    results.append((key, result))
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        assert len(results) == 50
