# API Input Validation Documentation

## Overview

All QuantumDev API endpoints now include comprehensive input validation using Pydantic v2 models. This ensures data integrity, prevents security vulnerabilities (XSS, SQL injection), and provides clear error messages for invalid inputs.

## Validation Features

### Security Measures
- **XSS Protection**: Blocks `<script>`, `<iframe>`, `<object>`, event handlers (`onclick=`, etc.), and `javascript:` protocols
- **SQL Injection Protection**: Blocks SQL keywords (`UNION SELECT`, `DROP TABLE`, `INSERT INTO`, etc.)
- **Path Traversal Protection**: Blocks `../`, `..`, `~/` patterns in URLs
- **Nested Depth Limits**: Prevents DOS attacks via deeply nested JSON (max depth: 5)

### Data Sanitization
- **Whitespace Stripping**: Automatically removes leading/trailing whitespace
- **Unicode Normalization**: Normalizes all text to NFC form for consistency
- **HTML Escaping**: Escapes special HTML characters

### Field Constraints
- **Length Limits**: Enforced on all text fields
- **Range Validation**: Numeric fields validated against min/max values
- **Enum Validation**: Source and tool names validated against allowed values
- **Pattern Matching**: source_id limited to alphanumeric, underscore, hyphen, colon

## API Models

### ChatRequest

Used by: `POST /chat`

**Fields:**
- `text` (required): User's message (1-5000 chars)
- `source` (optional): Source type (api, tg, gui, web, system, test) - default: "api"
- `source_id` (optional): User identifier (1-100 chars, alphanumeric + _:-) - default: "default"
- `system_prompt` (optional): Custom system prompt (max 2000 chars)
- `messages` (optional): OpenAI-style messages array

**Example Valid Request:**
```json
{
  "text": "What's the weather in Rome?",
  "source": "api",
  "source_id": "user123"
}
```

**Example Error Response (422):**
```json
{
  "error": "validation_error",
  "detail": "text: text cannot be empty or whitespace only",
  "status_code": 422
}
```

### WebSearchRequest

Used by: `POST /web/search`

**Fields:**
- `q` (required): Search query (1-500 chars)
- `k` (optional): Number of results (1-20) - default: 6
- `summarize_top` (optional): Number to summarize (0-10) - default: 2
- `source` (optional): Source type - default: "api"
- `source_id` (optional): User identifier - default: "default"

**Example Valid Request:**
```json
{
  "q": "latest Python 3.12 features",
  "k": 10,
  "summarize_top": 3
}
```

**Example Error Response (422):**
```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "q"],
      "msg": "q contains potentially dangerous HTML/JavaScript. Please remove script tags and event handlers.",
      "input": "<script>alert('xss')</script>"
    }
  ]
}
```

### WebSummarizeRequest

Used by: `POST /web/summarize`

**Fields:**
- `url` (optional): URL to summarize (max 2000 chars, must start with http/https)
- `q` (optional): Search query (max 500 chars)
- `k` (optional): Number of results (1-20) - default: 6
- `summarize_top` (optional): Number to summarize (0-10) - default: 2
- `return_sources` (optional): Return source URLs - default: true
- `source` (optional): Source type - default: "tg"
- `source_id` (optional): User identifier - default: "default"

**Note:** Either `url` OR `q` must be provided, but not both.

**Example Valid Request (URL mode):**
```json
{
  "url": "https://example.com/article",
  "return_sources": true
}
```

**Example Valid Request (Query mode):**
```json
{
  "q": "Python asyncio tutorial",
  "summarize_top": 5
}
```

**Example Error Response (422):**
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

### AutonomousRequest

Used by: `POST /autonomous`

**Fields:**
- `goal` (required): Task description (1-1000 chars)
- `show_plan` (optional): Include execution plan - default: true
- `max_steps` (optional): Max execution steps (1-20) - default: 10
- `source` (optional): Source type - default: "api"
- `source_id` (optional): User identifier - default: "default"
- `require_approval` (optional): Return plan for approval - default: false

**Example Valid Request:**
```json
{
  "goal": "Find the best Python web frameworks for 2024",
  "show_plan": true,
  "max_steps": 10
}
```

**Example Error Response (422):**
```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "max_steps"],
      "msg": "Input should be less than or equal to 20",
      "input": 25
    }
  ]
}
```

### ToolRequest

Used by: Tool execution endpoints

**Fields:**
- `tool_name` (required): Tool to execute (math, python, web_search, etc.)
- `parameters` (optional): Tool-specific parameters (max depth: 5) - default: {}
- `source` (optional): Source type - default: "api"
- `source_id` (optional): User identifier - default: "default"

**Example Valid Request:**
```json
{
  "tool_name": "math",
  "parameters": {
    "expr": "2 + 2 * 3"
  }
}
```

**Example Error Response (422):**
```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "parameters"],
      "msg": "Object nesting depth exceeds maximum of 5. Please reduce nesting complexity."
    }
  ]
}
```

## Common Validation Errors

