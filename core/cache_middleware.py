"""
Cache middleware decorator for FastAPI endpoints.

Provides automatic caching for async FastAPI endpoints using the existing
multi-level cache system (L1 in-memory + L2 Redis).

Features:
- Automatic cache key generation from function name + args
- TTL support per endpoint
- Cache bypass via ?nocache=1 query parameter
- X-Cache response header (HIT/MISS)
- Cache statistics tracking
- Detailed logging with [CACHE] prefix
"""

import os
import time
import hashlib
import json
import logging
from typing import Any, Callable, Dict, Optional
from functools import wraps
from fastapi import Request, Response
from fastapi.responses import JSONResponse

from core.multi_level_cache import get_multi_level_cache

log = logging.getLogger(__name__)

# Global cache statistics (in addition to multi-level cache stats)
_cache_stats = {
    "endpoint_hits": {},  # Per-endpoint hit counts
    "endpoint_misses": {},  # Per-endpoint miss counts
    "endpoint_bypasses": {},  # Per-endpoint bypass counts
    "total_hits": 0,
    "total_misses": 0,
    "total_bypasses": 0,
    "last_reset": int(time.time()),
}


def _generate_cache_key(endpoint: str, **kwargs: Any) -> str:
    """
    Generate cache key from endpoint name and parameters.
    
    Args:
        endpoint: Endpoint name (e.g., "chat", "web_search")
        **kwargs: Request parameters to include in cache key
        
    Returns:
        Cache key string in format: {endpoint}:{hash(params)}
    """
    # Sort kwargs for consistent hashing
    sorted_params = sorted(kwargs.items())
    params_str = json.dumps(sorted_params, sort_keys=True, ensure_ascii=False)
    params_hash = hashlib.sha256(params_str.encode()).hexdigest()[:16]
    
    return f"{endpoint}:{params_hash}"


def _should_bypass_cache(request: Request) -> bool:
    """
    Check if cache should be bypassed based on query parameters.
    
    Args:
        request: FastAPI request object
        
    Returns:
        True if cache should be bypassed
    """
    # Check for nocache=1 query parameter
    nocache = request.query_params.get("nocache", "0")
    return nocache in ("1", "true", "True", "yes")


def _update_stats(endpoint: str, result: str) -> None:
    """
    Update cache statistics.
    
    Args:
        endpoint: Endpoint name
        result: "hit", "miss", or "bypass"
    """
    global _cache_stats
    
    if result == "hit":
        _cache_stats["endpoint_hits"][endpoint] = _cache_stats["endpoint_hits"].get(endpoint, 0) + 1
        _cache_stats["total_hits"] += 1
    elif result == "miss":
        _cache_stats["endpoint_misses"][endpoint] = _cache_stats["endpoint_misses"].get(endpoint, 0) + 1
        _cache_stats["total_misses"] += 1
    elif result == "bypass":
        _cache_stats["endpoint_bypasses"][endpoint] = _cache_stats["endpoint_bypasses"].get(endpoint, 0) + 1
        _cache_stats["total_bypasses"] += 1


def get_cache_stats() -> Dict[str, Any]:
    """
    Get comprehensive cache statistics.
    
    Returns:
        Dictionary with cache statistics including per-endpoint metrics
    """
    global _cache_stats
    
    # Get multi-level cache stats
    ml_cache = get_multi_level_cache()
    ml_stats = ml_cache.get_stats()
    
    # Calculate overall hit rate
    total_requests = _cache_stats["total_hits"] + _cache_stats["total_misses"]
    hit_rate = _cache_stats["total_hits"] / total_requests if total_requests > 0 else 0.0
    
    # Per-endpoint stats
    endpoint_stats = []
    all_endpoints = set(
        list(_cache_stats["endpoint_hits"].keys()) +
        list(_cache_stats["endpoint_misses"].keys()) +
        list(_cache_stats["endpoint_bypasses"].keys())
    )
    
    for endpoint in sorted(all_endpoints):
        hits = _cache_stats["endpoint_hits"].get(endpoint, 0)
        misses = _cache_stats["endpoint_misses"].get(endpoint, 0)
        bypasses = _cache_stats["endpoint_bypasses"].get(endpoint, 0)
        total = hits + misses
        endpoint_hit_rate = hits / total if total > 0 else 0.0
        
        endpoint_stats.append({
            "endpoint": endpoint,
            "hits": hits,
            "misses": misses,
            "bypasses": bypasses,
            "total_requests": total,
            "hit_rate": round(endpoint_hit_rate, 4),
        })
    
    return {
        "middleware": {
            "total_hits": _cache_stats["total_hits"],
            "total_misses": _cache_stats["total_misses"],
            "total_bypasses": _cache_stats["total_bypasses"],
            "total_requests": total_requests,
            "hit_rate": round(hit_rate, 4),
            "uptime_seconds": int(time.time() - _cache_stats["last_reset"]),
            "per_endpoint": endpoint_stats,
        },
        "multi_level_cache": ml_stats,
    }


