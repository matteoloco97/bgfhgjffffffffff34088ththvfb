#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
core/metrics.py - Prometheus metrics for QuantumDev monitoring

This module defines custom Prometheus metrics for tracking:
- Request counts by endpoint
- Response latencies
- Cache performance
- LLM operations
- Active sessions and resource usage
"""

from prometheus_client import Counter, Histogram, Gauge, Summary
import time
import asyncio
from typing import Callable, Any
from functools import wraps

# ============================================================================
# COUNTER METRICS - Monotonically increasing counts
# ============================================================================

chat_requests_total = Counter(
    'chat_requests_total',
    'Total number of chat requests',
    ['endpoint', 'status']
)

web_searches_total = Counter(
    'web_searches_total',
    'Total number of web search requests',
    ['search_type', 'status']
)

cache_hits_total = Counter(
    'cache_hits_total',
    'Total number of cache hits',
    ['cache_type']
)

cache_misses_total = Counter(
    'cache_misses_total',
    'Total number of cache misses',
    ['cache_type']
)

llm_requests_total = Counter(
    'llm_requests_total',
    'Total number of LLM API requests',
    ['model', 'status']
)

errors_total = Counter(
    'errors_total',
    'Total number of errors',
    ['endpoint', 'error_type']
)

# ============================================================================
# HISTOGRAM METRICS - Distribution of observed values
# ============================================================================

# Buckets: 0.1s, 0.5s, 1s, 2s, 5s, 10s, 30s
LATENCY_BUCKETS = [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]

chat_latency_seconds = Histogram(
    'chat_latency_seconds',
    'Chat endpoint response latency in seconds',
    ['endpoint'],
    buckets=LATENCY_BUCKETS
)

llm_synthesis_seconds = Histogram(
    'llm_synthesis_seconds',
    'LLM synthesis/generation latency in seconds',
    ['model'],
    buckets=LATENCY_BUCKETS
)

web_fetch_seconds = Histogram(
    'web_fetch_seconds',
    'Web content fetch latency in seconds',
    ['source_type'],
    buckets=LATENCY_BUCKETS
)

cache_operation_seconds = Histogram(
    'cache_operation_seconds',
    'Cache operation latency in seconds',
    ['operation', 'cache_type'],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0]
)

# ============================================================================
# GAUGE METRICS - Values that can go up and down
# ============================================================================

active_sessions = Gauge(
    'active_sessions',
    'Number of active chat sessions'
)

cache_size_bytes = Gauge(
    'cache_size_bytes',
    'Current cache size in bytes',
    ['cache_type']
)

llm_queue_size = Gauge(
    'llm_queue_size',
    'Number of requests waiting in LLM queue'
)

# Additional gauges for resource monitoring
memory_usage_bytes = Gauge(
    'memory_usage_bytes',
    'Current memory usage in bytes'
)

redis_connections = Gauge(
    'redis_connections',
    'Number of active Redis connections'
)

# ============================================================================
# SUMMARY METRICS - Similar to histogram but with configurable quantiles
# ============================================================================

response_size_bytes = Summary(
    'response_size_bytes',
    'Size of API responses in bytes',
    ['endpoint']
)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def track_chat_request(endpoint: str, status: str = "success"):
    """Track a chat request."""
    chat_requests_total.labels(endpoint=endpoint, status=status).inc()


def track_web_search(search_type: str = "general", status: str = "success"):
    """Track a web search request."""
    web_searches_total.labels(search_type=search_type, status=status).inc()


def track_cache_hit(cache_type: str = "redis"):
    """Track a cache hit."""
    cache_hits_total.labels(cache_type=cache_type).inc()


def track_cache_miss(cache_type: str = "redis"):
    """Track a cache miss."""
    cache_misses_total.labels(cache_type=cache_type).inc()


def track_llm_request(model: str = "gpt-4", status: str = "success"):
    """Track an LLM API request."""
    llm_requests_total.labels(model=model, status=status).inc()


def track_error(endpoint: str, error_type: str):
    """Track an error occurrence."""
    errors_total.labels(endpoint=endpoint, error_type=error_type).inc()


def observe_chat_latency(endpoint: str, duration: float):
    """Observe chat endpoint latency."""
    chat_latency_seconds.labels(endpoint=endpoint).observe(duration)


def observe_llm_synthesis(model: str, duration: float):
    """Observe LLM synthesis latency."""
    llm_synthesis_seconds.labels(model=model).observe(duration)


def observe_web_fetch(source_type: str, duration: float):
    """Observe web fetch latency."""
    web_fetch_seconds.labels(source_type=source_type).observe(duration)


def observe_cache_operation(operation: str, cache_type: str, duration: float):
    """Observe cache operation latency."""
    cache_operation_seconds.labels(operation=operation, cache_type=cache_type).observe(duration)


def observe_response_size(endpoint: str, size_bytes: int):
    """Observe response size."""
    response_size_bytes.labels(endpoint=endpoint).observe(size_bytes)


def set_active_sessions(count: int):
    """Set the number of active sessions."""
    active_sessions.set(count)


def set_cache_size(cache_type: str, size_bytes: int):
    """Set cache size."""
    cache_size_bytes.labels(cache_type=cache_type).set(size_bytes)


def set_llm_queue_size(count: int):
    """Set LLM queue size."""
    llm_queue_size.set(count)


def set_memory_usage(bytes_used: int):
    """Set memory usage."""
    memory_usage_bytes.set(bytes_used)


def set_redis_connections(count: int):
    """Set Redis connection count."""
    redis_connections.set(count)


# ============================================================================
# DECORATORS FOR AUTOMATIC METRIC TRACKING
# ============================================================================

def track_latency(metric_name: str, **labels):
    """
    Decorator to automatically track function execution latency.
    
    Args:
        metric_name: Name of the metric to use ('chat', 'llm', 'web', 'cache')
        **labels: Labels to apply to the metric
    
    Example:
        @track_latency('chat', endpoint='/chat')
        async def chat_handler():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                duration = time.perf_counter() - start_time
                
                if metric_name == 'chat':
                    observe_chat_latency(labels.get('endpoint', 'unknown'), duration)
                elif metric_name == 'llm':
                    observe_llm_synthesis(labels.get('model', 'unknown'), duration)
                elif metric_name == 'web':
                    observe_web_fetch(labels.get('source_type', 'unknown'), duration)
                elif metric_name == 'cache':
                    observe_cache_operation(
                        labels.get('operation', 'unknown'),
                        labels.get('cache_type', 'unknown'),
                        duration
                    )
                
                return result
            except Exception as e:
                duration = time.perf_counter() - start_time
                # Still track the latency even on error
                if metric_name == 'chat':
                    observe_chat_latency(labels.get('endpoint', 'unknown'), duration)
                raise e
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                duration = time.perf_counter() - start_time
                
                if metric_name == 'chat':
                    observe_chat_latency(labels.get('endpoint', 'unknown'), duration)
                elif metric_name == 'llm':
                    observe_llm_synthesis(labels.get('model', 'unknown'), duration)
                elif metric_name == 'web':
                    observe_web_fetch(labels.get('source_type', 'unknown'), duration)
                elif metric_name == 'cache':
                    observe_cache_operation(
                        labels.get('operation', 'unknown'),
                        labels.get('cache_type', 'unknown'),
                        duration
                    )
                
                return result
            except Exception as e:
                duration = time.perf_counter() - start_time
                # Still track the latency even on error
                if metric_name == 'chat':
                    observe_chat_latency(labels.get('endpoint', 'unknown'), duration)
                raise e
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def track_request(endpoint: str, request_type: str = "chat"):
    """
    Decorator to automatically track requests.
    
    Args:
        endpoint: Endpoint being called
        request_type: Type of request ('chat', 'web_search', etc.)
    
    Example:
        @track_request('/chat', 'chat')
        async def chat_handler():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                result = await func(*args, **kwargs)
                if request_type == "chat":
                    track_chat_request(endpoint, "success")
                elif request_type == "web_search":
                    track_web_search("general", "success")
                return result
            except Exception as e:
                if request_type == "chat":
                    track_chat_request(endpoint, "error")
                elif request_type == "web_search":
                    track_web_search("general", "error")
                raise e
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                if request_type == "chat":
                    track_chat_request(endpoint, "success")
                elif request_type == "web_search":
                    track_web_search("general", "success")
                return result
            except Exception as e:
                if request_type == "chat":
                    track_chat_request(endpoint, "error")
                elif request_type == "web_search":
                    track_web_search("general", "error")
                raise e
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator
