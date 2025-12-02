#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/function_calling.py — Function Calling System for QuantumDev Max

Features:
- LLM-driven tool selection
- Parallel tool execution
- Multi-turn orchestration
- Extensible tool registry
- Automatic parameter extraction

Author: Matteo (QuantumDev)
Version: 2.0.0
"""

from __future__ import annotations

import os
import json
import time
import asyncio
import logging
import re
from typing import Dict, Any, Optional, List, Callable, Awaitable, Union
from dataclasses import dataclass, field, asdict
from enum import Enum
from functools import wraps

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# === ENV Configuration ===
def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name, "1" if default else "0") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)) or str(default)
    try:
        m = re.search(r"-?\d+", raw)
        return int(m.group(0)) if m else default
    except Exception:
        return default


ENABLE_FUNCTION_CALLING = _env_bool("ENABLE_FUNCTION_CALLING", True)
MAX_ORCHESTRATION_TURNS = _env_int("MAX_ORCHESTRATION_TURNS", 5)
TOOL_TIMEOUT_S = _env_int("TOOL_TIMEOUT_S", 30)


# === Data Classes ===
class ToolCategory(str, Enum):
    """Tool categories for organization."""
    SEARCH = "search"
    DATA = "data"
    COMPUTATION = "computation"
    GENERATION = "generation"
    MEMORY = "memory"
    SPECIALIZED = "specialized"


@dataclass
class ToolParameter:
    """Tool parameter definition."""
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
class ToolDefinition:
    """Complete tool definition."""
    name: str
    description: str
    category: ToolCategory
    handler: Callable[..., Awaitable[Any]]
    parameters: List[ToolParameter] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    requires_confirmation: bool = False
    timeout_s: int = TOOL_TIMEOUT_S
    enabled: bool = True
    
    def to_function_schema(self) -> Dict[str, Any]:
        """Convert to OpenAI function calling schema."""
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


@dataclass
class ToolCall:
    """Record of a tool call."""
    tool_name: str
    arguments: Dict[str, Any]
    result: Any = None
    error: Optional[str] = None
    duration_ms: int = 0
    timestamp: int = field(default_factory=lambda: int(time.time()))
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OrchestrationResult:
    """Result of multi-tool orchestration."""
    query: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    final_response: str = ""
    total_duration_ms: int = 0
    turns: int = 0
    success: bool = True
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "final_response": self.final_response,
            "total_duration_ms": self.total_duration_ms,
            "turns": self.turns,
            "success": self.success,
            "error": self.error,
        }


# === Tool Registry ===
class ToolRegistry:
    """Registry for all available tools."""
    
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._categories: Dict[ToolCategory, List[str]] = {cat: [] for cat in ToolCategory}
    
    def register(
        self,
        name: str,
        description: str,
        category: ToolCategory,
        parameters: Optional[List[ToolParameter]] = None,
        examples: Optional[List[str]] = None,
        requires_confirmation: bool = False,
        timeout_s: int = TOOL_TIMEOUT_S,
    ) -> Callable:
        """
        Decorator to register a tool.
        
        Usage:
            @registry.register(
                name="web_search",
                description="Search the web",
                category=ToolCategory.SEARCH,
                parameters=[ToolParameter("query", "string", "Search query")]
            )
            async def web_search(query: str) -> Dict[str, Any]:
                ...
        """
        def decorator(func: Callable[..., Awaitable[Any]]) -> Callable:
            tool = ToolDefinition(
                name=name,
                description=description,
                category=category,
                handler=func,
                parameters=parameters or [],
                examples=examples or [],
                requires_confirmation=requires_confirmation,
                timeout_s=timeout_s,
            )
            self._tools[name] = tool
            self._categories[category].append(name)
            log.info(f"Tool registered: {name} ({category.value})")
            return func
        return decorator
    
    def register_tool(self, tool: ToolDefinition) -> None:
        """Register a pre-built tool definition."""
        self._tools[tool.name] = tool
        self._categories[tool.category].append(tool.name)
        log.info(f"Tool registered: {tool.name} ({tool.category.value})")
    
    def get(self, name: str) -> Optional[ToolDefinition]:
        """Get tool by name."""
        return self._tools.get(name)
    
    def list_tools(self, category: Optional[ToolCategory] = None) -> List[ToolDefinition]:
        """List all tools, optionally filtered by category."""
        if category:
            names = self._categories.get(category, [])
            return [self._tools[n] for n in names if n in self._tools]
        return list(self._tools.values())
    
    def get_all_schemas(self, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """Get all tool schemas for LLM function calling."""
        tools = self.list_tools()
        if enabled_only:
            tools = [t for t in tools if t.enabled]
        return [t.to_function_schema() for t in tools]
    
    def get_tools_description(self) -> str:
        """Get human-readable description of all tools."""
        lines = ["AVAILABLE TOOLS:\n"]
        for cat in ToolCategory:
            tools = self.list_tools(cat)
            if tools:
                lines.append(f"\n{cat.value.upper()}:")
                for t in tools:
                    params_str = ", ".join([f"{p.name}: {p.type}" for p in t.parameters])
                    lines.append(f"  - {t.name}({params_str}): {t.description}")
        return "\n".join(lines)


# Global registry
_registry = ToolRegistry()


def register_tool(
    name: str,
    description: str,
    category: ToolCategory,
    parameters: Optional[List[ToolParameter]] = None,
    examples: Optional[List[str]] = None,
    requires_confirmation: bool = False,
    timeout_s: int = TOOL_TIMEOUT_S,
) -> Callable:
    """Convenience decorator for global registry."""
    return _registry.register(
        name=name,
        description=description,
        category=category,
        parameters=parameters,
        examples=examples,
        requires_confirmation=requires_confirmation,
        timeout_s=timeout_s,
    )


def get_registry() -> ToolRegistry:
    """Get the global tool registry."""
    return _registry


# === Function Caller ===
class FunctionCaller:
    """
    Handles function calling with LLM-driven tool selection.
    """
    
    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        llm_func: Optional[Callable] = None,
    ):
        """
        Initialize Function Caller.
        
        Args:
            registry: Tool registry to use
            llm_func: Async function to call LLM for tool selection
        """
        self.registry = registry or _registry
        self.llm_func = llm_func
    
    async def analyze_query(self, query: str) -> Dict[str, Any]:
        """
        Analyze query to determine which tools are needed.
        
        Args:
            query: User query
            
        Returns:
            Dict with tool recommendations
        """
        if not self.llm_func:
            return {"tools": [], "direct_response": True}
        
        tools_desc = self.registry.get_tools_description()
        
        prompt = f"""Analizza questa richiesta e determina quali tool usare.

