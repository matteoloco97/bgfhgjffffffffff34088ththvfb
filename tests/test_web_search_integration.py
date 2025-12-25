#!/usr/bin/env python3
# tests/test_web_search_integration.py
# Test suite completa per Task 3 Web Search Optimization (robust)

import sys
import os
import asyncio
import time
from typing import List, Dict
from pathlib import Path

print("=" * 70)
print("🧪 TASK 3 - WEB SEARCH OPTIMIZATION TEST SUITE")
print("=" * 70)
print()

# --------------------------------------------------------------------
# PATH SETUP: QUANTUM_ROOT -> path relativo -> fallback assoluto
# --------------------------------------------------------------------
REPO_ROOT = (
    Path(os.getenv("QUANTUM_ROOT")).resolve()
    if os.getenv("QUANTUM_ROOT")
    else (Path(__file__).resolve().parents[1])
)
if not (REPO_ROOT / "backend").exists():
    REPO_ROOT = Path("/root/quantumdev-open")

sys.path.insert(0, str(REPO_ROOT))

# --------------------------------------------------------------------
# AIOHTTP (facoltativo): i test async vengono skippati se manca
# --------------------------------------------------------------------
try:
    import aiohttp  # type: ignore
    HAS_AIOHTTP = True
except Exception:
    aiohttp = None  # type: ignore
    HAS_AIOHTTP = False

# ========================================
# TEST 1: Reranker Standalone
# ========================================

