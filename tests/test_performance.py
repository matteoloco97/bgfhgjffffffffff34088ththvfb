#!/usr/bin/env python3
# tests/test_performance.py — Performance benchmark web search pipeline

import sys
import asyncio
import time
import statistics
from typing import List, Dict, Any

sys.path.insert(0, "/root/quantumdev-open")

# Test queries (mix di velocità)
TEST_QUERIES = [
    ("prezzo bitcoin", "fast_live"),
    ("meteo roma", "fast_live"),
    ("risultati serie a", "fast_live"),
    ("artificial intelligence trends 2024", "medium_general"),
    ("quantum computing applications", "medium_general"),
    ("climate change impact europe", "slow_complex"),
    ("latest developments machine learning", "slow_complex"),
]


async def benchmark_query(query: str, category: str) -> Dict[str, Any]:
    """Benchmark singola query con debug avanzato"""
    from backend.quantum_api import _web_search_pipeline

    t_start = time.perf_counter()

    try:
        result = await _web_search_pipeline(
            q=query,
            src="test",
            sid="benchmark",
            k=6,
            nsum=3,
        )

        latency_ms = (time.perf_counter() - t_start) * 1000.0

        stats = result.get("stats", {}) or {}
        note = result.get("note")
        error = result.get("error")
        summary = result.get("summary") or ""

        return {
            "query": query,
            "category": category,
            "latency_ms": latency_ms,
            "success": bool(summary.strip()),
            "summary_len": len(summary),
            "results_count": len(result.get("results", [])),
            "fetch_ok": stats.get("fetch_ok", 0),
            "fetch_attempted": stats.get("fetch_attempted", 0),
            "fetch_duration_ms": stats.get("fetch_duration_ms", 0),
            "early_exit": stats.get("early_exit", False),
            "note": note,
            "error": error,
        }
    except Exception as e:
        latency_ms = (time.perf_counter() - t_start) * 1000.0
        return {
            "query": query,
            "category": category,
            "latency_ms": latency_ms,
            "success": False,
            "summary_len": 0,
            "results_count": 0,
            "fetch_ok": 0,
            "fetch_attempted": 0,
            "fetch_duration_ms": 0,
            "early_exit": False,
            "note": None,
            "error": str(e),
        }


async def run_benchmark() -> int:
    print("⚡ WEB SEARCH PERFORMANCE BENCHMARK")
    print("=" * 70)

    results: List[Dict[str, Any]] = []

    for i, (query, category) in enumerate(TEST_QUERIES, 1):
        print(f"\n[{i}/{len(TEST_QUERIES)}] Testing: {query}")
        print(f"  Category: {category}")

        # Warm-up run (non contato)
        _ = await benchmark_query(query, category)
        await asyncio.sleep(0.5)

        # 3 run effettivi
        runs: List[Dict[str, Any]] = []
        for run in range(3):
            result = await benchmark_query(query, category)
            runs.append(result)

            status = "✅" if result["success"] else "❌"
            print(
                f"  Run {run+1}: {result['latency_ms']:.0f}ms {status} | "
                f"res={result['results_count']} "
                f"fetch_ok={result['fetch_ok']}/{result['fetch_attempted']} "
                f"fetch_ms={result['fetch_duration_ms']} "
                f"note={result['note']} "
                f"err={result['error'] or '-'}"
            )
            await asyncio.sleep(0.3)

        # Media runs
        avg_latency = statistics.mean(r["latency_ms"] for r in runs)
        success_rate = sum(1 for r in runs if r["success"]) / len(runs)

        results.append(
            {
                "query": query,
                "category": category,
                "avg_latency_ms": avg_latency,
                "success_rate": success_rate,
                "runs": runs,
            }
        )

    # === REPORT ===
    print("\n" + "=" * 70)
    print("📊 PERFORMANCE REPORT")
    print("=" * 70)

    all_latencies = [r["avg_latency_ms"] for r in results]

    print(f"\n⏱️  LATENCY METRICS:")
    print(f"  Mean:   {statistics.mean(all_latencies):.0f}ms")
    print(f"  Median: {statistics.median(all_latencies):.0f}ms")
    print(
        f"  p90:    "
        f"{sorted(all_latencies)[int(len(all_latencies)*0.9)]:.0f}ms"
    )
    print(
        f"  p95:    "
        f"{sorted(all_latencies)[int(len(all_latencies)*0.95)]:.0f}ms"
    )
    print(f"  Max:    {max(all_latencies):.0f}ms")

    # Per categoria
    print(f"\n📂 BY CATEGORY:")
    for cat in ["fast_live", "medium_general", "slow_complex"]:
        cat_results = [r for r in results if r["category"] == cat]
        if cat_results:
            cat_latencies = [r["avg_latency_ms"] for r in cat_results]
            print(f"  {cat:20}: {statistics.mean(cat_latencies):.0f}ms avg")

    # Success rate
    success_rate_global = statistics.mean(r["success_rate"] for r in results)
    print(f"\n✅ SUCCESS RATE: {success_rate_global*100:.1f}%")

    # Early exit rate
    early_exits = sum(
        1 for r in results for run in r["runs"] if run.get("early_exit")
    )
    total_runs = sum(len(r["runs"]) for r in results)
    early_rate = (early_exits / total_runs * 100.0) if total_runs else 0.0
    print(f"⚡ EARLY EXIT RATE: {early_exits}/{total_runs} ({early_rate:.1f}%)")

    # Target check
    p95 = sorted(all_latencies)[int(len(all_latencies) * 0.95)]

    print(f"\n🎯 TARGET CHECK:")
    success_flag = True

    if p95 < 3000:
        print(f"  ✅ p95 latency: {p95:.0f}ms < 3000ms TARGET")
    else:
        print(f"  ❌ p95 latency: {p95:.0f}ms >= 3000ms TARGET")
        success_flag = False

    if success_rate_global >= 0.85:
        print(
            f"  ✅ Success rate: "
            f"{success_rate_global*100:.1f}% >= 85% TARGET"
        )
    else:
        print(
            f"  ❌ Success rate: "
            f"{success_rate_global*100:.1f}% < 85% TARGET"
        )
        success_flag = False

    print("\n" + "=" * 70)
    if success_flag:
        print("🎉 PERFORMANCE TARGETS MET!")
        return 0
    else:
        print("⚠️  PERFORMANCE BELOW TARGET")
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_benchmark()))
