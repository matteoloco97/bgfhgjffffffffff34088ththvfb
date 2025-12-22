# Cache Middleware Integration

## Overview

The cache middleware system provides automatic response caching for FastAPI endpoints using a multi-level cache architecture (L1 in-memory + L2 Redis).

## Features

- ✅ **Automatic caching** with `@cached_response` decorator
- ✅ **Configurable TTL** per endpoint
- ✅ **Cache bypass** via `?nocache=1` query parameter
- ✅ **X-Cache headers** (`HIT`/`MISS`/`BYPASS`)
- ✅ **Comprehensive statistics** tracking
- ✅ **Detailed logging** with `[CACHE]` prefix
- ✅ **Multi-level cache** integration (L1 + L2)

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│              Cache Middleware Decorator                  │
│  (@cached_response)                                      │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│         Multi-Level Cache System                         │
│  ┌─────────────────┐      ┌──────────────────┐         │
│  │  L1: In-Memory  │ ───▶ │  L2: Redis       │         │
│  │  (100 items)    │      │  (5000 items)     │         │
│  │  <1ms latency   │      │  <10ms latency    │         │
│  └─────────────────┘      └──────────────────┘         │
└─────────────────────────────────────────────────────────┘
```

## Usage

### 1. Decorate Your Endpoint

```python
from core.cache_middleware import cached_response

@app.post("/chat")
@cached_response("chat", ttl=300, cache_key_params=["text", "source", "source_id"])
async def chat(payload: dict = Body(...)) -> Dict[str, Any]:
    # Your endpoint logic here
    return {"response": "..."}
```

### 2. Decorator Parameters

- **endpoint_name** (str): Name for logging and statistics
- **ttl** (int): Time-to-live in seconds (default: 300)
- **cache_key_params** (list[str], optional): Request parameters to include in cache key
  - If `None`, all request body fields are used
  - Specify params for better cache key control

### 3. Cache Key Generation

Cache keys are automatically generated in the format:
```
{endpoint_name}:{hash(params)}
```

Example:
```
chat:92e5f85c3a026faf
web_search:4b7a8f2d1c9e3f0a
```

### 4. Cache Bypass

Users can bypass the cache by adding `?nocache=1` to the query string:

```bash
# Normal request (uses cache)
curl -X POST http://localhost:8000/chat -d '{"text": "Hello"}'

# Bypass cache
curl -X POST "http://localhost:8000/chat?nocache=1" -d '{"text": "Hello"}'
```

### 5. Cache Headers

All cached responses include an `X-Cache` header:
- `X-Cache: HIT` - Response served from cache
- `X-Cache: MISS` - Response computed and cached
- `X-Cache: BYPASS` - Cache bypassed by user request

### 6. View Cache Statistics

```bash
curl http://localhost:8000/cache/stats
```

Response:
```json
{
  "ok": true,
  "middleware": {
    "total_hits": 150,
    "total_misses": 50,
    "total_bypasses": 5,
    "total_requests": 200,
    "hit_rate": 0.75,
    "uptime_seconds": 3600,
    "per_endpoint": [
      {
        "endpoint": "chat",
        "hits": 100,
        "misses": 30,
        "bypasses": 3,
        "total_requests": 130,
        "hit_rate": 0.7692
      },
      {
        "endpoint": "web_search",
        "hits": 50,
        "misses": 20,
        "bypasses": 2,
        "total_requests": 70,
        "hit_rate": 0.7143
      }
    ]
  },
  "multi_level_cache": {
    "l1_hits": 140,
    "l1_misses": 60,
    "l2_hits": 10,
    "l2_misses": 50,
    "hit_rate": 0.75,
    "l1_size": 85,
    "l1_max_size": 100,
    "l1_enabled": true,
    "l2_enabled": true
  }
}
```

## Integrated Endpoints

The following endpoints are cached with specified TTLs:

| Endpoint | TTL | Cache Key Params |
|----------|-----|------------------|
| `/chat` | 300s (5 min) | `text`, `source`, `source_id` |
| `/web/search` | 600s (10 min) | `q`, `source`, `source_id` |
| `/web/summarize` | 1800s (30 min) | `q`, `source`, `source_id` |
| `/unified` | 300s (5 min) | `q`, `source`, `source_id` |

## Performance Impact

### Expected Latency Reduction

Based on the multi-level cache architecture:

- **L1 Hit**: <1ms (99.9% faster than original)
- **L2 Hit**: <10ms (99% faster than original)
- **Cache Miss**: Original latency + caching overhead (~2-5ms)

### Example Metrics

For a typical chat request that normally takes 100ms:

| Scenario | Latency | Improvement |
|----------|---------|-------------|
| Cache MISS | 102ms | baseline |
| L1 Cache HIT | 0.5ms | **200x faster** |
| L2 Cache HIT | 8ms | **12x faster** |

## Logging

All cache operations are logged with the `[CACHE]` prefix:

```
INFO [CACHE] MISS for chat (key=chat:92e5f85c..., lookup=0ms)
INFO [CACHE] Cached result for chat (key=chat:92e5f85c..., ttl=300s, exec=102ms, size=456 bytes)
INFO [CACHE] HIT for chat (key=chat:92e5f85c..., lookup=0ms)
INFO [CACHE] Bypass requested for chat
```

## Testing

### Unit Tests
```bash
python tests/test_cache_middleware.py
```

### Demo
```bash
python tests/demo_cache_middleware.py
```

### Manual Testing
```bash
# Start the server
uvicorn backend.quantum_api:app --reload

