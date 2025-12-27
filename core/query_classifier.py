#!/usr/bin/env python3
"""
core/query_classifier.py — Advanced Query Intent Classification

Classifies query intent for optimized handling:
- conversational: chit-chat, no search
- factual: static fact, check memory first
- live_data: real-time data, always search
- research: in-depth research, deep search
- calculation: math, no search

Author: QuantumDev
Version: 1.0.0
"""

from __future__ import annotations

import os
import re
import logging
from typing import Dict, Any, List, Optional
from enum import Enum

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


INTENT_CLASSIFIER_ENABLED = _env_bool("INTENT_CLASSIFIER_ENABLED", True)
INTENT_CONFIDENCE_MIN = _env_float("INTENT_CONFIDENCE_MIN", 0.6)


class QueryIntent(str, Enum):
    """Query intent types."""
    CONVERSATIONAL = "conversational"
    FACTUAL = "factual"
    LIVE_DATA = "live_data"
    RESEARCH = "research"
    CALCULATION = "calculation"
    CODE = "code"
    CREATIVE = "creative"


class SearchUrgency(str, Enum):
    """Search urgency levels."""
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# === Pattern Definitions ===

# Conversational patterns
CONVERSATIONAL_PATTERNS = [
    # Greetings (standalone or with question mark)
    r'^\s*(ciao|salve|hey|hi|hello|hola)\s*[!?.]?\s*$',
    r'^\s*(buongiorno|buonasera|buonanotte)\s*[!?.]?\s*$',
    # Greeting + how are you (combined)
    r'^\s*(ciao|salve|hey|hi|hello)\s+(come\s+(stai|va))\s*[?!.]?\s*$',
    # How are you (standalone)
    r'^\s*(come\s+(stai|va)|come\s+te\s+la\s+passi)\s*[?]?\s*$',
    r'^\s*(tutto\s*(bene|ok)|stai\s+bene)\s*[?]?\s*$',
    # Acknowledgments (single or combined)
    r'^\s*(grazie(\s+mille)?|thanks|thank\s+you)\s*[!.]?\s*$',
    r'^\s*(ok|okay|perfetto|ottimo|grande|bene)(\s+(ok|perfetto|ottimo|bene))?\s*[!.]?\s*$',
    r'^\s*(va\s+bene|capito|d\'accordo)\s*[!.]?\s*$',
]

# Opinion/advice patterns (no search needed)
OPINION_PATTERNS = [
    r'\bcosa\s+ne\s+pensi\b',
    r'\bsecondo\s+te\b',
    r'\bche\s+ne\s+dici\b',
    r'\bmi\s+consigli\b',
    r'\bche\s+ne\s+pensi\b',
    r'\btuo\s+parere\b',
]

# Factual question patterns
FACTUAL_PATTERNS = [
    r"\b(cos['']?è|che\s+cos['']?è|what\s+is)\b",
    r'\b(chi\s+è|who\s+is)\b',
    r'\b(dove\s+si\s+trova|where\s+is)\b',
    r'\b(quando\s+è\s+stato|when\s+was)\b',
    r'\b(come\s+funziona|how\s+does\s+it\s+work)\b',
    r'\b(definizione\s+di|define)\b',
    r'\b(significato\s+di|meaning\s+of)\b',
    r'\b(storia\s+di|history\s+of)\b',
]

# Live data patterns
LIVE_DATA_PATTERNS = {
    'price': [
        r'\b(prezzo|quotazione|valore)\b',
        r'\b(quanto\s+(vale|costa))\b',
        r'\b(price|value|worth)\b',
        r'\b(market\s+cap|capitalizzazione)\b',
    ],
    'weather': [
        r'\b(meteo|weather)\b',
        r'\b(che\s+tempo\s+fa)\b',
        r'\b(temperatura|temperature)\b',
        r'\b(previsioni|forecast)\b',
        r'\b(piove|nevica|rain|snow)\b',
    ],
    'news': [
        r'\b(ultime\s+notizie|breaking\s+news)\b',
        r'\b(news\s+su|notizie\s+su)\b',
        r'\b(novità|aggiornamenti)\b',
        r'\b(latest\s+news|current\s+events)\b',
    ],
    'sports': [
        r'\b(risultato|risultati|score)\b',
        r'\b(classifica|standings)\b',
        r'\b(partita|match|game)\b',
        r'\b(chi\s+ha\s+vinto)\b',
        r'\b(serie\s+a|champions|europa\s+league)\b',
    ],
    'schedule': [
        r'\b(orari|orario|schedule)\b',
        r'\b(a\s+che\s+ora)\b',
        r'\b(quando\s+(gioca|inizia|parte))\b',
        r'\b(prossima\s+partita)\b',
    ],
}

