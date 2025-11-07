#!/usr/bin/env python3
# core/semantic_cache.py - Semantic Caching Layer with Embeddings
# Version: 1.1 (Patched - Production Ready)

import hashlib
import redis
import numpy as np
import logging
import time
from sentence_transformers import SentenceTransformer
from typing import Optional, Tuple, Dict

# Configure module logger
log = logging.getLogger(__name__)

class SemanticCache:
    """
    Semantic cache using embedding similarity.
    
    Features:
    - Find similar queries even if worded differently
    - Configurable similarity threshold
    - TTL management
    - Hit rate tracking
    - Robust error handling
    
    Example:
        >>> cache = SemanticCache(redis_client)
        >>> cache.set("What time is it?", "It's 3:30 PM")
        >>> result = cache.get("What's the time?")  # Different wording
        >>> if result:
        >>>     response, similarity = result
        >>>     print(f"Cache hit! Similarity: {similarity:.2f}")
    """
    
    def __init__(
        self, 
        redis_client: redis.Redis,
        model_name: str = "all-MiniLM-L6-v2",
        threshold: float = 0.85,
        ttl: int = 86400,
        max_scan: int = 200
    ):
        """
        Initialize semantic cache.
        
        Args:
            redis_client: Redis connection instance
            model_name: SentenceTransformer model name
                       (all-MiniLM-L6-v2 = lightweight, fast, good quality)
            threshold: Cosine similarity threshold (0-1)
                      0.85 = 85% similar minimum to be cache hit
            ttl: Time-to-live in seconds (default 24h)
            max_scan: Max cache entries to scan per lookup (performance)
        """
        self.redis = redis_client
        self.threshold = threshold
        self.ttl = ttl
        self.max_scan = max_scan
        
        # Load embedding model
        log.info(f"Loading embedding model: {model_name}")
        try:
            self.model = SentenceTransformer(model_name)
            log.info(f"✅ Semantic cache ready (threshold={threshold})")
        except Exception as e:
            log.error(f"❌ Failed to load model {model_name}: {e}")
            raise
        
        # Statistics tracking
        self._hits = 0
        self._misses = 0
        self._errors = 0
    
    def _embed(self, text: str) -> np.ndarray:
        """
        Generate embedding vector for text.
        
        Args:
            text: Input text to embed
            
        Returns:
            Numpy array of embeddings (384 dimensions for MiniLM)
        """
        try:
            return self.model.encode(text, convert_to_numpy=True)
        except Exception as e:
            log.error(f"Embedding generation failed: {e}")
            raise
    
    def _cache_key(self, text: str) -> str:
        """
        Generate Redis key for cache entry.
        
        Uses first 16 chars of SHA256 hash to avoid key collisions
        while keeping keys short.
        
        Args:
            text: Query text
            
        Returns:
            Redis key string
        """
        hash_val = hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]
        return f"sem_cache:{hash_val}"
    
    def _cosine_similarity(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """
        Calculate cosine similarity between two embeddings.
        
        Formula: cos(θ) = (A·B) / (||A|| ||B||)
        Range: -1 to 1 (we expect 0 to 1 for text similarity)
        
        Args:
            emb1: First embedding vector
            emb2: Second embedding vector
            
        Returns:
            Similarity score (0-1, where 1 = identical)
        """
        try:
            dot_product = np.dot(emb1, emb2)
            norm1 = np.linalg.norm(emb1)
            norm2 = np.linalg.norm(emb2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            similarity = dot_product / (norm1 * norm2)
            return float(similarity)
        except Exception as e:
            log.warning(f"Similarity calculation error: {e}")
            return 0.0
    
    def get(self, query: str) -> Optional[Tuple[str, float]]:
        """
        Try to find similar cached query.
        
        Scans recent cache entries and returns best match if similarity
        exceeds threshold.
        
        Args:
            query: User query text
            
        Returns:
            Tuple of (cached_response, similarity_score) if hit, else None
        """
        if not query or not query.strip():
            return None
        
        start_time = time.time()
        
        try:
            # Generate query embedding
            query_emb = self._embed(query)
            
            # Scan cache for similar entries
            best_match = None
            best_similarity = 0.0
            scanned = 0
            
            cursor = 0
            while True:
                cursor, keys = self.redis.scan(
                    cursor, 
                    match="sem_cache:*", 
                    count=100
                )
                
                for key in keys:
                    if scanned >= self.max_scan:
                        break
                    
                    try:
                        # Get cached data
                        data = self.redis.hgetall(key)
                        if not data or b'emb' not in data or b'response' not in data:
                            continue
                        
                        # Decode embedding
                        cached_emb = np.frombuffer(
                            data[b'emb'], 
                            dtype=np.float32
                        )
                        
                        # Calculate similarity
                        similarity = self._cosine_similarity(query_emb, cached_emb)
                        
                        # Track best match
                        if similarity > best_similarity:
                            best_similarity = similarity
                            best_match = data[b'response'].decode('utf-8')
                        
                        scanned += 1
                        
                    except Exception as e:
                        log.debug(f"Error reading cache entry {key}: {e}")
                        continue
                
                # Stop if we've scanned enough or reached end
                if cursor == 0 or scanned >= self.max_scan:
                    break
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            # Check if best match meets threshold
            if best_similarity >= self.threshold:
                self._hits += 1
                log.info(
                    f"✅ Cache HIT: similarity={best_similarity:.3f}, "
                    f"scanned={scanned}, time={elapsed_ms:.0f}ms"
                )
                return (best_match, best_similarity)
            
            self._misses += 1
            log.info(
                f"❌ Cache MISS: best_similarity={best_similarity:.3f}, "
                f"scanned={scanned}, time={elapsed_ms:.0f}ms"
            )
            return None
            
        except Exception as e:
            self._errors += 1
            log.error(f"Cache GET error: {e}")
            return None
    
    def set(self, query: str, response: str, metadata: Dict = None):
        """
        Cache query-response pair with embedding.
        
        Args:
            query: User query text
            response: LLM response to cache
            metadata: Optional metadata dict (will be stringified)
        """
        if not query or not query.strip() or not response:
            return
        
        try:
            key = self._cache_key(query)
            emb = self._embed(query)
            
            # Prepare cache data
            cache_data = {
                'query': query,
                'response': response,
                'emb': emb.astype(np.float32).tobytes(),
                'timestamp': int(time.time())
            }
            
            # Add metadata if provided
            if metadata:
                cache_data['metadata'] = str(metadata)
            
            # Store in Redis hash
            self.redis.hset(key, mapping=cache_data)
            self.redis.expire(key, self.ttl)
            
            log.debug(f"💾 Cached: {query[:50]}...")
            
        except Exception as e:
            log.error(f"Cache SET error: {e}")
    
    def clear(self) -> int:
        """
        Clear all semantic cache entries.
        
        Returns:
            Number of entries deleted
        """
        try:
            cursor = 0
            deleted = 0
            
            while True:
                cursor, keys = self.redis.scan(
                    cursor, 
                    match="sem_cache:*", 
                    count=1000
                )
                if keys:
                    deleted += self.redis.delete(*keys)
                if cursor == 0:
                    break
            
            log.info(f"🧹 Cleared {deleted} cache entries")
            
            # Reset stats
            self._hits = 0
            self._misses = 0
            self._errors = 0
            
            return deleted
            
        except Exception as e:
            log.error(f"Cache CLEAR error: {e}")
            return 0
    
    def stats(self) -> Dict:
        """
        Get cache statistics.
        
        Returns:
            Dict with hits, misses, hit_rate, etc.
        """
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0
        
        return {
            'hits': self._hits,
            'misses': self._misses,
            'errors': self._errors,
            'total_queries': total,
            'hit_rate_pct': round(hit_rate, 2),
            'threshold': self.threshold
        }


# ============================================================================
# STANDALONE TEST
# ============================================================================

if __name__ == "__main__":
    import redis
    import sys
    
    # ✅ Configure logging for standalone test
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s: %(message)s'
    )
    
    print("=" * 70)
    print("🧪 SEMANTIC CACHE - Comprehensive Test")
    print("=" * 70)
    print()
    
    # Step 1: Connect to Redis
    print("Step 1: Connecting to Redis...")
    try:
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.ping()
        print("  ✅ Redis connected\n")
    except Exception as e:
        print(f"  ❌ Redis connection failed: {e}")
        print("  Make sure Redis is running: sudo systemctl start redis")
        sys.exit(1)
    
    # Step 2: Create cache
    print("Step 2: Creating SemanticCache instance...")
    try:
        cache = SemanticCache(r, threshold=0.85)
        print("  ✅ Cache initialized\n")
    except Exception as e:
        print(f"  ❌ Cache initialization failed: {e}")
        sys.exit(1)
    
    # Step 3: Test embedding similarity
    print("Step 3: Testing embedding similarity...")
    emb1 = cache._embed("What time is it?")
    emb2 = cache._embed("What's the current time?")
    emb3 = cache._embed("What is Python?")
    
    sim_similar = cache._cosine_similarity(emb1, emb2)
    sim_different = cache._cosine_similarity(emb1, emb3)
    
    print(f"  Embedding dimensions: {emb1.shape[0]}")
    print(f"  Similarity (similar queries): {sim_similar:.3f}")
    print(f"  Similarity (different topics): {sim_different:.3f}")
    
    if sim_similar < 0.70:
        print(f"  ⚠️  WARNING: Similar queries have low similarity!")
    else:
        print(f"  ✅ Embeddings working correctly\n")
    
    # Step 4: Test cache operations
    print("Step 4: Testing cache SET and GET...")
    print()
    
    test_cases = [
        ("What time is it?", "It's 3:30 PM"),
        ("Tell me about Python", "Python is a programming language"),
    ]
    
    # Cache first queries
    for query, response in test_cases:
        cache.set(query, response)
    
    # Test retrieval with similar wording
    test_queries = [
        ("What time is it?", True, "Exact match"),
        ("What's the current time?", True, "Similar wording"),
        ("Dimmi l'ora", False, "Different language (should miss)"),
        ("Tell me about Python", True, "Exact match"),
        ("Explain Python to me", True, "Similar wording"),
        ("What is JavaScript?", False, "Different topic"),
    ]
    
    results = []
    for i, (query, should_hit, description) in enumerate(test_queries, 1):
        print(f"Test {i}: {description}")
        print(f"  Query: '{query}'")
        
        result = cache.get(query)
        
        if result:
            response, similarity = result
            status = "✅ HIT" if should_hit else "⚠️  HIT (unexpected)"
            print(f"  {status}: {response[:50]}")
            print(f"  Similarity: {similarity:.3f}")
            results.append(('hit', should_hit))
        else:
            status = "❌ MISS" if should_hit else "✅ MISS (expected)"
            print(f"  {status}")
            results.append(('miss', should_hit))
        
        print()
    
    # Step 5: Statistics
    print("=" * 70)
    print("📊 CACHE STATISTICS")
    print("=" * 70)
    stats = cache.stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # Step 6: Verify results
    print()
    print("=" * 70)
    print("✅ TEST RESULTS")
    print("=" * 70)
    
    correct = sum(1 for status, expected in results if (status == 'hit') == expected)
    total = len(results)
    
    print(f"  Tests passed: {correct}/{total} ({correct/total*100:.0f}%)")
    
    if correct == total:
        print("  🎉 All tests PASSED!")
        exit_code = 0
    else:
        print("  ⚠️  Some tests FAILED")
        exit_code = 1
    
    # Cleanup
    print()
    print("Cleaning up test cache entries...")
    cache.clear()
    print("✅ Cleanup complete")
    
    print()
    print("=" * 70)
    sys.exit(exit_code)
