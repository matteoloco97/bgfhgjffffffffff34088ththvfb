#!/usr/bin/env python3
"""Test semantic cache integration"""

import requests
import time

BASE_URL = "http://localhost:8081"

def test_semantic_cache():
    """Test complete semantic cache workflow"""
    
    print("\n🧪 SEMANTIC CACHE INTEGRATION TEST")
    print("="*70)
    
    # 1. Health check
    print("\n1. Checking /healthz...")
    try:
        r = requests.get(f"{BASE_URL}/healthz")
        if r.ok:
            print("   ✅ API online")
        else:
            print(f"   ❌ API error: {r.status_code}")
            return
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return
    
    # 2. Test queries
    print("\n2. Testing /chat endpoint...")
    
    queries = [
        ("Che ora è?", "First query"),
        ("Che ore sono?", "Similar - should hit"),
        ("What time is it?", "Different language"),
    ]
    
    results = []
    
    for query, label in queries:
        print(f"\nTest: {label}")
        print(f"  Query: {query}")
        
        payload = {
            "source": "test",
            "source_id": "semantic_test",
            "text": query
        }
        
        start = time.time()
        try:
            r = requests.post(f"{BASE_URL}/chat", json=payload, timeout=10)
            latency = (time.time() - start) * 1000
            
            if r.ok:
                data = r.json()
                reply = data.get("reply", "")[:50]
                
                # Check cache indicators
                if latency < 200:
                    cache_status = "💨 Cache: semantic"
                elif latency < 1000:
                    cache_status = "🔍 Cache: likely hit"
                else:
                    cache_status = "🔍 Cache: none"
                
                print(f"  {cache_status}")
                print(f"  Latency: {int(latency)}ms")
                print(f"  Reply: {reply}...")
                
                results.append({
                    "query": query,
                    "latency": latency,
                    "cached": latency < 200
                })
            else:
                print(f"  ❌ Error: {r.status_code}")
        
        except Exception as e:
            print(f"  ❌ Error: {e}")
    
    # 3. Results
    print("\n" + "="*70)
    print("📊 RESULTS:")
    
    cache_hits = sum(1 for r in results if r["cached"])
    total = len(results)
    
    print(f"\n  Total queries: {total}")
    print(f"  Cache hits: {cache_hits}")
    print(f"  Hit rate: {cache_hits/total*100:.1f}%")
    
    if cache_hits > 0:
        print("\n✅ Semantic cache working!")
    else:
        print("\n⚠️  No cache hits detected")
    
    print("\n" + "="*70)

if __name__ == "__main__":
    test_semantic_cache()
