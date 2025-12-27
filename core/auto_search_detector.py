#!/usr/bin/env python3
"""
core/auto_search_detector.py — Auto Search Detector for Web Intelligence

Detects automatically if a query requires web search based on:
- Linguistic patterns (oggi, adesso, attuale, recente, ultimamente)
- Temporal entities (dates, times, current events)
- Topics requiring live data (prices, weather, news, sports)
- Knowledge gap in memory (question about something not discussed)

Author: QuantumDev
Version: 1.0.0
"""

from __future__ import annotations

import os
import re
import logging
from typing import Dict, Any, List, Tuple, Optional

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
AUTO_SEARCH_CONFIDENCE_THRESHOLD = _env_float("AUTO_SEARCH_CONFIDENCE_THRESHOLD", 0.7)
AUTO_SEARCH_TEMPORAL_ENABLED = _env_bool("AUTO_SEARCH_TEMPORAL_ENABLED", True)
AUTO_SEARCH_LIVE_DATA_ENABLED = _env_bool("AUTO_SEARCH_LIVE_DATA_ENABLED", True)
AUTO_SEARCH_KNOWLEDGE_GAP_ENABLED = _env_bool("AUTO_SEARCH_KNOWLEDGE_GAP_ENABLED", True)
AUTO_SEARCH_GAP_MIN_CONFIDENCE = _env_float("AUTO_SEARCH_GAP_MIN_CONFIDENCE", 0.6)


# === Pattern Detection Rules ===
TEMPORAL_PATTERNS = {
    'now': ['adesso', 'ora', 'attualmente', 'in questo momento', 'now', 'current', 'currently'],
    'today': ['oggi', 'today', 'questa mattina', 'questo pomeriggio', 'stasera', 'stanotte'],
    'recent': ['recente', 'ultimamente', 'latest', 'recent', 'nuovo', 'aggiornamento', 
               'ultime', 'ultimo', 'ultimi', 'breaking', 'appena'],
    'future': ['domani', 'prossimo', 'futuro', 'tomorrow', 'next', 'will', 'prossima', 
               'settimana prossima', 'mese prossimo'],
    'past': ['ieri', 'yesterday', 'scorso', 'scorsa', 'passato', 'last'],
}

LIVE_DATA_KEYWORDS = {
    'price': ['prezzo', 'quotazione', 'valore', 'costa', 'price', 'value', 'worth',
              'quanto vale', 'quanto costa', 'market cap', 'capitalizzazione', 'cambio'],
    'weather': ['tempo', 'meteo', 'temperatura', 'piove', 'weather', 'forecast',
                'previsioni', 'pioggia', 'neve', 'nuvoloso', 'sereno', 'che tempo fa'],
    'news': ['notizie', 'news', 'ultime', 'breaking', 'evento', 'successo',
             'novità', 'aggiornamenti', 'headline', 'headlines'],
    'sports': ['partita', 'risultato', 'classifica', 'match', 'score', 'game',
               'serie a', 'champions', 'europa league', 'premier', 'bundesliga',
               'gol', 'vincitore', 'chi ha vinto'],
}

# Entities that always require updated data
LIVE_ENTITIES = [
    # Crypto
    'Bitcoin', 'BTC', 'Ethereum', 'ETH', 'Solana', 'SOL', 'XRP', 'Ripple',
    'Cardano', 'ADA', 'Dogecoin', 'DOGE', 'Polkadot', 'DOT', 'Chainlink', 'LINK',
    # Stock symbols
    'AAPL', 'TSLA', 'GOOGL', 'AMZN', 'MSFT', 'META', 'NVDA', 'NFLX',
    # Forex
    'EUR/USD', 'USD/JPY', 'GBP/USD', 'USD/CHF', 'EURUSD', 'USDJPY',
    # Commodities
    'oro', 'gold', 'argento', 'silver', 'petrolio', 'oil',
]

# Conversational patterns that don't require search
CONVERSATIONAL_PATTERNS = [
    r'^\s*(ciao|salve|hey|hi|hello|hola|buongiorno|buonasera|buonanotte)\s*$',
    r'^\s*(come\s+stai|come\s+va|tutto\s*bene)\s*[?]?\s*$',
    r'^\s*(grazie|thanks|thank you|ok|perfetto|va bene)\s*$',
    r'^\s*(cosa\s+ne\s+pensi|secondo\s+te|che\s+ne\s+dici)\b',
    r'^\s*(racconta|dimmi\s+qualcosa)\b',
]

