#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
core/web_router.py — Intelligent WebRouter for deterministic web detection

This module provides a WebRouter that intelligently decides when to use the web pipeline
vs pure LLM response, preventing hallucinations on web-required queries.

Features:
- Rule-based heuristics for explicit web triggers
- Time-sensitive query detection
- Optional LLM micro-classifier for ambiguous cases
- Structured decision output with diagnostics
- Comprehensive logging for debugging
"""

from __future__ import annotations

import re
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

log = logging.getLogger(__name__)

# ===================== CONSTANTS & PATTERNS =====================

# Explicit trigger keywords (always web_required=true)
EXPLICIT_TRIGGERS = [
    # Search triggers
    "cerca", "cercami", "su internet", "online", "cerca online",
    "search", "find", "lookup", "google", "bing",
    # Source/verification triggers
    "fonti", "link", "verifica", "controlla", "conferma",
    "sources", "links", "verify", "check", "confirm",
    # Time-sensitive triggers
    "ultime notizie", "notizie", "oggi", "ieri", "questa settimana",
    "latest news", "news", "today", "yesterday", "this week",
    "aggiornato", "recente", "attuale", "corrente", "latest",
    "updated", "recent", "current", "now",
    # Current state triggers
    "prezzo attuale", "quota attuale", "valore attuale",
    "current price", "current value", "current quote",
    "chi è il CEO adesso", "attuale presidente", "current CEO",
    "nuovo update", "nuova versione", "new update", "new version",
]

# Time-sensitive patterns (web_required=true even without explicit keyword)
TIME_SENSITIVE_PATTERNS = [
    # Current state queries
    r"\b(qual[ei]?\s+(?:è|sono)\s+(?:il|i|la|le)\s+(?:ultimo|ultimi|ultima|ultime))\b",
    r"\b(what\s+(?:is|are)\s+the\s+latest)\b",
    r"\b(stato\s+attuale|current\s+state)\b",
    # Today/recent events
    r"\b(successo\s+oggi|capitato\s+oggi|happened\s+today)\b",
    r"\b(nelle\s+ultime|in\s+the\s+last)\b",
    r"\b(cosa\s+(?:è|e)\s+successo|what\s+happened)\b",
    # Market/price queries
    r"\b(prezzo|quota|valore|cambio|quotazione)\s+(di|del|della|dei|delle)\b",
    r"\b(quotazione|cambio)\s+\w+",
    r"\b(price|quote|value|exchange|rate)\s+of\b",
    # News/politics/economy
    r"\b(risultati?\s+(?:di|delle?|della)\s+(?:elezioni?|partita|match))\b",
    r"\b(risultato)\s+\w+",  # "risultato milan" etc. - more flexible
    r"\b(classifica|standings?|ranking)\b",
    # Weather
    r"\b(meteo|tempo|temperature?|previsioni?|weather|forecast)\b",
]

# Category mappings for different query types
CATEGORY_PATTERNS = {
    "news": [
        r"\b(notizie?|news|ultime|breaking)\b",
        r"\b(giornale|newspaper|articolo|article)\b",
        r"\b(successo|capitato|happened)\b",
        r"\b(politica|politics)\b",
    ],
    "price": [
        r"\b(prezzo|price|quota|quotazione|valore|value|cambio|exchange)\b",
        r"\b(bitcoin|btc|ethereum|eth|crypto|azioni|stocks|forex)\b",
        r"\b(euro|dollaro|usd|eur)\b",
    ],
    "weather": [
        r"\b(meteo|weather|tempo|temperature?|previsioni?|forecast)\b",
        r"\b(piove|rain|sole|sun|nuvoloso|cloudy|domani|tomorrow)\b",
    ],
    "sports": [
        r"\b(risultat[oi]|result)\s+(?:di|del|della|delle|dei)?\s*(?:partita|match)?\s+\w+",
        r"\b(partita|match)\s+\w+",
        r"\b(classifica|standings?)\b",
        r"\b(calcio|football|soccer|serie\s+a|champions)\b",
        r"\b(milan|juventus|inter|napoli)\s+(juventus|milan|inter|napoli|roma)\b",  # Team vs Team
    ],
    "tech": [
        r"\b(update|version|release|nuovo|new|aggiornamento)\b",
        r"\b(software|hardware|app|applicazione)\b",
    ],
}

# Compile patterns for performance
_TIME_SENSITIVE_REGEX = [re.compile(p, re.IGNORECASE) for p in TIME_SENSITIVE_PATTERNS]
_CATEGORY_REGEX = {
    cat: [re.compile(p, re.IGNORECASE) for p in patterns]
    for cat, patterns in CATEGORY_PATTERNS.items()
}


# ===================== WEBROUTER CLASS =====================

class WebRouter:
    """
    Intelligent router for deciding web vs LLM responses.
    
    The router uses a multi-level approach:
    1. Explicit triggers (keywords) → always web_required=true
    2. Time-sensitive patterns → web_required=true
    3. LLM micro-classifier (optional) → for ambiguous cases
    4. Default → web_required=false
    
    Each decision includes diagnostic information for debugging.
    """
    
    def __init__(self, use_llm_classifier: bool = True, llm_classifier_timeout: float = 5.0):
        """
        Initialize WebRouter.
        
        Parameters
        ----------
        use_llm_classifier : bool
            Whether to use LLM micro-classifier for ambiguous cases.
        llm_classifier_timeout : float
            Timeout in seconds for LLM classifier.
        """
        self.use_llm_classifier = use_llm_classifier
        self.llm_classifier_timeout = llm_classifier_timeout
        log.info(f"[WebRouter] Initialized (LLM classifier: {use_llm_classifier})")
    
    def route(self, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Determine if query requires web search.
        
        Parameters
        ----------
        query : str
            User query text.
        context : dict, optional
            Additional context (user memory, conversation history, etc.).
        
        Returns
        -------
        dict
            {
                'web_required': bool,
                'category': str,
                'languages': List[str],
                'freshness_days': int,
                'reason': str,
                'confidence': float,
                'trigger_type': str  # 'explicit', 'time_sensitive', 'llm', 'none'
            }
        """
        context = context or {}
        query_lower = query.lower().strip()
        
        # Step 1: Check explicit triggers
        explicit_result = self._check_explicit_triggers(query_lower)
        if explicit_result['web_required']:
            log.info(f"[WebRouter] EXPLICIT trigger: {explicit_result['reason']}")
            return explicit_result
        
        # Step 2: Check time-sensitive patterns
        time_sensitive_result = self._check_time_sensitive(query_lower)
        if time_sensitive_result['web_required']:
            log.info(f"[WebRouter] TIME-SENSITIVE trigger: {time_sensitive_result['reason']}")
            return time_sensitive_result
        
        # Step 3: Use LLM micro-classifier if enabled
        if self.use_llm_classifier:
            llm_result = self._llm_classify(query, context)
            if llm_result and llm_result.get('web_required'):
                log.info(f"[WebRouter] LLM classifier: {llm_result['reason']}")
                return llm_result
        
        # Step 4: Default to no web required
        default_result = {
            'web_required': False,
            'category': 'general',
            'languages': self._detect_languages(query),
            'freshness_days': 90,
            'reason': 'general chat query',
            'confidence': 0.7,
            'trigger_type': 'none'
        }
        log.info(f"[WebRouter] No web trigger detected (default)")
        return default_result
    
    def _check_explicit_triggers(self, query_lower: str) -> Dict[str, Any]:
        """
        Check for explicit web trigger keywords.
        
        Parameters
        ----------
        query_lower : str
            Lowercased query text.
        
        Returns
        -------
        dict
            Routing decision with diagnostics.
        """
        for trigger in EXPLICIT_TRIGGERS:
            if trigger in query_lower:
                category = self._categorize_query(query_lower)
                freshness = self._get_freshness_days(category)
                
                return {
                    'web_required': True,
                    'category': category,
                    'languages': self._detect_languages(query_lower),
                    'freshness_days': freshness,
                    'reason': f'explicit keyword: {trigger}',
                    'confidence': 0.95,
                    'trigger_type': 'explicit'
                }
        
        return {
            'web_required': False,
            'category': 'unknown',
            'languages': [],
            'freshness_days': 90,
            'reason': 'no explicit trigger',
            'confidence': 0.0,
            'trigger_type': 'none'
        }
    
    def _check_time_sensitive(self, query_lower: str) -> Dict[str, Any]:
        """
        Check for time-sensitive patterns.
        
        Parameters
        ----------
        query_lower : str
            Lowercased query text.
        
        Returns
        -------
        dict
            Routing decision with diagnostics.
        """
        for pattern in _TIME_SENSITIVE_REGEX:
            if pattern.search(query_lower):
                category = self._categorize_query(query_lower)
                freshness = self._get_freshness_days(category)
                
                return {
                    'web_required': True,
                    'category': category,
                    'languages': self._detect_languages(query_lower),
                    'freshness_days': freshness,
                    'reason': f'time-sensitive pattern: {pattern.pattern[:50]}',
                    'confidence': 0.90,
                    'trigger_type': 'time_sensitive'
                }
        
        return {
            'web_required': False,
            'category': 'unknown',
            'languages': [],
            'freshness_days': 90,
            'reason': 'no time-sensitive pattern',
            'confidence': 0.0,
            'trigger_type': 'none'
        }
    
    def _llm_classify(self, query: str, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Use LLM micro-classifier for ambiguous cases.
        
        NOTE: This feature is EXPERIMENTAL and disabled by default.
        The async handling is complex and should only be enabled if needed.
        
        This is a lightweight classifier that uses a short prompt (80-120 tokens)
        to determine if web search is needed.
        
        Parameters
        ----------
        query : str
            User query text.
        context : dict
            Additional context.
        
        Returns
        -------
        dict or None
            Routing decision if classification succeeds, None if fails/timeout.
        """
        import asyncio
        import json
        
        # IMPORTANT: LLM classifier is experimental - disabled by default
        # The async/sync interaction here is complex and may cause issues
        log.warning("[WebRouter] LLM classifier called but is experimental - returning None")
        return None
        
        # TODO: Fix async handling before enabling
        # The code below has issues with asyncio.wait_for/asyncio.run interaction
        # Need to refactor to properly handle async context
        
        # try:
        #     # Import here to avoid circular dependency
        #     from core.chat_engine import reply_with_llm
        #     
        #     # Build classification prompt (short and focused)
        #     prompt = f"""Analyze this query and determine if it requires web search (current/live data).
        # 
        # Query: "{query}"
        # 
        # Return ONLY a JSON object (no explanation):
        # {{
        #   "web_required": true/false,
        #   "category": "news|tech|price|sports|weather|general",
        #   "freshness_days": 7,
        #   "reason": "brief reason"
        # }}
        # 
        # Rules:
        # - web_required=true if query needs current/live/recent data
        # - web_required=false for general knowledge, opinions, calculations
        # - freshness_days: 1-7 for very recent, 30 for monthly, 90 for general
        # 
        # JSON:"""
        #     
        #     # TODO: Fix async handling here
        #     # Current code doesn't properly await or handle async context
        #     
        # except Exception as e:
        #     log.warning(f"[WebRouter] LLM classifier error: {e}")
        #     return None
    
    def _categorize_query(self, query_lower: str) -> str:
        """
        Categorize query based on content.
        
        Parameters
        ----------
        query_lower : str
            Lowercased query text.
        
        Returns
        -------
        str
            Category name (news, price, weather, sports, tech, general).
        """
        # Check categories in priority order (more specific first)
        # Sports has specific team names, so check it first
        priority_order = ['sports', 'weather', 'price', 'tech', 'news']
        
        for category in priority_order:
            if category in _CATEGORY_REGEX:
                for pattern in _CATEGORY_REGEX[category]:
                    if pattern.search(query_lower):
                        return category
        
        # Check remaining categories
        for category, patterns in _CATEGORY_REGEX.items():
            if category not in priority_order:
                for pattern in patterns:
                    if pattern.search(query_lower):
                        return category
        
        return 'general'
    
    def _detect_languages(self, query: str) -> List[str]:
        """
        Detect languages in query text.
        
        Parameters
        ----------
        query : str
            Query text.
        
        Returns
        -------
        List[str]
            List of detected language codes.
        """
        languages = []
        
        # Simple heuristic: check for Italian/English chars
        if re.search(r'[àèéìòù]', query.lower()):
            languages.append('it')
        
        # Check for English words
        if re.search(r'\b(the|is|are|what|how|when|where)\b', query.lower()):
            languages.append('en')
        
        # Default to both if not detected
        if not languages:
            languages = ['it', 'en']
        
        return languages
    
    def _get_freshness_days(self, category: str) -> int:
        """
        Get freshness requirement (days) based on category.
        
        Parameters
        ----------
        category : str
            Query category.
        
        Returns
        -------
        int
            Number of days for freshness requirement.
        """
        freshness_map = {
            'news': 7,      # 1 week for news
            'price': 1,     # 1 day for prices (very fresh)
            'weather': 1,   # 1 day for weather
            'sports': 7,    # 1 week for sports results
            'tech': 30,     # 1 month for tech updates
            'general': 90,  # 3 months for general
        }
        
        return freshness_map.get(category, 30)
    
    def format_log(self, decision: Dict[str, Any]) -> str:
        """
        Format routing decision as a single log line.
        
        Parameters
        ----------
        decision : dict
            Routing decision from route().
        
        Returns
        -------
        str
            Formatted log line.
        """
        langs = ','.join(decision.get('languages', []))
        return (
            f"[WEB_ROUTER] "
            f"required={decision.get('web_required', False)} "
            f"category={decision.get('category', 'unknown')} "
            f"langs={langs} "
            f"freshness={decision.get('freshness_days', 0)} "
            f"route={'web' if decision.get('web_required') else 'llm'} "
            f"reason=\"{decision.get('reason', 'unknown')}\""
        )


# ===================== SINGLETON INSTANCE =====================

_ROUTER_INSTANCE: Optional[WebRouter] = None


def get_web_router(use_llm_classifier: bool = True) -> WebRouter:
    """
    Get singleton WebRouter instance.
    
    Parameters
    ----------
    use_llm_classifier : bool
        Whether to enable LLM micro-classifier.
    
    Returns
    -------
    WebRouter
        Singleton instance.
    """
    global _ROUTER_INSTANCE
    
    if _ROUTER_INSTANCE is None:
        _ROUTER_INSTANCE = WebRouter(use_llm_classifier=use_llm_classifier)
    
    return _ROUTER_INSTANCE


# ===================== CONVENIENCE FUNCTIONS =====================

def should_use_web(query: str, context: Optional[Dict[str, Any]] = None) -> bool:
    """
    Quick check if query requires web search.
    
    Parameters
    ----------
    query : str
        User query text.
    context : dict, optional
        Additional context.
    
    Returns
    -------
    bool
        True if web search is required.
    """
    router = get_web_router()
    decision = router.route(query, context)
    return decision['web_required']


def route_query(query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Route query and get full decision with diagnostics.
    
    Parameters
    ----------
    query : str
        User query text.
    context : dict, optional
        Additional context.
    
    Returns
    -------
    dict
        Full routing decision with diagnostics.
    """
    router = get_web_router()
    return router.route(query, context)
