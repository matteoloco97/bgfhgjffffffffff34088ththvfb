# API Request Examples

## Quick Reference: Valid Request Payloads

### POST /chat

**Basic Chat:**
```json
{
  "text": "What is the capital of France?",
  "source": "api",
  "source_id": "user123"
}
```

**With Custom System Prompt:**
```json
{
  "text": "Explain quantum computing",
  "source": "api",
  "source_id": "user123",
  "system_prompt": "You are a helpful physics tutor. Explain concepts clearly and simply."
}
```

**OpenAI-style Messages:**
```json
{
  "messages": [
    {
      "role": "system",
      "content": "You are a helpful assistant."
    },
    {
      "role": "user",
      "content": "What's the weather today?"
    }
  ],
  "source": "gui",
  "source_id": "webapp-session-456"
}
```

### POST /web/search

**Basic Search:**
```json
{
  "q": "Python asyncio tutorial",
  "k": 6,
  "summarize_top": 2
}
```

**Advanced Search:**
```json
{
  "q": "latest developments in AI safety research",
  "k": 15,
  "summarize_top": 5,
  "source": "api",
  "source_id": "researcher-001"
}
```

### POST /web/summarize

**URL Summarization:**
```json
{
  "url": "https://example.com/long-article",
  "return_sources": true,
  "source": "tg",
  "source_id": "telegram-user-123"
}
```

**Query-based Summarization:**
```json
{
  "q": "best practices for Python type hints",
  "k": 10,
  "summarize_top": 3,
  "return_sources": true
}
```

### POST /autonomous

**Simple Goal:**
```json
{
  "goal": "Find the top 5 Python web frameworks and compare them",
  "show_plan": true,
  "max_steps": 10
}
```

**With Approval Required:**
```json
{
  "goal": "Research and summarize recent breakthroughs in quantum computing",
  "require_approval": true,
  "show_plan": true,
  "max_steps": 15,
  "source": "api",
  "source_id": "research-assistant"
}
```

### POST /tools/math

**Basic Calculation:**
```json
{
  "tool_name": "math",
  "parameters": {
    "expr": "2 + 2"
  }
}
```

**Complex Expression:**
```json
{
  "tool_name": "math",
  "parameters": {
    "expr": "sqrt(16) + (3 * 4) - 2^3"
  }
}
```

### POST /tools/python

**Code Execution:**
```json
{
  "tool_name": "python",
  "parameters": {
    "code": "print('Hello, World!')\nresult = sum(range(10))\nprint(f'Sum: {result}')"
  }
}
```

## Invalid Request Examples (Will Return 422)

### XSS Attempt
```json
{
  "text": "<script>alert('XSS')</script>",
  "source": "api",
  "source_id": "attacker"
}
```
**Error:**
```json
{
  "error": "validation_error",
  "detail": "text: text contains potentially dangerous HTML/JavaScript. Please remove script tags and event handlers.",
  "status_code": 422
}
```

### SQL Injection Attempt
```json
{
  "text": "Hello'; DROP TABLE users; --",
  "source": "api",
  "source_id": "user123"
}
```
**Error:**
```json
{
  "error": "validation_error",
  "detail": "text: text contains potentially dangerous SQL pattern. Please remove SQL-like syntax.",
  "status_code": 422
}
```

### Empty Required Field
```json
{
  "source": "api",
  "source_id": "user123"
}
```
**Error:**
```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "text"],
      "msg": "Field required"
    }
  ]
}
```

### Text Too Long
```json
{
  "text": "A".repeat(6000),
  "source": "api",
  "source_id": "user123"
}
```
**Error:**
```json
{
  "detail": [
    {
      "type": "string_too_long",
      "loc": ["body", "text"],
      "msg": "String should have at most 5000 characters"
    }
  ]
}
```

### Invalid URL Protocol
```json
{
  "url": "javascript:alert('XSS')",
  "return_sources": true
}
```
**Error:**
```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "url"],
      "msg": "url must start with http:// or https://"
    }
  ]
}
```

### Missing Either/Or Field
```json
{
  "return_sources": true,
  "source": "api"
}
```
**Error:**
```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body"],
      "msg": "Either 'url' or 'q' must be provided"
    }
  ]
}
```

### Invalid Enum Value
```json
{
  "text": "Hello",
  "source": "invalid_source",
  "source_id": "user123"
}
```
**Error:**
```json
{
  "detail": [
    {
      "type": "enum",
      "loc": ["body", "source"],
      "msg": "Input should be 'api', 'tg', 'gui', 'web', 'system' or 'test'"
    }
  ]
}
```

### Path Traversal in URL
```json
{
  "url": "https://example.com/../../etc/passwd",
  "return_sources": true
}
```
**Error:**
```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "url"],
      "msg": "url contains invalid path traversal patterns"
    }
  ]
}
```

### Value Out of Range
```json
{
  "q": "Python tutorial",
  "k": 25
}
```
**Error:**
```json
{
  "detail": [
    {
      "type": "less_than_equal",
      "loc": ["body", "k"],
      "msg": "Input should be less than or equal to 20"
    }
  ]
}
```

### Invalid source_id Format
```json
{
  "text": "Hello",
  "source": "api",
  "source_id": "user@email.com"
}
```
**Error:**
```json
{
  "error": "validation_error",
  "detail": "source_id: source_id must contain only alphanumeric characters, underscores, hyphens, and colons",
  "status_code": 422
}
```

## Testing with curl

### Valid Request
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "text": "What is AI?",
    "source": "api",
    "source_id": "test-user"
  }'
```

### Test XSS Protection
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "text": "<script>alert(\"xss\")</script>",
    "source": "api",
    "source_id": "test-user"
  }'
```

### Test SQL Injection Protection
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hello; DROP TABLE users;--",
    "source": "api",
    "source_id": "test-user"
  }'
```

## Testing with Python

```python
import requests

# Valid request
response = requests.post(
    "http://localhost:8000/web/search",
    json={
        "q": "Python asyncio tutorial",
        "k": 10,
        "summarize_top": 3
    }
)
print(response.json())

# Invalid request (should return 422)
response = requests.post(
    "http://localhost:8000/web/search",
    json={
        "q": "<script>alert('xss')</script>",
        "k": 10
    }
)
print(f"Status: {response.status_code}")
print(response.json())
```

## Testing with JavaScript/fetch

```javascript
// Valid request
fetch('http://localhost:8000/chat', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    text: 'What is the weather today?',
    source: 'gui',
    source_id: 'webapp-123'
  })
})
  .then(response => response.json())
  .then(data => console.log(data))
  .catch(error => console.error('Error:', error));

// Invalid request (should return 422)
fetch('http://localhost:8000/web/summarize', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    url: 'javascript:alert("xss")',
    return_sources: true
  })
})
  .then(response => response.json())
  .then(data => console.log('Validation error:', data))
  .catch(error => console.error('Error:', error));
```
