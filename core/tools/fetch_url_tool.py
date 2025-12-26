#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/tools/fetch_url_tool.py — URL Fetch Tool for Autonomous Agent

Provides webpage content extraction capabilities for the ReAct-style autonomous agent.
Uses the existing core.web_tools module for content fetching and extraction.

Example Usage:
    from core.tools.fetch_url_tool import FetchUrlTool
    
    tool = FetchUrlTool()
    result = await tool.execute(url="https://example.com/article")
    # Returns: {"ok": True, "result": {...}, "error": None}

Author: Matteo (QuantumDev)
Version: 1.0.0
"""

from __future__ import annotations

import logging
import re
from typing import Dict, Any, Optional

log = logging.getLogger(__name__)


class FetchUrlTool:
    """
    URL Fetch Tool for autonomous agent.
    
    Fetches and extracts text content from a specific URL.
    Useful for reading articles, documentation, or any web content.
    
    Parameters Schema:
        {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch content from"
                }
            },
            "required": ["url"]
        }
    
    Returns:
        {
            "ok": bool,
            "result": {
                "url": str,
                "title": str,
                "text": str,  # Extracted text content (max 2000 chars)
                "length": int  # Original text length
            },
            "error": Optional[str]
        }
    
    Examples:
        - fetch_url(url="https://example.com/article")
        - fetch_url(url="https://docs.python.org/3/library/asyncio.html")
    """
    
    name = "fetch_url"
    description = "Fetch and extract text content from a specific URL"
    category = "data"
    timeout_s = 15
    
    # JSON Schema for LLM function calling
    parameters_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL to fetch content from"
            }
        },
        "required": ["url"]
    }
    
    # Maximum text length to return
    MAX_TEXT_LENGTH = 2000
    
    @staticmethod
    def validate_parameters(url: str) -> Optional[str]:
        """
        Validate input parameters.
        
        Args:
            url: URL to fetch
            
        Returns:
            Error message if validation fails, None if valid
        """
        if not url or not isinstance(url, str):
            return "url must be a non-empty string"
        
        url = url.strip()
        
        if len(url) == 0:
            return "url cannot be empty or whitespace only"
        
        if len(url) > 2000:
            return "url exceeds maximum length of 2000 characters"
        
        # Check for valid URL format
        if not re.match(r"^https?://", url, re.IGNORECASE):
            return "url must start with http:// or https://"
        
        # Check for dangerous protocols
        dangerous_protocols = ["javascript:", "data:", "file:", "ftp:"]
        for protocol in dangerous_protocols:
            if url.lower().startswith(protocol):
                return f"url protocol '{protocol}' is not allowed"
        
        # Check for path traversal
        if ".." in url:
            return "url contains path traversal patterns"
        
        return None
    
    @staticmethod
    async def execute(url: str) -> Dict[str, Any]:
        """
        Execute URL fetch.
        
        Args:
            url: URL to fetch content from
            
        Returns:
            Structured result: {"ok": bool, "result": any, "error": str}
        """
        url_preview = url[:80] + "..." if len(url) > 80 else url
        log.info(f"[TOOL] fetch_url: url='{url_preview}'")
        
        # Validate parameters
        validation_error = FetchUrlTool.validate_parameters(url)
        if validation_error:
            log.warning(f"[TOOL] fetch_url validation failed: {validation_error}")
            return {
                "ok": False,
                "result": None,
                "error": validation_error
            }
        
        try:
            from core.web_tools import fetch_and_extract
            
            result = await fetch_and_extract(url.strip())
            
            title = result.get("title", "")
            text = result.get("text", "")
            original_length = len(text)
            
            # Truncate text if too long
            if len(text) > FetchUrlTool.MAX_TEXT_LENGTH:
                text = text[:FetchUrlTool.MAX_TEXT_LENGTH] + "..."
            
            log.info(f"[TOOL] fetch_url: extracted {original_length} chars from '{url[:50]}...'")
            
            return {
                "ok": True,
                "result": {
                    "url": url,
                    "title": title,
                    "text": text,
                    "length": original_length
                },
                "error": None
            }
            
        except ImportError as e:
            error_msg = f"URL fetch module not available: {e}"
            log.error(f"[TOOL] fetch_url: {error_msg}")
            return {
                "ok": False,
                "result": None,
                "error": error_msg
            }
        except Exception as e:
            error_msg = f"URL fetch failed: {e}"
            log.error(f"[TOOL] fetch_url: {error_msg}")
            return {
                "ok": False,
                "result": None,
                "error": error_msg
            }
