#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/code_executor.py — Safe Python Code Executor

Provides a sandboxed environment for executing small Python code snippets.

SECURITY NOTICE:
This module implements basic safety measures but is NOT a fully trusted
multi-tenant environment. It should only be used in controlled contexts
where the user is trusted or has been authenticated.

Safety measures:
- Code length limits (max 4000 chars)
- Blacklist of dangerous imports and operations
- Subprocess isolation
- Timeout enforcement
- No environment variable leakage
- Runs in temporary directory

Author: QuantumDev Team
Version: 1.0.0
"""

from __future__ import annotations

import subprocess
import tempfile
import logging
import os
from typing import Dict, Any

log = logging.getLogger(__name__)

# Maximum code length in characters
MAX_CODE_LENGTH = 4000

# Blacklist of dangerous patterns
# These are checked as substrings in the raw code
FORBIDDEN_PATTERNS = [
    "import os",
    "from os",
    "import sys",
    "from sys",
    "import subprocess",
    "from subprocess",
    "import socket",
    "from socket",
    "import shutil",
    "from shutil",
    "open(",
    "eval(",
    "exec(",
    "__import__",
    "import pickle",
    "from pickle",
    "import multiprocessing",
    "from multiprocessing",
    "import ctypes",
    "from ctypes",
    "import platform",
    "from platform",
]


def execute_python_snippet(code: str, timeout_s: float = 3.0) -> Dict[str, Any]:
    """
    Execute a Python code snippet in an isolated subprocess.
    
    This function enforces basic safety limits before execution and runs
    the code in a sandboxed subprocess with timeout.
    
    Args:
        code: Python code to execute (string)
        timeout_s: Maximum execution time in seconds (default: 3.0)
        
    Returns:
        Dictionary with keys:
        - ok: bool, whether execution succeeded
        - stdout: str, captured standard output
        - stderr: str, captured standard error
        - error: str, error message if any (empty string if ok)
        - timeout: bool, whether execution timed out
        
    Security:
        - Enforces code length limit
        - Blocks dangerous import patterns
        - Runs in isolated subprocess
        - No environment variable leakage
        - Executes in temporary directory
        
    Example:
        >>> result = execute_python_snippet("print('Hello')")
        >>> result['ok']
        True
        >>> result['stdout']
        'Hello\\n'
    """
    # Strip code and check if empty
    code = code.strip()
    if not code:
        log.warning("Code executor: empty code provided")
        return {
            "ok": False,
            "stdout": "",
            "stderr": "",
            "error": "empty_code",
            "timeout": False,
        }
    
    # Enforce length limit
    if len(code) > MAX_CODE_LENGTH:
        log.warning(f"Code executor: code too long ({len(code)} > {MAX_CODE_LENGTH} chars)")
        return {
            "ok": False,
            "stdout": "",
            "stderr": "",
            "error": "code_too_long",
            "timeout": False,
        }
    
    # Check for forbidden patterns (case-insensitive)
    code_lower = code.lower()
    for pattern in FORBIDDEN_PATTERNS:
        if pattern in code_lower:
            log.warning(f"Code executor: forbidden pattern detected: {pattern}")
            return {
                "ok": False,
                "stdout": "",
                "stderr": "",
                "error": "forbidden_code_pattern",
                "timeout": False,
            }
    
    # Log only metadata (never log full code for security)
    log.info(f"Executing Python snippet: length={len(code)} chars, timeout={timeout_s}s")
    
    try:
        # Execute in temporary directory to avoid file system access
        # Use subprocess.run with strict isolation
        result = subprocess.run(
            ["python3", "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=tempfile.gettempdir(),  # Run in /tmp
            env={},  # No environment variables passed
            check=False,  # Don't raise on non-zero exit
        )
        
        # Successful execution (even if code had errors, subprocess completed)
        success = result.returncode == 0
        
        return {
            "ok": success,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "error": result.stderr if not success else "",
            "timeout": False,
        }
        
    except subprocess.TimeoutExpired:
        log.warning(f"Code executor: timeout after {timeout_s}s")
        return {
            "ok": False,
            "stdout": "",
            "stderr": "",
            "error": f"execution_timeout ({timeout_s}s)",
            "timeout": True,
        }
        
    except Exception as e:
        log.error(f"Code executor: unexpected error: {e}")
        return {
            "ok": False,
            "stdout": "",
            "stderr": "",
            "error": f"execution_error: {str(e)}",
            "timeout": False,
        }


# === Self-test ===
if __name__ == "__main__":
    import sys
    
    print("=== Code Executor Self-Test ===\n")
    
    # Test 1: Simple print
    print("Test 1: Simple print")
    result = execute_python_snippet("print('Hello, World!')")
    print(f"  Result: {result}")
    assert result["ok"] is True
    assert "Hello, World!" in result["stdout"]
    print("  ✓ PASS\n")
    
    # Test 2: Math calculation
    print("Test 2: Math calculation")
    result = execute_python_snippet("x = 2 + 3\nprint(f'Result: {x}')")
    print(f"  Result: {result}")
    assert result["ok"] is True
    assert "Result: 5" in result["stdout"]
    print("  ✓ PASS\n")
    
    # Test 3: Empty code
    print("Test 3: Empty code")
    result = execute_python_snippet("")
    print(f"  Result: {result}")
    assert result["ok"] is False
    assert result["error"] == "empty_code"
    print("  ✓ PASS\n")
    
    # Test 4: Code too long
    print("Test 4: Code too long")
    long_code = "print('x')\n" * 5000
    result = execute_python_snippet(long_code)
    print(f"  Result: {result}")
    assert result["ok"] is False
    assert result["error"] == "code_too_long"
    print("  ✓ PASS\n")
    
    # Test 5: Forbidden pattern (import os)
    print("Test 5: Forbidden pattern (import os)")
    result = execute_python_snippet("import os\nprint(os.getcwd())")
    print(f"  Result: {result}")
    assert result["ok"] is False
    assert result["error"] == "forbidden_code_pattern"
    print("  ✓ PASS\n")
    
    # Test 6: Timeout
    print("Test 6: Timeout")
    result = execute_python_snippet("import time\ntime.sleep(10)", timeout_s=0.5)
    print(f"  Result: {result}")
    assert result["ok"] is False
    assert result["timeout"] is True
    print("  ✓ PASS\n")
    
    # Test 7: Runtime error
    print("Test 7: Runtime error")
    result = execute_python_snippet("x = 1 / 0")
    print(f"  Result: {result}")
    assert result["ok"] is False
    assert "ZeroDivisionError" in result["stderr"]
    print("  ✓ PASS\n")
    
    print("=== All Tests Passed ===")
    sys.exit(0)