### 1. XSS Attempt
**Input:**
```json
{
  "text": "<script>alert('xss')</script>"
}
```

**Error:**
```
text: text contains potentially dangerous HTML/JavaScript. Please remove script tags and event handlers.
```

### 2. SQL Injection Attempt
**Input:**
```json
{
  "text": "'; DROP TABLE users; --"
}
```

**Error:**
```
text: text contains potentially dangerous SQL pattern. Please remove SQL-like syntax.
```

### 3. Invalid URL Protocol
**Input:**
```json
{
  "url": "javascript:alert('xss')"
}
```

**Error:**
```
url: url must start with http:// or https://
```

### 4. Path Traversal
**Input:**
```json
{
  "url": "https://example.com/../../etc/passwd"
}
```

**Error:**
```
url: url contains invalid path traversal patterns
```

### 5. Text Too Long
**Input:**
```json
{
  "text": "a".repeat(6000)
}
```

**Error:**
```
text: String should have at most 5000 characters
```

### 6. Missing Required Field
**Input:**
```json
{
  "source": "api"
}
```

**Error:**
```
text: Field required
```

### 7. Invalid Enum Value
**Input:**
```json
{
  "text": "Hello",
  "source": "invalid_source"
}
```

**Error:**
```
source: Input should be 'api', 'tg', 'gui', 'web', 'system' or 'test'
```

### 8. Invalid source_id Format
**Input:**
```json
{
  "text": "Hello",
  "source_id": "user@email.com"
}
```

**Error:**
```
source_id: source_id must contain only alphanumeric characters, underscores, hyphens, and colons
```

## Testing Validation

Use the provided test suite to verify validation:

```bash
cd /home/runner/work/bgfhgjffffffffff34088ththvfb/bgfhgjffffffffff34088ththvfb
PYTHONPATH=. pytest tests/test_input_validation.py -v
```

All 27 tests should pass:
- 7 ChatRequest tests
- 4 WebSearchRequest tests
- 6 WebSummarizeRequest tests
- 4 AutonomousRequest tests
- 3 ToolRequest tests
- 3 General validation tests

## Implementation Details

### Validator Functions

**`check_injection_patterns(text, field_name)`**
- Checks for SQL injection patterns
- Checks for XSS patterns
- Checks for path traversal patterns
- Raises `ValueError` with descriptive message if dangerous pattern detected

**`sanitize_html(text)`**
- Removes HTML tags with regex
- Escapes special characters (`<`, `>`, `&`, `"`, `'`)
- Returns sanitized text

**`normalize_unicode(text)`**
- Normalizes text to NFC form
- Ensures consistent representation of unicode characters

**`check_nested_depth(obj, max_depth)`**
- Recursively checks nesting depth of dicts and lists
- Prevents DOS attacks via deeply nested JSON
- Raises `ValueError` if depth exceeds limit

### Custom Validators

All models use Pydantic's `@field_validator` and `@model_validator` decorators:

```python
@field_validator("text")
@classmethod
def validate_text(cls, v: str) -> str:
    """Validate and sanitize text field."""
    v = v.strip()
    v = normalize_unicode(v)
    v = check_injection_patterns(v, "text")
    return v
```

## Migration Guide

### Old Code (No Validation)
```python
@app.post("/chat")
async def chat(payload: dict = Body(...)):
    text = payload.get("text", "")
    # No validation - vulnerable to XSS, SQL injection, etc.
    return {"reply": process(text)}
```

### New Code (With Validation)
```python
@app.post("/chat")
async def chat(payload: dict = Body(...)):
    # Validate using ChatRequest model
    try:
        validated = ChatRequest(
            text=payload.get("text", ""),
            source=payload.get("source", "api"),
            source_id=payload.get("source_id", "default")
        )
    except ValidationError as e:
        # Return 422 with clear error messages
        error_details = []
        for error in e.errors():
            field = " -> ".join(str(x) for x in error["loc"])
            msg = error["msg"]
            error_details.append(f"{field}: {msg}")
        
        return {
            "error": "validation_error",
            "detail": "; ".join(error_details),
            "status_code": 422
        }
    
    # Use validated data
    return {"reply": process(validated.text)}
```

## Best Practices

1. **Always validate user input** - Never trust client-side validation alone
2. **Use clear error messages** - Help users understand what went wrong
3. **Log validation failures** - Monitor for potential attack attempts
4. **Keep validators up to date** - Add new patterns as threats evolve
5. **Test thoroughly** - Include edge cases and malicious inputs in tests
6. **Document constraints** - Make API limits clear to consumers
7. **Use type hints** - Leverage Pydantic's type checking with mypy

## Security Notes

- Validation is the first line of defense, not the only defense
- Backend should still sanitize data before database operations
- Consider rate limiting for additional protection
- Monitor validation failure patterns for security insights
- Update injection patterns regularly as new attack vectors emerge

## Support

For issues or questions:
- Check the test suite: `tests/test_input_validation.py`
- Review model definitions: `backend/models.py`
- See endpoint implementations: `backend/quantum_api.py`