# Research patterns (need deep search)
RESEARCH_PATTERNS = [
    r'\b(approfondimento|approfondisci)\b',
    r'\b(analisi\s+(completa|dettagliata))\b',
    r'\b(ricerca\s+su)\b',
    r'\b(spiegami\s+in\s+dettaglio)\b',
    r'\b(tutto\s+(su|quello\s+che\s+sai))\b',
    r'\b(comprehensive|in-depth|detailed)\b',
]

# Calculation patterns
CALCULATION_PATTERNS = [
    r'\b(calcola|calculate|compute)\b',
    r'\b(quanto\s+fa)\b',
    r'\b(somma|sum|add)\b',
    r'\b(sottrai|subtract)\b',
    r'\b(moltiplica|multiply)\b',
    r'\b(dividi|divide)\b',
    r'[\d]+\s*[\+\-\*\/\^%]\s*[\d]+',
    r'\d+\s*(più|meno|per|diviso)\s*\d+',
    r'\b(radice|square\s+root|sqrt)\b',
    r'\b(percentuale|percentage|%\s+di)\b',
]

# Code generation patterns
CODE_PATTERNS = [
    r'\b(scrivi|genera|crea)\s+(codice|script|programma|funzione|classe)\b',
    r'\b(write|generate|create)\s+(code|script|function|class)\b',
    r'\b(implementa|implement)\b',
    r'\b(codice\s+(python|javascript|java|php|c\+\+|go|rust))\b',
    r'\b(script\s+(bash|shell|python|node))\b',
    r'\b(esempio\s+di\s+codice)\b',
    r'\b(code\s+example)\b',
]

# Creative patterns
CREATIVE_PATTERNS = [
    r'\b(scrivi|genera)\s+(una\s+)?(storia|poesia|racconto|testo)\b',
    r'\b(write|generate)\s+(a\s+)?(story|poem|essay|text)\b',
    r'\b(inventa|create)\b',
    r'\b(traduci|translate)\b',
    r'\b(riscrivi|rewrite|riformula|rephrase)\b',
    r'\b(riassumi|summarize|summarise)\b',
]


