# Rate Limiting Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Incoming HTTP Request                            │
│                    (to /chat, /web/search, etc.)                     │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
                ┌────────────────────────────┐
                │   Rate Limiter Middleware  │
                │  get_remote_address_with_  │
                │        whitelist()         │
                └────────────┬───────────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
    ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
    │ Check Admin │  │   Check IP  │  │ Get Proxy   │
    │   Token     │  │  Localhost? │  │   Headers   │
    │ X-Admin-    │  │ 127.0.0.1?  │  │ X-Forwarded │
    │   Token     │  │    ::1?     │  │   -For      │
    └─────┬───────┘  └──────┬──────┘  └──────┬──────┘
          │                 │                 │
          │ Yes             │ Yes             │ No bypass
          ▼                 ▼                 ▼
    ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
    │   Return    │   │   Return    │   │   Return    │
    │ "admin-     │   │ "localhost- │   │  Real IP    │
    │  bypass"    │   │   bypass"   │   │ (e.g. 1.2.  │
    │             │   │             │   │   3.4)      │
    └─────┬───────┘   └──────┬──────┘   └──────┬──────┘
          │                  │                  │
          └──────────────────┼──────────────────┘
                             │
                             ▼
                    ┌────────────────┐
                    │  Rate Limiter  │
                    │   Check Key    │
                    │  in Redis      │
                    └────────┬───────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
    ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
    │   Bypass    │  │  Within     │  │  Exceeded   │
    │    Key?     │  │   Limit?    │  │   Limit?    │
    │ (admin/     │  │             │  │             │
    │ localhost)  │  │             │  │             │
    └─────┬───────┘  └──────┬──────┘  └──────┬──────┘
          │ Yes             │ Yes             │ Yes
          │                 │                 │
          ▼                 ▼                 ▼
    ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
    │   BYPASS    │   │  INCREMENT  │   │   RAISE     │
    │ Rate Limit  │   │   Counter   │   │ RateLimit   │
    │             │   │  in Redis   │   │  Exceeded   │
    └─────┬───────┘   └──────┬──────┘   └──────┬──────┘
          │                  │                  │
          │                  │                  │
          └──────────────────┼──────────────────┘
                             │                  │
                             ▼                  ▼
                    ┌────────────────┐   ┌─────────────┐
                    │  Add Rate      │   │  Custom 429 │
                    │  Limit Headers │   │   Handler   │
                    │  X-RateLimit-* │   │             │
                    └────────┬───────┘   └──────┬──────┘
                             │                  │
                             ▼                  ▼
                    ┌────────────────┐   ┌─────────────┐
                    │   Execute      │   │   Return    │
                    │   Endpoint     │   │   JSON      │
                    │   Handler      │   │   Error     │
                    └────────┬───────┘   └──────┬──────┘
                             │                  │
                             ▼                  ▼
                    ┌────────────────┐   ┌─────────────┐
                    │  200 OK        │   │  429 Too    │
                    │  Response      │   │  Many       │
                    │  + Headers     │   │  Requests   │
                    └────────────────┘   └─────────────┘
```

## Key Decision Points

### 1. Admin Token Check
```
IF X-Admin-Token == ADMIN_TOKEN:
    RETURN "admin-bypass"  → BYPASS rate limiting
```

### 2. Localhost Check
```
IF client_ip IN [127.0.0.1, ::1, localhost]:
    RETURN "localhost-bypass"  → BYPASS rate limiting
```

### 3. Rate Limit Check
```
key = f"{endpoint}:{client_ip}"
IF Redis.get(key) >= limit:
    RAISE RateLimitExceeded  → 429 Error
ELSE:
    Redis.increment(key)
    CONTINUE  → Execute endpoint
```

## Rate Limit Storage (Redis)

```
Key Format: "slowapi:{endpoint}:{ip}:{window}"

Examples:
  slowapi:/chat:203.0.113.1:1703001000  →  count: 7
  slowapi:/web/search:192.168.1.1:1703001060  →  count: 15
  slowapi:/autonomous:10.0.0.5:1703001120  →  count: 3

TTL: 60 seconds (auto-expire)
```

## Response Headers Flow

### Success (200 OK)
```http
HTTP/1.1 200 OK
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 3
X-RateLimit-Reset: 1703001234
Content-Type: application/json

{response body}
```

### Rate Limited (429)
```http
HTTP/1.1 429 Too Many Requests
Retry-After: 45
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1703001234
Content-Type: application/json

{
  "error": "rate_limit_exceeded",
  "message": "Too many requests...",
  "retry_after_seconds": 45
}
```

## Logging Flow

```
[INFO] [RATELIMIT] Rate limiting initialized with Redis storage
[INFO] [RATELIMIT] Localhost (127.0.0.1) and ::1 are AUTOMATICALLY whitelisted
[INFO] [RATELIMIT] Admin token bypass is configured

→ Request from 127.0.0.1:
[INFO] [RATELIMIT] Localhost bypass: 127.0.0.1

→ Request with admin token:
[INFO] [RATELIMIT] Admin token bypass used

→ Rate limit exceeded:
[WARNING] [RATELIMIT] Rate limit exceeded for /chat from 203.0.113.1
```

## Example Scenarios

### Scenario 1: Normal User
```
User (IP: 203.0.113.1) → /chat
├─ Check admin token: No
├─ Check localhost: No (external IP)
├─ Get real IP: 203.0.113.1
├─ Check Redis: 7/10 requests
├─ Increment: 8/10
└─ Response: 200 OK + Headers
```

### Scenario 2: Telegram Bot (Localhost)
```
Bot (IP: 127.0.0.1) → /chat
├─ Check admin token: No
├─ Check localhost: YES ✓
├─ Return: "localhost-bypass"
├─ SKIP Redis check
└─ Response: 200 OK (no rate limiting)
```

### Scenario 3: Admin with Token
```
Admin (IP: 203.0.113.2, Token: valid) → /autonomous
├─ Check admin token: YES ✓
├─ Return: "admin-bypass"
├─ SKIP Redis check
└─ Response: 200 OK (no rate limiting)
```

### Scenario 4: Rate Limit Exceeded
```
User (IP: 203.0.113.3) → /autonomous (6th request)
├─ Check admin token: No
├─ Check localhost: No
├─ Get real IP: 203.0.113.3
├─ Check Redis: 5/5 requests ✗
├─ RAISE RateLimitExceeded
└─ Response: 429 Too Many Requests
```

## Performance Impact

```
┌─────────────────────┐
│  Request comes in   │  T = 0ms
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Check bypass logic  │  T = +0.1ms (in-memory)
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Redis lookup/update │  T = +0.5ms (network + DB)
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Execute endpoint    │  T = +100-1000ms (LLM/web)
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Return response     │  T = Total ~100-1000ms
└─────────────────────┘

Rate limiting overhead: < 1ms (< 1% of total request time)
```
