# Quick Reference: Python Code Executor + Telegram Bot Commands

## Quick Start

### 1. Enable Code Execution

Add to your `.env` file:
```bash
# Enable Python code execution
TOOLS_PYTHON_EXEC_ENABLED=1
CODE_EXEC_ENABLED=1
CODE_EXEC_TIMEOUT=10.0

# Telegram admin (for /py command)
TELEGRAM_ADMIN_ID=your_chat_id_here
```

### 2. Telegram Bot Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/status` | System metrics | Shows CPU, RAM, disk, GPU, uptime |
| `/autobug` | Health diagnostics | Runs checks on all subsystems |
| `/math <expr>` | Calculator | `/math 2*(3+5.5)` → 17.0 |
| `/py <code>` | Python executor | `/py print("Hello")` (admin only) |

### 3. API Endpoint

```bash
# Execute Python code
curl -X POST http://127.0.0.1:8081/tools/python \
  -H "Content-Type: application/json" \
  -d '{"code": "print(2 + 2)", "timeout_s": 5.0}'

# Response
{
  "ok": true,
  "stdout": "4\n",
  "stderr": "",
  "error": "",
  "timeout": false
}
```

### 4. Python Module Usage

```python
from core.code_executor import execute_python_snippet

# Execute code
result = execute_python_snippet("print('Hello')")

# Check result
if result["ok"]:
    print(result["stdout"])  # "Hello\n"
else:
    print(result["error"])
```

## Security Blacklist

The following patterns are blocked:
- `import os`, `from os`
- `import sys`, `from sys`
- `import subprocess`, `from subprocess`
- `import socket`, `from socket`
- `import shutil`, `from shutil`
- `import time`, `from time`
- `open(`, `eval(`, `exec(`, `__import__`
- `import pickle`, `from pickle`
- `import multiprocessing`, `from multiprocessing`
- `import ctypes`, `from ctypes`
- `import platform`, `from platform`

## Testing

```bash
# Run self-tests
cd "Contabo VPS/quantumdev-open"
python3 core/code_executor.py

# Expected output: All Tests Passed ✓
```

## Troubleshooting

**Problem:** `/tools/python` returns "python_exec_disabled"
- **Solution:** Set both `TOOLS_PYTHON_EXEC_ENABLED=1` and `CODE_EXEC_ENABLED=1`

**Problem:** `/py` command says "not allowed"
- **Solution:** Set `TELEGRAM_ADMIN_ID` to your Telegram chat ID

**Problem:** Code execution times out
- **Solution:** Increase `CODE_EXEC_TIMEOUT` or use shorter code

## Files Modified

1. ✅ `core/code_executor.py` (NEW) - Safe executor module
2. ✅ `backend/quantum_api.py` - Updated /tools/python endpoint
3. ✅ `scripts/telegram_bot.py` - Added new commands

## Next Steps

1. Deploy updated code
2. Restart backend and bot
3. Test commands in Telegram
4. Monitor logs for any issues

**For full documentation, see:**
- `CODE_EXECUTOR_IMPLEMENTATION.md` - Technical details
- `IMPLEMENTATION_COMPLETE.md` - Requirements checklist