# Test endpoint (first request - MISS)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello", "source": "api", "source_id": "test"}' \
  -v | grep X-Cache

# Test endpoint (second request - HIT)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello", "source": "api", "source_id": "test"}' \
  -v | grep X-Cache

# Test bypass
curl -X POST "http://localhost:8000/chat?nocache=1" \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello", "source": "api", "source_id": "test"}' \
  -v | grep X-Cache

# View statistics
curl http://localhost:8000/cache/stats | python -m json.tool
```

## Configuration

Cache behavior can be configured via environment variables:

```bash
# L1 Cache (In-Memory)
L1_CACHE_SIZE=100        # Max items in L1 cache
L1_CACHE_TTL=300         # Default TTL in seconds
ENABLE_L1_CACHE=1        # Enable/disable L1

# L2 Cache (Redis)
ENABLE_L2_CACHE=1        # Enable/disable L2
REDIS_HOST=127.0.0.1     # Redis server host
REDIS_PORT=6379          # Redis server port
REDIS_DB=0               # Redis database number
```

## Implementation Details

### Cache Key Generation

```python
def _generate_cache_key(endpoint: str, **kwargs: Any) -> str:
    sorted_params = sorted(kwargs.items())
    params_str = json.dumps(sorted_params, sort_keys=True, ensure_ascii=False)
    params_hash = hashlib.sha256(params_str.encode()).hexdigest()[:16]
    return f"{endpoint}:{params_hash}"
```

### Statistics Tracking

The middleware maintains two levels of statistics:
1. **Middleware-level stats**: Per-endpoint hit/miss/bypass counts
2. **Multi-level cache stats**: L1/L2 performance metrics

### Response Serialization

- Dict responses are serialized to JSON and cached
- FastAPI Response objects cannot be cached (limitation)
- Cached responses are returned as JSONResponse with X-Cache header

## Troubleshooting

### Cache Not Working

1. Check if cache is enabled:
   ```bash
   curl http://localhost:8000/cache/stats
   ```

2. Check logs for `[CACHE]` messages

3. Verify Redis is running (for L2 cache):
   ```bash
   redis-cli ping
   ```

### Low Hit Rate

- Check if requests have identical parameters
- Verify cache key params are correctly specified
- Check TTL settings (may be too short)

### High Memory Usage

- Reduce L1_CACHE_SIZE
- Implement cache eviction policies
- Monitor `/cache/stats` for L1 size

## Future Enhancements

- [ ] Automatic cache warming
- [ ] Cache invalidation API
- [ ] Per-user cache quotas
- [ ] Cache compression for large responses
- [ ] Redis Sentinel support for HA
- [ ] Cache hit ratio alerts
- [ ] Response size limits

## Related Files

- `core/cache_middleware.py` - Main middleware implementation
- `core/multi_level_cache.py` - Multi-level cache system
- `backend/quantum_api.py` - FastAPI application with cached endpoints
- `tests/test_cache_middleware.py` - Unit tests
- `tests/demo_cache_middleware.py` - Demo script
