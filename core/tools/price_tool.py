#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/tools/price_tool.py — Price Tool for Autonomous Agent

Provides cryptocurrency, stock, and forex price retrieval capabilities
for the ReAct-style autonomous agent.

Example Usage:
    from core.tools.price_tool import PriceTool
    
    tool = PriceTool()
    result = await tool.execute(asset="BTC")
    # Returns: {"ok": True, "result": {...}, "error": None}

Author: Matteo (QuantumDev)
Version: 1.0.0
"""

from __future__ import annotations

import logging
from typing import Dict, Any, Optional

log = logging.getLogger(__name__)


class PriceTool:
    """
    Price Tool for autonomous agent.
    
    Gets current price for cryptocurrency, stocks, or forex pairs.
    
    Parameters Schema:
        {
            "type": "object",
            "properties": {
                "asset": {
                    "type": "string",
                    "description": "Asset symbol or name (e.g., BTC, AAPL, EUR/USD)"
                }
            },
            "required": ["asset"]
        }
    
    Returns:
        {
            "ok": bool,
            "result": {
                "asset": str,
                "price_info": str  # Price information/data
            },
            "error": Optional[str]
        }
    
    Examples:
        - get_price(asset="BTC")
        - get_price(asset="NVDA")
        - get_price(asset="EUR/USD")
        - get_price(asset="ethereum")
    """
    
    name = "get_price"
    description = "Get current price for cryptocurrency, stocks, or forex pairs"
    category = "data"
    timeout_s = 10
    
    # JSON Schema for LLM function calling
    parameters_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "asset": {
                "type": "string",
                "description": "Asset symbol or name (e.g., BTC, AAPL, EUR/USD)"
            }
        },
        "required": ["asset"]
    }
    
    @staticmethod
    def validate_parameters(asset: str) -> Optional[str]:
        """
        Validate input parameters.
        
        Args:
            asset: Asset symbol or name
            
        Returns:
            Error message if validation fails, None if valid
        """
        if not asset or not isinstance(asset, str):
            return "asset must be a non-empty string"
        
        if len(asset.strip()) == 0:
            return "asset cannot be empty or whitespace only"
        
        if len(asset) > 100:
            return "asset exceeds maximum length of 100 characters"
        
        return None
    
    @staticmethod
    async def execute(asset: str) -> Dict[str, Any]:
        """
        Execute price lookup.
        
        Args:
            asset: Asset symbol or name (e.g., BTC, AAPL, EUR/USD)
            
        Returns:
            Structured result: {"ok": bool, "result": any, "error": str}
        """
        log.info(f"[TOOL] get_price: asset='{asset}'")
        
        # Validate parameters
        validation_error = PriceTool.validate_parameters(asset)
        if validation_error:
            log.warning(f"[TOOL] get_price validation failed: {validation_error}")
            return {
                "ok": False,
                "result": None,
                "error": validation_error
            }
        
        try:
            from agents.price_agent import get_price_for_query
            
            if not callable(get_price_for_query):
                return {
                    "ok": False,
                    "result": None,
                    "error": "Price agent not available"
                }
            
            # Call price agent
            result = await get_price_for_query(
                f"price of {asset.strip()}",
                None,
                None
            )
            
            log.info(f"[TOOL] get_price: got result for '{asset}'")
            
            return {
                "ok": True,
                "result": {
                    "asset": asset,
                    "price_info": result
                },
                "error": None
            }
            
        except ImportError as e:
            error_msg = f"Price agent module not available: {e}"
            log.error(f"[TOOL] get_price: {error_msg}")
            return {
                "ok": False,
                "result": None,
                "error": error_msg
            }
        except Exception as e:
            error_msg = f"Price lookup failed: {e}"
            log.error(f"[TOOL] get_price: {error_msg}")
            return {
                "ok": False,
                "result": None,
                "error": error_msg
            }
