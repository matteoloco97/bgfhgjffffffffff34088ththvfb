#!/usr/bin/env python3
"""
smart_intent_classifier.py
---------------------------------------------

This module contains a lightweight, rule-based intent classifier
used by the quantumdev-open assistant for routing user queries.  The
classifier decides whether a prompt should be handled directly by the
language model (DIRECT_LLM), looked up via a live web search
(WEB_SEARCH) or read directly from a provided URL (WEB_READ).  The
design favours correctness and up-to-date answers: whenever a query
could benefit from fresh information – e.g. it references a
person/event/product, uses temporal phrases like "oggi"/"adesso", or
asks "chi è", "che cos'è", "dove si trova" – it is routed to
WEB_SEARCH.  Short or general queries that are likely to be factual
knowledge fall into the same category.  Queries involving code
generation, tool execution or conversational smalltalk bypass web
search and go directly to the LLM.

By centralising routing logic here, the assistant can be extended
without changing core API code.  Additional languages, categories or
patterns can be added by modifying this file.  The classifier
returns a dictionary with keys:

    intent: one of {"DIRECT_LLM", "WEB_SEARCH", "WEB_READ"}
    confidence: float confidence score in [0,1]
    reason: human‑readable string explaining the routing decision
    url: extracted URL (for WEB_READ) or None
    live_type: subtype of WEB_SEARCH for certain live categories

"""

from __future__ import annotations

import os
import re
import logging
from typing import Dict, Optional, Any

# Setup logging
log = logging.getLogger(__name__)

# ===== ENVIRONMENT CONFIGURATION =====
def _env_float(name: str, default: float) -> float:
    """Safely read float from environment with default."""
    try:
        return float(os.getenv(name, str(default)))
    except (ValueError, TypeError):
        return default

def _env_int(name: str, default: int) -> int:
    """Safely read int from environment with default."""
    try:
        return int(os.getenv(name, str(default)))
    except (ValueError, TypeError):
        return default

