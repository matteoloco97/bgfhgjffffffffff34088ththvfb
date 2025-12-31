#!/usr/bin/env python3
"""
core/auto_search_detector.py — LLM-Powered Auto Search Detector

Detects automatically if a query requires web search using:
- Remote LLM (DeepSeek 32B) for semantic intent understanding
- Fallback regex patterns for reliability when LLM is unavailable

This refactored version offloads decision-making to the LLM instead of
relying solely on static keyword patterns.

Author: QuantumDev (Refactored for VPS + GPU Node architecture)
Version: 2.0.0
"""

from __future__ import annotations

import os
import re
import json
import asyncio
import logging
from typing import Dict, Any, List, Optional

log = logging.getLogger(__name__)


# === Environment Configuration ===
def _env_bool(name: str, default: bool = False) -> bool:
    """Safely read bool from environment."""
    raw = (os.getenv(name, "1" if default else "0") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    """Safely read float from environment."""
    try:
        return float(os.getenv(name, str(default)))
    except (ValueError, TypeError):
        return default


# Configuration from environment
AUTO_SEARCH_ENABLED = _env_bool("AUTO_SEARCH_ENABLED", True)
AUTO_SEARCH_LLM_TIMEOUT = _env_float("AUTO_SEARCH_LLM_TIMEOUT", 3.0)  # Keep it snappy


# === Fallback Patterns (Used when LLM fails/times out) ===
# Simple patterns for quick fallback detection
FALLBACK_LIVE_KEYWORDS = [
    # News & current events
    'news', 'notizie', 'ultime', 'breaking', 'latest', 'recent', 'recente',
    # Prices & financial
    'price', 'prezzo', 'quotazione', 'valore', 'quanto vale', 'quanto costa',
    # Weather
    'weather', 'meteo', 'tempo', 'temperatura', 'forecast', 'previsioni',
    # Sports
    'live', 'risultati', 'partita', 'match', 'score', 'classifica',
    # Temporal
    'oggi', 'adesso', 'now', 'attualmente', 'currently', 'today'
]


class AutoSearchDetector:
    """
    LLM-Powered Auto Search Detector.
    
    Uses remote LLM (DeepSeek 32B) to intelligently determine if a query
    requires real-time external data. Falls back to regex patterns if LLM
    is unavailable or times out.
    """
    
    def __init__(self, llm_client: Optional[Any] = None) -> None:
        """
        Initialize the detector.
        
        Parameters
        ----------
        llm_client : Optional[Any]
            Optional LLM client. If not provided, will use chat_engine's reply_with_llm.
        """
        self._llm_client = llm_client
        log.info("AutoSearchDetector initialized (LLM-powered v2.0)")
    
    async def _get_llm_response(self, prompt: str, timeout: float = 3.0) -> Optional[str]:
        """
        Get LLM response with timeout.
        
        Parameters
        ----------
        prompt : str
            The prompt to send to the LLM.
        timeout : float
            Timeout in seconds.
        
        Returns
        -------
        Optional[str]
            LLM response or None if failed/timed out.
        """
        try:
            # Use provided client or import chat_engine's function
            if self._llm_client:
                # Custom LLM client provided
                response = await asyncio.wait_for(
                    self._llm_client(prompt, timeout=timeout),
                    timeout=timeout
                )
            else:
                # Import here to avoid circular dependencies
                from core.chat_engine import reply_with_llm
                
                # Run LLM call with timeout
                response = await asyncio.wait_for(
                    reply_with_llm(
                        user_text=prompt,
                        persona="You are a precise query analyzer. Follow instructions exactly.",
                        temperature=0.1,  # Low temperature for consistent JSON output
                        max_tokens=200,  # We only need a small JSON response
                    ),
                    timeout=timeout
                )
            return response
            
        except asyncio.TimeoutError:
            log.warning(f"LLM timeout after {timeout}s for intent analysis")
            return None
        except Exception as e:
            log.error(f"LLM call failed for intent analysis: {e}")
            return None
    
    async def analyze_intent(self, query: str, context: str = "") -> dict:
        """
        Analyze query intent using LLM.
        
        This is the main method that determines if a query requires web search
        by asking the LLM to analyze whether it needs REAL-TIME external data.
        
        Parameters
        ----------
        query : str
            The user query to analyze.
        context : str, optional
            Additional context (conversation history, user info, etc.)
        
        Returns
        -------
        dict
            {
                "should_search": bool,
                "search_type": "quick" | "deep",
                "optimized_query": str,
                "reason": str,
                "source": "llm" | "fallback",
                "confidence": float
            }
        """
        if not AUTO_SEARCH_ENABLED:
            return self._create_result(
                should_search=False,
                search_type="none",
                optimized_query=query,
                reason="auto_search_disabled",
                source="config",
                confidence=1.0
            )
        
        if not query or not query.strip():
            return self._create_result(
                should_search=False,
                search_type="none",
                optimized_query="",
                reason="empty_query",
                source="validation",
                confidence=1.0
            )
        
        # Build LLM prompt
        llm_prompt = self._build_llm_prompt(query, context)
        
        # Try LLM analysis first
        log.debug(f"Analyzing intent with LLM: '{query[:50]}...'")
        llm_response = await self._get_llm_response(llm_prompt, timeout=AUTO_SEARCH_LLM_TIMEOUT)
        
        if llm_response:
            # Try to parse LLM response as JSON
            parsed = self._parse_llm_response(llm_response)
            if parsed:
                log.info(
                    f"LLM decision: should_search={parsed['should_search']}, "
                    f"type={parsed['search_type']}, reason={parsed['reason']}"
                )
                return parsed
        
        # LLM failed - use fallback
        log.warning("LLM analysis failed/timed out, using fallback regex")
        return await self._fallback_analysis(query)
    
    def _build_llm_prompt(self, query: str, context: str) -> str:
        """
        Build the strict system prompt for LLM analysis.
        
        Parameters
        ----------
        query : str
            User query.
        context : str
            Optional context.
        
        Returns
        -------
        str
            The complete prompt for the LLM.
        """
        prompt = f"""Analyze this query and determine if it requires REAL-TIME external data.

**Query:** "{query}"
{f'**Context:** {context}' if context else ''}

**Does this query need real-time data?**
Consider if the query asks for:
- Current prices (crypto, stocks, forex)
- Live weather/forecasts
- Recent news or events
- Sports scores/results
- Current time-sensitive information
- Updated documentation (APIs, libraries)

**Important:**
- If it's a general knowledge question answerable from training data → NO search
- If it's conversational/opinion/reasoning → NO search
- If it needs CURRENT/LIVE data → YES search

**Respond ONLY with valid JSON:**
{{
    "should_search": true/false,
    "search_type": "quick" or "deep",
    "optimized_query": "improved search query",
    "reason": "brief explanation why search is needed/not needed"
}}

JSON response:"""
        
        return prompt
    
    def _parse_llm_response(self, response: str) -> Optional[Dict[str, Any]]:
        """
        Parse LLM JSON response.
        
        Parameters
        ----------
        response : str
            Raw LLM response.
        
        Returns
        -------
        Optional[Dict[str, Any]]
            Parsed result or None if parsing failed.
        """
        try:
            # Try to parse the entire response as JSON first
            try:
                data = json.loads(response.strip())
            except json.JSONDecodeError:
                # If that fails, try to extract JSON using a more robust approach
                # Look for the first { and last } to handle nested objects
                start = response.find('{')
                end = response.rfind('}')
                
                if start == -1 or end == -1 or end <= start:
                    log.warning("No JSON object found in LLM response")
                    return None
                
                json_str = response[start:end+1]
                data = json.loads(json_str)
            
            # Validate required fields
            required = ["should_search", "search_type", "optimized_query", "reason"]
            if not all(k in data for k in required):
                log.warning(f"Missing required fields in LLM response: {data}")
                return None
            
            # Normalize and validate
            return self._create_result(
                should_search=bool(data["should_search"]),
                search_type=str(data["search_type"]).lower() if data["should_search"] else "none",
                optimized_query=str(data["optimized_query"]),
                reason=str(data["reason"]),
                source="llm",
                confidence=0.9  # High confidence for LLM decisions
            )
            
        except json.JSONDecodeError as e:
            log.warning(f"JSON parse error in LLM response: {e}")
            return None
        except Exception as e:
            log.error(f"Error parsing LLM response: {e}")
            return None
    
    async def _fallback_analysis(self, query: str) -> Dict[str, Any]:
        """
        Fallback regex-based analysis when LLM is unavailable.
        
        Parameters
        ----------
        query : str
            User query.
        
        Returns
        -------
        Dict[str, Any]
            Analysis result.
        """
        query_lower = query.lower()
        
        # Check for live data keywords
        for keyword in FALLBACK_LIVE_KEYWORDS:
            if keyword in query_lower:
                log.info(f"Fallback: detected live keyword '{keyword}'")
                return self._create_result(
                    should_search=True,
                    search_type="quick",
                    optimized_query=query,
                    reason=f"fallback_keyword:{keyword}",
                    source="fallback",
                    confidence=0.7
                )
        
        # No trigger - assume conversational/general knowledge
        return self._create_result(
            should_search=False,
            search_type="none",
            optimized_query=query,
            reason="fallback_no_trigger",
            source="fallback",
            confidence=0.6
        )
    
    def _create_result(
        self,
        should_search: bool,
        search_type: str,
        optimized_query: str,
        reason: str,
        source: str,
        confidence: float
    ) -> Dict[str, Any]:
        """
        Create standardized result dictionary.
        
        Parameters
        ----------
        should_search : bool
            Whether to trigger web search.
        search_type : str
            Type of search: "quick", "deep", or "none".
        optimized_query : str
            Optimized query for search.
        reason : str
            Reason for the decision.
        source : str
            Decision source: "llm", "fallback", "config", "validation".
        confidence : float
            Confidence score (0-1).
        
        Returns
        -------
        Dict[str, Any]
            Standardized result dictionary.
        """
        return {
            "should_search": should_search,
            "search_type": search_type,
            "optimized_query": optimized_query,
            "reason": reason,
            "source": source,
            "confidence": confidence
        }
    
    # === Backward Compatibility Methods ===
    # These methods maintain compatibility with existing code that calls the old interface
    
    async def should_trigger_search(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        user_memory: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Backward-compatible method for existing code.
        
        This method maintains the old interface while using the new LLM-based
        analyze_intent() under the hood.
        
        Parameters
        ----------
        query : str
            The user query to analyze.
        context : Dict, optional
            Current conversation context (not used in new implementation).
        user_memory : Dict, optional
            User's memory/history data (not used in new implementation).
        
        Returns
        -------
        Dict[str, Any]
            {
                'should_search': bool,
                'confidence': float,  # 0-1
                'reason': str,
                'search_type': str,   # 'quick', 'deep', 'none'
                'suggested_queries': List[str]
            }
        """
        # Build concise context string if provided
        context_str = ""
        if context:
            # Only include key context info to avoid bloating the prompt
            context_keys = ['recent_topic', 'last_query', 'conversation_mode']
            context_items = {k: context.get(k) for k in context_keys if k in context}
            if context_items:
                context_str = f"Context: {', '.join(f'{k}={v}' for k, v in context_items.items())}"
        
        # Call new analyze_intent method
        result = await self.analyze_intent(query, context_str)
        
        # Convert to old format
        suggested_queries = [result["optimized_query"]] if result["should_search"] else []
        
        return {
            'should_search': result['should_search'],
            'confidence': result['confidence'],
            'reason': result['reason'],
            'search_type': result['search_type'],
            'suggested_queries': suggested_queries,
            'source': result['source']  # New field to indicate decision source
        }


# === Factory Function ===
_detector_instance: Optional[AutoSearchDetector] = None


def get_auto_search_detector() -> AutoSearchDetector:
    """Get singleton instance of AutoSearchDetector."""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = AutoSearchDetector()
    return _detector_instance


# === CLI Test ===
if __name__ == "__main__":
    import asyncio
    
    print("🔍 AUTO SEARCH DETECTOR v2.0 (LLM-Powered) - TEST\n" + "=" * 70)
    
    detector = AutoSearchDetector()
    
    test_cases = [
        # Live data tests (should trigger search)
        ("Quanto costa Bitcoin adesso?", True, "live_price"),
        ("Prezzo Ethereum", True, "live_price"),
        ("Che tempo fa a Roma?", True, "live_weather"),
        ("Ultime notizie su Bitcoin", True, "live_news"),
        ("Risultati Serie A oggi", True, "live_sports"),
        
        # General knowledge (should NOT trigger search)
        ("Chi ha inventato Bitcoin?", False, "general_knowledge"),
        ("Come funziona la blockchain?", False, "general_knowledge"),
        ("Cos'è il machine learning?", False, "general_knowledge"),
        
        # Conversational tests (should NOT trigger search)
        ("Ciao come stai?", False, "conversational"),
        ("Cosa ne pensi?", False, "conversational"),
        ("Grazie mille!", False, "conversational"),
    ]
    
    async def run_tests():
        passed = 0
        failed = 0
        
        for query, expected_search, description in test_cases:
            print(f"\n{'='*70}")
            print(f"Query: '{query}'")
            print(f"Expected: should_search={expected_search} ({description})")
            
            result = await detector.analyze_intent(query)
            actual_search = result['should_search']
            
            status = "✅ PASS" if actual_search == expected_search else "❌ FAIL"
            if actual_search == expected_search:
                passed += 1
            else:
                failed += 1
            
            print(f"{status}")
            print(f"Got: should_search={actual_search}")
            print(f"  - search_type: {result['search_type']}")
            print(f"  - reason: {result['reason']}")
            print(f"  - source: {result['source']}")
            print(f"  - confidence: {result['confidence']:.2f}")
            print(f"  - optimized_query: '{result['optimized_query']}'")
        
        print("\n" + "=" * 70)
        print(f"📊 RESULTS: {passed}/{len(test_cases)} passed ({100*passed//len(test_cases) if test_cases else 0}%)")
        if failed > 0:
            print(f"⚠️  {failed} test(s) failed")
        else:
            print("🎉 ALL TESTS PASSED!")
        
        print("\n" + "=" * 70)
        print("Note: Tests using LLM may show different 'source' based on LLM availability")
        print("      'llm' = LLM-powered decision")
        print("      'fallback' = Regex-based fallback")
        print("=" * 70)
    
    asyncio.run(run_tests())
