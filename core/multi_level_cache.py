"""
Multi-level cache system for QuantumDev (Phase 2 - Priority 7).

L1: In-memory LRU cache (100 items, <1ms)
L2: Redis semantic cache (5000 items, <10ms) - already implemented in semantic_cache.py
L3: Disk cache for large responses (optional, not implemented yet)

This module provides a unified interface for caching query responses across
multiple levels, with automatic fallback between levels.
"""

import os
import time
import logging
import hashlib
from typing import Optional, Dict, Any, List, Tuple
from collections import OrderedDict

log = logging.getLogger(__name__)

# Configuration from environment
L1_CACHE_SIZE = int(os.getenv('L1_CACHE_SIZE', '100'))
L1_CACHE_TTL = int(os.getenv('L1_CACHE_TTL', '300'))  # 5 minutes default

ENABLE_L1_CACHE = os.getenv('ENABLE_L1_CACHE', '1') == '1'
ENABLE_L2_CACHE = os.getenv('ENABLE_L2_CACHE', '1') == '1'

# Redis configuration (for L2 cache)
REDIS_HOST = os.getenv('REDIS_HOST', '127.0.0.1')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
REDIS_DB = int(os.getenv('REDIS_DB', '0'))


class MultiLevelCache:
    """
    Multi-level cache with automatic fallback.
    
    Cache hierarchy:
    1. L1 (memory) - exact match only, ultra-fast (<1ms)
    2. L2 (Redis) - semantic match, fast (<10ms)
    
    The cache transparently falls back between levels, populating
    faster levels on cache hits from slower levels.
    """
    
    def __init__(self):
        self.l1_enabled = ENABLE_L1_CACHE
        self.l2_enabled = ENABLE_L2_CACHE
        
        # L1: OrderedDict for LRU behavior
        self._l1_cache: OrderedDict[str, Tuple[str, float]] = OrderedDict()
        self._l1_max_size = L1_CACHE_SIZE
        self._l1_ttl = L1_CACHE_TTL
        
        # L2: Redis connection (lazy init)
        self._redis_client: Optional[Any] = None
        
        # Stats
        self.stats = {
            'l1_hits': 0,
            'l1_misses': 0,
            'l2_hits': 0,
            'l2_misses': 0,
            'total_requests': 0,
            'l1_evictions': 0,
        }
        
        log.info(
            f"MultiLevelCache initialized: L1={'ON' if self.l1_enabled else 'OFF'} "
            f"(size={L1_CACHE_SIZE}, ttl={L1_CACHE_TTL}s), "
            f"L2={'ON' if self.l2_enabled else 'OFF'}"
        )
    
    def _hash_query(self, query: str) -> str:
        """Generate hash for query (exact match key)."""
        return hashlib.sha256(query.encode()).hexdigest()[:16]
    
    def _get_redis_client(self):
        """Lazy initialization of Redis client."""
        if self._redis_client is None and self.l2_enabled:
            try:
                import redis
                self._redis_client = redis.Redis(
                    host=REDIS_HOST,
                    port=REDIS_PORT,
                    db=REDIS_DB,
                    decode_responses=False  # Binary data
                )
                # Test connection
                self._redis_client.ping()
            except Exception as e:
                log.warning(f"Redis connection failed (L2 cache disabled): {e}")
                self._redis_client = None
                self.l2_enabled = False
        return self._redis_client
    
    def get(self, query: str) -> Optional[str]:
        """
        Get cached response for query.
        Checks L1 (exact match) then L2 (semantic match).
        
        Args:
            query: User query string
            
        Returns:
            Cached response or None if not found
        """
        self.stats['total_requests'] += 1
        query_hash = self._hash_query(query)
        
        # Try L1 first (exact match only)
        if self.l1_enabled:
            if query_hash in self._l1_cache:
                result, ts = self._l1_cache[query_hash]
                
                # Check expiry
                if time.time() - ts < self._l1_ttl:
                    # Move to end (LRU)
                    self._l1_cache.move_to_end(query_hash)
                    self.stats['l1_hits'] += 1
                    log.debug(f"L1 cache hit: {query[:50]}...")
                    return result
                else:
                    # Expired
                    del self._l1_cache[query_hash]
            
            self.stats['l1_misses'] += 1
        
        # Try L2 (semantic match via existing semantic_cache)
        if self.l2_enabled:
            try:
                from core.semantic_cache import get_semantic_cache
                semcache = get_semantic_cache()
                result = semcache.get(query)
                
                if result:
                    self.stats['l2_hits'] += 1
                    # Populate L1 for future fast access
                    if self.l1_enabled:
                        self._set_l1(query_hash, result)
                    log.debug(f"L2 cache hit: {query[:50]}...")
                    return result
                else:
                    self.stats['l2_misses'] += 1
            except Exception as e:
                log.warning(f"L2 cache error: {e}")
                self.stats['l2_misses'] += 1
        
        return None
    
    def set(self, query: str, result: str):
        """
        Cache result at all enabled levels.
        
        Args:
            query: User query string
            result: Response to cache
        """
        query_hash = self._hash_query(query)
        
        # Set L1
        if self.l1_enabled:
            self._set_l1(query_hash, result)
        
        # Set L2 (semantic cache handles this already)
        if self.l2_enabled:
            try:
                from core.semantic_cache import get_semantic_cache
                semcache = get_semantic_cache()
                semcache.set(query, result)
            except Exception as e:
                log.warning(f"L2 cache set error: {e}")
    
    def _set_l1(self, query_hash: str, result: str):
        """Set L1 cache with LRU eviction."""
        # Evict oldest if full
        if len(self._l1_cache) >= self._l1_max_size:
            # Remove oldest (first item)
            self._l1_cache.popitem(last=False)
            self.stats['l1_evictions'] += 1
        
        self._l1_cache[query_hash] = (result, time.time())
    
    def clear_l1(self) -> int:
        """Clear L1 cache. Returns number of items cleared."""
        count = len(self._l1_cache)
        self._l1_cache.clear()
        log.info(f"L1 cache cleared: {count} items removed")
        return count
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dict with cache performance metrics
        """
        total = self.stats['total_requests']
        l1_hits = self.stats['l1_hits']
        l2_hits = self.stats['l2_hits']
        total_hits = l1_hits + l2_hits
        
        return {
            **self.stats,
            'hit_rate': total_hits / total if total > 0 else 0.0,
            'l1_hit_rate': l1_hits / total if total > 0 else 0.0,
            'l2_hit_rate': l2_hits / total if total > 0 else 0.0,
            'l1_size': len(self._l1_cache),
            'l1_max_size': self._l1_max_size,
            'l1_enabled': self.l1_enabled,
            'l2_enabled': self.l2_enabled,
        }
    
    def reset_stats(self):
        """Reset all statistics counters."""
        self.stats = {
            'l1_hits': 0,
            'l1_misses': 0,
            'l2_hits': 0,
            'l2_misses': 0,
            'total_requests': 0,
            'l1_evictions': 0,
        }
        log.info("Cache statistics reset")


# Singleton instance
_cache_instance: Optional[MultiLevelCache] = None


def get_multi_level_cache() -> MultiLevelCache:
    """Get or create MultiLevelCache singleton."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = MultiLevelCache()
    return _cache_instance
