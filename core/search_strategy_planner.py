#!/usr/bin/env python3
"""
core/search_strategy_planner.py — Search Strategy Planner

Plans optimal search strategy based on:
- Query type
- Available cache data
- Informational complexity required

Author: QuantumDev
Version: 1.0.0
"""

from __future__ import annotations

import os
import time
import logging
from typing import Dict, Any, List, Optional
from enum import Enum

log = logging.getLogger(__name__)


# === Environment Configuration ===
def _env_int(name: str, default: int) -> int:
    """Safely read int from environment."""
    try:
        return int(os.getenv(name, str(default)))
    except (ValueError, TypeError):
        return default


def _env_float(name: str, default: float) -> float:
    """Safely read float from environment."""
    try:
        return float(os.getenv(name, str(default)))
    except (ValueError, TypeError):
        return default


# Timeout configurations
AUTO_SEARCH_QUICK_TIMEOUT = _env_int("AUTO_SEARCH_QUICK_TIMEOUT", 10)
AUTO_SEARCH_DEEP_TIMEOUT = _env_int("AUTO_SEARCH_DEEP_TIMEOUT", 30)
AUTO_SEARCH_RESEARCH_TIMEOUT = _env_int("AUTO_SEARCH_RESEARCH_TIMEOUT", 60)

# Cache policies (TTL in seconds)
CACHE_POLICY_PRICE = _env_int("CACHE_POLICY_PRICE", 60)        # 1 minute
CACHE_POLICY_WEATHER = _env_int("CACHE_POLICY_WEATHER", 1800)   # 30 minutes
CACHE_POLICY_NEWS = _env_int("CACHE_POLICY_NEWS", 600)          # 10 minutes
CACHE_POLICY_SPORTS = _env_int("CACHE_POLICY_SPORTS", 300)      # 5 minutes
CACHE_POLICY_SCHEDULE = _env_int("CACHE_POLICY_SCHEDULE", 600)  # 10 minutes
CACHE_POLICY_DEFAULT = _env_int("CACHE_POLICY_DEFAULT", 3600)   # 1 hour

# Synthesis token limits
SYNTHESIS_CONCISE_MAX_TOKENS = _env_int("SYNTHESIS_CONCISE_MAX_TOKENS", 100)
SYNTHESIS_DETAILED_MAX_TOKENS = _env_int("SYNTHESIS_DETAILED_MAX_TOKENS", 300)
SYNTHESIS_COMPREHENSIVE_MAX_TOKENS = _env_int("SYNTHESIS_COMPREHENSIVE_MAX_TOKENS", 800)


class SearchStrategy(str, Enum):
    """Search strategy types."""
    QUICK = "quick"           # Fast, single source, concise
    PARALLEL = "parallel"     # Multiple sources in parallel
    DEEP = "deep"             # Deeper research, more sources
    RESEARCH = "research"     # Comprehensive, multi-step


class CachePolicy(str, Enum):
    """Cache policy types."""
    AGGRESSIVE = "aggressive"  # Cache as much as possible
    NORMAL = "normal"          # Standard caching
    BYPASS = "bypass"          # Skip cache, always fetch fresh


class SynthesisMode(str, Enum):
    """Synthesis modes for response generation."""
    CONCISE = "concise"           # 2-3 sentences, essential data
    DETAILED = "detailed"         # Full paragraph
    COMPREHENSIVE = "comprehensive"  # Multi-paragraph with sources


# Data type to cache TTL mapping
DATA_TYPE_CACHE_TTL = {
    'price': CACHE_POLICY_PRICE,
    'weather': CACHE_POLICY_WEATHER,
    'news': CACHE_POLICY_NEWS,
    'sports': CACHE_POLICY_SPORTS,
    'schedule': CACHE_POLICY_SCHEDULE,
    'default': CACHE_POLICY_DEFAULT,
}