# Calculation patterns
CALCULATION_PATTERNS = [
    r'calcola\s+',
    r'quanto\s+fa\s+',
    r'somma\s+',
    r'moltiplica\s+',
    r'dividi\s+',
    r'[\d]+\s*[\+\-\*\/\^]\s*[\d]+',
    r'\d+\s*(più|meno|per|diviso)\s*\d+',
]


class AutoSearchDetector:
    """
    Detects automatically if a query requires web search based on:
    - Linguistic patterns (oggi, adesso, attuale, recente, ultimamente)
    - Temporal entities (dates, times, current events)
    - Topics requiring live data (prices, weather, news, sports)
    - Knowledge gap in memory (question about something not discussed)
    """
    
    def __init__(self) -> None:
        """Initialize the detector with compiled patterns."""
        self._conversational_re = [re.compile(p, re.IGNORECASE) for p in CONVERSATIONAL_PATTERNS]
        self._calculation_re = [re.compile(p, re.IGNORECASE) for p in CALCULATION_PATTERNS]
        self._live_entities_lower = [e.lower() for e in LIVE_ENTITIES]
    
    async def should_trigger_search(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        user_memory: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Determine if a query should trigger a web search.
        
        Parameters
        ----------
        query : str
            The user query to analyze.
        context : Dict, optional
            Current conversation context.
        user_memory : Dict, optional
            User's memory/history data.
        
        Returns
        -------
        Dict[str, Any]
            {
                'should_search': bool,
                'confidence': float,  # 0-1
                'reason': str,        # 'temporal', 'live_data', 'knowledge_gap', etc
                'search_type': str,   # 'quick', 'deep', 'research'
                'suggested_queries': List[str]  # Query optimized for search
            }
        """
        if not AUTO_SEARCH_ENABLED:
            return self._no_search_result("auto_search_disabled")
        
        query = (query or "").strip()
        if not query:
            return self._no_search_result("empty_query")
        
        query_lower = query.lower()
        context = context or {}
        user_memory = user_memory or {}
        
        # Check for conversational intent (no search needed)
        if await self.detect_conversational_intent(query):
            return self._no_search_result("conversational")
        
        # Check for calculation intent (no search needed)
        if await self.detect_calculation_intent(query):
            return self._no_search_result("calculation")
        
        # Check for temporal intent
        if AUTO_SEARCH_TEMPORAL_ENABLED:
            has_temporal = await self.detect_temporal_intent(query)
            if has_temporal:
                suggested = await self.generate_search_queries(query, "quick")
                return {
                    'should_search': True,
                    'confidence': 0.85,
                    'reason': 'temporal',
                    'search_type': 'quick',
                    'suggested_queries': suggested
                }
        
        # Check for live data need
        if AUTO_SEARCH_LIVE_DATA_ENABLED:
            needs_live, data_type = await self.detect_live_data_need(query)
            if needs_live:
                search_type = 'quick' if data_type in ['price', 'weather'] else 'deep'
                suggested = await self.generate_search_queries(query, search_type)
                return {
                    'should_search': True,
                    'confidence': 0.90,
                    'reason': f'live_data:{data_type}',
                    'search_type': search_type,
                    'suggested_queries': suggested,
                    'data_type': data_type
                }
        
        # Check for knowledge gap
        if AUTO_SEARCH_KNOWLEDGE_GAP_ENABLED:
            has_gap = await self.detect_knowledge_gap(query, user_memory)
            if has_gap:
                suggested = await self.generate_search_queries(query, "research")
                return {
                    'should_search': True,
                    'confidence': AUTO_SEARCH_GAP_MIN_CONFIDENCE,
                    'reason': 'knowledge_gap',
                    'search_type': 'research',
                    'suggested_queries': suggested
                }
        
        # Check for live entities (crypto, stocks, etc.)
        if self._has_live_entity(query_lower):
            suggested = await self.generate_search_queries(query, "quick")
            return {
                'should_search': True,
                'confidence': 0.88,
                'reason': 'live_entity',
                'search_type': 'quick',
                'suggested_queries': suggested
            }
        
        # Default: no search needed
        return self._no_search_result("no_trigger")
    
    async def detect_temporal_intent(self, query: str) -> bool:
        """
        Detect temporal intent in query.
        
        Detects patterns like:
        - "oggi", "adesso", "attualmente", "in questo momento"
        - "ultime notizie", "aggiornamenti recenti"
        - Specific dates: "prezzo Bitcoin 27 dicembre 2024"
        
        Parameters
        ----------
        query : str
            The query to analyze.
        
        Returns
        -------
        bool
            True if temporal intent is detected.
        """
        query_lower = query.lower()
        
        # Check temporal pattern categories
        for category, patterns in TEMPORAL_PATTERNS.items():
            for pattern in patterns:
                if pattern in query_lower:
                    log.debug(f"Temporal intent detected: '{pattern}' (category: {category})")
                    return True
        
        # Check for date patterns (e.g., "27 dicembre 2024", "2024-12-27")
        date_patterns = [
            r'\d{1,2}\s+(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)',
            r'\d{4}[-/]\d{2}[-/]\d{2}',
            r'\d{1,2}[-/]\d{1,2}[-/]\d{2,4}',
        ]
        for pattern in date_patterns:
            if re.search(pattern, query_lower):
                log.debug(f"Date pattern detected in query")
                return True
        
        return False
    
    async def detect_live_data_need(self, query: str) -> Tuple[bool, str]:
        """
        Detect if query needs live data.
        
        Parameters
        ----------
        query : str
            The query to analyze.
        
        Returns
        -------
        Tuple[bool, str]
            (needs_live_data, data_type)
            Data types: 'price', 'weather', 'news', 'sports', 'schedule', None
        """
        query_lower = query.lower()
        
        for data_type, keywords in LIVE_DATA_KEYWORDS.items():
            for keyword in keywords:
                if keyword in query_lower:
                    log.debug(f"Live data need detected: '{keyword}' (type: {data_type})")
                    return (True, data_type)
        
        return (False, '')
    
    async def detect_knowledge_gap(
        self,
        query: str,
        user_memory: Dict[str, Any]
    ) -> bool:
        """
        Detect if query requires info not present in memory.
        
        Checks:
        - Entities never mentioned
        - Topics never discussed
        - Specific facts not known
        
        Parameters
        ----------
        query : str
            The query to analyze.
        user_memory : Dict
            User's memory/history data.
        
        Returns
        -------
        bool
            True if knowledge gap is detected.
        """
        if not user_memory:
            # No memory means potential knowledge gap for factual queries
            return self._is_factual_query(query)
        
        # Extract main entities from query
        query_entities = self._extract_entities(query)
        
        # Also extract multi-word phrases from query for better matching
        query_lower = query.lower()
        
        # Check if any entity is in memory
        memory_topics = user_memory.get('topics', [])
        memory_entities = user_memory.get('entities', [])
        
        all_known = set(str(t).lower() for t in memory_topics + memory_entities)
        
        # If no entities extracted, check if any known topic appears in query
        if not query_entities:
            for known in all_known:
                if known in query_lower:
                    log.debug(f"Found known topic '{known}' in query")
                    return False  # No gap - known topic found
            return self._is_factual_query(query)
        
        # Check if any extracted entity is known
        for entity in query_entities:
            entity_lower = entity.lower()
            # Check for exact match or partial match in known entities
            for known in all_known:
                if entity_lower in known or known in entity_lower:
                    log.debug(f"Entity '{entity}' matches known '{known}'")
                    return False  # No gap
        
        # Also check if query text contains any known topic
        for known in all_known:
            if known in query_lower:
                log.debug(f"Known topic '{known}' found in query text")
                return False  # No gap
        
        # If we get here, there might be a knowledge gap
        log.debug(f"Knowledge gap: entities {query_entities} not found in memory")
        return True
    
    async def detect_conversational_intent(self, query: str) -> bool:
        """
        Detect if query is purely conversational.
        
        Patterns:
        - Greetings: "ciao", "come stai", "hey"
        - Opinions: "cosa ne pensi", "secondo te"
        - Chit-chat: "racconta", "dimmi qualcosa"
        
        Parameters
        ----------
        query : str
            The query to analyze.
        
        Returns
        -------
        bool
            True if conversational intent is detected.
        """
        for pattern in self._conversational_re:
            if pattern.search(query):
                return True
        return False
    
    async def detect_calculation_intent(self, query: str) -> bool:
        """
        Detect if query requires calculation.
        
        Patterns:
        - "calcola", "quanto fa", "somma"
        - Operators: +, -, *, /, ^
        - Numbers + operations
        
        Parameters
        ----------
        query : str
            The query to analyze.
        
        Returns
        -------
        bool
            True if calculation intent is detected.
        """
        for pattern in self._calculation_re:
            if pattern.search(query):
                return True
        return False
    
    async def generate_search_queries(
        self,
        original_query: str,
        search_type: str
    ) -> List[str]:
        """
        Generate optimized search queries from natural language query.
        
        Parameters
        ----------
        original_query : str
            The original user query.
        search_type : str
            Type of search: 'quick', 'deep', 'research'
        
        Returns
        -------
        List[str]
            List of optimized search queries.
        
        Examples
        --------
        Input: "Quanto costa Bitcoin adesso?"
        Output: ["Bitcoin price USD", "BTC current price", "Bitcoin live"]
        
        Input: "Che tempo farà domani a Roma?"
        Output: ["Rome weather forecast tomorrow", "meteo Roma domani"]
        """
        queries = []
        query_lower = original_query.lower()
        
        # Remove question words and noise
        cleaned = self._clean_for_search(original_query)
        
        # Add original cleaned query
        if cleaned:
            queries.append(cleaned)
        
        # Detect specific types and generate specialized queries
        needs_live, data_type = await self.detect_live_data_need(original_query)
        
        if data_type == 'price':
            # Extract asset name and generate price queries
            asset = self._extract_asset(query_lower)
            if asset:
                queries.extend([
                    f"{asset} price USD",
                    f"{asset} current price",
                    f"{asset} live quote",
                ])
        
        elif data_type == 'weather':
            # Extract city and generate weather queries
            city = self._extract_city(original_query)
            if city:
                queries.extend([
                    f"weather {city}",
                    f"meteo {city}",
                    f"{city} weather forecast",
                ])
        
        elif data_type == 'news':
            # Generate news-focused queries
            topic = self._extract_topic(original_query)
            if topic:
                queries.extend([
                    f"{topic} latest news",
                    f"{topic} news today",
                    f"ultime notizie {topic}",
                ])
        
        elif data_type == 'sports':
            # Generate sports-focused queries
            team_or_league = self._extract_sports_entity(original_query)
            if team_or_league:
                queries.extend([
                    f"{team_or_league} results",
                    f"{team_or_league} score",
                    f"risultati {team_or_league}",
                ])
        
        # Limit to top 3 queries
        return queries[:3] if queries else [cleaned or original_query]
    
    # === Helper Methods ===
    
    def _no_search_result(self, reason: str) -> Dict[str, Any]:
        """Create a no-search result."""
        return {
            'should_search': False,
            'confidence': 0.0,
            'reason': reason,
            'search_type': 'none',
            'suggested_queries': []
        }
    
    def _has_live_entity(self, query_lower: str) -> bool:
        """Check if query contains a live entity."""
        for entity in self._live_entities_lower:
            if entity in query_lower:
                return True
        return False
    
    def _is_factual_query(self, query: str) -> bool:
        """Check if query is asking for factual information."""
        factual_patterns = [
            r"(cos['']?è|che\s+cos['']?è|what\s+is)",
            r"(chi\s+è|who\s+is)",
            r"(dove\s+(si\s+trova|è)|where\s+is)",
            r"(quando|when)",
            r"(perché|why)",
            r"(come\s+funziona|how\s+does)",
        ]
        query_lower = query.lower()
        for pattern in factual_patterns:
            if re.search(pattern, query_lower):
                return True
        return False
    
    def _extract_entities(self, query: str) -> List[str]:
        """Extract potential entities from query."""
        # Simple approach: extract capitalized words and known entities
        entities = []
        words = query.split()
        
        for word in words:
            # Check if word starts with capital
            if word and word[0].isupper():
                clean_word = re.sub(r'[^\w]', '', word)
                if clean_word and len(clean_word) > 2:
                    entities.append(clean_word)
        
        return entities
    
    def _clean_for_search(self, query: str) -> str:
        """Clean query for search engine optimization."""
        # Remove question marks and common question words
        cleaned = query.strip()
        
        # Remove Italian question words
        noise_words = [
            'quanto', 'quale', 'quali', 'come', 'cosa', 'chi', 'dove', 'quando', 'perché',
            'dimmi', 'sai', 'puoi', 'vorrei', 'sapere', 'dirmi',
        ]
        
        words = cleaned.split()
        filtered = [w for w in words if w.lower() not in noise_words]
        
        result = ' '.join(filtered)
        # Remove punctuation at the end
        result = re.sub(r'[?!.,;:]+$', '', result)
        
        return result.strip()
    
    def _extract_asset(self, query_lower: str) -> Optional[str]:
        """Extract asset name from query."""
        for entity in LIVE_ENTITIES:
            if entity.lower() in query_lower:
                return entity
        return None
    
    def _extract_city(self, query: str) -> Optional[str]:
        """Extract city name from query."""
        # Common Italian cities
        cities = ['roma', 'milano', 'napoli', 'torino', 'firenze', 'venezia', 
                  'bologna', 'genova', 'palermo', 'bari', 'catania', 'verona']
        
        query_lower = query.lower()
        for city in cities:
            if city in query_lower:
                return city.capitalize()
        
        # Try to extract from "a [City]" pattern
        match = re.search(r'\b(?:a|in)\s+(\w+)', query_lower)
        if match:
            potential_city = match.group(1)
            if len(potential_city) > 2:
                return potential_city.capitalize()
        
        return None
    
    def _extract_topic(self, query: str) -> Optional[str]:
        """Extract main topic from query."""
        # Remove common words and extract the topic
        cleaned = self._clean_for_search(query)
        words = cleaned.split()
        
        # Filter out very short words
        significant_words = [w for w in words if len(w) > 3]
        
        if significant_words:
            return ' '.join(significant_words[:2])
        return None
    
    def _extract_sports_entity(self, query: str) -> Optional[str]:
        """Extract sports team or league from query."""
        sports_entities = [
            'milan', 'inter', 'juventus', 'juve', 'napoli', 'roma', 'lazio',
            'serie a', 'champions league', 'europa league', 'premier league',
            'bundesliga', 'la liga', 'ligue 1',
        ]
        
        query_lower = query.lower()
        for entity in sports_entities:
            if entity in query_lower:
                return entity.title()
        return None


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
    
    print("🔍 AUTO SEARCH DETECTOR - TEST\n" + "=" * 60)
    
    detector = AutoSearchDetector()
    
    test_cases = [
        # Temporal detection tests
        ("Quanto costa Bitcoin adesso?", True, "temporal/live_data"),
        ("Chi ha inventato Bitcoin?", False, "knowledge_gap possible"),
        ("Ultime notizie su Bitcoin", True, "temporal"),
        
        # Live data tests
        ("Prezzo Ethereum", True, "live_data:price"),
        ("Che tempo fa a Roma?", True, "live_data:weather"),
        ("Risultati Serie A oggi", True, "live_data:sports"),
        
        # Conversational tests
        ("Ciao come stai?", False, "conversational"),
        ("Cosa ne pensi?", False, "conversational"),
        
        # Calculation tests
        ("Calcola 234 * 567", False, "calculation"),
        ("Quanto fa 10 + 5?", False, "calculation"),
    ]
    
    async def run_tests():
        passed = 0
        failed = 0
        
        for query, expected_search, description in test_cases:
            result = await detector.should_trigger_search(query)
            actual_search = result['should_search']
            
            status = "✅" if actual_search == expected_search else "❌"
            if actual_search == expected_search:
                passed += 1
            else:
                failed += 1
            
            print(f"{status} '{query}'")
            print(f"   Expected search: {expected_search} ({description})")
            print(f"   Got: {actual_search} (reason: {result['reason']}, conf: {result['confidence']:.2f})")
            print()
        
        print("=" * 60)
        print(f"📊 RESULTS: {passed}/{len(test_cases)} passed ({100*passed//len(test_cases)}%)")
        if failed > 0:
            print(f"⚠️  {failed} test(s) failed")
        else:
            print("🎉 ALL TESTS PASSED!")
    
    asyncio.run(run_tests())
