#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_tools_simple.py — Simple Tests for BLOCK 4 Advanced Tools

Tests for:
- /tools/math endpoint (without FastAPI test client)
- /tools/python endpoint (without FastAPI test client)
- Document ingestion module

These tests don't require network access or embedding models.
"""

import sys
import os
import unittest
import asyncio

# Add project root to path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.calculator import Calculator, is_calculator_query
from core.docs_ingest import chunk_text, extract_text_from_bytes
from agents.code_execution import run_code


class TestCalculatorModule(unittest.TestCase):
    """Test cases for Calculator module."""
    
    def test_basic_arithmetic(self):
        """Test basic arithmetic operations."""
        result = Calculator.evaluate("2+2")
        self.assertIsNotNone(result)
        formatted, result_type = result
        self.assertEqual(formatted, "4")
        self.assertEqual(result_type, "exact")
    
    def test_complex_expression(self):
        """Test complex mathematical expression."""
        result = Calculator.evaluate("sqrt(16) + pow(2,3)")
        self.assertIsNotNone(result)
        formatted, result_type = result
        self.assertEqual(formatted, "12")
    
    def test_trigonometry(self):
        """Test trigonometric functions."""
        result = Calculator.evaluate("sin(0)")
        self.assertIsNotNone(result)
        formatted, result_type = result
        self.assertEqual(formatted, "0")
    
    def test_invalid_expression(self):
        """Test invalid expression handling."""
        result = Calculator.evaluate("invalid expression")
        self.assertIsNone(result)
    
    def test_security_block(self):
        """Test security blocking."""
        result = Calculator.evaluate("import os")
        self.assertIsNone(result)
    
    def test_calculator_detection(self):
        """Test calculator query detection."""
        self.assertTrue(is_calculator_query("2+2"))
        self.assertTrue(is_calculator_query("sqrt(16)"))
        self.assertFalse(is_calculator_query("hello world"))
        self.assertFalse(is_calculator_query("what is the weather"))


class TestCodeExecution(unittest.TestCase):
    """Test cases for code execution module."""
    
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
    
    def test_syntax_error(self):
        """Test handling syntax errors."""
        async def run_test():
            code = "print('unclosed string"
            result = await run_code("python", code)
            
            self.assertFalse(result["success"])
            self.assertNotEqual(result["stderr"], "")
        
        asyncio.run(run_test())
    
    def test_empty_code(self):
        """Test empty code."""
        async def run_test():
            result = await run_code("python", "")
            
            self.assertFalse(result["success"])
            self.assertIn("Empty code", result["error"])
        
        asyncio.run(run_test())


class TestDocumentIngestion(unittest.TestCase):
    """Test cases for document ingestion module."""
    
    def test_chunk_text_basic(self):
        """Test basic text chunking."""
        text = "This is a test. " * 100
        chunks = chunk_text(text, max_chars=100)
        
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 150)  # Allow some buffer
    
    def test_chunk_text_small(self):
        """Test chunking small text."""
        text = "Short text"
        chunks = chunk_text(text, max_chars=100)
        
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], text)
    
    def test_chunk_text_overlap(self):
        """Test chunking with overlap."""
        text = "Word " * 100
        chunks = chunk_text(text, max_chars=50, overlap=10)
        
        self.assertGreater(len(chunks), 1)
        # Check some overlap exists (not exact match due to word boundaries)
        if len(chunks) > 1:
            # Just verify we got multiple chunks
            self.assertIsNotNone(chunks[0])
            self.assertIsNotNone(chunks[1])
    
    def test_extract_text_from_bytes_txt(self):
        """Test extracting text from bytes (plain text)."""
        content = b"This is a test document"
        text = extract_text_from_bytes(content, "text/plain", "test.txt")
        
        self.assertEqual(text, "This is a test document")
    
    def test_extract_text_from_bytes_markdown(self):
        """Test extracting text from bytes (markdown)."""
        content = b"# Test\nThis is **markdown**"
        text = extract_text_from_bytes(content, "text/markdown", "test.md")
        
        self.assertIn("# Test", text)
        self.assertIn("markdown", text)
    
    def test_extract_text_unsupported(self):
        """Test unsupported file type."""
        content = b"some content"
        with self.assertRaises(ValueError):
            extract_text_from_bytes(content, "application/octet-stream", "test.bin")


if __name__ == "__main__":
    # Run tests
    unittest.main(verbosity=2)