# Data type to sources mapping
DATA_TYPE_SOURCES = {
    'price': ['price_api', 'web_search'],
    'weather': ['weather_api', 'web_search'],
    'news': ['web_search', 'news_api'],
    'sports': ['sports_api', 'web_search'],
    'schedule': ['web_search'],
    'default': ['web_search'],
}


class SearchStrategyPlanner:
    """
    Plans optimal search strategy based on:
    - Query type
    - Available cache data
    - Informational complexity required
    """
    
    def __init__(self) -> None:
        """Initialize the strategy planner."""
        self._cache_timestamps: Dict[str, float] = {}
    
    async def plan_search_strategy(
        self,
        query: str,
        intent_classification: Dict[str, Any],
        cache_status: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Plan the optimal search strategy.
        
        Parameters
        ----------
        query : str
            The user query.
        intent_classification : Dict
            Classification result from QueryClassifier.
        cache_status : Dict, optional
            Current cache status information.
        
        Returns
        -------
        Dict[str, Any]
            {
                'strategy': str,       # 'quick', 'parallel', 'deep', 'research'
                'sources': List[str],  # ['web_search', 'price_api', 'weather_api']
                'max_results': int,
                'timeout': int,
                'cache_policy': str,   # 'aggressive', 'normal', 'bypass'
                'synthesis_mode': str  # 'concise', 'detailed', 'comprehensive'
            }
        """
        cache_status = cache_status or {}
        
        intent = intent_classification.get('intent', 'factual')
        sub_intent = intent_classification.get('sub_intent', '')
        urgency = intent_classification.get('search_urgency', 'medium')
        
        # Determine data type for specialized handling
        data_type = self._extract_data_type(sub_intent)
        
        # Plan based on intent type
        if intent == 'live_data':
            return await self.optimize_for_live_data(data_type, cache_status)
        
        elif intent == 'research':
            return self._research_strategy()
        
        elif intent == 'factual':
            return self._factual_strategy(urgency)
        
        else:
            # Default strategy for unknown intents
            return self._default_strategy()
    
    async def optimize_for_live_data(
        self,
        data_type: str,
        cache_status: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Optimize strategy for live data queries.
        
        Parameters
        ----------
        data_type : str
            Type of live data: 'price', 'weather', 'news', 'sports'.
        cache_status : Dict, optional
            Current cache information.
        
        Returns
        -------
        Dict[str, Any]
            Optimized search strategy.
        """
        cache_status = cache_status or {}
        
        # Get cache TTL for this data type
        cache_ttl = DATA_TYPE_CACHE_TTL.get(data_type, CACHE_POLICY_DEFAULT)
        
        # Get sources for this data type
        sources = DATA_TYPE_SOURCES.get(data_type, ['web_search'])
        
        # Determine cache policy
        cache_age = cache_status.get('age', float('inf'))
        if cache_age > cache_ttl:
            cache_policy = CachePolicy.BYPASS.value
        else:
            cache_policy = CachePolicy.NORMAL.value
        
        # Strategy based on data type
        if data_type == 'price':
            return {
                'strategy': SearchStrategy.QUICK.value,
                'sources': sources,
                'max_results': 3,
                'timeout': AUTO_SEARCH_QUICK_TIMEOUT,
                'cache_policy': cache_policy,
                'synthesis_mode': SynthesisMode.CONCISE.value,
                'cache_ttl': cache_ttl,
                'data_type': data_type
            }
        
        elif data_type == 'weather':
            return {
                'strategy': SearchStrategy.QUICK.value,
                'sources': sources,
                'max_results': 3,
                'timeout': AUTO_SEARCH_QUICK_TIMEOUT,
                'cache_policy': cache_policy,
                'synthesis_mode': SynthesisMode.CONCISE.value,
                'cache_ttl': cache_ttl,
                'data_type': data_type
            }
        
        elif data_type == 'news':
            return {
                'strategy': SearchStrategy.PARALLEL.value,
                'sources': sources,
                'max_results': 5,
                'timeout': AUTO_SEARCH_DEEP_TIMEOUT,
                'cache_policy': cache_policy,
                'synthesis_mode': SynthesisMode.DETAILED.value,
                'cache_ttl': cache_ttl,
                'data_type': data_type
            }
        
        elif data_type == 'sports':
            return {
                'strategy': SearchStrategy.QUICK.value,
                'sources': sources,
                'max_results': 3,
                'timeout': AUTO_SEARCH_QUICK_TIMEOUT,
                'cache_policy': cache_policy,
                'synthesis_mode': SynthesisMode.DETAILED.value,
                'cache_ttl': cache_ttl,
                'data_type': data_type
            }
        
        else:
            return self._default_strategy()
    
    async def should_use_cache(
        self,
        query: str,
        data_type: str,
        cache_age: int
    ) -> bool:
        """
        Decide if cache should be used or fresh data fetched.
        
        Parameters
        ----------
        query : str
            The query string.
        data_type : str
            Type of data being requested.
        cache_age : int
            Age of cached data in seconds.
        
        Returns
        -------
        bool
            True if cache should be used.
        """
        max_age = DATA_TYPE_CACHE_TTL.get(data_type, CACHE_POLICY_DEFAULT)
        return cache_age <= max_age
    
    def get_synthesis_config(self, mode: str) -> Dict[str, Any]:
        """
        Get synthesis configuration for a given mode.
        
        Parameters
        ----------
        mode : str
            Synthesis mode: 'concise', 'detailed', 'comprehensive'.
        
        Returns
        -------
        Dict[str, Any]
            Configuration for synthesis.
        """
        if mode == SynthesisMode.CONCISE.value:
            return {
                'max_tokens': SYNTHESIS_CONCISE_MAX_TOKENS,
                'style': 'brief',
                'include_sources': False
            }
        elif mode == SynthesisMode.DETAILED.value:
            return {
                'max_tokens': SYNTHESIS_DETAILED_MAX_TOKENS,
                'style': 'informative',
                'include_sources': True
            }
        else:  # comprehensive
            return {
                'max_tokens': SYNTHESIS_COMPREHENSIVE_MAX_TOKENS,
                'style': 'thorough',
                'include_sources': True
            }
    
    # === Private Methods ===
    
    def _extract_data_type(self, sub_intent: str) -> str:
        """Extract data type from sub_intent."""
        # Map sub_intents to data types
        if sub_intent in ['price', 'price_check', 'market']:
            return 'price'
        elif sub_intent in ['weather', 'weather_check', 'forecast']:
            return 'weather'
        elif sub_intent in ['news', 'news_lookup', 'current_events']:
            return 'news'
        elif sub_intent in ['sports', 'score', 'standings']:
            return 'sports'
        elif sub_intent in ['schedule', 'time', 'when']:
            return 'schedule'
        else:
            return 'default'
    
    def _research_strategy(self) -> Dict[str, Any]:
        """Strategy for research queries."""
        return {
            'strategy': SearchStrategy.RESEARCH.value,
            'sources': ['web_search', 'memory'],
            'max_results': 10,
            'timeout': AUTO_SEARCH_RESEARCH_TIMEOUT,
            'cache_policy': CachePolicy.NORMAL.value,
            'synthesis_mode': SynthesisMode.COMPREHENSIVE.value,
            'cache_ttl': CACHE_POLICY_DEFAULT,
            'data_type': 'research'
        }
    
    def _factual_strategy(self, urgency: str) -> Dict[str, Any]:
        """Strategy for factual queries."""
        if urgency == 'high':
            strategy = SearchStrategy.PARALLEL.value
            timeout = AUTO_SEARCH_DEEP_TIMEOUT
        elif urgency == 'medium':
            strategy = SearchStrategy.DEEP.value
            timeout = AUTO_SEARCH_DEEP_TIMEOUT
        else:
            strategy = SearchStrategy.QUICK.value
            timeout = AUTO_SEARCH_QUICK_TIMEOUT
        
        return {
            'strategy': strategy,
            'sources': ['web_search', 'memory'],
            'max_results': 5,
            'timeout': timeout,
            'cache_policy': CachePolicy.NORMAL.value,
            'synthesis_mode': SynthesisMode.DETAILED.value,
            'cache_ttl': CACHE_POLICY_DEFAULT,
            'data_type': 'factual'
        }
    
    def _default_strategy(self) -> Dict[str, Any]:
        """Default fallback strategy."""
        return {
            'strategy': SearchStrategy.QUICK.value,
            'sources': ['web_search'],
            'max_results': 5,
            'timeout': AUTO_SEARCH_QUICK_TIMEOUT,
            'cache_policy': CachePolicy.NORMAL.value,
            'synthesis_mode': SynthesisMode.DETAILED.value,
            'cache_ttl': CACHE_POLICY_DEFAULT,
            'data_type': 'default'
        }


# === Factory Function ===
_planner_instance: Optional[SearchStrategyPlanner] = None


def get_search_strategy_planner() -> SearchStrategyPlanner:
    """Get singleton instance of SearchStrategyPlanner."""
    global _planner_instance
    if _planner_instance is None:
        _planner_instance = SearchStrategyPlanner()
    return _planner_instance


# === CLI Test ===
if __name__ == "__main__":
    import asyncio
    
    print("📋 SEARCH STRATEGY PLANNER - TEST\n" + "=" * 60)
    
    planner = SearchStrategyPlanner()
    
    test_cases = [
        # Live data tests
        (
            {'intent': 'live_data', 'sub_intent': 'price', 'search_urgency': 'high'},
            SearchStrategy.QUICK.value,
            SynthesisMode.CONCISE.value
        ),
        (
            {'intent': 'live_data', 'sub_intent': 'weather', 'search_urgency': 'high'},
            SearchStrategy.QUICK.value,
            SynthesisMode.CONCISE.value
        ),
        (
            {'intent': 'live_data', 'sub_intent': 'news', 'search_urgency': 'high'},
            SearchStrategy.PARALLEL.value,
            SynthesisMode.DETAILED.value
        ),
        
        # Research test
        (
            {'intent': 'research', 'sub_intent': 'deep_research', 'search_urgency': 'medium'},
            SearchStrategy.RESEARCH.value,
            SynthesisMode.COMPREHENSIVE.value
        ),
        
        # Factual tests
        (
            {'intent': 'factual', 'sub_intent': 'knowledge_query', 'search_urgency': 'low'},
            SearchStrategy.QUICK.value,
            SynthesisMode.DETAILED.value
        ),
        (
            {'intent': 'factual', 'sub_intent': 'knowledge_query', 'search_urgency': 'high'},
            SearchStrategy.PARALLEL.value,
            SynthesisMode.DETAILED.value
        ),
    ]
    
    async def run_tests():
        passed = 0
        failed = 0
        
        for classification, expected_strategy, expected_synthesis in test_cases:
            result = await planner.plan_search_strategy("test query", classification)
            
            strategy_match = result['strategy'] == expected_strategy
            synthesis_match = result['synthesis_mode'] == expected_synthesis
            
            status = "✅" if (strategy_match and synthesis_match) else "❌"
            if strategy_match and synthesis_match:
                passed += 1
            else:
                failed += 1
            
            print(f"{status} Intent: {classification['intent']}, Sub: {classification['sub_intent']}")
            print(f"   Expected: strategy={expected_strategy}, synthesis={expected_synthesis}")
            print(f"   Got: strategy={result['strategy']}, synthesis={result['synthesis_mode']}")
            print(f"   Timeout: {result['timeout']}s, Sources: {result['sources']}")
            print()
        
        print("=" * 60)
        print(f"📊 RESULTS: {passed}/{len(test_cases)} passed ({100*passed//len(test_cases)}%)")
        if failed > 0:
            print(f"⚠️  {failed} test(s) failed")
        else:
            print("🎉 ALL TESTS PASSED!")
    
    asyncio.run(run_tests())
