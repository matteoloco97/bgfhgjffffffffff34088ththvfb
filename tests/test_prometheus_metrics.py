#!/usr/bin/env python3
"""
Test script for Prometheus metrics integration

This script verifies that:
1. Metrics module imports correctly
2. Custom metrics are registered
3. Metrics can be tracked
4. Metrics are exported in Prometheus format
"""

import sys
sys.path.insert(0, '/home/runner/work/bgfhgjffffffffff34088ththvfb/bgfhgjffffffffff34088ththvfb')

from core.metrics import (
    # Counter metrics
    chat_requests_total,
    web_searches_total,
    cache_hits_total,
    cache_misses_total,
    llm_requests_total,
    errors_total,
    # Histogram metrics
    chat_latency_seconds,
    llm_synthesis_seconds,
    web_fetch_seconds,
    cache_operation_seconds,
    # Gauge metrics
    active_sessions,
    cache_size_bytes,
    llm_queue_size,
    memory_usage_bytes,
    redis_connections,
    # Summary metrics
    response_size_bytes,
    # Helper functions
    track_chat_request,
    track_web_search,
    track_cache_hit,
    track_cache_miss,
    track_llm_request,
    track_error,
    observe_chat_latency,
    observe_llm_synthesis,
    observe_web_fetch,
    observe_cache_operation,
    observe_response_size,
    set_active_sessions,
    set_cache_size,
    set_llm_queue_size,
    set_memory_usage,
    set_redis_connections,
)

from prometheus_client import generate_latest

def test_counter_metrics():
    """Test counter metrics"""
    print("\n=== Testing Counter Metrics ===")
    
    # Track some requests
    track_chat_request("/chat", "success")
    track_chat_request("/chat", "success")
    track_chat_request("/chat", "error")
    
    track_web_search("standard", "success")
    track_web_search("deep", "success")
    
    track_cache_hit("redis")
    track_cache_hit("redis")
    track_cache_miss("redis")
    
    track_llm_request("gpt-4", "success")
    track_error("/chat", "timeout")
    
    print("✓ Counter metrics tracked successfully")

def test_histogram_metrics():
    """Test histogram metrics"""
    print("\n=== Testing Histogram Metrics ===")
    
    # Track latencies
    observe_chat_latency("/chat", 0.5)
    observe_chat_latency("/chat", 1.2)
    observe_chat_latency("/chat", 0.3)
    
    observe_llm_synthesis("gpt-4", 2.5)
    observe_llm_synthesis("gpt-3.5-turbo", 1.1)
    
    observe_web_fetch("web", 3.2)
    observe_cache_operation("get", "redis", 0.01)
    
    print("✓ Histogram metrics observed successfully")

def test_gauge_metrics():
    """Test gauge metrics"""
    print("\n=== Testing Gauge Metrics ===")
    
    set_active_sessions(42)
    set_cache_size("redis", 1024 * 1024 * 10)  # 10 MB
    set_llm_queue_size(5)
    set_memory_usage(512 * 1024 * 1024)  # 512 MB
    set_redis_connections(10)
    
    print("✓ Gauge metrics set successfully")

def test_summary_metrics():
    """Test summary metrics"""
    print("\n=== Testing Summary Metrics ===")
    
    observe_response_size("/chat", 1024)
    observe_response_size("/chat", 2048)
    observe_response_size("/web/search", 4096)
    
    print("✓ Summary metrics observed successfully")

def test_metrics_export():
    """Test metrics export in Prometheus format"""
    print("\n=== Testing Metrics Export ===")
    
    metrics_output = generate_latest().decode('utf-8')
    
    # Check that all custom metrics are present
    expected_metrics = [
        'chat_requests_total',
        'web_searches_total',
        'cache_hits_total',
        'cache_misses_total',
        'llm_requests_total',
        'errors_total',
        'chat_latency_seconds',
        'llm_synthesis_seconds',
        'web_fetch_seconds',
        'cache_operation_seconds',
        'active_sessions',
        'cache_size_bytes',
        'llm_queue_size',
        'memory_usage_bytes',
        'redis_connections',
        'response_size_bytes',
    ]
    
    missing_metrics = []
    for metric in expected_metrics:
        if metric not in metrics_output:
            missing_metrics.append(metric)
    
    if missing_metrics:
        print(f"✗ Missing metrics: {missing_metrics}")
        return False
    
    print("✓ All expected metrics present in export")
    
    # Print sample of metrics
    print("\n=== Sample Metrics Output ===")
    lines = metrics_output.split('\n')
    for line in lines:
        if any(m in line for m in ['chat_requests_total', 'chat_latency_seconds', 'active_sessions']):
            if line and not line.startswith('#'):
                print(line)
    
    return True

def main():
    """Run all tests"""
    print("=" * 60)
    print("Prometheus Metrics Integration Test")
    print("=" * 60)
    
    try:
        test_counter_metrics()
        test_histogram_metrics()
        test_gauge_metrics()
        test_summary_metrics()
        
        success = test_metrics_export()
        
        print("\n" + "=" * 60)
        if success:
            print("✅ ALL TESTS PASSED")
        else:
            print("❌ SOME TESTS FAILED")
        print("=" * 60)
        
        return 0 if success else 1
        
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
