# Python Code Executor + Telegram Bot Commands - Implementation Summary

## Overview

This implementation adds a safe Python code executor module and enhances the Telegram bot with new commands for system status, diagnostics, calculator, and code execution.

## Files Modified/Created

### 1. `core/code_executor.py` (NEW)
**Purpose:** Safe Python code executor with sandboxing and security limits

**Key Features:**
- **Code length limit:** Max 4000 characters
- **Blacklist filtering:** Blocks dangerous imports and operations (os, sys, subprocess, socket, shutil, open, eval, exec, __import__, pickle, multiprocessing, ctypes, platform)
- **Subprocess isolation:** Executes code in isolated subprocess
- **Timeout enforcement:** Configurable timeout (default 3.0s)
- **No environment leakage:** Runs with empty environment variables
- **Temporary directory:** Executes in /tmp to prevent file system access

**API:**
```python
def execute_python_snippet(code: str, timeout_s: float = 3.0) -> Dict[str, Any]:
    """
    Returns:
        {
            "ok": bool,           # Success status
            "stdout": str,        # Captured stdout
            "stderr": str,        # Captured stderr
            "error": str,         # Error message (empty if ok)
            "timeout": bool       # Whether execution timed out
        }
    """
```

**Security Notice:**
This is NOT a fully trusted multi-tenant environment. Use only with trusted users or in controlled contexts.

### 2. `backend/quantum_api.py` (MODIFIED)

**Changes:**
1. **Added environment variables:**
   ```python
   CODE_EXEC_ENABLED = env_bool("CODE_EXEC_ENABLED", False)
   CODE_EXEC_TIMEOUT = env_float("CODE_EXEC_TIMEOUT", 10.0)
   ```

2. **Added import:**
   ```python
   from core.code_executor import execute_python_snippet
   ```

3. **Updated `/tools/python` endpoint:**
   - Now uses the new `core/code_executor` module
   - Accepts JSON with `code` and optional `timeout_s` fields
   - Requires both `TOOLS_PYTHON_EXEC_ENABLED` and `CODE_EXEC_ENABLED` to be true
   - Returns consistent response format matching spec

**Endpoint:**
```
POST /tools/python
Body: {"code": "print('Hello')", "timeout_s": 5.0}
Response: {"ok": true, "stdout": "Hello\n", "stderr": "", "error": "", "timeout": false}
```

### 3. `scripts/telegram_bot.py` (MODIFIED)

**Changes:**

1. **Added environment variables:**
   ```python
   BACKEND_CHAT_URL = QUANTUM_UNIFIED_URL or QUANTUM_CHAT_URL
   QUANTUM_SYSTEM_STATUS_URL = "http://127.0.0.1:8081/system/status"
   QUANTUM_AUTOBUG_URL = "http://127.0.0.1:8081/autobug/run"
   QUANTUM_MATH_URL = "http://127.0.0.1:8081/tools/math"
   QUANTUM_PYTHON_URL = "http://127.0.0.1:8081/tools/python"
   ```

2. **Added helper function:**
   ```python
   async def call_backend_json(http, url, payload=None, method="POST", timeout=30.0) -> dict:
       """Generic helper for calling backend JSON endpoints"""
   ```

3. **New Commands:**

   **a. `/status` - System Status**
   - Shows: CPU usage, RAM usage, disk usage, GPU info (if available), uptime
   - Format: Human-readable with emoji icons
   - Example output:
     ```
     📊 System Status:
     • CPU: 23.4% (8 cores)
     • RAM: 6.2 / 12.0 GB (51.7%)
     • Disk: 40.5 / 100.0 GB (40.5%)
     • GPU 0: RTX A4000 (45%, 8.1 / 48.0 GB)
     • Uptime: 3h 12m
     ```

   **b. `/autobug` - Health Diagnostics**
   - Runs comprehensive health checks on all subsystems
   - Shows: LLM, web search, Redis, ChromaDB, system status, OCR (if enabled)
   - Format: Shows passed/failed with latency
   - Example output:
     ```
     ✅ AutoBug Report:
     Duration: 2345ms
     Passed: 5/6

     • llm: OK (2100ms)
     • web: OK (1234ms)
     • redis: OK (45ms)
     • chroma: OK (567ms)
     • system: OK (123ms)
     • ocr: FAIL (module not available)
     ```

   **c. `/math <expression>` - Calculator**
   - Evaluates mathematical expressions safely
   - Example: `/math 2*(3+5.5)` → `🧮 Risultato: 17.0`
   - Handles errors gracefully

   **d. `/py <code>` - Python Code Executor (Admin Only)**
   - Executes Python code snippets
   - **Restricted to admin user only** (TELEGRAM_ADMIN_ID)
   - Shows stdout, stderr, and execution status
   - Truncates output (stdout: 800 chars, stderr: 400 chars)
   - Example:
     ```
     /py print("Hello!")
     
     ✅ Execution successful
     📤 Output:
     Hello!
     ```

4. **Updated help text:**
   - Added all new commands to `/help` output

5. **Updated startup logging:**
   - Shows all endpoint URLs on bot startup

## Environment Variables

