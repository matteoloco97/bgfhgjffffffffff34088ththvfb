#!/usr/bin/env python3
"""
Test multi-level cache integration in /chat endpoint.

Tests:
1. Cache miss on first query
2. Cache hit on second identical query
3. User-specific caching (different users get separate caches)
4. Cache stats endpoint
5. Cache clear endpoint (admin)
6. Response format includes cache metadata
"""

import requests
import time
import os

BASE = os.getenv("TEST_BASE_URL", "http://localhost:8081")
ADMIN_SECRET = os.getenv("QUANTUM_SHARED_SECRET", "test_secret")

print("🧪 MULTI-LEVEL CACHE INTEGRATION TEST")
print("=" * 70)

# Test 1: Cache miss then hit
print("\n1. Testing cache miss → cache hit...")
query = "Ciao come va?"
source = "test"
source_id = "cache_test_1"

print(f"   Query: '{query}'")
print(f"   Source: {source}:{source_id}")

# First call - should be cache miss
start = time.time()
try:
    r1 = requests.post(f"{BASE}/chat", json={
        "text": query,
        "source": source,
        "source_id": source_id
    })
    elapsed_ms_1 = (time.time() - start) * 1000
    
    data1 = r1.json()
    cached_1 = data1.get("cached", False)
    latency_1 = data1.get("latency_ms", 0)
    reply_1 = data1.get("reply", "")
    
    print(f"   First call:")
    print(f"     ❌ Cached: {cached_1} (expected: False)")
    print(f"     ⏱  Latency: {latency_1}ms (wall time: {elapsed_ms_1:.0f}ms)")
    print(f"     📝 Reply length: {len(reply_1)} chars")
    
    if cached_1:
        print(f"     ⚠️  WARNING: First call should not be cached!")
except Exception as e:
    print(f"   ❌ Error on first call: {e}")
    exit(1)

# Wait a moment to ensure cache write completes
time.sleep(0.5)

# Second call - should be cache hit
start = time.time()
try:
    r2 = requests.post(f"{BASE}/chat", json={
        "text": query,
        "source": source,
        "source_id": source_id
    })
    elapsed_ms_2 = (time.time() - start) * 1000
    
    data2 = r2.json()
    cached_2 = data2.get("cached", False)
    cache_level_2 = data2.get("cache_level")
    latency_2 = data2.get("latency_ms", 0)
    reply_2 = data2.get("reply", "")
    
    print(f"   Second call:")
    print(f"     ✅ Cached: {cached_2} (expected: True)")
    print(f"     📊 Cache level: {cache_level_2}")
    print(f"     ⚡ Latency: {latency_2}ms (wall time: {elapsed_ms_2:.0f}ms)")
    print(f"     📝 Reply length: {len(reply_2)} chars")
    
    if not cached_2:
        print(f"     ⚠️  WARNING: Second call should be cached!")
    
    if latency_2 > 5:
        print(f"     ⚠️  WARNING: Cache latency ({latency_2}ms) > 5ms threshold")
    
    # Verify replies are identical
    if reply_1 == reply_2:
        print(f"     ✅ Replies match (cache returning same content)")
    else:
        print(f"     ❌ ERROR: Replies differ!")
        print(f"        First: {reply_1[:50]}...")
        print(f"        Second: {reply_2[:50]}...")
except Exception as e:
    print(f"   ❌ Error on second call: {e}")
    exit(1)

print()

# Test 2: User-specific caching
print("2. Testing user-specific caching...")
query2 = "Che ore sono?"
source2a = "test"
source_id2a = "user_a"
source2b = "test"
source_id2b = "user_b"

print(f"   Query: '{query2}'")
print(f"   User A: {source2a}:{source_id2a}")
print(f"   User B: {source2b}:{source_id2b}")

# Query from User A
try:
    ra = requests.post(f"{BASE}/chat", json={
        "text": query2,
        "source": source2a,
        "source_id": source_id2a
    })
    data_a = ra.json()
    reply_a = data_a.get("reply", "")
    cached_a = data_a.get("cached", False)
    
    print(f"   User A:")
    print(f"     Cached: {cached_a}")
    print(f"     Reply: {reply_a[:60]}...")
except Exception as e:
    print(f"   ❌ Error for User A: {e}")

time.sleep(0.5)

# Query from User B (should NOT hit User A's cache)
try:
    rb = requests.post(f"{BASE}/chat", json={
        "text": query2,
        "source": source2b,
        "source_id": source_id2b
    })
    data_b = rb.json()
    reply_b = data_b.get("reply", "")
    cached_b = data_b.get("cached", False)
    
    print(f"   User B:")
    print(f"     Cached: {cached_b} (expected: False - different user)")
    print(f"     Reply: {reply_b[:60]}...")
    
    if cached_b:
        print(f"     ⚠️  WARNING: User B should not hit User A's cache!")
