#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/tools/__init__.py — Tool implementations for Autonomous Agent

This package contains individual tool implementations for the ReAct-style
autonomous agent. Each tool provides:
- JSON Schema for parameters
- Async execute function
- Validation logic
- Error handling
- Usage examples in docstring

Available tools:
- web_search: Search the web for information
- calculator: Evaluate mathematical expressions
- memory_search: Search conversation/knowledge memory
- fetch_url: Fetch and extract webpage content
- get_weather: Get weather data for a location
- get_price: Get crypto/stock/forex prices

Author: Matteo (QuantumDev)
Version: 1.0.0
"""

from core.tools.web_search_tool import WebSearchTool
from core.tools.calculator_tool import CalculatorTool
from core.tools.memory_tool import MemorySearchTool
from core.tools.fetch_url_tool import FetchUrlTool
from core.tools.weather_tool import WeatherTool
from core.tools.price_tool import PriceTool

__all__ = [
    "WebSearchTool",
    "CalculatorTool",
    "MemorySearchTool",
    "FetchUrlTool",
    "WeatherTool",
    "PriceTool",
]
