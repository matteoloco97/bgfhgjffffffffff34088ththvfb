#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agents/code_execution.py — Safe Code Execution for QuantumDev Max

Features:
- Isolated subprocess execution
- Timeout enforcement
- Basic security restrictions
- Currently supports Python only

Author: Matteo (QuantumDev)
Version: 2.0.0
"""

from __future__ import annotations

import os
import sys
import asyncio
import logging
from typing import Dict, Any, Optional

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# === ENV Configuration ===
CODE_EXEC_TIMEOUT = int(os.getenv("CODE_EXEC_TIMEOUT", "10"))
CODE_EXEC_ENABLED = os.getenv("CODE_EXEC_ENABLED", "1") == "1"


async def run_code(
    language: str,
    code: str,
    input_data: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute code in a safe, isolated environment.
    
    Args:
        language: Programming language (currently only "python" supported)
        code: Code to execute
        input_data: Optional input data to pass to the code
        
    Returns:
        Dictionary with execution results (stdout, stderr, exit_code, error)
    """
    if not CODE_EXEC_ENABLED:
        return {
            "success": False,
            "error": "Code execution is disabled",
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
        }
    
    if not code or not code.strip():
        return {
            "success": False,
            "error": "Empty code provided",
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
        }
    
    language = language.lower().strip()
    
    # Only support Python for now
    if language != "python":
        return {
            "success": False,
            "error": f"Language '{language}' not supported. Only 'python' is currently supported.",
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
        }
    
    try:
        # Basic security check - block dangerous imports/operations
        dangerous_patterns = [
            "import os",
            "from os",
            "import subprocess",
            "from subprocess",
            "import sys",
            "__import__",
            "eval(",
            "exec(",
            "compile(",
            "open(",
            "file(",
            "input(",
            "raw_input(",
        ]
        
        code_lower = code.lower()
        for pattern in dangerous_patterns:
            if pattern in code_lower:
                log.warning(f"Code execution blocked: dangerous pattern '{pattern}' detected")
                return {
                    "success": False,
                    "error": f"Security violation: '{pattern}' is not allowed",
                    "stdout": "",
                    "stderr": "",
                    "exit_code": -1,
                }
        
        # Create subprocess to execute code
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            code,
            stdin=asyncio.subprocess.PIPE if input_data else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        # Run with timeout
        try:
            stdout_data, stderr_data = await asyncio.wait_for(
                process.communicate(input=input_data.encode() if input_data else None),
                timeout=CODE_EXEC_TIMEOUT
            )
            
            stdout = stdout_data.decode('utf-8', errors='replace')
            stderr = stderr_data.decode('utf-8', errors='replace')
            exit_code = process.returncode
            
            success = exit_code == 0
            
            return {
                "success": success,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
                "error": stderr if not success else None,
            }
            
        except asyncio.TimeoutError:
            # Kill process on timeout
            try:
                process.kill()
                await process.wait()
            except:
                pass
            
            return {
                "success": False,
                "error": f"Code execution timed out after {CODE_EXEC_TIMEOUT} seconds",
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
            }
            
    except Exception as e:
        log.error(f"Code execution error: {e}")
        return {
            "success": False,
            "error": f"Execution error: {str(e)}",
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
        }


# === Test ===
if __name__ == "__main__":
    import asyncio
    
    async def test():
        # Test simple code
        result = await run_code("python", "print('Hello, World!')")
        print("Test 1:", result)
        
        # Test with calculation
        result = await run_code("python", "result = 2 + 2\nprint(f'Result: {result}')")
        print("Test 2:", result)
        
        # Test security block
        result = await run_code("python", "import os\nprint(os.getcwd())")
        print("Test 3 (should fail):", result)
    
    asyncio.run(test())
