# Rate Limiting Implementation

This document describes the comprehensive rate limiting implementation for the QuantumDev FastAPI backend using `slowapi`.

## Overview

Rate limiting has been implemented to protect the API from abuse and DoS attacks while ensuring internal services (like the Telegram Bot running on localhost) are never affected.

## Features

### 1. Per-Endpoint Rate Limits

Different endpoints have different rate limits based on their resource consumption:

| Endpoint | Rate Limit | Description |
|----------|------------|-------------|
| `/chat` | 10 requests/minute | Main chat endpoint with LLM |
| `/web/search` | 20 requests/minute | Web search with synthesis |
| `/web/summarize` | 15 requests/minute | Web content summarization |
| `/unified` | 10 requests/minute | Unified orchestrator |
| `/autonomous` | 5 requests/minute | Autonomous agent (most resource-intensive) |

### 2. Automatic Localhost Bypass

**CRITICAL**: All requests from localhost addresses are **AUTOMATICALLY** whitelisted and will **NEVER** be rate limited. This ensures the internal Telegram Bot continues to function without interruption.

Whitelisted addresses:
- `127.0.0.1` (IPv4 loopback)
- `::1` (IPv6 loopback)
- `localhost`

### 3. Admin Token Bypass

Administrators can bypass rate limits using the `X-Admin-Token` header:

```bash
curl -X POST http://localhost:8000/chat \
  -H "X-Admin-Token: your-secure-admin-token" \
  -H "Content-Type: application/json" \
  -d '{"text": "test", "source": "api", "source_id": "admin"}'
```

### 4. Proxy-Aware IP Detection

The rate limiter correctly handles proxy headers to identify the real client IP:
- `X-Forwarded-For` (takes the first IP in the chain)
- `X-Real-IP` (fallback)

This ensures accurate rate limiting when the API is behind Nginx or other reverse proxies.

### 5. Rate Limit Headers

All responses include rate limit headers:

```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 7
X-RateLimit-Reset: 1703001234
```

### 6. Custom 429 Error Responses

When rate limited, clients receive a helpful JSON response:

```json
{
  "error": "rate_limit_exceeded",
  "message": "Too many requests. Please slow down and try again later.",
  "detail": "Rate limit exceeded for this endpoint. Please wait 60 seconds before retrying.",
  "retry_after_seconds": 60,
  "endpoint": "/chat"
}
```

## Configuration

### Environment Variables

Add to your `.env` file:

```bash
# Redis connection (required for rate limiting)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# Admin token for bypassing rate limits
ADMIN_TOKEN=your-secure-admin-token-here
```

**Generate a secure admin token:**
```bash
openssl rand -hex 32
```

### Installation

The required dependency is already in `requirements.txt`:

```
slowapi>=0.1.9
```

Install with:
```bash
pip install -r requirements.txt
```

## Architecture

### Rate Limiter Initialization

```python
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

# Custom key function with whitelist logic
def get_remote_address_with_whitelist(request: Request) -> str:
    # Check admin token
    if ADMIN_TOKEN and request.headers.get("X-Admin-Token") == ADMIN_TOKEN:
        return "admin-bypass"
    
    # Get real IP from proxy headers
    client_ip = get_real_ip(request)
    
    # Check localhost
    if client_ip in ["127.0.0.1", "::1", "localhost"]:
        return "localhost-bypass"
    
    return client_ip

# Initialize with Redis storage
limiter = Limiter(
    key_func=get_remote_address_with_whitelist,
    storage_uri=f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}",
)
```

### Applying to Endpoints

```python
@app.post("/chat")
@limiter.limit("10/minute")
async def chat(payload: dict, request: Request = None):
    # Handler code
    pass
```

### Custom Error Handler

```python
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "message": "Too many requests...",
            "retry_after_seconds": exc.retry_after,
        },
        headers={"Retry-After": str(exc.retry_after)}
    )
```

## Testing

### Automated Validation

Run the validation test to verify configuration:

```bash
python tests/test_rate_limiting_validation.py
```

### Manual Testing

Use the provided shell script to test all scenarios:

```bash
# Start Redis
redis-server

# Start the API server
uvicorn backend.quantum_api:app --reload

# Run manual tests
./tests/manual_rate_limit_test.sh
```

### Test Scenarios

1. **External IP Rate Limiting**: Make 11 requests to `/chat` from an external IP, expect 429 on the 11th
2. **Localhost Bypass**: Make 20+ requests from localhost, expect no rate limiting
3. **Admin Token Bypass**: Make 20+ requests with `X-Admin-Token`, expect no rate limiting
4. **Different Limits**: Verify each endpoint has its specific limit
5. **Headers**: Check that `X-RateLimit-*` headers are present

## Security Considerations

### Localhost Whitelist

The localhost whitelist is **intentional and critical** for the following reasons:

1. **Telegram Bot Integration**: The bot runs on the same server and must not be rate limited
2. **Internal Services**: Other internal services need unrestricted access
3. **No External Risk**: Localhost addresses cannot be reached from outside the server

### Admin Token

- **Generate a strong token**: Use `openssl rand -hex 32` or similar
- **Keep it secret**: Never commit `.env` to version control
- **Rotate periodically**: Change the token regularly in production
- **Log usage**: Admin bypass events are logged with `[RATELIMIT]` prefix

### Redis Security

- **Bind to localhost**: Configure Redis to only accept local connections
- **Use authentication**: Set `requirepass` in `redis.conf`
- **Separate database**: Use a dedicated Redis DB for rate limiting

## Monitoring

All rate limiting events are logged with the `[RATELIMIT]` prefix:

```
[RATELIMIT] Localhost bypass: 127.0.0.1
[RATELIMIT] Admin token bypass used
[RATELIMIT] Rate limit exceeded for /chat from 203.0.113.1
```

Monitor these logs to:
- Detect abuse attempts
- Verify bypass mechanisms work correctly
- Tune rate limits based on usage patterns

## Troubleshooting

### "Connection refused" to Redis

**Problem**: Rate limiter cannot connect to Redis

**Solution**:
```bash
# Start Redis
redis-server

# Or specify custom config
redis-server /path/to/redis.conf
```

### Localhost is being rate limited

**Problem**: Internal services are blocked

**Solution**: Verify the IP is truly localhost:
- Check `request.client.host` in logs
- Ensure no proxy is translating localhost to another IP
- Verify `X-Forwarded-For` is not overriding with external IP

### Admin token not working

**Problem**: Admin requests are rate limited

**Solution**:
- Verify `ADMIN_TOKEN` is set in `.env`
- Check header name is exactly `X-Admin-Token`
- Ensure token matches exactly (no whitespace)
- Look for `[RATELIMIT] Admin token bypass used` in logs

## Performance Impact

Rate limiting with Redis has minimal performance impact:

- **Storage**: O(1) lookup/update in Redis
- **Network**: Single Redis query per request
- **Latency**: < 1ms added to request processing
- **Memory**: ~100 bytes per unique IP/endpoint pair

## Future Enhancements

Potential improvements:

1. **User-based limits**: Track by user ID instead of IP
2. **Dynamic limits**: Adjust limits based on server load
3. **Burst allowance**: Allow short bursts above the limit
4. **Whitelist API**: Add/remove IPs from whitelist via API
5. **Analytics dashboard**: Real-time rate limit monitoring

## References

- [slowapi Documentation](https://slowapi.readthedocs.io/)
- [Redis Rate Limiting](https://redis.io/docs/manual/patterns/rate-limiter/)
- [FastAPI Middleware](https://fastapi.tiangolo.com/advanced/middleware/)
