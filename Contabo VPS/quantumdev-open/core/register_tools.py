#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/register_tools.py — Tool Registration Utilities for QuantumDev Max

Registers all available tools for the function calling system.

Author: Matteo (QuantumDev)
Version: 2.0.0
"""

from __future__ import annotations

import os
import logging
from typing import Dict, Any, Optional, List

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# Import function calling components
from core.function_calling import (
    register_tool,
    get_registry,
    ToolCategory,
    ToolParameter,
    ToolDefinition,
)


# ============================================================================
# WEB SEARCH TOOL
# ============================================================================
@register_tool(
    name="web_search",
    description="Cerca informazioni su internet usando il motore di ricerca",
    category=ToolCategory.SEARCH,
    parameters=[
        ToolParameter("query", "string", "Query di ricerca"),
        ToolParameter("k", "number", "Numero di risultati", required=False, default=5),
    ],
    examples=[
        "cerca le ultime notizie su Bitcoin",
        "trova informazioni sul meteo a Roma",
        "ricerca novità su Python 3.12",
    ],
)
async def web_search_tool(query: str, k: int = 5) -> Dict[str, Any]:
    """Search the web."""
    try:
        from core.web_search import search as web_search_core
        results = web_search_core(query, num=k)
        return {
            "query": query,
            "results": results[:k],
            "count": len(results),
        }
    except Exception as e:
        return {"query": query, "error": str(e)}


# ============================================================================
# WEATHER TOOL
# ============================================================================
@register_tool(
    name="weather",
    description="Ottiene informazioni meteo per una città",
    category=ToolCategory.DATA,
    parameters=[
        ToolParameter("city", "string", "Nome della città"),
    ],
    examples=[
        "meteo Roma",
        "che tempo fa a Milano",
        "previsioni per Napoli",
    ],
)
async def weather_tool(city: str) -> Dict[str, Any]:
    """Get weather data."""
    try:
        from agents.weather_open_meteo import get_weather_for_query
        result = await get_weather_for_query(f"meteo {city}")
        return {"city": city, "weather": result}
    except Exception as e:
        return {"city": city, "error": str(e)}


# ============================================================================
# PRICE LOOKUP TOOL
# ============================================================================
@register_tool(
    name="price_lookup",
    description="Ottiene quotazioni di crypto, azioni, forex",
    category=ToolCategory.DATA,
    parameters=[
        ToolParameter("symbol", "string", "Simbolo (es: BTC, AAPL, EUR/USD)"),
        ToolParameter("type", "string", "Tipo: crypto, stock, forex", required=False, default="crypto"),
    ],
    examples=[
        "prezzo Bitcoin",
        "quotazione AAPL",
        "cambio EUR/USD",
    ],
)
async def price_lookup_tool(symbol: str, type: str = "crypto") -> Dict[str, Any]:
    """Get price data."""
    try:
        from agents.price_agent import get_price_for_query
        query = f"prezzo {symbol}"
        result = await get_price_for_query(query)
        return {"symbol": symbol, "type": type, "data": result}
    except Exception as e:
        return {"symbol": symbol, "error": str(e)}


# ============================================================================
# CODE GENERATOR TOOL
# ============================================================================
@register_tool(
    name="code_generator",
    description="Genera codice in vari linguaggi di programmazione",
    category=ToolCategory.GENERATION,
    parameters=[
        ToolParameter("description", "string", "Descrizione di cosa deve fare il codice"),
        ToolParameter("language", "string", "Linguaggio di programmazione", required=False, default="python"),
    ],
    examples=[
        "funzione per ordinare una lista",
        "API REST con FastAPI",
        "script bash per backup",
    ],
)
async def code_generator_tool(description: str, language: str = "python") -> Dict[str, Any]:
    """Generate code."""
    try:
        from agents.code_agent import get_code_for_query
        query = f"scrivi codice {language}: {description}"
        
        # Get LLM function
        from core.chat_engine import reply_with_llm
        
        result = await get_code_for_query(query, llm_func=reply_with_llm)
        return {
            "description": description,
            "language": language,
            "code": result,
        }
    except Exception as e:
        return {"description": description, "error": str(e)}


# ============================================================================
# NEWS SEARCH TOOL
# ============================================================================
@register_tool(
    name="news_search",
    description="Cerca notizie recenti su un argomento",
    category=ToolCategory.SEARCH,
    parameters=[
        ToolParameter("topic", "string", "Argomento delle notizie"),
        ToolParameter("limit", "number", "Numero massimo di notizie", required=False, default=5),
    ],
    examples=[
        "ultime notizie su Apple",
        "breaking news crypto",
        "novità intelligenza artificiale",
    ],
)
async def news_search_tool(topic: str, limit: int = 5) -> Dict[str, Any]:
    """Search for news."""
    try:
        from agents.news_agent import get_news_for_query
        result = await get_news_for_query(f"ultime notizie {topic}")
        return {"topic": topic, "news": result}
    except Exception as e:
        return {"topic": topic, "error": str(e)}


# ============================================================================
# SPORTS RESULTS TOOL
# ============================================================================
@register_tool(
    name="sports_results",
    description="Ottiene risultati e classifiche sportive",
    category=ToolCategory.DATA,
    parameters=[
        ToolParameter("query", "string", "Query sportiva (es: 'risultati Serie A', 'classifica Premier')"),
    ],
    examples=[
        "risultati Serie A",
        "classifica Champions League",
        "prossime partite Juventus",
    ],
)
async def sports_results_tool(query: str) -> Dict[str, Any]:
    """Get sports results."""
    try:
        from agents.sports_agent import get_sports_for_query
        result = await get_sports_for_query(query)
        return {"query": query, "data": result}
    except Exception as e:
        return {"query": query, "error": str(e)}


# ============================================================================
# SCHEDULE/CALENDAR TOOL
# ============================================================================
@register_tool(
    name="schedule_lookup",
    description="Trova orari ed eventi (partite, eventi, appuntamenti)",
    category=ToolCategory.DATA,
    parameters=[
        ToolParameter("query", "string", "Query per orari/eventi"),
    ],
    examples=[
        "a che ora gioca la Juventus",
        "quando inizia il GP di Monza",
        "orari film al cinema",
    ],
)
async def schedule_lookup_tool(query: str) -> Dict[str, Any]:
    """Get schedule/events."""
    try:
        from agents.schedule_agent import get_schedule_for_query
        result = await get_schedule_for_query(query)
        return {"query": query, "schedule": result}
    except Exception as e:
        return {"query": query, "error": str(e)}


# ============================================================================
# URL READER TOOL
# ============================================================================
@register_tool(
    name="url_reader",
    description="Legge e riassume il contenuto di una pagina web",
    category=ToolCategory.SEARCH,
    parameters=[
        ToolParameter("url", "string", "URL della pagina da leggere"),
    ],
    examples=[
        "leggi https://example.com/article",
        "riassumi questa pagina: https://...",
    ],
)
async def url_reader_tool(url: str) -> Dict[str, Any]:
    """Read URL content."""
    try:
        from core.web_tools import fetch_and_extract
        text, og_image = await fetch_and_extract(url)
        return {
            "url": url,
            "text": text[:5000] if text else "",  # Limit text length
            "og_image": og_image,
            "length": len(text) if text else 0,
        }
    except Exception as e:
        return {"url": url, "error": str(e)}


# ============================================================================
# DATETIME HELPER TOOL
# ============================================================================
@register_tool(
    name="datetime_info",
    description="Fornisce informazioni su data e ora corrente",
    category=ToolCategory.COMPUTATION,
    parameters=[
        ToolParameter("timezone", "string", "Timezone (es: Europe/Rome)", required=False, default="Europe/Rome"),
    ],
    examples=[
        "che giorno è oggi",
        "che ora è",
        "data e ora corrente",
    ],
)
async def datetime_info_tool(timezone: str = "Europe/Rome") -> Dict[str, Any]:
    """Get current datetime info."""
    try:
        from core.datetime_helper import format_datetime_context
        context = format_datetime_context()
        return {"timezone": timezone, "datetime_context": context}
    except Exception as e:
        import time
        from datetime import datetime
        now = datetime.now()
        return {
            "timezone": timezone,
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "weekday": now.strftime("%A"),
            "timestamp": int(time.time()),
        }


# ============================================================================
# REGISTER ALL TOOLS FUNCTION
# ============================================================================
def register_all_tools() -> int:
    """
    Ensure all tools are registered.
    
    Returns:
        Number of registered tools
    """
    registry = get_registry()
    tools = registry.list_tools()
    log.info(f"Registered {len(tools)} tools")
    return len(tools)


def get_tools_summary() -> str:
    """Get a summary of all registered tools."""
    registry = get_registry()
    lines = ["📦 **AVAILABLE TOOLS**\n"]
    
    for category in ToolCategory:
        tools = registry.list_tools(category)
        if tools:
            lines.append(f"\n**{category.value.upper()}:**")
            for tool in tools:
                params = ", ".join([p.name for p in tool.parameters])
                lines.append(f"  • `{tool.name}({params})` - {tool.description}")
    
    return "\n".join(lines)


# === Auto-register on import ===
_registered = False


def ensure_tools_registered() -> None:
    """Ensure tools are registered (idempotent)."""
    global _registered
    if not _registered:
        register_all_tools()
        _registered = True


# Register on import
ensure_tools_registered()


# === Test ===
if __name__ == "__main__":
    import asyncio
    
    async def test():
        print("🧪 Testing Tool Registration")
        print("=" * 60)
        
        # Ensure registration
        count = register_all_tools()
        print(f"Registered tools: {count}")
        
        # Get summary
        summary = get_tools_summary()
        print(summary)
        
        # Test individual tools
        print("\n--- Testing Tools ---")
        
        # Test calculator (from function_calling.py)
        from core.function_calling import get_function_caller
        caller = get_function_caller()
        
        calc_result = await caller.call_tool("calculator", {"expression": "2 + 2 * 10"})
        print(f"Calculator: {calc_result.result}")
        
        # Test datetime
        dt_result = await caller.call_tool("datetime_info", {})
        print(f"DateTime: {dt_result.result}")
        
        print("\n✅ All tests passed!")
    
    asyncio.run(test())