RICHIESTA: {query}

{tools_desc}

RISPONDI IN JSON:
{{
    "needs_tools": true/false,
    "tools": [
        {{"name": "tool_name", "arguments": {{"param": "value"}}, "reason": "why"}}
    ],
    "direct_response": true/false se risposta diretta senza tool,
    "parallel": true/false se i tool possono essere eseguiti in parallelo
}}

Solo JSON, nessun altro testo."""
        
        try:
            response = await self.llm_func(
                prompt,
                "Sei un analizzatore di query. Rispondi SOLO in JSON valido.",
            )
            
            # Parse JSON from response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            
            return {"tools": [], "direct_response": True}
            
        except Exception as e:
            log.error(f"Query analysis failed: {e}")
            return {"tools": [], "direct_response": True, "error": str(e)}
    
    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> ToolCall:
        """
        Call a single tool.
        
        Args:
            tool_name: Name of the tool
            arguments: Tool arguments
            
        Returns:
            ToolCall with result
        """
        tool = self.registry.get(tool_name)
        call = ToolCall(tool_name=tool_name, arguments=arguments)
        
        if not tool:
            call.error = f"Tool not found: {tool_name}"
            return call
        
        if not tool.enabled:
            call.error = f"Tool disabled: {tool_name}"
            return call
        
        start_time = time.perf_counter()
        
        try:
            result = await asyncio.wait_for(
                tool.handler(**arguments),
                timeout=tool.timeout_s,
            )
            call.result = result
            
        except asyncio.TimeoutError:
            call.error = f"Timeout after {tool.timeout_s}s"
            
        except Exception as e:
            call.error = str(e)
            log.error(f"Tool {tool_name} error: {e}")
        
        call.duration_ms = int((time.perf_counter() - start_time) * 1000)
        return call
    
    async def call_tools_parallel(
        self,
        tool_calls: List[Dict[str, Any]],
    ) -> List[ToolCall]:
        """
        Call multiple tools in parallel.
        
        Args:
            tool_calls: List of {"name": str, "arguments": dict}
            
        Returns:
            List of ToolCall results
        """
        tasks = [
            self.call_tool(tc["name"], tc.get("arguments", {}))
            for tc in tool_calls
        ]
        return await asyncio.gather(*tasks)
    
    async def orchestrate(
        self,
        query: str,
        max_turns: int = MAX_ORCHESTRATION_TURNS,
    ) -> OrchestrationResult:
        """
        Orchestrate multi-turn tool calling for a query.
        
        Args:
            query: User query
            max_turns: Maximum orchestration turns
            
        Returns:
            OrchestrationResult with all tool calls and final response
        """
        result = OrchestrationResult(query=query)
        start_time = time.perf_counter()
        
        if not ENABLE_FUNCTION_CALLING:
            result.error = "Function calling is disabled"
            result.success = False
            return result
        
        try:
            for turn in range(max_turns):
                result.turns = turn + 1
                
                # Analyze what tools are needed
                analysis = await self.analyze_query(query)
                
                if analysis.get("direct_response"):
                    # No tools needed, generate direct response
                    if self.llm_func:
                        result.final_response = await self.llm_func(query, "")
                    break
                
                tools_to_call = analysis.get("tools", [])
                if not tools_to_call:
                    break
                
                # Call tools
                if analysis.get("parallel"):
                    calls = await self.call_tools_parallel(tools_to_call)
                else:
                    calls = []
                    for tc in tools_to_call:
                        call = await self.call_tool(tc["name"], tc.get("arguments", {}))
                        calls.append(call)
                
                result.tool_calls.extend(calls)
                
                # Check if any tool failed
                failed = [c for c in calls if c.error]
                if failed:
                    log.warning(f"Some tools failed: {[c.tool_name for c in failed]}")
                
                # Build context with tool results for final response
                successful = [c for c in calls if not c.error]
                if successful:
                    tool_context = "\n".join([
                        f"[{c.tool_name}]: {json.dumps(c.result, ensure_ascii=False)[:1000]}"
                        for c in successful
                    ])
                    
                    synthesis_query = (
                        f"Query originale: {query}\n\n"
                        f"Risultati dei tool:\n{tool_context}\n\n"
                        "Sintetizza una risposta completa basata su questi risultati."
                    )
                    
                    if self.llm_func:
                        result.final_response = await self.llm_func(
                            synthesis_query,
                            "Sei un assistente che sintetizza informazioni da varie fonti.",
                        )
                    break
        
        except Exception as e:
            result.error = str(e)
            result.success = False
            log.error(f"Orchestration error: {e}")
        
        result.total_duration_ms = int((time.perf_counter() - start_time) * 1000)
        return result


# === Singleton Instance ===
_caller_instance: Optional[FunctionCaller] = None


def get_function_caller(llm_func: Optional[Callable] = None) -> FunctionCaller:
    """
    Get or create FunctionCaller singleton.
    
    Args:
        llm_func: LLM function for tool selection
        
    Returns:
        FunctionCaller instance
    """
    global _caller_instance
    
    if _caller_instance is None:
        _caller_instance = FunctionCaller(llm_func=llm_func)
    elif llm_func and _caller_instance.llm_func is None:
        _caller_instance.llm_func = llm_func
    
    return _caller_instance


# === Built-in Tools (Examples) ===
@register_tool(
    name="calculator",
    description="Esegue calcoli matematici",
    category=ToolCategory.COMPUTATION,
    parameters=[
        ToolParameter("expression", "string", "Espressione matematica da valutare"),
    ],
    examples=["2 + 2", "sqrt(16)", "100 * 0.15"],
)
async def calculator_tool(expression: str) -> Dict[str, Any]:
    """Safe calculator tool using AST for expression evaluation."""
    import ast
    import operator
    import math
    
    # Supported operators
    operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }
    
    # Supported math functions
    functions = {
        'abs': abs,
        'round': round,
        'min': min,
        'max': max,
        'pow': pow,
        'sqrt': math.sqrt,
        'sin': math.sin,
        'cos': math.cos,
        'tan': math.tan,
        'log': math.log,
        'log10': math.log10,
        'exp': math.exp,
        'floor': math.floor,
        'ceil': math.ceil,
    }
    
    # Supported constants
    constants = {
        'pi': math.pi,
        'e': math.e,
    }
    
    def safe_eval_node(node):
        """Safely evaluate an AST node."""
        if isinstance(node, ast.Constant):  # Python 3.8+
            return node.value
        elif isinstance(node, ast.Num):  # Python 3.7 compatibility
            return node.n
        elif isinstance(node, ast.BinOp):
            left = safe_eval_node(node.left)
            right = safe_eval_node(node.right)
            op = operators.get(type(node.op))
            if op is None:
                raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
            return op(left, right)
        elif isinstance(node, ast.UnaryOp):
            operand = safe_eval_node(node.operand)
            op = operators.get(type(node.op))
            if op is None:
                raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
            return op(operand)
        elif isinstance(node, ast.Call):
            func_name = node.func.id if isinstance(node.func, ast.Name) else None
            if func_name not in functions:
                raise ValueError(f"Unsupported function: {func_name}")
            args = [safe_eval_node(arg) for arg in node.args]
            return functions[func_name](*args)
        elif isinstance(node, ast.Name):
            if node.id in constants:
                return constants[node.id]
            raise ValueError(f"Unknown variable: {node.id}")
        else:
            raise ValueError(f"Unsupported expression type: {type(node).__name__}")
    
    try:
        # Parse expression
        tree = ast.parse(expression, mode='eval')
        result = safe_eval_node(tree.body)
        return {"expression": expression, "result": result}
    except Exception as e:
        return {"expression": expression, "error": str(e)}


@register_tool(
    name="memory_search",
    description="Cerca nella memoria ChromaDB",
    category=ToolCategory.MEMORY,
    parameters=[
        ToolParameter("query", "string", "Query di ricerca"),
        ToolParameter("k", "number", "Numero di risultati", required=False, default=5),
    ],
    examples=["cerca preferenze utente", "trova facts su trading"],
)
async def memory_search_tool(query: str, k: int = 5) -> Dict[str, Any]:
    """Search ChromaDB memory."""
    try:
        from utils.chroma_handler import search_topk
        results = search_topk(query, k=k)
        return {"query": query, "results": results, "count": len(results)}
    except Exception as e:
        return {"query": query, "error": str(e)}


# === Test ===
if __name__ == "__main__":
    async def test():
        print("🧪 Testing Function Calling System")
        print("=" * 60)
        
        # Test registry
        registry = get_registry()
        tools = registry.list_tools()
        print(f"Registered tools: {len(tools)}")
        for t in tools:
            print(f"  - {t.name}: {t.description}")
        
        print("\nTool schemas:")
        schemas = registry.get_all_schemas()
        print(json.dumps(schemas, indent=2))
        
        # Test calculator
        caller = get_function_caller()
        result = await caller.call_tool("calculator", {"expression": "2 + 2 * 10"})
        print(f"\nCalculator test: {result.result}")
        
        print("\n✅ All tests passed!")
    
    asyncio.run(test())
