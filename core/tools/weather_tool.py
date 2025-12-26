#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/tools/weather_tool.py — Weather Tool for Autonomous Agent

Provides weather data retrieval capabilities for the ReAct-style autonomous agent.
Uses the Open-Meteo API for weather forecasts.

Example Usage:
    from core.tools.weather_tool import WeatherTool
    
    tool = WeatherTool()
    result = await tool.execute(location="Rome")
    # Returns: {"ok": True, "result": {...}, "error": None}

Author: Matteo (QuantumDev)
Version: 1.0.0
"""

from __future__ import annotations

import logging
from typing import Dict, Any, Optional

log = logging.getLogger(__name__)


class WeatherTool:
    """
    Weather Tool for autonomous agent.
    
    Gets current weather and forecast for a specific location.
    Uses Open-Meteo API (free, no API key required).
    
    Parameters Schema:
        {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City or location name"
                }
            },
            "required": ["location"]
        }
    
    Returns:
        {
            "ok": bool,
            "result": {
                "location": str,
                "weather": str  # Weather description/data
            },
            "error": Optional[str]
        }
    
    Examples:
        - get_weather(location="Rome")
        - get_weather(location="New York")
        - get_weather(location="Tokyo, Japan")
    """
    
    name = "get_weather"
    description = "Get current weather and forecast for a specific location"
    category = "data"
    timeout_s = 10
    
    # JSON Schema for LLM function calling
    parameters_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "City or location name"
            }
        },
        "required": ["location"]
    }
    
    @staticmethod
    def validate_parameters(location: str) -> Optional[str]:
        """
        Validate input parameters.
        
        Args:
            location: City or location name
            
        Returns:
            Error message if validation fails, None if valid
        """
        if not location or not isinstance(location, str):
            return "location must be a non-empty string"
        
        if len(location.strip()) == 0:
            return "location cannot be empty or whitespace only"
        
        if len(location) > 200:
            return "location exceeds maximum length of 200 characters"
        
        return None
    
    @staticmethod
    async def execute(location: str) -> Dict[str, Any]:
        """
        Execute weather lookup.
        
        Args:
            location: City or location name
            
        Returns:
            Structured result: {"ok": bool, "result": any, "error": str}
        """
        log.info(f"[TOOL] get_weather: location='{location}'")
        
        # Validate parameters
        validation_error = WeatherTool.validate_parameters(location)
        if validation_error:
            log.warning(f"[TOOL] get_weather validation failed: {validation_error}")
            return {
                "ok": False,
                "result": None,
                "error": validation_error
            }
        
        try:
            from agents.weather_open_meteo import get_weather_for_query
            
            if not callable(get_weather_for_query):
                return {
                    "ok": False,
                    "result": None,
                    "error": "Weather agent not available"
                }
            
            # Call weather agent
            result = await get_weather_for_query(
                f"weather in {location.strip()}",
                None,
                None
            )
            
            log.info(f"[TOOL] get_weather: got result for '{location}'")
            
            return {
                "ok": True,
                "result": {
                    "location": location,
                    "weather": result
                },
                "error": None
            }
            
        except ImportError as e:
            error_msg = f"Weather agent module not available: {e}"
            log.error(f"[TOOL] get_weather: {error_msg}")
            return {
                "ok": False,
                "result": None,
                "error": error_msg
            }
        except Exception as e:
            error_msg = f"Weather lookup failed: {e}"
            log.error(f"[TOOL] get_weather: {error_msg}")
            return {
                "ok": False,
                "result": None,
                "error": error_msg
            }