def _env_bool(name: str, default: bool = False) -> bool:
    """Safely read bool from environment."""
    raw = (os.getenv(name, "1" if default else "0") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")

# Intent LLM configuration
LLM_INTENT_ENABLED = _env_bool("LLM_INTENT_ENABLED", False)
INTENT_LLM_MIN_CONFIDENCE = _env_float("INTENT_LLM_MIN_CONFIDENCE", 0.45)
INTENT_LLM_MAX_FALLBACKS = _env_int("INTENT_LLM_MAX_FALLBACKS", 1)


# Regular expression to detect a URL in the text.  The classifier
# considers any HTTP or HTTPS URL as a request to read a page verbatim.
_URL_RE = re.compile(r"(https?://\S+)", re.IGNORECASE)

# Simple greetings/smalltalk patterns.  These patterns match polite
# salutations, acknowledgements or confirmations.  Such inputs are
# handled directly by the LLM without invoking web search.
_SMALLTALK_RE = re.compile(
    r"""(?ix)^
        \s*(
            ciao|hey|hi|hello|salve|
            buongiorno|buonasera|buonanotte|
            grazie|grazie\s+mille|thanks|
            ok+|okk+|perfetto|grande|grandioso|
            ci\s*sei\??|sei\s*online\??
        )\b
    """
)

# Explicit patterns that identify general‑knowledge requests.  These
# expressions catch common linguistic forms for asking "who", "what",
# "where", "when" and "how" questions.  Historically such queries
# were routed directly to the model.  In this version we send them
# through the web search pipeline to pull the latest facts from
# reliable sources.
_GENERAL_KNOWLEDGE_RE = re.compile(
    r"""(?ix)
        (che\s+cos[’']?è|cos[’']?è|what\s+is|explain) |
        (chi\s+è|who\s+is) |
        (dove\s+si\s+trova|where\s+is) |
        (quando\s+è\s+stato|quando\s+è\s+nata|when\s+was) |
        (come\s+funziona|how\s+does\s+it\s+work)
    """
)


class SmartIntentClassifier:
    """Rule‑based intent classifier for query routing.

    The classifier examines the lower‑cased user input and applies
    pattern matching and keyword detection to determine the best
    handling strategy.  It aims to maximise answer accuracy and
    freshness by using web search aggressively for general or
    time‑dependent questions while avoiding unnecessary searches for
    conversational or creative tasks.
    """

    def __init__(self) -> None:
        # Keywords indicating a request about weather conditions.  If any
        # appear in the query, we treat the query as a live weather
        # request and search the web for current data.
        # STEP 2: Expanded with natural language phrases
        self.weather_keywords = [
            "meteo",
            "che tempo",
            "weather",
            "temperatura",
            "pioggia",
            "neve",
            "previsioni",
            "previsione",
            "nuvoloso",
            "sereno",
            "temporale",
            # STEP 2: Natural language additions
            "piove",
            "nevica",
            "fa caldo",
            "fa freddo",
            "condizioni meteo",
            "previsioni del tempo",
            "com'è il tempo",
            "come è il tempo",
            "nevicherà",
            "pioverà",
        ]
        
        # Pattern più specifici per query meteo con città
        # STEP 2: Enhanced patterns for natural language
        self.weather_patterns = [
            r"meteo\s+\w+",                    # "meteo roma"
            r"che\s+tempo\s+fa",               # "che tempo fa a..."
            r"com['']?è\s+il\s+tempo",         # "com'è il tempo", "come è il tempo"
            r"come\s+è\s+il\s+tempo",          # "come è il tempo"
            r"previsioni\s+\w+",               # "previsioni milano"
            r"weather\s+\w+",                  # "weather rome"
            r"piove\s+(a|in|su)",              # "piove a Roma"
            r"nevica\s+(a|in|su)",             # "nevica a Milano"
            r"fa\s+(caldo|freddo)\s+(a|in)",   # "fa caldo a Roma"
            r"nevicherà\s+(a|in|domani|oggi)", # "nevicherà a Roma domani"
            r"pioverà\s+(a|in|domani|oggi)",   # "pioverà domani"
            r"condizioni\s+meteo\s+\w+",       # "condizioni meteo roma"
            r"previsioni\s+del\s+tempo",       # "previsioni del tempo"
        ]

        # Asset keywords representing financial instruments, precious metals
        # or currencies.  When combined with price triggers or temporal
        # indicators these cause the classifier to search for live price
        # information.
        # EXTENDED: più crypto, azioni, forex, indici
        self.asset_keywords = [
            # Crypto principali
            "btc", "bitcoin", "eth", "ethereum", "sol", "solana",
            "xrp", "ripple", "ada", "cardano", "doge", "dogecoin",
            "bnb", "binance coin", "usdt", "tether", "usdc",
            "dot", "polkadot", "avax", "avalanche", "matic", "polygon",
            "link", "chainlink", "uni", "uniswap", "ltc", "litecoin",
            "shib", "shiba", "atom", "cosmos", "near", "apt", "aptos",
            "arb", "arbitrum", "sui", "pepe", "trx", "tron",
            # Forex
            "eurusd", "eur/usd", "usd/eur", "gbpusd", "gbp/usd",
            "usdjpy", "usd/jpy", "usdchf", "usd/chf",
            "eurgbp", "eur/gbp", "forex", "fx",
            # Commodities
            "oro", "gold", "xauusd", "xau/usd",
            "argento", "silver", "xagusd", "xag/usd",
            "petrolio", "oil", "crude", "brent", "wti",
            # Azioni/ETF
            "azioni", "stock", "stocks", "shares",
            "apple", "aapl", "microsoft", "msft", "google", "googl",
            "amazon", "amzn", "tesla", "tsla", "nvidia", "nvda",
            "meta", "facebook", "netflix", "nflx",
            # Indici
            "indice", "index", "indices",
            "dow jones", "dow", "nasdaq", "s&p", "s&p 500", "sp500",
            "ftse", "dax", "cac", "nikkei", "hang seng",
            "ftsemib", "ftse mib",
        ]

        # Triggers for price or value queries.  Used in conjunction
        # with asset keywords to detect requests like "prezzo del bitcoin"
        # or "quanto vale l'oro adesso".
        # EXTENDED: più trigger per finanza/trading
        self.price_trigger_keywords = [
            "prezzo", "quotazione", "quanto vale", "quanto costa",
            "valore", "tasso di cambio", "cambio",
            "price", "exchange rate", "quote",
            "market cap", "capitalizzazione",
            "volume", "trading volume",
            "bid", "ask", "spread",
        ]

        # Words that suggest the user is asking for the result of a
        # sporting event or league table.  When present alongside
        # temporal hints (oggi, ieri, etc.) we route to web search for
        # fresh scores and standings.
        # EXTENDED: più sport, squadre, competizioni
        self.results_keywords = [
            "risultato", "risultati", "score", "scores",
            "quanto è finita", "com'è finita",
            "chi ha vinto", "chi ha segnato", "gol",
            "classifica", "standing", "table", "standings",
            "partita", "partite", "match",
            # Squadre italiane (trigger diretto)
            "milan", "inter", "juventus", "juve", "napoli", "roma",
            "lazio", "atalanta", "fiorentina", "torino", "bologna",
            # Squadre internazionali
            "real madrid", "barcellona", "barcelona", "psg",
            "manchester", "liverpool", "chelsea", "arsenal", "bayern",
            # Competizioni - EXPANDED with complete names
            "serie a", "premier league", 
            "champions", "champions league", "uefa champions",  # Complete "champions league"
            "europa league", "uefa europa",  # Complete "uefa europa"
            "la liga", "bundesliga", "ligue 1",
            "coppa italia", "coppa del mondo", "world cup",  # Italian/International cups
            "europei", "mondiali",  # Championships
        ]

        # Terms indicating a schedule or time query, such as asking
        # when a match starts or what time an event occurs.
        # EXTENDED: F1, MotoGP, eventi finanziari, indirect interrogative forms
        self.schedule_keywords = [
            "orari", "orario", "a che ora",
            "quando gioca", "quando inizia", "quando parte",
            "what time", "schedule", "calendario",
            "prossima partita", "prossimo match",
            # Indirect interrogative forms - EXPANDED
            "se oggi gioca", "se domani gioca", "se stasera gioca",
            "se c'è partita", "se ci sono partite",
            "gioca oggi", "gioca stasera", "gioca domani",
            "gioca",  # Standalone "gioca" also indicates schedule context
            "partite di oggi", "partite oggi", "partite stasera",
            "partite di",  # "partite di" pattern
            "c'è la partita", "c'è la champions",
            # F1/Motorsport
            "f1", "formula 1", "formula1", "gran premio", "gp",
            "motogp", "moto gp",
            "prossima gara", "prossimo gp",
            # Eventi finanziari
            "quando è", "quando sarà",
            "fed", "fomc", "bce", "ecb",
            "riunione fed", "riunione bce",
        ]

        # High‑level news triggers.  These capture phrases like
        # "ultime notizie" or "breaking news" and cause the query to be
        # handled via web search to fetch the most recent headlines.
        # EXTENDED: più pattern news
        self.news_keywords = [
            "ultime notizie", "breaking news", "news",
            "oggi in", "oggi cosa è successo", "oggi cosa succede",
            "ultime news", "news oggi", "notizie oggi",
            "cosa è successo oggi", "cosa succede",
            "novità", "aggiornamenti", "headline", "headlines",
            "latest news", "current events",
        ]

        # Temporal indicators implying that the user expects live or
        # recent information.  Combined with other keywords, these
        # encourage the classifier to choose web search.
        self.time_live_keywords = [
            "oggi", "stamattina", "stasera", "adesso", "ora",
            "in tempo reale", "in real time", "live",
            "ultimi", "ieri", "pochi minuti fa",
            "ultima ora", "ultimo aggiornamento",
            "attuale", "corrente", "now", "current",
        ]
        
        # NUOVO: Keywords per betting/trading (per future integrazioni)
        self.betting_keywords = [
            "scommessa", "scommesse", "bet", "betting",
            "quote", "odds", "pronostico", "pronostici",
            "value bet", "over", "under", "handicap",
            "1x2", "combo", "multipla", "singola",
        ]
        
        self.trading_keywords = [
            "trading", "trader", "trade",
            "long", "short", "buy", "sell",
            "stop loss", "take profit", "tp", "sl",
            "leva", "leverage", "margin",
            "analisi tecnica", "technical analysis",
            "supporto", "resistenza", "support", "resistance",
            "candlestick", "pattern", "trend",
        ]
        
        # NUOVO: Keywords per code generation (script, software, coding)
        self.code_generation_keywords = [
            "scrivi codice", "genera codice", "crea script",
            "scrivi uno script", "genera uno script",
            "scrivi un programma", "crea un programma",
            "implementa", "programma che", "script che",
            "funzione che", "classe che", "metodo che",
            "codice python", "codice javascript", "codice java",
            "script bash", "script python", "script shell",
            "write code", "generate code", "create script",
            "implementa una funzione", "crea una funzione",
            "scrivi una funzione", "genera una funzione",
            "codice per", "script per", "programma per",
        ]
        
        # NUOVO: Keywords per health/salute (per future integrazioni)
        self.health_keywords = [
            "salute", "health", "sintomi", "symptoms",
            "malattia", "malattie", "disease",
            "medicina", "medicine", "farmaco", "farmaci",
            "vaccino", "vaccini", "cura", "cure",
            "dieta", "nutrizione", "calorie",
            "fitness", "allenamento", "workout",
            "benessere", "wellness",
        ]
        
        # NUOVO: Keywords per viaggi (per future integrazioni)
        self.travel_keywords = [
            "volo", "voli", "flight", "flights",
            "hotel", "albergo", "alberghi", "booking",
            "viaggio", "viaggi", "travel", "trip",
            "vacanza", "vacanze", "holiday",
            "destinazione", "destination",
            "itinerario", "itinerary",
            "biglietto", "biglietti", "ticket",
            "aereo", "treno", "autobus",
        ]

    # ------------------------------------------------------------------
    # Helpers
    @staticmethod
    def _clean(text: str) -> str:
        """Trim whitespace from a string, returning an empty string if
        the input is None.  This helper prevents AttributeError when
        handling None inputs from external callers.
        """
        return (text or "").strip()

    @staticmethod
    def _lower(text: str) -> str:
        """Return a lower‑cased version of the input string after
        trimming whitespace.  This is used to normalise user input
        before applying regexes and keyword checks.
        """
        return SmartIntentClassifier._clean(text).lower()

    @staticmethod
    def _clean_query_for_matching(text: str) -> str:
        """Remove punctuation (?!.,;:) and normalize whitespace for pattern matching.
        
        This method strips common punctuation that can interfere with keyword
        and pattern matching while preserving the semantic content of the query.
        The original query is maintained for other uses (logging, display, etc.).
        
        Parameters
        ----------
        text : str
            The query text to clean.
        
        Returns
        -------
        str
            Cleaned query with punctuation removed and normalized whitespace.
        
        Examples
        --------
        >>> SmartIntentClassifier._clean_query_for_matching("Meteo Roma?")
        "Meteo Roma"
        >>> SmartIntentClassifier._clean_query_for_matching("Prezzo Bitcoin!!!")
        "Prezzo Bitcoin"
        >>> SmartIntentClassifier._clean_query_for_matching("Chi è Einstein?!")
        "Chi è Einstein"
        """
        if not text:
            return ""
        
        # Remove punctuation: ?!.,;:
        cleaned = text
        for char in "?!.,;:":
            cleaned = cleaned.replace(char, "")
        
        # Normalize whitespace (collapse multiple spaces into one)
        cleaned = " ".join(cleaned.split())
        
        return cleaned.strip()

    @staticmethod
    def _extract_url(text: str) -> Optional[str]:
        """Extract the first URL from a given text or return None if
        no URL is present.  Only HTTP and HTTPS URLs are recognised.
        """
        m = _URL_RE.search(text or "")
        return m.group(1) if m else None

    def _try_llm_classification(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Tenta classificazione con LLM Intent Classifier.
        
        Returns None se LLM non disponibile o fallisce.
        Altrimenti ritorna dict con intent, confidence, reason, source="llm".
        """
        if not LLM_INTENT_ENABLED:
            return None
        
        try:
            from core.llm_intent_classifier import get_llm_intent_classifier
            
            llm_classifier = get_llm_intent_classifier()
            if not llm_classifier:
                return None
            
            # Call LLM classifier
            llm_result = llm_classifier.classify(text)
            
            if not llm_result or llm_result.get("confidence", 0) < INTENT_LLM_MIN_CONFIDENCE:
                log.debug(f"LLM intent below threshold: {llm_result}")
                return None
            
            # Convert LLM result format to SmartIntent format
            return {
                "intent": llm_result.get("intent", "DIRECT_LLM"),
                "confidence": llm_result.get("confidence", 0.5),
                "reason": f"llm_classified:{llm_result.get('reasoning', 'semantic')}",
                "source": "llm",
                "low_confidence": llm_result.get("confidence", 0) < 0.65,
                "url": None,
                "live_type": llm_result.get("live_type"),
            }
        except Exception as e:
            log.warning(f"LLM intent classification failed: {e}")
            return None

    @staticmethod
    def _normalize_result(result: Dict[str, Any], source: str = "pattern") -> Dict[str, Any]:
        """Normalizza risultato classificazione aggiungendo campi standard."""
        if "source" not in result:
            result["source"] = source
        if "low_confidence" not in result:
            # Considera low se confidence < 0.65
            result["low_confidence"] = result.get("confidence", 0.0) < 0.65
        # Assicura che ci siano tutti i campi base
        if "url" not in result:
            result["url"] = None
        if "live_type" not in result:
            result["live_type"] = None
        return result

    # ------------------------------------------------------------------
    # Main classification logic
    def classify(self, text: str) -> Dict[str, object]:
        """Classify a user query into one of three intents: DIRECT_LLM,
        WEB_SEARCH or WEB_READ.  The returned dictionary contains
        additional metadata (confidence, reason, url, live_type) used
        by the caller to handle the request appropriately.

        Parameters
        ----------
        text : str
            The user prompt to classify.

        Returns
        -------
        Dict[str, object]
            A dictionary describing the routing decision.
        """
        raw = self._clean(text)
        low = self._lower(text)
        
        # Clean query for pattern matching (removes punctuation ?!.,;:)
        # Use this for keyword and pattern checks, but keep 'low' for other uses
        low_clean = self._lower(self._clean_query_for_matching(text))

        # If the input is empty, return a low‑confidence DIRECT_LLM
        if not raw:
            return self._normalize_result({
                "intent": "DIRECT_LLM",
                "confidence": 0.0,
                "reason": "empty",
            }, source="pattern")

        # If a URL is present, we should read the page content via WEB_READ
        url = self._extract_url(raw)
        if url:
            return self._normalize_result({
                "intent": "WEB_READ",
                "confidence": 0.95,
                "reason": "url_detected",
                "url": url,
                "live_type": None,
            }, source="pattern")

        # Handle basic greetings or confirmations via the LLM
        # Use low_clean for pattern matching to ignore punctuation
        if _SMALLTALK_RE.search(low_clean):
            return self._normalize_result({
                "intent": "DIRECT_LLM",
                "confidence": 0.9,
                "reason": "smalltalk",
            }, source="pattern")

        # One‑word queries like "Roma" or "Einstein" typically
        # correspond to a general knowledge lookup.  We route these
        # through the web for the most up‑to‑date information.
        # Use low_clean to properly count tokens without punctuation
        tokens = low_clean.split()
        if len(tokens) == 1:
            return self._normalize_result({
                "intent": "WEB_SEARCH",
                "confidence": 0.75,
                "reason": "single_token_general_knowledge",
                "url": None,
                "live_type": None,
            }, source="pattern")

        # If the text matches our general‑knowledge patterns, send it to
        # web search rather than the LLM so the assistant can draw on
        # external sources and deliver citations.
        # Use low_clean for pattern matching
        if _GENERAL_KNOWLEDGE_RE.search(low_clean):
            return self._normalize_result({
                "intent": "WEB_SEARCH",
                "confidence": 0.9,
                "reason": "general_knowledge_query",
                "url": None,
                "live_type": None,
            }, source="pattern")

        # Determine whether the prompt contains any temporal indicators
        # Use low_clean for keyword matching
        has_live_time = any(k in low_clean for k in self.time_live_keywords)

        # Weather queries: if the prompt mentions weather terms or matches
        # weather patterns, send directly to web search.
        # STEP 2: Enhanced with LLM fallback for borderline cases
        # Use low_clean for keyword and pattern matching
        has_weather_keyword = any(k in low_clean for k in self.weather_keywords)
        has_weather_pattern = any(re.search(p, low_clean) for p in self.weather_patterns)
        
        if has_weather_keyword or has_weather_pattern:
            # High confidence if both keyword AND pattern match
            confidence = 0.95 if (has_weather_keyword and has_weather_pattern) else 0.80
            return self._normalize_result({
                "intent": "WEB_SEARCH",
                "confidence": confidence,
                "reason": "weather_query",
                "live_type": "weather",
                "url": None,
            }, source="pattern")

        # Price/market queries: an asset keyword plus either a price
        # trigger or a temporal hint implies the user wants a live
        # quote.  Route to web search and mark the live_type.
        # Use low_clean for keyword matching
        has_asset = any(k in low_clean for k in self.asset_keywords)
        has_price_trigger = any(k in low_clean for k in self.price_trigger_keywords)
        if has_asset and (has_price_trigger or has_live_time):
            return self._normalize_result({
                "intent": "WEB_SEARCH",
                "confidence": 0.92,
                "reason": "price_or_market_live_query",
                "live_type": "price",
                "url": None,
            }, source="pattern")
        
        # NUOVO: Asset da solo con contesto implicito di prezzo
        # Es: "bitcoin ora", "btc oggi", "ethereum" (query singola già gestita sopra)
        if has_asset and len(tokens) <= 3:
            return self._normalize_result({
                "intent": "WEB_SEARCH",
                "confidence": 0.88,
                "reason": "asset_implicit_price_query",
                "live_type": "price",
                "url": None,
            }, source="pattern")
        
        # PRIORITÀ: Travel keywords → check PRIMA di sports per evitare conflitti
        # Es: "volo roma parigi" non deve matchare "roma" come squadra
        # Use low_clean for keyword matching
        has_travel = any(k in low_clean for k in self.travel_keywords)
        if has_travel:
            return self._normalize_result({
                "intent": "WEB_SEARCH",
                "confidence": 0.85,
                "reason": "travel_query",
                "live_type": "travel",
                "url": None,
            }, source="pattern")

        # PRIORITÀ: Schedule + temporal queries (ALTA PRIORITÀ)
        # Query come "Sai se oggi gioca la Champions league?" devono essere riconosciute
        # Use low_clean for keyword matching
        has_schedule = any(k in low_clean for k in self.schedule_keywords)
        has_temporal = any(k in low_clean for k in self.time_live_keywords)
        
        if has_schedule and has_temporal:
            return self._normalize_result({
                "intent": "WEB_SEARCH",
                "confidence": 0.92,
                "reason": "schedule_query_with_temporal",
                "live_type": "schedule",
                "url": None,
            }, source="pattern")
        
        # Schedule queries normali (senza hint temporali espliciti)
        if has_schedule:
            return self._normalize_result({
                "intent": "WEB_SEARCH",
                "confidence": 0.88,
                "reason": "schedule_or_time_query",
                "live_type": "schedule",
                "url": None,
            }, source="pattern")

        # Live results: detect sports scores or standings requests when
        # accompanied by temporal hints (today, yesterday).  These
        # queries are best answered with a fresh web search.
        # EXTENDED: anche senza hint temporali se menziona squadre/competizioni
        # Use low_clean for keyword matching
        has_sports_keywords = any(k in low_clean for k in self.results_keywords)
        if has_sports_keywords:
            return self._normalize_result({
                "intent": "WEB_SEARCH",
                "confidence": 0.90,
                "reason": "sports_results_query",
                "live_type": "sports",
                "url": None,
            }, source="pattern")


        # Generic news queries or references to current events trigger a
        # search for recent headlines.
        # STEP 2: Enhanced with pattern confidence check
        # Use low_clean for keyword matching
        has_news_keywords = any(k in low_clean for k in self.news_keywords)
        has_news_with_time = "news" in low_clean and has_live_time
        
        if has_news_keywords or has_news_with_time:
            pattern_result = self._normalize_result({
                "intent": "WEB_SEARCH",
                "confidence": 0.85,
                "reason": "news_live_query",
                "live_type": "news",
                "url": None,
            }, source="pattern")
            return pattern_result
        
        # NUOVO: Betting keywords → WEB_SEARCH per dati aggiornati
        # Use low_clean for keyword matching
        if any(k in low_clean for k in self.betting_keywords):
            return self._normalize_result({
                "intent": "WEB_SEARCH",
                "confidence": 0.80,
                "reason": "betting_query",
                "live_type": "betting",
                "url": None,
            }, source="pattern")
        
        # NUOVO: Trading keywords → mix LLM + context
        # Use low_clean for keyword matching
        if any(k in low_clean for k in self.trading_keywords):
            # Se è una domanda educativa ("cos'è lo stop loss") → LLM
            if _GENERAL_KNOWLEDGE_RE.search(low_clean):
                return self._normalize_result({
                    "intent": "DIRECT_LLM",
                    "confidence": 0.85,
                    "reason": "trading_educational_query",
                }, source="pattern")
            # Altrimenti potrebbe volere dati live
            return self._normalize_result({
                "intent": "WEB_SEARCH",
                "confidence": 0.78,
                "reason": "trading_live_query",
                "live_type": "trading",
                "url": None,
            }, source="pattern")
        
        # NUOVO: Code generation → DIRECT_LLM con alta confidence
        # Richieste esplicite di generazione codice vanno direttamente al LLM
        # Use low_clean for keyword matching
        if any(k in low_clean for k in self.code_generation_keywords):
            return self._normalize_result({
                "intent": "DIRECT_LLM",
                "confidence": 0.95,
                "reason": "code_generation_request",
                "live_type": "code",
            }, source="pattern")
        
        # NUOVO: Health keywords → WEB_SEARCH (con nota che non è consiglio medico)
        # Use low_clean for keyword matching
        if any(k in low_clean for k in self.health_keywords):
            # Domande educative → LLM
            if _GENERAL_KNOWLEDGE_RE.search(low_clean):
                return self._normalize_result({
                    "intent": "DIRECT_LLM",
                    "confidence": 0.80,
                    "reason": "health_educational_query",
                    "live_type": "health",
                }, source="pattern")
            # Informazioni su farmaci/malattie → WEB_SEARCH per dati aggiornati
            return self._normalize_result({
                "intent": "WEB_SEARCH",
                "confidence": 0.75,
                "reason": "health_info_query",
                "live_type": "health",
                "url": None,
            }, source="pattern")

        # Operational requests (coding, writing, optimisation, etc.)
        # should stay within the LLM environment.  Recognise Italian
        # verbs like "scrivi", "genera", "crea" and treat them as
        # direct commands rather than search queries.
        # Use low_clean for pattern matching
        if re.search(
            r"\b(scrivi|genera|crea|aggiorna|ottimizza|refactor|fixa|implementa|programma|codice)\b",
            low_clean,
        ):
            return self._normalize_result({
                "intent": "DIRECT_LLM",
                "confidence": 0.85,
                "reason": "tooling_or_coding_request",
                "live_type": "code",
            }, source="pattern")

        # Default fallback: for anything not matched above, use the
        # LLM directly.  This includes open‑ended chat, deep
        # reasoning, personal advice and other creative tasks.
        
        # STEP 2: Enhanced LLM Intent Classifier integration
        # Try LLM classification for borderline/generic queries
        pattern_result = {
            "intent": "DIRECT_LLM",
            "confidence": 0.6,
            "reason": "default_direct_llm",
        }
        
        # STEP 2: If pattern confidence is low/uncertain AND LLM is enabled,
        # let LLM classifier attempt to provide better classification
        if LLM_INTENT_ENABLED and pattern_result["confidence"] < 0.7:
            llm_result = self._try_llm_classification(raw)
            if llm_result and llm_result.get("confidence", 0) >= INTENT_LLM_MIN_CONFIDENCE:
                # LLM has higher confidence - use its classification
                log.info(
                    f"Intent: LLM override pattern "
                    f"(pattern={pattern_result['confidence']:.2f} → "
                    f"llm={llm_result.get('confidence', 0):.2f}, "
                    f"intent={llm_result.get('intent')})"
                )
                return self._normalize_result(llm_result, source="llm")
        
        # Return pattern-based result
        return self._normalize_result(pattern_result, source="pattern")
    
    def classify_with_unified(self, text: str) -> Dict[str, object]:
        """
        Alternativa a classify() che delega a UnifiedIntentDetector.
        
        Questa funzione garantisce coerenza con unified_web_handler.py
        e converte automaticamente il formato di ritorno per 
        retrocompatibilità con il sistema SmartIntent.
        
        Parameters
        ----------
        text : str
            The user prompt to classify.

        Returns
        -------
        Dict[str, object]
            A dictionary in SmartIntentClassifier format.
        """
        try:
            from core.unified_web_handler import UnifiedIntentDetector
            
            detector = UnifiedIntentDetector()
            classification = detector.classify(text)
            
            # Converti al formato SmartIntentClassifier
            return detector.to_smart_intent_format(classification)
            
        except ImportError:
            # Fallback alla logica originale se UnifiedIntentDetector non è disponibile
            return self.classify(text)
