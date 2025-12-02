#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_code_execution.py — Test Code Execution

Tests for safe code execution functionality.
"""

import sys
import os
import unittest
import asyncio

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.code_execution import run_code


class TestCodeExecution(unittest.TestCase):
    """Test cases for code execution."""
    
    def test_simple_print(self):
        """Test executing simple print statement."""
        async def run_test():
            result = await run_code("python", "print('Hello, World!')")
            
            self.assertTrue(result["success"])
            self.assertIn("Hello, World!", result["stdout"])
            self.assertEqual(result["exit_code"], 0)
        
        asyncio.run(run_test())
    
    def test_calculation(self):
        """Test executing calculation."""
        async def run_test():
            code = """
result = 5 + 3 * 2
print(f"Result: {result}")
"""
            result = await run_code("python", code)
            
            self.assertTrue(result["success"])
            self.assertIn("Result: 11", result["stdout"])
        
        asyncio.run(run_test())
    
    def test_security_block_os(self):
        """Test security blocking of os import."""
        async def run_test():
            code = "import os\nprint(os.getcwd())"
            result = await run_code("python", code)
            
            self.assertFalse(result["success"])
            self.assertIn("Security violation", result["error"])
        
        asyncio.run(run_test())
    
    def test_security_block_subprocess(self):
        """Test security blocking of subprocess."""
        async def run_test():
            code = "import subprocess\nsubprocess.run(['ls'])"
            result = await run_code("python", code)
            
            self.assertFalse(result["success"])
            self.assertIn("Security violation", result["error"])
        
        asyncio.run(run_test())
    
    def test_security_block_eval(self):
        """Test security blocking of eval."""
        async def run_test():
            code = "eval('2 + 2')"
            result = await run_code("python", code)
            
            self.assertFalse(result["success"])
            self.assertIn("Security violation", result["error"])
        
        asyncio.run(run_test())
    
    def test_timeout(self):
        """Test timeout enforcement."""
        async def run_test():
            code = """
import time
time.sleep(15)
print('Should not print')
"""
            result = await run_code("python", code)
            
            self.assertFalse(result["success"])
            self.assertIn("timed out", result["error"].lower())
        
        asyncio.run(run_test())
    
    def test_syntax_error(self):
        """Test handling syntax errors."""
        async def run_test():
            code = "print('unclosed string"
            result = await run_code("python", code)
            
            self.assertFalse(result["success"])
            self.assertNotEqual(result["stderr"], "")
        
        asyncio.run(run_test())
    
    def test_runtime_error(self):
        """Test handling runtime errors."""
        async def run_test():
            code = "x = 1 / 0"
            result = await run_code("python", code)
            
            self.assertFalse(result["success"])
            self.assertIn("ZeroDivisionError", result["stderr"])
        
        asyncio.run(run_test())
    
    def test_unsupported_language(self):
        """Test unsupported language."""
        async def run_test():
            result = await run_code("javascript", "console.log('test')")
            
            self.assertFalse(result["success"])
            self.assertIn("not supported", result["error"])
        
        asyncio.run(run_test())
    
    def test_empty_code(self):
        """Test empty code."""
        async def run_test():
            result = await run_code("python", "")
            
            self.assertFalse(result["success"])
            self.assertIn("Empty code", result["error"])
        
        asyncio.run(run_test())


if __name__ == "__main__":
    # Run tests
    unittest.main()