### Backend (quantum_api.py)
```bash
# Enable Python code execution (both must be true)
TOOLS_PYTHON_EXEC_ENABLED=1    # Master switch for /tools/python endpoint
CODE_EXEC_ENABLED=1             # Enable actual code execution

# Timeout for code execution
CODE_EXEC_TIMEOUT=10.0          # Default timeout in seconds
```

### Telegram Bot (telegram_bot.py)
```bash
# Backend endpoints
QUANTUM_UNIFIED_URL=http://127.0.0.1:8081/unified
QUANTUM_SYSTEM_STATUS_URL=http://127.0.0.1:8081/system/status
QUANTUM_AUTOBUG_URL=http://127.0.0.1:8081/autobug/run
QUANTUM_MATH_URL=http://127.0.0.1:8081/tools/math
QUANTUM_PYTHON_URL=http://127.0.0.1:8081/tools/python

# Admin user (for /py command)
TELEGRAM_ADMIN_ID=123456789     # Telegram chat ID of admin user
```

## Usage Examples

### 1. Using `/tools/python` API Endpoint

```python
import requests

# Simple calculation
response = requests.post(
    "http://127.0.0.1:8081/tools/python",
    json={"code": "print(2 + 2)"}
)
# Response: {"ok": true, "stdout": "4\n", "stderr": "", "error": "", "timeout": false}

# With custom timeout
response = requests.post(
    "http://127.0.0.1:8081/tools/python",
    json={"code": "import time; time.sleep(1); print('done')", "timeout_s": 2.0}
)
```

### 2. Telegram Bot Commands

```
User: /status
Bot: 📊 System Status:
     • CPU: 23.4% (8 cores)
     • RAM: 6.2 / 12.0 GB (51.7%)
     • Disk: 40.5 / 100.0 GB (40.5%)
     • Uptime: 3h 12m

User: /math 2+2*10
Bot: 🧮 Risultato: 22

Admin: /py for i in range(5): print(i)
Bot: ✅ Execution successful
     📤 Output:
     0
     1
     2
     3
     4
```

## Security Considerations

### Code Executor Module
1. **Blacklist-based filtering** - Blocks known dangerous patterns
2. **Subprocess isolation** - Code runs in separate process
3. **No environment variables** - Prevents leaking secrets
4. **Temporary directory** - Limits file system access
5. **Timeout enforcement** - Prevents infinite loops
6. **Length limits** - Max 4000 chars to prevent abuse

**Limitations:**
- Blacklist can be bypassed (e.g., `getattr(__builtins__, 'open')`)
- Not suitable for untrusted multi-tenant environments
- Use only with authenticated/trusted users
- Consider additional sandboxing (Docker, firejail, etc.) for production

### Telegram Bot
1. **Admin-only `/py` command** - Only TELEGRAM_ADMIN_ID can execute code
2. **Public commands** - /status, /autobug, /math are available to all users
3. **Rate limiting** - Not implemented (add if needed)

## Testing

### Unit Tests
Run the code executor self-test:
```bash
cd "Contabo VPS/quantumdev-open"
python3 core/code_executor.py
```

Expected output:
```
=== Code Executor Self-Test ===
Test 1: Simple print ✓ PASS
Test 2: Math calculation ✓ PASS
Test 3: Empty code ✓ PASS
Test 4: Code too long ✓ PASS
Test 5: Forbidden pattern ✓ PASS
Test 6: Timeout ✓ PASS
Test 7: Runtime error ✓ PASS
=== All Tests Passed ===
```

### Integration Tests
Test the API endpoint (requires backend running):
```bash
curl -X POST http://127.0.0.1:8081/tools/python \
  -H "Content-Type: application/json" \
  -d '{"code": "print(\"Hello, World!\")"}'
```

Expected response:
```json
{
  "ok": true,
  "stdout": "Hello, World!\n",
  "stderr": "",
  "error": "",
  "timeout": false
}
```

## Backend Endpoints Used

The Telegram bot now uses the following endpoints:

| Command | Endpoint | Method | Purpose |
|---------|----------|--------|---------|
| (chat) | `/unified` or `/chat` | POST | Normal chat messages |
| `/status` | `/system/status` | GET | System metrics |
| `/autobug` | `/autobug/run` | POST | Health diagnostics |
| `/math` | `/tools/math` | POST | Calculator |
| `/py` | `/tools/python` | POST | Python executor |
| `/web` | `/web/summarize` or `/web/research` | POST | Web search |
| `/read` | `/web/summarize` | POST | Read URL |

## Future Enhancements

1. **Enhanced sandboxing:** Use Docker containers or firejail for better isolation
2. **Whitelist approach:** Instead of blacklist, only allow specific safe operations
3. **Resource limits:** CPU, memory limits per execution
4. **Rate limiting:** Prevent abuse of /py command
5. **Logging:** Track all code executions for audit
6. **Code formatting:** Auto-format Python code before execution
7. **Multi-language support:** Add support for JavaScript, Bash, etc.

## Summary

This implementation provides:
- ✅ Safe Python code executor module (`core/code_executor.py`)
- ✅ Updated `/tools/python` endpoint in backend
- ✅ New Telegram bot commands: `/status`, `/autobug`, `/math`, `/py`
- ✅ Unified chat endpoint usage in bot
- ✅ Comprehensive error handling and security measures
- ✅ Full documentation and testing

All requirements from the problem statement have been met!