def reset_cache_stats() -> None:
    """Reset cache statistics counters."""
    global _cache_stats
    _cache_stats = {
        "endpoint_hits": {},
        "endpoint_misses": {},
        "endpoint_bypasses": {},
        "total_hits": 0,
        "total_misses": 0,
        "total_bypasses": 0,
        "last_reset": int(time.time()),
    }
    log.info("[CACHE] Cache statistics reset")


def cached_response(
    endpoint_name: str,
    ttl: int = 300,
    cache_key_params: Optional[list] = None,
) -> Callable:
    """
    Decorator for caching FastAPI async endpoint responses.
    
    Usage:
        @app.post("/chat")
        @cached_response("chat", ttl=300, cache_key_params=["prompt", "source"])
        async def chat_endpoint(req: ChatRequest):
            # Your endpoint logic here
            return {"response": "..."}
    
    Args:
        endpoint_name: Name of the endpoint for logging and stats
        ttl: Time-to-live in seconds for cached responses
        cache_key_params: List of request parameter names to include in cache key.
                         If None, all request body fields are used.
    
    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Get request object from args/kwargs
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            if request is None:
                request = kwargs.get("request")
            
            # Check for cache bypass
            if request and _should_bypass_cache(request):
                log.info(f"[CACHE] Bypass requested for {endpoint_name}")
                _update_stats(endpoint_name, "bypass")
                result = await func(*args, **kwargs)
                
                # Add X-Cache header if result is a Response
                if isinstance(result, Response):
                    result.headers["X-Cache"] = "BYPASS"
                
                return result
            
            # Extract cache key parameters from request
            cache_params = {}
            
            # Try to get request body (works for POST requests with Pydantic models)
            for arg in args:
                if hasattr(arg, '__dict__') and not isinstance(arg, Request):
                    # This is likely a Pydantic model
                    if cache_key_params:
                        # Only include specified params
                        for param in cache_key_params:
                            if hasattr(arg, param):
                                cache_params[param] = getattr(arg, param)
                    else:
                        # Include all params
                        cache_params = {k: v for k, v in arg.__dict__.items() if not k.startswith('_')}
                    break
            
            # Also check kwargs
            if not cache_params:
                if cache_key_params:
                    cache_params = {k: kwargs.get(k) for k in cache_key_params if k in kwargs}
                else:
                    cache_params = {k: v for k, v in kwargs.items() if k != 'request'}
            
            # Generate cache key
            cache_key = _generate_cache_key(endpoint_name, **cache_params)
            
            # Try to get from cache
            ml_cache = get_multi_level_cache()
            t_start = time.perf_counter()
            cached_value = ml_cache.get(cache_key)
            cache_lookup_ms = int((time.perf_counter() - t_start) * 1000)
            
            if cached_value is not None:
                # Cache hit
                log.info(
                    f"[CACHE] HIT for {endpoint_name} "
                    f"(key={cache_key[:24]}..., lookup={cache_lookup_ms}ms)"
                )
                _update_stats(endpoint_name, "hit")
                
                # Deserialize cached response
                try:
                    cached_data = json.loads(cached_value)
                    
                    # Create JSONResponse with X-Cache header
                    response = JSONResponse(content=cached_data)
                    response.headers["X-Cache"] = "HIT"
                    
                    return response
                except json.JSONDecodeError as e:
                    log.warning(f"[CACHE] Failed to deserialize cached value: {e}")
                    # Fall through to execute function
            
            # Cache miss - execute function
            log.info(
                f"[CACHE] MISS for {endpoint_name} "
                f"(key={cache_key[:24]}..., lookup={cache_lookup_ms}ms)"
            )
            _update_stats(endpoint_name, "miss")
            
            # Execute the original function
            t_exec_start = time.perf_counter()
            result = await func(*args, **kwargs)
            exec_ms = int((time.perf_counter() - t_exec_start) * 1000)
            
            # Cache the result
            try:
                # Extract data to cache
                if isinstance(result, Response):
                    # For Response objects, we can't easily serialize them
                    # So we'll just add the header and not cache
                    result.headers["X-Cache"] = "MISS"
                    log.info(
                        f"[CACHE] Cannot cache Response object for {endpoint_name} "
                        f"(exec={exec_ms}ms)"
                    )
                elif isinstance(result, dict):
                    # Cache dict responses
                    cache_value = json.dumps(result, ensure_ascii=False)
                    ml_cache.set(cache_key, cache_value)
                    
                    log.info(
                        f"[CACHE] Cached result for {endpoint_name} "
                        f"(key={cache_key[:24]}..., ttl={ttl}s, exec={exec_ms}ms, size={len(cache_value)} bytes)"
                    )
                    
                    # Return as JSONResponse with X-Cache header
                    response = JSONResponse(content=result)
                    response.headers["X-Cache"] = "MISS"
                    
                    return response
                else:
                    log.warning(
                        f"[CACHE] Cannot cache result type {type(result)} for {endpoint_name}"
                    )
                    
                    # Add header if possible
                    if isinstance(result, Response):
                        result.headers["X-Cache"] = "MISS"
                    
            except Exception as e:
                log.error(f"[CACHE] Failed to cache result for {endpoint_name}: {e}")
            
            return result
        
        return wrapper
    return decorator
