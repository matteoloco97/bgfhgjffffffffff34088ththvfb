#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/tool_registry.py — Tool Registry for Autonomous Agent

Provides a unified tool abstraction layer for the ReAct-style autonomous agent.
Each tool has: name, description, parameters schema, and async handler.

Author: Matteo (QuantumDev)
Version: 1.0.0
"""

from __future__ import annotations

import os
import json
import logging
from typing import Dict, Any, Optional, List, Callable, Awaitable
from dataclasses import dataclass, field, asdict
from enum import Enum

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)


# === Configuration ===
def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name, "1" if default else "0") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


ENABLE_AUTONOMOUS_MODE = _env_bool("ENABLE_AUTONOMOUS_MODE", True)


# === Enums ===
class ToolCategory(str, Enum):
    """Tool categories for organization."""
    SEARCH = "search"
    DATA = "data"
    COMPUTATION = "computation"
    GENERATION = "generation"
    MEMORY = "memory"
    CODE = "code"
    SPECIALIZED = "specialized"


# === Data Classes ===
@dataclass
class ToolParameter:
    """Tool parameter definition for schema generation."""
    name: str
    type: str  # "string", "number", "boolean", "array", "object"
    description: str
    required: bool = True
    default: Any = None
    enum: Optional[List[str]] = None
    
    def to_schema(self) -> Dict[str, Any]:
        """Convert to JSON Schema format."""
        schema: Dict[str, Any] = {
            "type": self.type,
            "description": self.description,
        }
        if self.enum:
            schema["enum"] = self.enum
        if self.default is not None:
            schema["default"] = self.default
        return schema


@dataclass
class Tool:
    """
    Complete tool definition for the autonomous agent.
    
    Attributes:
        name: Unique tool identifier (e.g., "web_search", "calculator")
        description: Human-readable description for LLM tool selection
        category: Tool category for organization
        handler: Async function that executes the tool
        parameters: List of parameter definitions
        examples: Example usage strings
        timeout_s: Execution timeout in seconds
        enabled: Whether the tool is available
        requires_confirmation: Whether user confirmation is needed before execution
    """
    name: str
    description: str
    category: ToolCategory
    handler: Callable[..., Awaitable[Any]]
    parameters: List[ToolParameter] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    timeout_s: int = 30
    enabled: bool = True
    requires_confirmation: bool = False
    
    def to_function_schema(self) -> Dict[str, Any]:
        """Convert to OpenAI function calling schema format."""
        properties = {}
        required = []
        
        for param in self.parameters:
            properties[param.name] = param.to_schema()
            if param.required:
                required.append(param.name)
        
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "parameters": [asdict(p) for p in self.parameters],
            "examples": self.examples,
            "timeout_s": self.timeout_s,
            "enabled": self.enabled,
            "requires_confirmation": self.requires_confirmation,
        }


# === Tool Registry ===
class AutonomousToolRegistry:
    """
    Registry for all available tools in the autonomous agent system.
    
    Provides:
    - Tool registration and lookup
    - Schema generation for LLM function calling
    - Tool descriptions for planning prompts
    """
    
    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self._categories: Dict[ToolCategory, List[str]] = {cat: [] for cat in ToolCategory}
    
    def register(
        self,
        name: str,
        description: str,
        category: ToolCategory,
        handler: Callable[..., Awaitable[Any]],
        parameters: Optional[List[ToolParameter]] = None,
        examples: Optional[List[str]] = None,
        timeout_s: int = 30,
        requires_confirmation: bool = False,
    ) -> Tool:
        """
        Register a tool in the registry.
        
        Args:
            name: Unique tool name
            description: Tool description for LLM
            category: Tool category
            handler: Async function to execute
            parameters: Parameter definitions
            examples: Example usages
            timeout_s: Execution timeout
            requires_confirmation: Whether confirmation is needed
            
        Returns:
            The registered Tool instance
        """
        tool = Tool(
            name=name,
            description=description,
            category=category,
            handler=handler,
            parameters=parameters or [],
            examples=examples or [],
            timeout_s=timeout_s,
            requires_confirmation=requires_confirmation,
        )
        self._tools[name] = tool
        self._categories[category].append(name)
        log.info(f"Tool registered: {name} ({category.value})")
        return tool
    
    def register_decorator(
        self,
        name: str,
        description: str,
        category: ToolCategory,
        parameters: Optional[List[ToolParameter]] = None,
        examples: Optional[List[str]] = None,
        timeout_s: int = 30,
        requires_confirmation: bool = False,
    ) -> Callable:
        """
        Decorator to register a tool function.
        
        Usage:
            @registry.register_decorator(
                name="web_search",
                description="Search the web",
                category=ToolCategory.SEARCH,
                parameters=[ToolParameter("query", "string", "Search query")]
            )
            async def web_search(query: str) -> Dict[str, Any]:
                ...
        """
        def decorator(func: Callable[..., Awaitable[Any]]) -> Callable:
            self.register(
                name=name,
                description=description,
                category=category,
                handler=func,
                parameters=parameters,
                examples=examples,
                timeout_s=timeout_s,
                requires_confirmation=requires_confirmation,
            )
            return func
        return decorator
    
    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name)
    
    def list_tools(
        self,
        category: Optional[ToolCategory] = None,
        enabled_only: bool = True,
    ) -> List[Tool]:
        """
        List all registered tools.
        
        Args:
            category: Filter by category (None for all)
            enabled_only: Only include enabled tools
            
        Returns:
            List of Tool instances
        """
        if category:
            names = self._categories.get(category, [])
            tools = [self._tools[n] for n in names if n in self._tools]
        else:
            tools = list(self._tools.values())
        
        if enabled_only:
            tools = [t for t in tools if t.enabled]
        
        return tools
    
    def get_tool_names(self, enabled_only: bool = True) -> List[str]:
        """Get list of all tool names."""
        tools = self.list_tools(enabled_only=enabled_only)
        return [t.name for t in tools]
    
    def get_all_schemas(self, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """Get all tool schemas for LLM function calling."""
        tools = self.list_tools(enabled_only=enabled_only)
        return [t.to_function_schema() for t in tools]
    
    def get_tools_description(self, include_examples: bool = False) -> str:
        """
        Get human-readable description of all tools for LLM prompts.
        
        Args:
            include_examples: Whether to include usage examples
            
        Returns:
            Formatted string describing all available tools
        """
        lines = ["AVAILABLE TOOLS:\n"]
        
        for cat in ToolCategory:
            tools = self.list_tools(category=cat)
            if tools:
                lines.append(f"\n## {cat.value.upper()}:")
                for t in tools:
                    params_str = ", ".join([
                        f"{p.name}: {p.type}{'?' if not p.required else ''}"
                        for p in t.parameters
                    ])
                    lines.append(f"- {t.name}({params_str})")
                    lines.append(f"  Description: {t.description}")
                    if include_examples and t.examples:
                        lines.append(f"  Examples: {', '.join(t.examples[:2])}")
        
        return "\n".join(lines)
    
    def get_tool_for_planning(self) -> str:
        """
        Get condensed tool list optimized for planning prompts.
        
        Returns:
            Compact string format for planning: "tool_name(params) - description"
        """
        lines = []
        for tool in self.list_tools():
            params = ", ".join([p.name for p in tool.parameters])
            lines.append(f"- {tool.name}({params}): {tool.description}")
        return "\n".join(lines)
    
    def get_tools_for_api(self, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """
        Get tools formatted for API response with full schema information.
        
        This method returns a list of tools with:
        - Name and description
        - JSON Schema for parameters
        - Example usage
        - Category and configuration
        
        Args:
            enabled_only: Only include enabled tools
            
        Returns:
            List of tool dicts with full schema information
        """
        tools = self.list_tools(enabled_only=enabled_only)
        result = []
        
        for tool in tools:
            # Build parameters schema
            properties = {}
            required = []
            
            for param in tool.parameters:
                properties[param.name] = {
                    "type": param.type,
                    "description": param.description
                }
                if param.default is not None:
                    properties[param.name]["default"] = param.default
                if param.enum:
                    properties[param.name]["enum"] = param.enum
                if param.required:
                    required.append(param.name)
            
            result.append({
                "name": tool.name,
                "description": tool.description,
                "category": tool.category.value,
                "parameters_schema": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                },
                "examples": tool.examples,
                "timeout_s": tool.timeout_s,
                "enabled": tool.enabled,
                "requires_confirmation": tool.requires_confirmation
            })
        
        return result
    
    def disable_tool(self, name: str) -> bool:
        """Disable a tool by name."""
        tool = self._tools.get(name)
        if tool:
            tool.enabled = False
            log.info(f"Tool disabled: {name}")
            return True
        return False
    
    def enable_tool(self, name: str) -> bool:
        """Enable a tool by name."""
        tool = self._tools.get(name)
        if tool:
            tool.enabled = True
            log.info(f"Tool enabled: {name}")
            return True
        return False


# === Tool Execution Wrapper ===
import asyncio
import time
from dataclasses import dataclass as execution_dataclass


@execution_dataclass
class ToolExecutionResult:
    """
    Structured result from tool execution.
    
    Attributes:
        ok: Whether the execution was successful
        result: The result data if successful, None otherwise
        error: Error message if execution failed, None otherwise
        tool_name: Name of the tool that was executed
        execution_time_ms: Time taken for execution in milliseconds
    """
    ok: bool
    result: Any
    error: Optional[str]
    tool_name: str
    execution_time_ms: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "ok": self.ok,
            "result": self.result,
            "error": self.error,
            "tool_name": self.tool_name,
            "execution_time_ms": self.execution_time_ms
        }


class ToolExecutionWrapper:
    """
    Wrapper for executing tools with timeout, validation, and logging.
    
    Features:
    - Parameter validation against JSON schema
    - Async execution with configurable timeout
    - Structured result format: {ok: bool, result: any, error: str}
    - Logging with [TOOL] prefix
    - Execution timing
    
    Usage:
        wrapper = ToolExecutionWrapper(registry)
        result = await wrapper.execute("calculator", expression="2 + 2")
        # Returns: ToolExecutionResult(ok=True, result={...}, error=None, ...)
    """
    
    def __init__(self, registry: AutonomousToolRegistry):
        """
        Initialize wrapper with tool registry.
        
        Args:
            registry: The tool registry to use for tool lookup
        """
        self.registry = registry
    
    def validate_parameters(self, tool: Tool, params: Dict[str, Any]) -> Optional[str]:
        """
        Validate parameters against tool's parameter definitions.
        
        Args:
            tool: The tool to validate parameters for
            params: The parameters to validate
            
        Returns:
            Error message if validation fails, None if valid
        """
        # Check required parameters
        for param_def in tool.parameters:
            if param_def.required and param_def.name not in params:
                return f"Missing required parameter: {param_def.name}"
            
            if param_def.name in params:
                value = params[param_def.name]
                
                # Type validation
                expected_type = param_def.type
                if expected_type == "string" and not isinstance(value, str):
                    return f"Parameter '{param_def.name}' must be a string"
                elif expected_type == "number" and not isinstance(value, (int, float)):
                    return f"Parameter '{param_def.name}' must be a number"
                elif expected_type == "boolean" and not isinstance(value, bool):
                    return f"Parameter '{param_def.name}' must be a boolean"
                elif expected_type == "array" and not isinstance(value, list):
                    return f"Parameter '{param_def.name}' must be an array"
                elif expected_type == "object" and not isinstance(value, dict):
                    return f"Parameter '{param_def.name}' must be an object"
                
                # Enum validation
                if param_def.enum and value not in param_def.enum:
                    return f"Parameter '{param_def.name}' must be one of: {param_def.enum}"
        
        return None
    
    async def execute(
        self,
        tool_name: str,
        timeout_override: Optional[int] = None,
        **params: Any
    ) -> ToolExecutionResult:
        """
        Execute a tool with timeout, validation, and logging.
        
        Args:
            tool_name: Name of the tool to execute
            timeout_override: Optional timeout override in seconds
            **params: Tool parameters
            
        Returns:
            ToolExecutionResult with ok, result, error, tool_name, execution_time_ms
        """
        start_time = time.perf_counter()
        
        # Get tool from registry
        tool = self.registry.get(tool_name)
        if tool is None:
            log.warning(f"[TOOL] Tool not found: {tool_name}")
            return ToolExecutionResult(
                ok=False,
                result=None,
                error=f"Tool not found: {tool_name}",
                tool_name=tool_name,
                execution_time_ms=0
            )
        
        # Check if tool is enabled
        if not tool.enabled:
            log.warning(f"[TOOL] Tool disabled: {tool_name}")
            return ToolExecutionResult(
                ok=False,
                result=None,
                error=f"Tool is disabled: {tool_name}",
                tool_name=tool_name,
                execution_time_ms=0
            )
        
        # Validate parameters
        validation_error = self.validate_parameters(tool, params)
        if validation_error:
            log.warning(f"[TOOL] Validation failed for {tool_name}: {validation_error}")
            return ToolExecutionResult(
                ok=False,
                result=None,
                error=validation_error,
                tool_name=tool_name,
                execution_time_ms=0
            )
        
        # Determine timeout
        timeout = timeout_override or tool.timeout_s
        
        log.info(f"[TOOL] Executing {tool_name} with params: {list(params.keys())} (timeout={timeout}s)")
        
        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                tool.handler(**params),
                timeout=timeout
            )
            
            execution_time = int((time.perf_counter() - start_time) * 1000)
            
            # Normalize result format
            if isinstance(result, dict):
                # Check if already in structured format
                if "ok" in result:
                    ok = result.get("ok", result.get("success", True))
                    return ToolExecutionResult(
                        ok=ok,
                        result=result.get("result", result),
                        error=result.get("error"),
                        tool_name=tool_name,
                        execution_time_ms=execution_time
                    )
                elif "success" in result:
                    ok = result.get("success", True)
                    return ToolExecutionResult(
                        ok=ok,
                        result=result,
                        error=result.get("error"),
                        tool_name=tool_name,
                        execution_time_ms=execution_time
                    )
            
            # Wrap raw result
            log.info(f"[TOOL] {tool_name} completed in {execution_time}ms")
            return ToolExecutionResult(
                ok=True,
                result=result,
                error=None,
                tool_name=tool_name,
                execution_time_ms=execution_time
            )
            
        except asyncio.TimeoutError:
            execution_time = int((time.perf_counter() - start_time) * 1000)
            error_msg = f"Tool execution timed out after {timeout}s"
            log.error(f"[TOOL] {tool_name}: {error_msg}")
            return ToolExecutionResult(
                ok=False,
                result=None,
                error=error_msg,
                tool_name=tool_name,
                execution_time_ms=execution_time
            )
            
        except Exception as e:
            execution_time = int((time.perf_counter() - start_time) * 1000)
            error_msg = f"Tool execution failed: {str(e)}"
            log.error(f"[TOOL] {tool_name}: {error_msg}")
            return ToolExecutionResult(
                ok=False,
                result=None,
                error=error_msg,
                tool_name=tool_name,
                execution_time_ms=execution_time
            )


def get_tool_execution_wrapper(registry: Optional[AutonomousToolRegistry] = None) -> ToolExecutionWrapper:
    """
    Get a tool execution wrapper instance.
    
    Args:
        registry: Optional registry to use, defaults to global registry
        
    Returns:
        ToolExecutionWrapper instance
    """
    if registry is None:
        registry = get_autonomous_tool_registry()
    return ToolExecutionWrapper(registry)


# === Global Registry Singleton ===
_autonomous_registry: Optional[AutonomousToolRegistry] = None


def get_autonomous_tool_registry() -> AutonomousToolRegistry:
    """
    Get or create the global AutonomousToolRegistry singleton.
    
    Returns:
        AutonomousToolRegistry instance
    """
    global _autonomous_registry
    
    if _autonomous_registry is None:
        _autonomous_registry = AutonomousToolRegistry()
        _register_default_tools(_autonomous_registry)
        log.info("AutonomousToolRegistry initialized with default tools")
    
    return _autonomous_registry


def _register_default_tools(registry: AutonomousToolRegistry) -> None:
    """Register default tools available to the autonomous agent."""
    
    # === Web Search Tool ===
    async def web_search(query: str, num_results: int = 5) -> Dict[str, Any]:
        """Search the web for information."""
        try:
            from core.web_search import search as web_search_core
            results = web_search_core(query, num=num_results)
            return {
                "success": True,
                "query": query,
                "results": results[:num_results],
                "count": len(results),
            }
        except Exception as e:
            return {"success": False, "query": query, "error": str(e)}
    
    registry.register(
        name="web_search",
        description="Search the web for current information, news, prices, or any real-time data",
        category=ToolCategory.SEARCH,
        handler=web_search,
        parameters=[
            ToolParameter("query", "string", "Search query"),
            ToolParameter("num_results", "number", "Number of results", required=False, default=5),
        ],
        examples=["web_search('Bitcoin price today')", "web_search('latest news on AI')"],
        timeout_s=15,
    )
    
    # === Calculator Tool ===
    async def calculator(expression: str) -> Dict[str, Any]:
        """Evaluate a mathematical expression safely."""
        try:
            from core.calculator import Calculator
            result = Calculator.evaluate(expression)
            if result:
                formatted_result, result_type = result
                return {
                    "success": True,
                    "expression": expression,
                    "result": formatted_result,
                    "type": result_type,
                }
            return {"success": False, "expression": expression, "error": "Invalid expression"}
        except Exception as e:
            return {"success": False, "expression": expression, "error": str(e)}
    
    registry.register(
        name="calculator",
        description="Evaluate mathematical expressions, perform calculations",
        category=ToolCategory.COMPUTATION,
        handler=calculator,
        parameters=[
            ToolParameter("expression", "string", "Mathematical expression to evaluate"),
        ],
        examples=["calculator('2 + 2 * 10')", "calculator('sqrt(16) + 5')"],
        timeout_s=5,
    )
    
    # === Memory Search Tool ===
    async def memory_search(query: str, k: int = 5) -> Dict[str, Any]:
        """Search the knowledge base for stored information."""
        try:
            from utils.chroma_handler import search_topk
            results = search_topk(query, k=k)
            return {
                "success": True,
                "query": query,
                "results": results,
                "count": len(results),
            }
        except Exception as e:
            return {"success": False, "query": query, "error": str(e)}
    
    registry.register(
        name="memory_search",
        description="Search stored knowledge, facts, preferences, and past conversations",
        category=ToolCategory.MEMORY,
        handler=memory_search,
        parameters=[
            ToolParameter("query", "string", "Search query for memory"),
            ToolParameter("k", "number", "Number of results", required=False, default=5),
        ],
        examples=["memory_search('user preferences')", "memory_search('trading strategies')"],
        timeout_s=10,
    )
    
    # === URL Fetch Tool ===
    async def fetch_url(url: str) -> Dict[str, Any]:
        """Fetch and extract content from a URL."""
        try:
            from core.web_tools import fetch_and_extract
            result = await fetch_and_extract(url)
            return {
                "success": True,
                "url": url,
                "title": result.get("title", ""),
                "text": result.get("text", "")[:2000],  # Limit to 2000 chars
            }
        except Exception as e:
            return {"success": False, "url": url, "error": str(e)}
    
    registry.register(
        name="fetch_url",
        description="Fetch and extract text content from a specific URL",
        category=ToolCategory.DATA,
        handler=fetch_url,
        parameters=[
            ToolParameter("url", "string", "URL to fetch content from"),
        ],
        examples=["fetch_url('https://example.com/article')"],
        timeout_s=15,
    )
    
    # === Code Execution Tool (if enabled) ===
    async def execute_code(code: str, language: str = "python") -> Dict[str, Any]:
        """Execute code in a sandboxed environment."""
        try:
            from core.code_executor import execute_python_snippet
            if language.lower() != "python":
                return {"success": False, "error": f"Language {language} not supported"}
            result = execute_python_snippet(code=code, timeout_s=10)
            return {
                "success": result.get("ok", False),
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
                "error": result.get("error"),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    if _env_bool("CODE_EXEC_ENABLED", False):
        registry.register(
            name="execute_code",
            description="Execute Python code in a sandboxed environment",
            category=ToolCategory.CODE,
            handler=execute_code,
            parameters=[
                ToolParameter("code", "string", "Python code to execute"),
                ToolParameter("language", "string", "Programming language", required=False, default="python"),
            ],
            examples=["execute_code('print(2 + 2)')"],
            timeout_s=15,
            requires_confirmation=True,
        )
    
    # === Weather Tool ===
    async def get_weather(location: str) -> Dict[str, Any]:
        """Get current weather for a location."""
        try:
            from agents.weather_open_meteo import get_weather_for_query
            if callable(get_weather_for_query):
                result = await get_weather_for_query(f"weather in {location}", None, None)
                return {"success": True, "location": location, "weather": result}
            return {"success": False, "error": "Weather agent not available"}
        except ImportError:
            return {"success": False, "error": "Weather agent module not available"}
        except Exception as e:
            return {"success": False, "location": location, "error": str(e)}
    
    registry.register(
        name="get_weather",
        description="Get current weather and forecast for a specific location",
        category=ToolCategory.DATA,
        handler=get_weather,
        parameters=[
            ToolParameter("location", "string", "City or location name"),
        ],
        examples=["get_weather('Rome')", "get_weather('New York')"],
        timeout_s=10,
    )
    
    # === Price Tool ===
    async def get_price(asset: str) -> Dict[str, Any]:
        """Get current price for crypto, stocks, or forex."""
        try:
            from agents.price_agent import get_price_for_query
            if callable(get_price_for_query):
                result = await get_price_for_query(f"price of {asset}", None, None)
                return {"success": True, "asset": asset, "price_info": result}
            return {"success": False, "error": "Price agent not available"}
        except ImportError:
            return {"success": False, "error": "Price agent module not available"}
        except Exception as e:
            return {"success": False, "asset": asset, "error": str(e)}
    
    registry.register(
        name="get_price",
        description="Get current price for cryptocurrency, stocks, or forex pairs",
        category=ToolCategory.DATA,
        handler=get_price,
        parameters=[
            ToolParameter("asset", "string", "Asset symbol or name (e.g., BTC, AAPL, EUR/USD)"),
        ],
        examples=["get_price('BTC')", "get_price('NVDA')"],
        timeout_s=10,
    )


# === Test ===
if __name__ == "__main__":
    import asyncio
    
    async def test():
        print("🧪 Testing Tool Registry")
        print("=" * 60)
        
        registry = get_autonomous_tool_registry()
        
        # List all tools
        tools = registry.list_tools()
        print(f"Registered tools: {len(tools)}")
        for t in tools:
            print(f"  - {t.name}: {t.description}")
        
        # Get schemas
        print("\nTool schemas:")
        schemas = registry.get_all_schemas()
        print(json.dumps(schemas[:2], indent=2))  # First 2 only
        
        # Get planning format
        print("\nPlanning format:")
        print(registry.get_tool_for_planning())
        
        # Test calculator tool
        print("\nTesting calculator tool:")
        calc = registry.get("calculator")
        if calc:
            result = await calc.handler("2 + 2 * 10")
            print(f"Result: {result}")
        
        print("\n✅ All tests passed!")
    
    asyncio.run(test())
