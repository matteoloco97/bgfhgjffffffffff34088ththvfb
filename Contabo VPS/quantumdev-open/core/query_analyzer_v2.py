#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/query_analyzer_v2.py — Advanced Query Analyzer

Multi-dimensional query analysis for optimal strategy selection.
Analyzes uncertainty, time sensitivity, and recommends execution strategy.

Author: QuantumDev Phase 3
Version: 1.0.0
"""

import re
import logging
from enum import Enum
from dataclasses import dataclass
from typing import Dict

log = logging.getLogger(__name__)


class UncertaintyLevel(str, Enum):
    """Confidence level in answering the query."""
    CONFIDENT = "confident"
    UNCERTAIN = "uncertain"
    REQUIRES_RESEARCH = "research"


class TimeSensitivity(str, Enum):
    """Time sensitivity classification for queries."""
    EVERGREEN = "evergreen"
    DYNAMIC = "dynamic"
    REAL_TIME = "real_time"


@dataclass
class QueryScore:
    """Complete query analysis result."""
    complexity: str
    uncertainty: UncertaintyLevel
    time_sensitivity: TimeSensitivity
    recommended_strategy: str
    confidence: float
    metadata: Dict
    
    def to_dict(self):
        """Convert to dictionary representation."""
        return {
            "complexity": self.complexity,
            "uncertainty": self.uncertainty.value,
            "time_sensitivity": self.time_sensitivity.value,
            "recommended_strategy": self.recommended_strategy,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


class AdvancedQueryAnalyzer:
    """
    Advanced query analyzer for strategy recommendation.
    
    Analyzes multiple dimensions:
    - Complexity (via TokenAllocationStrategy)
    - Uncertainty level
    - Time sensitivity
    
    Recommends optimal execution strategy:
    - direct_llm: Standard LLM response
    - web_search: Real-time or research queries
    - hybrid: Complex queries needing both LLM and tools
    """
    
    REAL_TIME_PATTERNS = [
        r'\b(ora|now|adesso|live|breaking)\b'
    ]
    
    DYNAMIC_PATTERNS = [
        r'\b(oggi|today|meteo|weather|prezzo|price)\b'
    ]
    
    RESEARCH_PATTERNS = [
        r'\b(ricerca|trova|chi ha vinto|ultimo)\b'
    ]
    
    def analyze_uncertainty(self, query: str) -> UncertaintyLevel:
        """
        Analyze uncertainty level of the query.
        
        Args:
            query: User query to analyze
            
        Returns:
            UncertaintyLevel indicating confidence in answering
        """
        q = query.lower()
        
        # Check if requires research
        for p in self.RESEARCH_PATTERNS:
            if re.search(p, q, re.I):
                return UncertaintyLevel.REQUIRES_RESEARCH
        
        # Check for uncertain indicators
        if any(w in q for w in ['opinione', 'pensi', 'forse']):
            return UncertaintyLevel.UNCERTAIN
        
        return UncertaintyLevel.CONFIDENT
    
    def analyze_time_sensitivity(self, query: str) -> TimeSensitivity:
        """
        Analyze time sensitivity of the query.
        
        Args:
            query: User query to analyze
            
        Returns:
            TimeSensitivity indicating temporal requirements
        """
        q = query.lower()
        
        # Check real-time patterns
        for p in self.REAL_TIME_PATTERNS:
            if re.search(p, q, re.I):
                return TimeSensitivity.REAL_TIME
        
        # Check dynamic patterns
        for p in self.DYNAMIC_PATTERNS:
            if re.search(p, q, re.I):
                return TimeSensitivity.DYNAMIC
        
        return TimeSensitivity.EVERGREEN
    
    def recommend_strategy(
        self,
        complexity: str,
        uncertainty: UncertaintyLevel,
        time_sens: TimeSensitivity
    ):
        """
        Recommend execution strategy based on analysis.
        
        Args:
            complexity: Query complexity level
            uncertainty: Uncertainty level
            time_sens: Time sensitivity
            
        Returns:
            Tuple of (strategy_name, confidence_score)
        """
        # Real-time queries need web search
        if time_sens == TimeSensitivity.REAL_TIME:
            return "web_search", 0.95
        
        # Research queries need web search
        if uncertainty == UncertaintyLevel.REQUIRES_RESEARCH:
            return "web_search", 0.90
        
        # Dynamic + uncertain = hybrid approach
        if time_sens == TimeSensitivity.DYNAMIC and uncertainty == UncertaintyLevel.UNCERTAIN:
            return "hybrid", 0.85
        
        # Complex queries benefit from hybrid
        if complexity in ("complex", "very_complex"):
            return "hybrid", 0.75
        
        # Default to direct LLM
        return "direct_llm", 0.70
    
    def analyze(self, query: str):
        """
        Perform complete query analysis.
        
        Args:
            query: User query to analyze
            
        Returns:
            QueryScore with complete analysis
        """
        from core.adaptive_token_allocator import get_token_allocator
        
        # Get token allocation and complexity
        allocator = get_token_allocator()
        token_budget, complexity_enum, token_meta = allocator.allocate_tokens(query)
        
        # Analyze other dimensions
        uncertainty = self.analyze_uncertainty(query)
        time_sens = self.analyze_time_sensitivity(query)
        
        # Recommend strategy
        strategy, confidence = self.recommend_strategy(
            complexity_enum.value,
            uncertainty,
            time_sens
        )
        
        # Build complete metadata
        metadata = {
            **token_meta,
            "token_budget": token_budget
        }
        
        return QueryScore(
            complexity=complexity_enum.value,
            uncertainty=uncertainty,
            time_sensitivity=time_sens,
            recommended_strategy=strategy,
            confidence=confidence,
            metadata=metadata
        )


# Singleton instance
_analyzer = None


def get_query_analyzer():
    """Get singleton AdvancedQueryAnalyzer instance."""
    global _analyzer
    if not _analyzer:
        _analyzer = AdvancedQueryAnalyzer()
    return _analyzer
