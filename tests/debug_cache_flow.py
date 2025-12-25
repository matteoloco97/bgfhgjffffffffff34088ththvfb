#!/usr/bin/env python3
import requests
import time

BASE = "http://localhost:8081"

print("🔍 CACHE DEBUG - Step by Step\n")
print("=" * 70)

# Step 1: Clear cache
print("1. Clearing cache...")
r = requests.post(f"{BASE}/cache/clear", json={})
print(f"   {r.json()}\n")

# Step 2: First query (should miss and save)
print("2. First query: 'Che ora è?'")
start = time.time()
r = requests.post(f"{BASE}/chat", json={
    "source": "test",
    "source_id": "debug1",
    "text": "Che ora è?"
})
elapsed = (time.time() - start) * 1000
data = r.json()
print(f"   Cached: {data.get('cached', False)}")
print(f"   Latency: {elapsed:.0f}ms")
print(f"   Reply length: {len(data.get('reply', ''))} chars")
print(f"   Reply preview: {data.get('reply', '')[:80]}...\n")

# Step 3: Check cache stats
print("3. Cache stats after first query:")
r = requests.get(f"{BASE}/cache/stats")
stats = r.json()['semantic_cache']
print(f"   Hits: {stats['hits']}")
print(f"   Misses: {stats['misses']}")
print(f"   Total: {stats['total_queries']}\n")

# Wait for cache to be written
print("4. Waiting 1 second for cache write...\n")
time.sleep(1)

# Step 4: Test direct cache module
print("5. Testing cache module directly (via Python):")
import sys
sys.path.insert(0, '/root/quantumdev-open')
import redis
from core.semantic_cache import SemanticCache

r = redis.Redis(host='localhost', port=6379, db=0)
cache = SemanticCache(r, threshold=0.8)

# Check if entry exists
result = cache.get("Che ora è?")
if result:
    resp, sim = result
    print(f"   ✅ Found in cache! Similarity: {sim:.3f}")
    print(f"   Response: {resp[:80]}...")
else:
    print(f"   ❌ NOT found in cache")

# Manual test of similar query
print("\n6. Testing similar query manually:")
result = cache.get("Che ore sono?")
if result:
    resp, sim = result
    print(f"   ✅ Found! Similarity: {sim:.3f}")
else:
    print(f"   ❌ NOT found")

print("\n" + "=" * 70)
print("Debug complete")
