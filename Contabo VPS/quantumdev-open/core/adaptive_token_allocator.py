#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/adaptive_token_allocator.py - Adaptive Token Allocation Strategy

Dynamically allocates token budgets based on query complexity analysis.
Inspired by Claude's adaptive token allocation approach.

Author: QuantumDev Phase 3
Version: 1.0.0
"""

import os
import re
import logging
from enum import Enum

log = logging.getLogger(__name__)


class QueryComplexity(str, Enum):
    """Query complexity levels for token allocation."""
    TRIVIAL = "trivial"
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    VERY_COMPLEX = "very_complex"


class TokenAllocationStrategy:
    """
    Strategy for allocating tokens based on query complexity.
    
    Maps complexity levels to token budgets:
    - TRIVIAL: 100 tokens (greetings, yes/no)
    - SIMPLE: 300 tokens (basic questions)
    - MODERATE: 600 tokens (standard queries)
    - COMPLEX: 1200 tokens (detailed analysis)
    - VERY_COMPLEX: 2048 tokens (research, implementation)
    """
    
    BUDGET_MAP = {
        QueryComplexity.TRIVIAL: 100,
        QueryComplexity.SIMPLE: 300,
        QueryComplexity.MODERATE: 600,
        QueryComplexity.COMPLEX: 1200,
        QueryComplexity.VERY_COMPLEX: 2048,
    }
    
    TRIVIAL_PATTERNS = [
        r'\b(ciao|hi|hello|grazie|thanks|ok)\b',
        r'^(sì|si|no|yes)$'
    ]
    
    SIMPLE_PATTERNS = [
        r"\b(cos['']è|what is|chi è|who is)\b",
        r'^.{1,30}$'
    ]
    
    COMPLEX_PATTERNS = [
        r'\b(analizza|analyze|confronta|compare)\b',
        r'\b(dettagliato|detailed)\b'
    ]
    
    VERY_COMPLEX_PATTERNS = [
        r'\b(ricerca|research|implementa|implement)\b',
        r'\b(step by step|passo dopo passo)\b'
    ]
    
    def analyze_complexity(self, query: str) -> QueryComplexity:
        """
        Analyze query complexity using pattern matching.
        
        Args:
            query: User query to analyze
            
        Returns:
            QueryComplexity enum indicating the complexity level
        """
        q = query.lower()
        
        # Check trivial patterns first (for short queries)
        if len(query.split()) <= 2:
            for p in self.TRIVIAL_PATTERNS:
                if re.search(p, q, re.I):
                    return QueryComplexity.TRIVIAL
        
        # Check very complex patterns
        for p in self.VERY_COMPLEX_PATTERNS:
            if re.search(p, q, re.I):
                return QueryComplexity.VERY_COMPLEX
        
        # Check complex patterns
        for p in self.COMPLEX_PATTERNS:
            if re.search(p, q, re.I):
                return QueryComplexity.COMPLEX
        
        # Check simple patterns
        for p in self.SIMPLE_PATTERNS:
            if re.search(p, q, re.I):
                return QueryComplexity.SIMPLE
        
        # Default to moderate
        return QueryComplexity.MODERATE
    
    def allocate_tokens(self, query: str):
        """
        Allocate token budget based on query complexity.
        
        Args:
            query: User query to analyze
            
        Returns:
            Tuple of (budget, complexity, metadata)
        """
        complexity = self.analyze_complexity(query)
        budget = self.BUDGET_MAP[complexity]
        
        metadata = {
            "query_len": len(query),
            "complexity": complexity.value
        }
        
        log.debug(f"Token allocation: {budget} tokens for {complexity.value} query")
        
        return budget, complexity, metadata


# Singleton instance
_allocator = None


def get_token_allocator():
    """Get singleton TokenAllocationStrategy instance."""
    global _allocator
    if not _allocator:
        _allocator = TokenAllocationStrategy()
    return _allocator
