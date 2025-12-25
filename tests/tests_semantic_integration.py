#!/usr/bin/env python3
import requests
import time
import json

BASE = "http://localhost:8081"

print("🧪 SEMANTIC CACHE INTEGRATION TEST\n")
print("=" * 70)

# Test 1: Health check
print("\n1. Checking /healthz...")
try:
    r = requests.get(f"{BASE}/healthz")
    health = r.json()
    print(f"   Cache status: {health['semantic_cache']['status']}")
    print(f"   Stats: {health['semantic_cache']['stats']}")
except Exception as e:
    print(f"   ❌ Error: {e}")
    exit(1)

# Test 2: Chat endpoint with cache
queries = [
    ("Che ora è?", "First query"),
    ("Che ore sono?", "Similar - should hit"),
    ("What time is it?", "English version"),
]

print("\n2. Testing /chat endpoint...\n")

for query, description in queries:
    print(f"Test: {description}")
    print(f"  Query: '{query}'")
    
    start = time.time()
    try:
        r = requests.post(f"{BASE}/chat", json={
            "source": "test",
            "source_id": "integration_test",
            "text": query
        })
        elapsed_ms = (time.time() - start) * 1000
        
        data = r.json()
        cached = data.get("cached", False)
        cache_type = data.get("cache_type", "none")
        similarity = data.get("similarity", 0)
        reply = data.get("reply", "")[:80]
        
        icon = "💨" if cached else "🔍"
        print(f"  {icon} Cache: {cache_type}")
        if similarity:
            print(f"     Similarity: {similarity:.3f}")
        print(f"     Latency: {elapsed_ms:.0f}ms")
        print(f"     Reply: {reply}...")
    except Exception as e:
        print(f"  ❌ Error: {e}")
    
    print()
    time.sleep(0.3)

# Test 3: Cache stats
print("3. Final cache stats...")
try:
    r = requests.get(f"{BASE}/cache/stats")
    stats = r.json()['semantic_cache']
    print(f"   Hits: {stats['hits']}")
    print(f"   Misses: {stats['misses']}")
    print(f"   Hit rate: {stats['hit_rate_pct']}%")
except Exception as e:
    print(f"   ❌ Error: {e}")

print("\n" + "=" * 70)
print("✅ Integration test complete!")