class QueryClassifier:
    """
    Classifies query intent for optimized handling.
    
    Intent types:
    - conversational: chit-chat, no search
    - factual: static fact, check memory first
    - live_data: real-time data, always search
    - research: in-depth research, deep search
    - calculation: math, no search
    - code: code generation, LLM direct
    - creative: creative writing, LLM direct
    """
    
    def __init__(self) -> None:
        """Initialize compiled patterns."""
        self._conversational_re = [re.compile(p, re.IGNORECASE) for p in CONVERSATIONAL_PATTERNS]
        self._opinion_re = [re.compile(p, re.IGNORECASE) for p in OPINION_PATTERNS]
        self._factual_re = [re.compile(p, re.IGNORECASE) for p in FACTUAL_PATTERNS]
        self._research_re = [re.compile(p, re.IGNORECASE) for p in RESEARCH_PATTERNS]
        self._calculation_re = [re.compile(p, re.IGNORECASE) for p in CALCULATION_PATTERNS]
        self._code_re = [re.compile(p, re.IGNORECASE) for p in CODE_PATTERNS]
        self._creative_re = [re.compile(p, re.IGNORECASE) for p in CREATIVE_PATTERNS]
        
        # Compile live data patterns
        self._live_data_re: Dict[str, List[re.Pattern]] = {}
        for category, patterns in LIVE_DATA_PATTERNS.items():
            self._live_data_re[category] = [re.compile(p, re.IGNORECASE) for p in patterns]
    
    async def classify_intent(self, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Classify the intent of a query.
        
        Parameters
        ----------
        query : str
            The user query to classify.
        context : Dict, optional
            Conversation context for additional hints.
        
        Returns
        -------
        Dict[str, Any]
            {
                'intent': str,          # conversational, factual, live_data, research, calculation
                'confidence': float,
                'sub_intent': str,      # price_check, weather_check, news_lookup, etc
                'entities': List[str],
                'requires_search': bool,
                'search_urgency': str   # 'none', 'low', 'medium', 'high'
            }
        """
        if not INTENT_CLASSIFIER_ENABLED:
            return self._default_result(query)
        
        query = (query or "").strip()
        if not query:
            return self._empty_result()
        
        context = context or {}
        
        # Check intents in priority order
        
        # 1. Conversational (highest priority - no search)
        if await self.detect_conversational_intent(query):
            return {
                'intent': QueryIntent.CONVERSATIONAL.value,
                'confidence': 0.95,
                'sub_intent': 'greeting' if self._is_greeting(query) else 'acknowledgment',
                'entities': [],
                'requires_search': False,
                'search_urgency': SearchUrgency.NONE.value
            }
        
        # 2. Opinion (no search, LLM opinion)
        if self._is_opinion_request(query):
            return {
                'intent': QueryIntent.CONVERSATIONAL.value,
                'confidence': 0.90,
                'sub_intent': 'opinion',
                'entities': [],
                'requires_search': False,
                'search_urgency': SearchUrgency.NONE.value
            }
        
        # 3. Calculation (no search)
        if await self.detect_calculation_intent(query):
            return {
                'intent': QueryIntent.CALCULATION.value,
                'confidence': 0.95,
                'sub_intent': 'math',
                'entities': self._extract_numbers(query),
                'requires_search': False,
                'search_urgency': SearchUrgency.NONE.value
            }
        
        # 4. Code generation (no search, LLM direct)
        if self._is_code_request(query):
            return {
                'intent': QueryIntent.CODE.value,
                'confidence': 0.90,
                'sub_intent': 'code_generation',
                'entities': self._extract_code_entities(query),
                'requires_search': False,
                'search_urgency': SearchUrgency.NONE.value
            }
        
        # 5. Creative (no search, LLM direct)
        if self._is_creative_request(query):
            return {
                'intent': QueryIntent.CREATIVE.value,
                'confidence': 0.88,
                'sub_intent': 'creative_writing',
                'entities': [],
                'requires_search': False,
                'search_urgency': SearchUrgency.NONE.value
            }
        
        # 6. Live data (always search, high urgency)
        live_result = self._detect_live_data(query)
        if live_result:
            return {
                'intent': QueryIntent.LIVE_DATA.value,
                'confidence': live_result['confidence'],
                'sub_intent': live_result['type'],
                'entities': live_result.get('entities', []),
                'requires_search': True,
                'search_urgency': SearchUrgency.HIGH.value
            }
        
        # 7. Research (deep search)
        if self._is_research_request(query):
            return {
                'intent': QueryIntent.RESEARCH.value,
                'confidence': 0.85,
                'sub_intent': 'deep_research',
                'entities': self._extract_entities(query),
                'requires_search': True,
                'search_urgency': SearchUrgency.MEDIUM.value
            }
        
        # 8. Factual (check memory, then search if needed)
        if self._is_factual_question(query):
            return {
                'intent': QueryIntent.FACTUAL.value,
                'confidence': 0.80,
                'sub_intent': 'knowledge_query',
                'entities': self._extract_entities(query),
                'requires_search': True,  # May need search
                'search_urgency': SearchUrgency.LOW.value
            }
        
        # Default: treat as factual with medium confidence
        return {
            'intent': QueryIntent.FACTUAL.value,
            'confidence': 0.60,
            'sub_intent': 'general_query',
            'entities': self._extract_entities(query),
            'requires_search': True,
            'search_urgency': SearchUrgency.LOW.value
        }
    
    async def detect_conversational_intent(self, query: str) -> bool:
        """
        Detect if query is purely conversational.
        
        Parameters
        ----------
        query : str
            Query to analyze.
        
        Returns
        -------
        bool
            True if conversational.
        """
        for pattern in self._conversational_re:
            if pattern.search(query):
                return True
        return False
    
    async def detect_calculation_intent(self, query: str) -> bool:
        """
        Detect if query requires calculation.
        
        Parameters
        ----------
        query : str
            Query to analyze.
        
        Returns
        -------
        bool
            True if calculation needed.
        """
        for pattern in self._calculation_re:
            if pattern.search(query):
                return True
        return False
    
    # === Helper Methods ===
    
    def _empty_result(self) -> Dict[str, Any]:
        """Return empty query result."""
        return {
            'intent': QueryIntent.CONVERSATIONAL.value,
            'confidence': 0.0,
            'sub_intent': 'empty',
            'entities': [],
            'requires_search': False,
            'search_urgency': SearchUrgency.NONE.value
        }
    
    def _default_result(self, query: str) -> Dict[str, Any]:
        """Return default result when classifier is disabled."""
        return {
            'intent': QueryIntent.FACTUAL.value,
            'confidence': 0.5,
            'sub_intent': 'unknown',
            'entities': [],
            'requires_search': True,
            'search_urgency': SearchUrgency.LOW.value
        }
    
    def _is_greeting(self, query: str) -> bool:
        """Check if query is a greeting."""
        greeting_words = ['ciao', 'salve', 'hey', 'hi', 'hello', 'hola', 
                         'buongiorno', 'buonasera', 'buonanotte']
        query_lower = query.lower().strip()
        return any(g in query_lower for g in greeting_words)
    
    def _is_opinion_request(self, query: str) -> bool:
        """Check if query asks for opinion."""
        for pattern in self._opinion_re:
            if pattern.search(query):
                return True
        return False
    
    def _is_code_request(self, query: str) -> bool:
        """Check if query asks for code generation."""
        for pattern in self._code_re:
            if pattern.search(query):
                return True
        return False
    
    def _is_creative_request(self, query: str) -> bool:
        """Check if query asks for creative content."""
        for pattern in self._creative_re:
            if pattern.search(query):
                return True
        return False
    
    def _is_research_request(self, query: str) -> bool:
        """Check if query needs deep research."""
        for pattern in self._research_re:
            if pattern.search(query):
                return True
        return False
    
    def _is_factual_question(self, query: str) -> bool:
        """Check if query is a factual question."""
        for pattern in self._factual_re:
            if pattern.search(query):
                return True
        return False
    
    def _detect_live_data(self, query: str) -> Optional[Dict[str, Any]]:
        """Detect if query needs live data and which type."""
        for data_type, patterns in self._live_data_re.items():
            for pattern in patterns:
                if pattern.search(query):
                    return {
                        'type': data_type,
                        'confidence': 0.90,
                        'entities': self._extract_entities(query)
                    }
        return None
    
    def _extract_entities(self, query: str) -> List[str]:
        """Extract potential entities from query."""
        entities = []
        words = query.split()
        
        for word in words:
            if word and word[0].isupper():
                clean_word = re.sub(r'[^\w]', '', word)
                if clean_word and len(clean_word) > 2:
                    entities.append(clean_word)
        
        return entities
    
    def _extract_numbers(self, query: str) -> List[str]:
        """Extract numbers from query."""
        return re.findall(r'-?\d+(?:\.\d+)?', query)
    
    def _extract_code_entities(self, query: str) -> List[str]:
        """Extract programming-related entities."""
        languages = ['python', 'javascript', 'java', 'php', 'ruby', 'go', 
                     'rust', 'c++', 'c#', 'typescript', 'bash', 'shell']
        query_lower = query.lower()
        found = [lang for lang in languages if lang in query_lower]
        return found


# === Factory Function ===
_classifier_instance: Optional[QueryClassifier] = None


def get_query_classifier() -> QueryClassifier:
    """Get singleton instance of QueryClassifier."""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = QueryClassifier()
    return _classifier_instance


# === CLI Test ===
if __name__ == "__main__":
    import asyncio
    
    print("🎯 QUERY CLASSIFIER - TEST\n" + "=" * 60)
    
    classifier = QueryClassifier()
    
    test_cases = [
        # Conversational
        ("Ciao come stai?", QueryIntent.CONVERSATIONAL, False),
        ("Grazie mille!", QueryIntent.CONVERSATIONAL, False),
        ("Ok perfetto", QueryIntent.CONVERSATIONAL, False),
        
        # Calculation
        ("Calcola 234 * 567", QueryIntent.CALCULATION, False),
        ("Quanto fa 10 + 5?", QueryIntent.CALCULATION, False),
        ("15 più 20", QueryIntent.CALCULATION, False),
        
        # Code
        ("Scrivi codice Python per ordinare una lista", QueryIntent.CODE, False),
        ("Genera uno script bash", QueryIntent.CODE, False),
        
        # Creative
        ("Scrivi una storia su un drago", QueryIntent.CREATIVE, False),
        ("Traduci questo testo in inglese", QueryIntent.CREATIVE, False),
        
        # Live data
        ("Prezzo Bitcoin", QueryIntent.LIVE_DATA, True),
        ("Che tempo fa a Roma?", QueryIntent.LIVE_DATA, True),
        ("Risultati Serie A", QueryIntent.LIVE_DATA, True),
        ("Ultime notizie su AI", QueryIntent.LIVE_DATA, True),
        
        # Factual
        ("Cos'è Python?", QueryIntent.FACTUAL, True),
        ("Chi era Einstein?", QueryIntent.FACTUAL, True),
    ]
    
    async def run_tests():
        passed = 0
        failed = 0
        
        for query, expected_intent, expected_search in test_cases:
            result = await classifier.classify_intent(query)
            actual_intent = result['intent']
            actual_search = result['requires_search']
            
            intent_match = actual_intent == expected_intent.value
            search_match = actual_search == expected_search
            
            status = "✅" if (intent_match and search_match) else "❌"
            if intent_match and search_match:
                passed += 1
            else:
                failed += 1
            
            print(f"{status} '{query}'")
            print(f"   Expected: {expected_intent.value}, search={expected_search}")
            print(f"   Got: {actual_intent}, search={actual_search}")
            print(f"   Sub-intent: {result['sub_intent']}, confidence: {result['confidence']:.2f}")
            print()
        
        print("=" * 60)
        print(f"📊 RESULTS: {passed}/{len(test_cases)} passed ({100*passed//len(test_cases)}%)")
        if failed > 0:
            print(f"⚠️  {failed} test(s) failed")
        else:
            print("🎉 ALL TESTS PASSED!")
    
    asyncio.run(run_tests())