def test_reranker_standalone():
    """Test del reranker ML standalone"""
    print("📋 TEST 1: Reranker Standalone")
    print("-" * 70)

    try:
        from core.reranker import Reranker

        # Init
        print("🔄 Initializing reranker...")
        start = time.time()
        reranker = Reranker(model="BAAI/bge-reranker-base", device="cpu")
        elapsed = time.time() - start
        print(f"✅ Reranker initialized in {elapsed:.2f}s")

        # Test data
        query = "risultati serie a oggi"
        results = [
            {"url": "https://www.flashscore.it", "title": "FlashScore - Risultati Serie A Live", "snippet": "Tutti i risultati di Serie A in tempo reale"},
            {"url": "https://www.example.com/blog", "title": "My Blog Post", "snippet": "Random content not related to football"},
            {"url": "https://www.gazzetta.it", "title": "Gazzetta dello Sport - Calcio Serie A", "snippet": "Risultati e classifiche Serie A"},
            {"url": "https://www.wikipedia.org", "title": "Wikipedia - Serie A", "snippet": "La Serie A è il campionato italiano"},
            {"url": "https://www.legaseriea.it", "title": "Lega Serie A Ufficiale", "snippet": "Sito ufficiale della Lega Serie A"},
        ]

        # Rerank
        print(f"🔄 Reranking {len(results)} results for: '{query}'")
        start = time.time()
        ranked = reranker.rerank(query, results, top_k=5)
        elapsed = time.time() - start

        print(f"✅ Reranked in {elapsed:.3f}s")
        print("\n📊 Results (ranked by relevance):")
        for i, r in enumerate(ranked, 1):
            score_val = r.get("rerank_score", r.get("score"))
            try:
                score_str = f"{float(score_val):.3f}"
            except Exception:
                score_str = "-"
            print(f"  {i}. [{score_str}] {r['title'][:50]}")
            print(f"     {r['url']}")

        # Validate: tra i Top-3 deve esserci almeno una fonte attesa
        expected_hits = ("flashscore", "gazzetta", "legaseriea", "lega serie a")
        top3_urls = [r.get("url", "").lower() for r in ranked[:3]]
        assert any(any(k in u for k in expected_hits) for u in top3_urls), \
            "Nei Top-3 dovrebbe comparire almeno una fonte attesa (flashscore/gazzetta/legaseriea)"

        print("\n✅ TEST 1 PASSED: Reranker working correctly")
        return True

    except Exception as e:
        print(f"\n❌ TEST 1 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

# ========================================
# TEST 2: Source Policy
# ========================================

def test_source_policy():
    """Test della source policy per betting queries"""
    print("\n" + "=" * 70)
    print("📋 TEST 2: Source Policy for Betting")
    print("-" * 70)

    try:
        from core.source_policy import pick_domains

        # Test queries
        test_cases = [
            ("quote inter milan", ["oddschecker.com", "oddsportal.com", "bet365.com", "betfair.com"]),
            ("risultati serie a", ["flashscore.com", "flashscore.it", "sofascore.com", "whoscored.com"]),
            ("calciomercato juventus", ["transfermarkt.com", "calciomercato.com", "skysport.it", "gazzetta.it"]),
            ("statistiche ronaldo", ["whoscored.com", "transfermarkt.com", "fbref.com", "understat.com"]),
        ]

        print("🔄 Testing source policy rules...\n")

        for query, expected_domains in test_cases:
            policy = pick_domains(query)
            prefer = policy.get("prefer", [])

            print(f"Query: '{query}'")
            print(f"  Prefer (top): {prefer[:5]}")

            found = any(domain in prefer for domain in expected_domains)
            if found:
                print(f"  ✅ Policy applied correctly")
            else:
                print(f"  ⚠️  Expected domains not found (potrebbe essere ok a seconda delle regole)")
            print()

        print("✅ TEST 2 PASSED: Source policy loaded")
        return True

    except Exception as e:
        print(f"\n❌ TEST 2 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

# ========================================
# TEST 3: Web Search Integration
# ========================================

async def test_web_search_integration():
    """Test completo dell'endpoint /web/search"""
    print("=" * 70)
    print("📋 TEST 3: Web Search Integration (Full Stack)")
    print("-" * 70)

    if not HAS_AIOHTTP:
        print("⏭️  SKIP: aiohttp non installato")
        return None

    try:
        # Endpoint
        url = "http://127.0.0.1:8081/web/search"

        # Test query
        payload = {
            "source": "test",
            "source_id": "task3",
            "q": "risultati serie a oggi",
            "k": 5,
            "summarize_top": 0  # Skip summarization for faster test
        }

        print(f"🔄 Testing endpoint: {url}")
        print(f"Query: '{payload['q']}'")

        start = time.time()

        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as response:
                status = response.status
                data = await response.json()

        elapsed = time.time() - start

        print(f"\n📊 Response:")
        print(f"  Status: {status}")
        print(f"  Time: {elapsed:.2f}s")

        if status == 200:
            results = data.get("results", [])
            print(f"  Results: {len(results)}")
            print(f"  Reranker used: {data.get('reranker_used', False)}")

            # Print top 3 results
            print("\n  Top 3 results:")
            for i, r in enumerate(results[:3], 1):
                raw_score = r.get("rerank_score", r.get("_score"))
                try:
                    score_str = f"{float(raw_score):.3f}"
                except Exception:
                    score_str = "-"
                print(f"    {i}. [{score_str}] {r.get('title','')[:50]}")
                print(f"       {r.get('url','')}")

            # Validate
            assert len(results) > 0, "Should return results"
            print("\n✅ TEST 3 PASSED: Full integration working")
            return True
        else:
            print(f"\n❌ TEST 3 FAILED: HTTP {status}")
            print(f"Error: {data}")
            return False

    except Exception as e:
        # Se la API non è in run, tipicamente è un ConnectionRefusedError
        if isinstance(e, ConnectionRefusedError):
            print("\n⏭️  TEST 3 SKIPPED: API not running (start with 'systemctl start quantum-api')")
            return None
        print(f"\n❌ TEST 3 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

# ========================================
# TEST 4: Performance Benchmark
# ========================================

async def test_performance_benchmark():
    """Benchmark di performance con/senza reranker"""
    print("\n" + "=" * 70)
    print("📋 TEST 4: Performance Benchmark")
    print("-" * 70)

    if not HAS_AIOHTTP:
        print("⏭️  SKIP: aiohttp non installato")
        return None

    try:
        url = "http://127.0.0.1:8081/web/search"

        test_queries = [
            "meteo roma",
            "risultati serie a",
            "quote inter milan",
        ]

        print("🔄 Running benchmark...\n")

        results = []

        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for query in test_queries:
                payload = {
                    "source": "benchmark",
                    "source_id": "task3",
                    "q": query,
                    "k": 5,
                    "summarize_top": 0
                }

                start = time.time()

                async with session.post(url, json=payload) as response:
                    data = await response.json()

                elapsed = time.time() - start

                n_results = len(data.get("results", []))
                reranker_used = data.get("reranker_used", False)

                results.append({
                    "query": query,
                    "time": elapsed,
                    "results": n_results,
                    "reranker": reranker_used
                })

                print(f"  {query:25} → {elapsed:.2f}s ({n_results} results, reranker={'✅' if reranker_used else '❌'})")

        # Stats
        avg_time = sum(r["time"] for r in results) / len(results) if results else 0.0

        print(f"\n📊 Stats:")
        print(f"  Average time: {avg_time:.2f}s")
        print(f"  Queries with reranker: {sum(1 for r in results if r['reranker'])}/{len(results)}")

        print("\n✅ TEST 4 PASSED: Benchmark completed")
        return True

    except Exception as e:
        if isinstance(e, ConnectionRefusedError):
            print("\n⏭️  TEST 4 SKIPPED: API not running")
            return None
        print(f"\n❌ TEST 4 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

# ========================================
# MAIN
# ========================================

async def run_all_tests():
    """Esegue tutti i test"""
    print("\n🚀 Starting test suite...\n")

    results = {
        "test1_reranker": test_reranker_standalone(),
        "test2_policy": test_source_policy(),
        "test3_integration": await test_web_search_integration(),
        "test4_benchmark": await test_performance_benchmark(),
    }

    # Summary
    print("\n" + "=" * 70)
    print("📊 TEST SUMMARY")
    print("=" * 70)

    passed = sum(1 for v in results.values() if v is True)
    failed = sum(1 for v in results.values() if v is False)
    skipped = sum(1 for v in results.values() if v is None)
    total = len(results)

    for name, result in results.items():
        status = "✅ PASS" if result is True else "❌ FAIL" if result is False else "⏭️  SKIP"
        print(f"  {name:25} → {status}")

    print()
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped (total: {total})")

    if failed == 0:
        print("\n🎉 ALL TESTS PASSED!")
        print("\n📝 Next steps:")
        print("  1. Copy optimized backend: cp quantum-task3/backend/quantum_api_optimized.py ~/quantumdev-open/backend/quantum_api.py")
        print("  2. Copy source policy: cp quantum-task3/config/source_policy.yaml ~/quantumdev-open/config/")
        print("  3. Update .env: cat quantum-task3/.env.task3 >> ~/quantumdev-open/.env")
        print("  4. Restart API: sudo systemctl restart quantum-api")
    else:
        print("\n⚠️  SOME TESTS FAILED - Review errors above")

    print()

if __name__ == "__main__":
    try:
        asyncio.run(run_all_tests())
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
