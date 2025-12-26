#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_tool_registry.py — Tests for Tool Registry

Tests for:
- ToolRegistry class
- ToolExecutionWrapper
- Individual tool implementations
- /tools/list endpoint
"""

import sys
import os
import unittest
import asyncio

# Add project root to path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Set test environment variables
os.environ["TOOLS_MATH_ENABLED"] = "1"
os.environ["CHROMA_PERSIST_DIR"] = "/tmp/test_chroma"


class TestToolRegistry(unittest.TestCase):
    """Test cases for AutonomousToolRegistry."""
    
    def test_get_registry_singleton(self):
        """Test registry singleton pattern."""
        from core.tool_registry import get_autonomous_tool_registry
        
        registry1 = get_autonomous_tool_registry()
        registry2 = get_autonomous_tool_registry()
        
        self.assertIs(registry1, registry2)
    
    def test_registry_has_default_tools(self):
        """Test that registry has default tools registered."""
        from core.tool_registry import get_autonomous_tool_registry
        
        registry = get_autonomous_tool_registry()
        tools = registry.list_tools()
        
        self.assertGreater(len(tools), 0)
        
        # Check for required tools
        tool_names = [t.name for t in tools]
        self.assertIn("web_search", tool_names)
        self.assertIn("calculator", tool_names)
        self.assertIn("memory_search", tool_names)
        self.assertIn("fetch_url", tool_names)
        self.assertIn("get_weather", tool_names)
        self.assertIn("get_price", tool_names)
    
    def test_get_tool_by_name(self):
        """Test getting a tool by name."""
        from core.tool_registry import get_autonomous_tool_registry
        
        registry = get_autonomous_tool_registry()
        
        tool = registry.get("calculator")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.name, "calculator")
        
        tool = registry.get("nonexistent_tool")
        self.assertIsNone(tool)
    
    def test_tool_has_schema(self):
        """Test that tools have proper schemas."""
        from core.tool_registry import get_autonomous_tool_registry
        
        registry = get_autonomous_tool_registry()
        tool = registry.get("calculator")
        
        self.assertIsNotNone(tool)
        
        schema = tool.to_function_schema()
        
        self.assertIn("name", schema)
        self.assertIn("description", schema)
        self.assertIn("parameters", schema)
        self.assertEqual(schema["name"], "calculator")
    
    def test_get_all_schemas(self):
        """Test getting all tool schemas."""
        from core.tool_registry import get_autonomous_tool_registry
        
        registry = get_autonomous_tool_registry()
        schemas = registry.get_all_schemas()
        
        self.assertIsInstance(schemas, list)
        self.assertGreater(len(schemas), 0)
        
        for schema in schemas:
            self.assertIn("name", schema)
            self.assertIn("description", schema)
            self.assertIn("parameters", schema)
    
    def test_get_tools_for_api(self):
        """Test getting tools formatted for API response."""
        from core.tool_registry import get_autonomous_tool_registry
        
        registry = get_autonomous_tool_registry()
        tools = registry.get_tools_for_api()
        
        self.assertIsInstance(tools, list)
        self.assertGreater(len(tools), 0)
        
        for tool in tools:
            self.assertIn("name", tool)
            self.assertIn("description", tool)
            self.assertIn("category", tool)
            self.assertIn("parameters_schema", tool)
            self.assertIn("examples", tool)
            self.assertIn("timeout_s", tool)
            self.assertIn("enabled", tool)
    
    def test_disable_enable_tool(self):
        """Test disabling and enabling a tool."""
        from core.tool_registry import get_autonomous_tool_registry
        
        registry = get_autonomous_tool_registry()
        
        # Disable
        result = registry.disable_tool("calculator")
        self.assertTrue(result)
        
        tool = registry.get("calculator")
        self.assertFalse(tool.enabled)
        
        # Re-enable
        result = registry.enable_tool("calculator")
        self.assertTrue(result)
        
        tool = registry.get("calculator")
        self.assertTrue(tool.enabled)


class TestToolExecutionWrapper(unittest.TestCase):
    """Test cases for ToolExecutionWrapper."""
    
    def test_execute_calculator_tool(self):
        """Test executing calculator through wrapper."""
        from core.tool_registry import get_autonomous_tool_registry, ToolExecutionWrapper
        
        registry = get_autonomous_tool_registry()
        wrapper = ToolExecutionWrapper(registry)
        
        async def run_test():
            result = await wrapper.execute("calculator", expression="2 + 2")
            
            self.assertTrue(result.ok)
            self.assertIsNone(result.error)
            self.assertEqual(result.tool_name, "calculator")
            self.assertGreaterEqual(result.execution_time_ms, 0)
        
        asyncio.run(run_test())
    
    def test_execute_nonexistent_tool(self):
        """Test executing a tool that doesn't exist."""
        from core.tool_registry import get_autonomous_tool_registry, ToolExecutionWrapper
        
        registry = get_autonomous_tool_registry()
        wrapper = ToolExecutionWrapper(registry)
        
        async def run_test():
            result = await wrapper.execute("nonexistent_tool")
            
            self.assertFalse(result.ok)
            self.assertIsNotNone(result.error)
            self.assertIn("not found", result.error.lower())
        
        asyncio.run(run_test())
    
    def test_parameter_validation(self):
        """Test parameter validation in wrapper."""
        from core.tool_registry import get_autonomous_tool_registry, ToolExecutionWrapper
        
        registry = get_autonomous_tool_registry()
        wrapper = ToolExecutionWrapper(registry)
        
        async def run_test():
            # Missing required parameter
            result = await wrapper.execute("calculator")  # Missing 'expression'
            
            self.assertFalse(result.ok)
            self.assertIsNotNone(result.error)
        
        asyncio.run(run_test())
    
    def test_result_to_dict(self):
        """Test converting result to dictionary."""
        from core.tool_registry import ToolExecutionResult
        
        result = ToolExecutionResult(
            ok=True,
            result={"value": 4},
            error=None,
            tool_name="calculator",
            execution_time_ms=10
        )
        
        d = result.to_dict()
        
        self.assertEqual(d["ok"], True)
        self.assertEqual(d["result"], {"value": 4})
        self.assertIsNone(d["error"])
        self.assertEqual(d["tool_name"], "calculator")
        self.assertEqual(d["execution_time_ms"], 10)


