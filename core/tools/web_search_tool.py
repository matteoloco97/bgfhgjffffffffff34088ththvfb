#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/tools/web_search_tool.py — Web Search Tool for Autonomous Agent

Provides web search capabilities for the ReAct-style autonomous agent.
Uses the existing core.web_search module for backend search functionality.

Example Usage:
    from core.tools.web_search_tool import WebSearchTool
    
    tool = WebSearchTool()
    result = await tool.execute(query="Python asyncio tutorial", num_results=5)
    # Returns: {"ok": True, "result": {...}, "error": None}

Author: Matteo (QuantumDev)
Version: 1.0.0
"""

from __future__ import annotations

import logging
from typing import Dict, Any, Optional

log = logging.getLogger(__name__)


class WebSearchTool:
    """
    Web Search Tool for autonomous agent.
    
    Searches the web for current information, news, prices, or any real-time data.
    
    Parameters Schema:
        {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query string"
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return (default: 5)",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20
                }
            },
            "required": ["query"]
        }
    
    Returns:
        {
            "ok": bool,
            "result": {
                "query": str,
                "results": List[Dict],  # List of search results with url, title, snippet
                "count": int
            },
            "error": Optional[str]
        }
    
    Examples:
        - web_search(query="Bitcoin price today")
        - web_search(query="latest news on AI", num_results=10)
        - web_search(query="weather forecast Rome")
    """
    
    name = "web_search"
    description = "Search the web for current information, news, prices, or any real-time data"
    category = "search"
    timeout_s = 15
    
    # JSON Schema for LLM function calling
    parameters_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query string"
            },
            "num_results": {
                "type": "integer",
                "description": "Number of results to return (default: 5)",
                "default": 5,
                "minimum": 1,
                "maximum": 20
            }
        },
        "required": ["query"]
    }
    
    @staticmethod
    def validate_parameters(query: str, num_results: int = 5) -> Optional[str]:
        """
        Validate input parameters.
        
        Args:
            query: Search query string
            num_results: Number of results to return
            
        Returns:
            Error message if validation fails, None if valid
        """
        if not query or not isinstance(query, str):
            return "query must be a non-empty string"
        
        if len(query.strip()) == 0:
            return "query cannot be empty or whitespace only"
        
        if len(query) > 500:
            return "query exceeds maximum length of 500 characters"
        
        if not isinstance(num_results, int) or num_results < 1 or num_results > 20:
            return "num_results must be an integer between 1 and 20"
        
        return None
    
    @staticmethod
    async def execute(query: str, num_results: int = 5) -> Dict[str, Any]:
        """
        Execute web search.
        
        Args:
            query: Search query string
            num_results: Number of results to return (default: 5)
            
        Returns:
            Structured result: {"ok": bool, "result": any, "error": str}
        """
        log.info(f"[TOOL] web_search: query='{query[:50]}...' num_results={num_results}")
        
        # Validate parameters
        validation_error = WebSearchTool.validate_parameters(query, num_results)
        if validation_error:
            log.warning(f"[TOOL] web_search validation failed: {validation_error}")
            return {
                "ok": False,
                "result": None,
                "error": validation_error
            }
        
        try:
            from core.web_search import search as web_search_core
            
            results = web_search_core(query.strip(), num=num_results)
            
            # Format results
            formatted_results = [
                {
                    "url": r.get("url", ""),
                    "title": r.get("title", ""),
                    "snippet": r.get("snippet", r.get("title", ""))
                }
                for r in (results or [])[:num_results]
            ]
            
            log.info(f"[TOOL] web_search: found {len(formatted_results)} results")
            
            return {
                "ok": True,
                "result": {
                    "query": query,
                    "results": formatted_results,
                    "count": len(formatted_results)
                },
                "error": None
            }
            
        except ImportError as e:
            error_msg = f"Web search module not available: {e}"
            log.error(f"[TOOL] web_search: {error_msg}")
            return {
                "ok": False,
                "result": None,
                "error": error_msg
            }
        except Exception as e:
            error_msg = f"Web search failed: {e}"
            log.error(f"[TOOL] web_search: {error_msg}")
            return {
                "ok": False,
                "result": None,
                "error": error_msg
            }
