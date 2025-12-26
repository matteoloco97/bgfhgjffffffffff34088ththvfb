#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/tools/memory_tool.py — Memory Search Tool for Autonomous Agent

Provides knowledge base and conversation memory search capabilities for the
ReAct-style autonomous agent. Uses ChromaDB for semantic search.

Example Usage:
    from core.tools.memory_tool import MemorySearchTool
    
    tool = MemorySearchTool()
    result = await tool.execute(query="user preferences for crypto", k=5)
    # Returns: {"ok": True, "result": {...}, "error": None}

Author: Matteo (QuantumDev)
Version: 1.0.0
"""

from __future__ import annotations

import logging
from typing import Dict, Any, Optional, List

log = logging.getLogger(__name__)


class MemorySearchTool:
    """
    Memory Search Tool for autonomous agent.
    
    Searches the knowledge base for stored information including:
    - Facts and knowledge
    - User preferences
    - Past conversations
    - Betting history
    
    Parameters Schema:
        {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query for memory"
                },
                "k": {
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
                "results": List[Dict],  # List of memory items with content, score, metadata
                "count": int
            },
            "error": Optional[str]
        }
    
    Examples:
        - memory_search(query="user preferences")
        - memory_search(query="trading strategies", k=10)
        - memory_search(query="what does the user like")
    """
    
    name = "memory_search"
    description = "Search stored knowledge, facts, preferences, and past conversations"
    category = "memory"
    timeout_s = 10
    
    # JSON Schema for LLM function calling
    parameters_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query for memory"
            },
            "k": {
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
    def validate_parameters(query: str, k: int = 5) -> Optional[str]:
        """
        Validate input parameters.
        
        Args:
            query: Search query string
            k: Number of results to return
            
        Returns:
            Error message if validation fails, None if valid
        """
        if not query or not isinstance(query, str):
            return "query must be a non-empty string"
        
        if len(query.strip()) == 0:
            return "query cannot be empty or whitespace only"
        
        if len(query) > 500:
            return "query exceeds maximum length of 500 characters"
        
        if not isinstance(k, int) or k < 1 or k > 20:
            return "k must be an integer between 1 and 20"
        
        return None
    
    @staticmethod
    async def execute(query: str, k: int = 5) -> Dict[str, Any]:
        """
        Execute memory search.
        
        Args:
            query: Search query string
            k: Number of results to return (default: 5)
            
        Returns:
            Structured result: {"ok": bool, "result": any, "error": str}
        """
        query_preview = query[:50] + "..." if len(query) > 50 else query
        log.info(f"[TOOL] memory_search: query='{query_preview}' k={k}")
        
        # Validate parameters
        validation_error = MemorySearchTool.validate_parameters(query, k)
        if validation_error:
            log.warning(f"[TOOL] memory_search validation failed: {validation_error}")
            return {
                "ok": False,
                "result": None,
                "error": validation_error
            }
        
        try:
            from utils.chroma_handler import search_topk
            
            results = search_topk(query.strip(), k=k)
            
            # Format results
            formatted_results: List[Dict[str, Any]] = []
            for r in (results or []):
                formatted_results.append({
                    "content": r.get("document", r.get("text", "")),
                    "score": r.get("score", r.get("sim", 0.0)),
                    "metadata": r.get("metadata", {}),
                    "collection": r.get("collection", "unknown")
                })
            
            log.info(f"[TOOL] memory_search: found {len(formatted_results)} results")
            
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
            error_msg = f"Memory search module not available: {e}"
            log.error(f"[TOOL] memory_search: {error_msg}")
            return {
                "ok": False,
                "result": None,
                "error": error_msg
            }
        except Exception as e:
            error_msg = f"Memory search failed: {e}"
            log.error(f"[TOOL] memory_search: {error_msg}")
            return {
                "ok": False,
                "result": None,
                "error": error_msg
            }
