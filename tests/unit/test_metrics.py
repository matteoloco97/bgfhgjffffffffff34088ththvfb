#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
tests/unit/test_metrics.py - Unit tests for Prometheus metrics.

Tests for metric registration, tracking, helper functions, and decorators.
"""

import os
import sys
import time
import asyncio
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

# Add project root to path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ============================================================================
# IMPORT TESTS
# ============================================================================

class TestMetricsImports:
    """Tests for metrics module imports."""
    
    def test_import_counter_metrics(self):
        """Test counter metrics can be imported."""
        from core.metrics import (
            chat_requests_total,
            web_searches_total,
            cache_hits_total,
            cache_misses_total,
            llm_requests_total,
            errors_total,
        )
        
        assert chat_requests_total is not None
        assert web_searches_total is not None
        assert cache_hits_total is not None
        assert cache_misses_total is not None
        assert llm_requests_total is not None
        assert errors_total is not None
    
    def test_import_histogram_metrics(self):
        """Test histogram metrics can be imported."""
        from core.metrics import (
            chat_latency_seconds,
            llm_synthesis_seconds,
            web_fetch_seconds,
            cache_operation_seconds,
        )
        
        assert chat_latency_seconds is not None
        assert llm_synthesis_seconds is not None
        assert web_fetch_seconds is not None
        assert cache_operation_seconds is not None
    
    def test_import_gauge_metrics(self):
        """Test gauge metrics can be imported."""
        from core.metrics import (
            active_sessions,
            cache_size_bytes,
            llm_queue_size,
            memory_usage_bytes,
            redis_connections,
        )
        
        assert active_sessions is not None
        assert cache_size_bytes is not None
        assert llm_queue_size is not None
        assert memory_usage_bytes is not None
        assert redis_connections is not None
    
    def test_import_summary_metrics(self):
        """Test summary metrics can be imported."""
        from core.metrics import response_size_bytes
        
        assert response_size_bytes is not None
    
    def test_import_helper_functions(self):
        """Test helper functions can be imported."""
        from core.metrics import (
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
        
        assert callable(track_chat_request)
        assert callable(track_web_search)
        assert callable(track_cache_hit)
        assert callable(track_cache_miss)
        assert callable(track_llm_request)
        assert callable(track_error)


# ============================================================================
# COUNTER METRIC TESTS
# ============================================================================

class TestCounterMetrics:
    """Tests for counter metrics functionality."""
    
    def test_track_chat_request(self):
        """Test tracking chat requests."""
        from core.metrics import track_chat_request, chat_requests_total
        
        # Track a request
        track_chat_request("/chat", "success")
        
        # Verify metric was incremented (counter value can only be checked via prometheus_client)
        # Just verify it doesn't raise
        assert True
    
    def test_track_chat_request_with_error(self):
        """Test tracking chat requests with error status."""
        from core.metrics import track_chat_request
        
        track_chat_request("/chat", "error")
        
        # Should not raise
        assert True
    
    def test_track_web_search(self):
        """Test tracking web searches."""
        from core.metrics import track_web_search
        
        track_web_search("standard", "success")
        track_web_search("deep", "success")
        track_web_search("standard", "error")
        
        # Should not raise
        assert True
    
    def test_track_cache_hit(self):
        """Test tracking cache hits."""
        from core.metrics import track_cache_hit
        
        track_cache_hit("redis")
        track_cache_hit("memory")
        
        # Should not raise
        assert True
    
    def test_track_cache_miss(self):
        """Test tracking cache misses."""
        from core.metrics import track_cache_miss
        
        track_cache_miss("redis")
        
        # Should not raise
        assert True
    
    def test_track_llm_request(self):
        """Test tracking LLM requests."""
        from core.metrics import track_llm_request
        
        track_llm_request("gpt-4", "success")
        track_llm_request("gpt-3.5-turbo", "error")
        
        # Should not raise
        assert True
    
    def test_track_error(self):
        """Test tracking errors."""
        from core.metrics import track_error
        
        track_error("/chat", "timeout")
        track_error("/web/search", "validation_error")
        
        # Should not raise
        assert True


# ============================================================================
# HISTOGRAM METRIC TESTS
# ============================================================================

class TestHistogramMetrics:
    """Tests for histogram metrics functionality."""
    
    def test_observe_chat_latency(self):
        """Test observing chat latency."""
        from core.metrics import observe_chat_latency
        
        observe_chat_latency("/chat", 0.5)
        observe_chat_latency("/chat", 1.2)
        observe_chat_latency("/unified", 0.3)
        
        # Should not raise
        assert True
    
    def test_observe_llm_synthesis(self):
        """Test observing LLM synthesis latency."""
        from core.metrics import observe_llm_synthesis
        
        observe_llm_synthesis("gpt-4", 2.5)
        observe_llm_synthesis("gpt-3.5-turbo", 1.1)
        
        # Should not raise
        assert True
    
    def test_observe_web_fetch(self):
        """Test observing web fetch latency."""
        from core.metrics import observe_web_fetch
        
        observe_web_fetch("web", 3.2)
        observe_web_fetch("api", 0.5)
        
        # Should not raise
        assert True
    
    def test_observe_cache_operation(self):
        """Test observing cache operation latency."""
        from core.metrics import observe_cache_operation
        
        observe_cache_operation("get", "redis", 0.01)
        observe_cache_operation("set", "redis", 0.02)
        observe_cache_operation("get", "memory", 0.001)
        
        # Should not raise
        assert True
    
    def test_latency_buckets_defined(self):
        """Test that latency buckets are defined."""
        from core.metrics import LATENCY_BUCKETS
        
        assert isinstance(LATENCY_BUCKETS, (list, tuple))
        assert len(LATENCY_BUCKETS) > 0
        # Buckets should be in ascending order
        assert LATENCY_BUCKETS == sorted(LATENCY_BUCKETS)


# ============================================================================
# GAUGE METRIC TESTS
# ============================================================================

class TestGaugeMetrics:
    """Tests for gauge metrics functionality."""
    
    def test_set_active_sessions(self):
        """Test setting active sessions gauge."""
        from core.metrics import set_active_sessions
        
        set_active_sessions(42)
        set_active_sessions(0)
        set_active_sessions(100)
        
        # Should not raise
        assert True
    
    def test_set_cache_size(self):
        """Test setting cache size gauge."""
        from core.metrics import set_cache_size
        
        set_cache_size("redis", 1024 * 1024 * 10)  # 10 MB
        set_cache_size("memory", 1024 * 1024)  # 1 MB
        
        # Should not raise
        assert True
    
    def test_set_llm_queue_size(self):
        """Test setting LLM queue size gauge."""
        from core.metrics import set_llm_queue_size
        
        set_llm_queue_size(5)
        set_llm_queue_size(0)
        
        # Should not raise
        assert True
    
    def test_set_memory_usage(self):
        """Test setting memory usage gauge."""
        from core.metrics import set_memory_usage
        
        set_memory_usage(512 * 1024 * 1024)  # 512 MB
        
        # Should not raise
        assert True
    
    def test_set_redis_connections(self):
        """Test setting Redis connections gauge."""
        from core.metrics import set_redis_connections
        
        set_redis_connections(10)
        set_redis_connections(5)
        
        # Should not raise
        assert True


# ============================================================================
# SUMMARY METRIC TESTS
# ============================================================================

class TestSummaryMetrics:
    """Tests for summary metrics functionality."""
    
    def test_observe_response_size(self):
        """Test observing response size."""
        from core.metrics import observe_response_size
        
        observe_response_size("/chat", 1024)
        observe_response_size("/chat", 2048)
        observe_response_size("/web/search", 4096)
        
        # Should not raise
        assert True


# ============================================================================
# DECORATOR TESTS
# ============================================================================

class TestMetricDecorators:
    """Tests for metric tracking decorators."""
    
    def test_track_latency_decorator_import(self):
        """Test track_latency decorator can be imported."""
        from core.metrics import track_latency
        
        assert callable(track_latency)
    
    def test_track_request_decorator_import(self):
        """Test track_request decorator can be imported."""
        from core.metrics import track_request
        
        assert callable(track_request)
    
    @pytest.mark.asyncio
    async def test_track_latency_async_function(self):
        """Test track_latency decorator on async function."""
        from core.metrics import track_latency
        
        @track_latency('chat', endpoint='/test')
        async def async_handler():
            await asyncio.sleep(0.01)
            return {"result": "success"}
        
        result = await async_handler()
        
        assert result == {"result": "success"}
    
    def test_track_latency_sync_function(self):
        """Test track_latency decorator on sync function."""
        from core.metrics import track_latency
        
        @track_latency('web', source_type='test')
        def sync_handler():
            time.sleep(0.01)
            return {"result": "success"}
        
        result = sync_handler()
        
        assert result == {"result": "success"}
    
    @pytest.mark.asyncio
    async def test_track_latency_on_error(self):
        """Test track_latency still records on error."""
        from core.metrics import track_latency
        
        @track_latency('chat', endpoint='/test')
        async def failing_handler():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            await failing_handler()
    
    @pytest.mark.asyncio
    async def test_track_request_async_success(self):
        """Test track_request decorator on async function success."""
        from core.metrics import track_request
        
        @track_request('/test', 'chat')
        async def async_handler():
            return {"result": "success"}
        
        result = await async_handler()
        
        assert result == {"result": "success"}
    
    @pytest.mark.asyncio
    async def test_track_request_async_error(self):
        """Test track_request decorator on async function error."""
        from core.metrics import track_request
        
        @track_request('/test', 'chat')
        async def failing_handler():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            await failing_handler()
    
    def test_track_request_sync_success(self):
        """Test track_request decorator on sync function success."""
        from core.metrics import track_request
        
        @track_request('/test', 'web_search')
        def sync_handler():
            return {"result": "success"}
        
        result = sync_handler()
        
        assert result == {"result": "success"}


# ============================================================================
# PROMETHEUS EXPORT TESTS
# ============================================================================

class TestPrometheusExport:
    """Tests for Prometheus metrics export."""
    
    def test_generate_latest(self):
        """Test generating Prometheus metrics output."""
        from prometheus_client import generate_latest
        
        output = generate_latest()
        
        assert isinstance(output, bytes)
        assert len(output) > 0
    
    def test_metrics_in_export(self):
        """Test that our metrics appear in export."""
        from prometheus_client import generate_latest
        from core.metrics import track_chat_request
        
        # Track something to ensure metrics exist
        track_chat_request("/test", "success")
        
        output = generate_latest().decode('utf-8')
        
        # Should contain our custom metrics
        assert 'chat_requests_total' in output
    
    def test_export_contains_expected_metrics(self):
        """Test that export contains expected metric names."""
        from prometheus_client import generate_latest
        
        output = generate_latest().decode('utf-8')
        
        expected_metrics = [
            'chat_requests_total',
            'cache_hits_total',
            'active_sessions',
        ]
        
        for metric in expected_metrics:
            assert metric in output, f"Missing metric: {metric}"


# ============================================================================
# METRIC LABELS TESTS
# ============================================================================

class TestMetricLabels:
    """Tests for metric labels."""
    
    def test_chat_requests_labels(self):
        """Test chat_requests_total has correct labels."""
        from core.metrics import chat_requests_total
        
        # Counter should have labels defined
        assert hasattr(chat_requests_total, 'labels')
    
    def test_cache_hits_labels(self):
        """Test cache_hits_total has correct labels."""
        from core.metrics import cache_hits_total
        
        # Should be able to call with cache_type label
        cache_hits_total.labels(cache_type="test").inc()
    
    def test_histogram_labels(self):
        """Test histogram metrics have correct labels."""
        from core.metrics import chat_latency_seconds
        
        # Should be able to observe with endpoint label
        chat_latency_seconds.labels(endpoint="/test").observe(0.5)


# ============================================================================
# EDGE CASES
# ============================================================================

class TestMetricsEdgeCases:
    """Tests for metrics edge cases."""
    
    def test_zero_latency(self):
        """Test observing zero latency."""
        from core.metrics import observe_chat_latency
        
        observe_chat_latency("/chat", 0.0)
        
        # Should not raise
        assert True
    
    def test_very_large_latency(self):
        """Test observing very large latency."""
        from core.metrics import observe_chat_latency
        
        observe_chat_latency("/chat", 1000.0)
        
        # Should not raise
        assert True
    
    def test_negative_gauge_value(self):
        """Test setting negative gauge value."""
        from core.metrics import set_llm_queue_size
        
        # While unusual, should not raise
        set_llm_queue_size(-1)
    
    def test_unicode_labels(self):
        """Test metrics with unicode in labels."""
        from core.metrics import track_error
        
        # Should handle unicode
        track_error("/test", "error_日本語")
        
        # Should not raise
        assert True
    
    def test_empty_string_labels(self):
        """Test metrics with empty string labels."""
        from core.metrics import track_chat_request
        
        track_chat_request("", "")
        
        # Should not raise
        assert True
    
    def test_concurrent_metric_updates(self):
        """Test concurrent metric updates."""
        from core.metrics import track_chat_request
        import threading
        
        def update_metrics():
            for _ in range(100):
                track_chat_request("/chat", "success")
        
        threads = [threading.Thread(target=update_metrics) for _ in range(5)]
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join()
        
        # Should not raise
        assert True


# ============================================================================
# DECORATOR EDGE CASES
# ============================================================================

class TestDecoratorEdgeCases:
    """Tests for decorator edge cases."""
    
    def test_decorator_preserves_function_name(self):
        """Test that decorators preserve function name."""
        from core.metrics import track_latency
        
        @track_latency('chat', endpoint='/test')
        def my_function():
            pass
        
        assert my_function.__name__ == 'my_function'
    
    @pytest.mark.asyncio
    async def test_async_decorator_preserves_name(self):
        """Test async decorator preserves function name."""
        from core.metrics import track_latency
        
        @track_latency('chat', endpoint='/test')
        async def my_async_function():
            pass
        
        assert my_async_function.__name__ == 'my_async_function'
    
    def test_multiple_decorators(self):
        """Test multiple decorators on same function."""
        from core.metrics import track_latency, track_request
        
        @track_request('/test', 'chat')
        @track_latency('chat', endpoint='/test')
        def double_decorated():
            return "result"
        
        result = double_decorated()
        
        assert result == "result"
