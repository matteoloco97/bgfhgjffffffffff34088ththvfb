#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_tools_endpoints.py — Test BLOCK 4 Advanced Tools

Tests for:
- /tools/math endpoint
- /tools/python endpoint
- /files/upload endpoint
- /files/query endpoint
"""

import sys
import os
import unittest
import asyncio
import tempfile
from pathlib import Path

# Add project root to path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Set test environment variables
os.environ["TOOLS_MATH_ENABLED"] = "1"
os.environ["TOOLS_PYTHON_EXEC_ENABLED"] = "1"
os.environ["TOOLS_DOCS_ENABLED"] = "1"
os.environ["SEARCH_ANALYTICS_LOG"] = "/tmp/test_analytics.jsonl"
os.environ["CHROMA_PERSIST_DIR"] = "/tmp/test_chroma"

from fastapi.testclient import TestClient
from backend.quantum_api import app


class TestMathToolEndpoint(unittest.TestCase):
    """Test cases for /tools/math endpoint."""
    
    def setUp(self):
        self.client = TestClient(app)
    
    def test_basic_addition(self):
        """Test simple addition."""
        response = self.client.post("/tools/math", json={"expr": "2+2"})
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["result"], "4")
        self.assertEqual(data["type"], "exact")
    
    def test_complex_expression(self):
        """Test complex mathematical expression."""
        response = self.client.post("/tools/math", json={"expr": "sqrt(16) + pow(2,3)"})
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["result"], "12")
    
    def test_trigonometry(self):
        """Test trigonometric functions."""
        response = self.client.post("/tools/math", json={"expr": "sin(0)"})
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["result"], "0")
    
    def test_invalid_expression(self):
        """Test invalid expression handling."""
        response = self.client.post("/tools/math", json={"expr": "invalid expression"})
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertIn("error", data)
    
    def test_security_block(self):
        """Test security blocking of dangerous code."""
        response = self.client.post("/tools/math", json={"expr": "import os"})
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertFalse(data["ok"])
    
    def test_empty_expression(self):
        """Test empty expression."""
        response = self.client.post("/tools/math", json={"expr": ""})
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "empty_expression")


class TestPythonToolEndpoint(unittest.TestCase):
    """Test cases for /tools/python endpoint."""
    
    def setUp(self):
        self.client = TestClient(app)
    
    def test_simple_print(self):
        """Test simple print statement."""
        response = self.client.post(
            "/tools/python",
            json={"code": "print('Hello, World!')"}
        )
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertIn("Hello, World!", data["stdout"])
    
    def test_calculation(self):
        """Test simple calculation."""
        code = """
result = 5 + 3 * 2
print(f"Result: {result}")
"""
        response = self.client.post("/tools/python", json={"code": code})
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertIn("Result: 11", data["stdout"])
    
    def test_security_block_import(self):
        """Test security blocking of dangerous imports."""
        response = self.client.post(
            "/tools/python",
            json={"code": "import os\nprint(os.getcwd())"}
        )
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertIn("Security violation", data["error"])
    
    def test_security_block_subprocess(self):
        """Test blocking of subprocess."""
        response = self.client.post(
            "/tools/python",
            json={"code": "import subprocess"}
        )
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertFalse(data["ok"])
    
    def test_syntax_error(self):
        """Test handling of syntax errors."""
        response = self.client.post(
            "/tools/python",
            json={"code": "print('unclosed string"}
        )
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertNotEqual(data["stderr"], "")
    
    def test_empty_code(self):
        """Test empty code."""
        response = self.client.post("/tools/python", json={"code": ""})
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "empty_code")
    
    def test_code_too_long(self):
        """Test code length limit."""
        long_code = "x = 1\n" * 10000  # Over 10KB
        response = self.client.post("/tools/python", json={"code": long_code})
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "code_too_long")


class TestFileEndpoints(unittest.TestCase):
    """Test cases for /files/upload and /files/query endpoints."""
    
    def setUp(self):
        self.client = TestClient(app)
    
    def test_upload_text_file(self):
        """Test uploading a text file."""
        content = "This is a test document.\nIt has multiple lines.\nFor testing purposes."
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(content)
            temp_path = f.name
        
        try:
            with open(temp_path, 'rb') as f:
                files = {'file': ('test.txt', f, 'text/plain')}
                data = {'user_id': 'test_user'}
                response = self.client.post("/files/upload", files=files, data=data)
            
            self.assertEqual(response.status_code, 200)
            result = response.json()
            
            self.assertTrue(result["ok"])
            self.assertIn("file_id", result)
            self.assertIn("num_chunks", result)
            self.assertGreater(result["num_chunks"], 0)
        finally:
            os.unlink(temp_path)
    
    def test_upload_markdown_file(self):
        """Test uploading a markdown file."""
        content = """# Test Document

This is a **test** markdown file.

## Section 1
Some content here.

## Section 2
More content here.
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(content)
            temp_path = f.name
        
        try:
            with open(temp_path, 'rb') as f:
                files = {'file': ('test.md', f, 'text/markdown')}
                data = {'user_id': 'test_user'}
                response = self.client.post("/files/upload", files=files, data=data)
            
            self.assertEqual(response.status_code, 200)
            result = response.json()
            
            self.assertTrue(result["ok"])
            self.assertIn("file_id", result)
        finally:
            os.unlink(temp_path)
    
    def test_query_documents(self):
        """Test querying documents."""
        # First upload a document
        content = "Python is a high-level programming language. It is widely used for web development."
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(content)
            temp_path = f.name
        
        try:
            # Upload
            with open(temp_path, 'rb') as f:
                files = {'file': ('test_python.txt', f, 'text/plain')}
                data = {'user_id': 'test_user2'}
                upload_response = self.client.post("/files/upload", files=files, data=data)
            
            self.assertEqual(upload_response.status_code, 200)
            
            # Query
            query_response = self.client.post(
                "/files/query",
                json={"q": "programming language", "user_id": "test_user2", "top_k": 5}
            )
            
            self.assertEqual(query_response.status_code, 200)
            result = query_response.json()
            
            self.assertTrue(result["ok"])
            self.assertIn("matches", result)
            # Should find at least one match
            if result["count"] > 0:
                self.assertGreater(len(result["matches"]), 0)
                match = result["matches"][0]
                self.assertIn("text", match)
                self.assertIn("score", match)
        finally:
            os.unlink(temp_path)
    
    def test_query_empty(self):
        """Test querying with empty query."""
        response = self.client.post(
            "/files/query",
            json={"q": "", "user_id": "test_user"}
        )
        
        self.assertEqual(response.status_code, 200)
        result = response.json()
        
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "empty_query")


if __name__ == "__main__":
    # Create test directories
    os.makedirs("/tmp/test_chroma", exist_ok=True)
    
    # Run tests
    unittest.main(verbosity=2)