except Exception as e:
    print(f"   ❌ Error for User B: {e}")

print()

# Test 3: Cache stats
print("3. Testing /cache/stats endpoint...")
try:
    r_stats = requests.get(f"{BASE}/cache/stats")
    stats = r_stats.json()
    
    print(f"   L1 hits: {stats.get('l1_hits', 0)}")
    print(f"   L2 hits: {stats.get('l2_hits', 0)}")
    print(f"   L1 misses: {stats.get('l1_misses', 0)}")
    print(f"   L2 misses: {stats.get('l2_misses', 0)}")
    print(f"   Total requests: {stats.get('total_requests', 0)}")
    print(f"   Hit rate: {stats.get('hit_rate', 0):.2%}")
    print(f"   L1 size: {stats.get('l1_size', 0)}/{stats.get('l1_max_size', 0)}")
    print(f"   L1 enabled: {stats.get('l1_enabled', False)}")
    print(f"   L2 enabled: {stats.get('l2_enabled', False)}")
    
    # Verify we have at least some requests
    if stats.get('total_requests', 0) > 0:
        print(f"   ✅ Cache is being used")
    else:
        print(f"   ⚠️  WARNING: No requests recorded in cache stats")
except Exception as e:
    print(f"   ❌ Error getting cache stats: {e}")

print()

# Test 4: Cache clear (admin only)
print("4. Testing /cache/clear endpoint...")
try:
    # Try without admin secret (should fail)
    r_clear_fail = requests.post(f"{BASE}/cache/clear", json={
        "level": "l1",
        "admin_secret": "wrong_secret"
    })
    if r_clear_fail.status_code == 403:
        print(f"   ✅ Unauthorized access rejected (403)")
    else:
        print(f"   ⚠️  WARNING: Expected 403, got {r_clear_fail.status_code}")
    
    # Try with correct admin secret
    r_clear_ok = requests.post(f"{BASE}/cache/clear", json={
        "level": "l1",
        "admin_secret": ADMIN_SECRET
    })
    clear_data = r_clear_ok.json()
    print(f"   Clear status: {clear_data.get('status')}")
    print(f"   Cleared level: {clear_data.get('cleared')}")
    
    if clear_data.get('status') == 'ok':
        print(f"   ✅ Cache cleared successfully")
    else:
        print(f"   ⚠️  Cache clear may have failed: {clear_data}")
    
    # Verify cache was cleared by checking stats
    time.sleep(0.5)
    r_stats_after = requests.get(f"{BASE}/cache/stats")
    stats_after = r_stats_after.json()
    l1_size_after = stats_after.get('l1_size', -1)
    
    print(f"   L1 size after clear: {l1_size_after}")
    
    if l1_size_after == 0:
        print(f"   ✅ L1 cache successfully emptied")
    else:
        print(f"   ⚠️  WARNING: L1 cache still has {l1_size_after} items")
        
except Exception as e:
    print(f"   ❌ Error testing cache clear: {e}")

print()

# Test 5: Response format validation
print("5. Validating response format...")
try:
    r_test = requests.post(f"{BASE}/chat", json={
        "text": "Test response format",
        "source": "test",
        "source_id": "format_test"
    })
    data_test = r_test.json()
    
    # Check required fields
    required_fields = ["reply", "cached", "cache_level", "latency_ms"]
    missing_fields = [f for f in required_fields if f not in data_test]
    
    if not missing_fields:
        print(f"   ✅ All required fields present: {required_fields}")
    else:
        print(f"   ❌ Missing fields: {missing_fields}")
    
    # Check field types
    if isinstance(data_test.get("cached"), bool):
        print(f"   ✅ 'cached' is boolean")
    else:
        print(f"   ❌ 'cached' should be boolean, got {type(data_test.get('cached'))}")
    
    if isinstance(data_test.get("latency_ms"), int):
        print(f"   ✅ 'latency_ms' is integer")
    else:
        print(f"   ❌ 'latency_ms' should be integer, got {type(data_test.get('latency_ms'))}")
    
    if isinstance(data_test.get("reply"), str):
        print(f"   ✅ 'reply' is string")
    else:
        print(f"   ❌ 'reply' should be string, got {type(data_test.get('reply'))}")
        
except Exception as e:
    print(f"   ❌ Error validating response format: {e}")

print()
print("=" * 70)
print("✅ Multi-level cache integration test complete!")
print()
print("Summary:")
print("  - Cache miss → hit cycle: tested")
print("  - User-specific caching: tested")
print("  - Cache stats endpoint: tested")
print("  - Cache clear endpoint: tested")
print("  - Response format: validated")