class TestIndividualTools(unittest.TestCase):
    """Test cases for individual tool implementations."""
    
    def test_calculator_tool_class(self):
        """Test CalculatorTool class."""
        from core.tools.calculator_tool import CalculatorTool
        
        # Test validation
        error = CalculatorTool.validate_parameters("")
        self.assertIsNotNone(error)
        
        error = CalculatorTool.validate_parameters("2 + 2")
        self.assertIsNone(error)
    
    def test_calculator_tool_execute(self):
        """Test CalculatorTool execute."""
        from core.tools.calculator_tool import CalculatorTool
        
        async def run_test():
            result = await CalculatorTool.execute("2 + 2")
            
            self.assertTrue(result["ok"])
            self.assertIsNotNone(result["result"])
            self.assertEqual(result["result"]["value"], "4")
        
        asyncio.run(run_test())
    
    def test_web_search_tool_validation(self):
        """Test WebSearchTool validation."""
        from core.tools.web_search_tool import WebSearchTool
        
        # Empty query
        error = WebSearchTool.validate_parameters("")
        self.assertIsNotNone(error)
        
        # Valid query
        error = WebSearchTool.validate_parameters("test query")
        self.assertIsNone(error)
        
        # Invalid num_results
        error = WebSearchTool.validate_parameters("test", 100)
        self.assertIsNotNone(error)
    
    def test_memory_tool_validation(self):
        """Test MemorySearchTool validation."""
        from core.tools.memory_tool import MemorySearchTool
        
        # Empty query
        error = MemorySearchTool.validate_parameters("")
        self.assertIsNotNone(error)
        
        # Valid query
        error = MemorySearchTool.validate_parameters("test query")
        self.assertIsNone(error)
    
    def test_fetch_url_tool_validation(self):
        """Test FetchUrlTool validation."""
        from core.tools.fetch_url_tool import FetchUrlTool
        
        # Empty URL
        error = FetchUrlTool.validate_parameters("")
        self.assertIsNotNone(error)
        
        # Invalid protocol
        error = FetchUrlTool.validate_parameters("ftp://example.com")
        self.assertIsNotNone(error)
        
        # Valid URL
        error = FetchUrlTool.validate_parameters("https://example.com")
        self.assertIsNone(error)
    
    def test_weather_tool_validation(self):
        """Test WeatherTool validation."""
        from core.tools.weather_tool import WeatherTool
        
        # Empty location
        error = WeatherTool.validate_parameters("")
        self.assertIsNotNone(error)
        
        # Valid location
        error = WeatherTool.validate_parameters("Rome")
        self.assertIsNone(error)
    
    def test_price_tool_validation(self):
        """Test PriceTool validation."""
        from core.tools.price_tool import PriceTool
        
        # Empty asset
        error = PriceTool.validate_parameters("")
        self.assertIsNotNone(error)
        
        # Valid asset
        error = PriceTool.validate_parameters("BTC")
        self.assertIsNone(error)


if __name__ == "__main__":
    # Create test directories
    os.makedirs("/tmp/test_chroma", exist_ok=True)
    
    # Run tests
    unittest.main(verbosity=2)
