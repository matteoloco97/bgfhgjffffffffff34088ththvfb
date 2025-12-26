#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/tools/calculator_tool.py — Calculator Tool for Autonomous Agent

Provides safe mathematical expression evaluation for the ReAct-style autonomous agent.
Uses the existing core.calculator module for secure expression evaluation.

Example Usage:
    from core.tools.calculator_tool import CalculatorTool
    
    tool = CalculatorTool()
    result = await tool.execute(expression="2 + 2 * 10")
    # Returns: {"ok": True, "result": {"expression": "2 + 2 * 10", "value": "22", "type": "exact"}, "error": None}

Author: Matteo (QuantumDev)
Version: 1.0.0
"""

from __future__ import annotations

import logging
from typing import Dict, Any, Optional

log = logging.getLogger(__name__)


class CalculatorTool:
    """
    Calculator Tool for autonomous agent.
    
    Evaluates mathematical expressions safely, supporting:
    - Basic arithmetic: +, -, *, /, **, %
    - Functions: sqrt, sin, cos, tan, log, exp, pow, abs, round, etc.
    - Constants: pi, e
    
    Parameters Schema:
        {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Mathematical expression to evaluate"
                }
            },
            "required": ["expression"]
        }
    
    Returns:
        {
            "ok": bool,
            "result": {
                "expression": str,
                "value": str,
                "type": str  # "exact" or "approximate"
            },
            "error": Optional[str]
        }
    
    Examples:
        - calculator(expression="2 + 2 * 10")  # Returns 22
        - calculator(expression="sqrt(16) + 5")  # Returns 9
        - calculator(expression="sin(pi/2)")  # Returns 1
        - calculator(expression="log(100, 10)")  # Returns 2
    """
    
    name = "calculator"
    description = "Evaluate mathematical expressions, perform calculations"
    category = "computation"
    timeout_s = 5
    
    # JSON Schema for LLM function calling
    parameters_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Mathematical expression to evaluate"
            }
        },
        "required": ["expression"]
    }
    
    @staticmethod
    def validate_parameters(expression: str) -> Optional[str]:
        """
        Validate input parameters.
        
        Args:
            expression: Mathematical expression to evaluate
            
        Returns:
            Error message if validation fails, None if valid
        """
        if not expression or not isinstance(expression, str):
            return "expression must be a non-empty string"
        
        if len(expression.strip()) == 0:
            return "expression cannot be empty or whitespace only"
        
        if len(expression) > 500:
            return "expression exceeds maximum length of 500 characters"
        
        return None
    
    @staticmethod
    async def execute(expression: str) -> Dict[str, Any]:
        """
        Execute calculator evaluation.
        
        Args:
            expression: Mathematical expression to evaluate
            
        Returns:
            Structured result: {"ok": bool, "result": any, "error": str}
        """
        expr_preview = expression[:50] + "..." if len(expression) > 50 else expression
        log.info(f"[TOOL] calculator: expression='{expr_preview}'")
        
        # Validate parameters
        validation_error = CalculatorTool.validate_parameters(expression)
        if validation_error:
            log.warning(f"[TOOL] calculator validation failed: {validation_error}")
            return {
                "ok": False,
                "result": None,
                "error": validation_error
            }
        
        try:
            from core.calculator import Calculator
            
            result = Calculator.evaluate(expression.strip())
            
            if result is None:
                log.warning(f"[TOOL] calculator: invalid expression '{expression}'")
                return {
                    "ok": False,
                    "result": None,
                    "error": "Invalid mathematical expression"
                }
            
            formatted_result, result_type = result
            
            log.info(f"[TOOL] calculator: result={formatted_result} type={result_type}")
            
            return {
                "ok": True,
                "result": {
                    "expression": expression,
                    "value": formatted_result,
                    "type": result_type
                },
                "error": None
            }
            
        except ImportError as e:
            error_msg = f"Calculator module not available: {e}"
            log.error(f"[TOOL] calculator: {error_msg}")
            return {
                "ok": False,
                "result": None,
                "error": error_msg
            }
        except Exception as e:
            error_msg = f"Calculation failed: {e}"
            log.error(f"[TOOL] calculator: {error_msg}")
            return {
                "ok": False,
                "result": None,
                "error": error_msg
            }
