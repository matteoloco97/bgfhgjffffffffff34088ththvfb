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

import re
from typing import Dict, Optional


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
        ]
        
        # Pattern più specifici per query meteo con città
        self.weather_patterns = [
            r"meteo\s+\w+",           # "meteo roma"
            r"che\s+tempo\s+fa",      # "che tempo fa a..."
            r"previsioni\s+\w+",      # "previsioni milano"
            r"weather\s+\w+",         # "weather rome"
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
            # Competizioni
            "serie a", "premier league", "champions", "europa league",
            "la liga", "bundesliga", "ligue 1",
        ]

        # Terms indicating a schedule or time query, such as asking
        # when a match starts or what time an event occurs.
        # EXTENDED: F1, MotoGP, eventi finanziari
        self.schedule_keywords = [
            "orari", "orario", "a che ora",
            "quando gioca", "quando inizia", "quando parte",
            "what time", "schedule", "calendario",
            "prossima partita", "prossimo match",
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
    def _extract_url(text: str) -> Optional[str]:
        """Extract the first URL from a given text or return None if
        no URL is present.  Only HTTP and HTTPS URLs are recognised.
        """
        m = _URL_RE.search(text or "")
        return m.group(1) if m else None

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

        # If the input is empty, return a low‑confidence DIRECT_LLM
        if not raw:
            return {
                "intent": "DIRECT_LLM",
                "confidence": 0.0,
                "reason": "empty",
            }

        # If a URL is present, we should read the page content via WEB_READ
        url = self._extract_url(raw)
        if url:
            return {
                "intent": "WEB_READ",
                "confidence": 0.95,
                "reason": "url_detected",
                "url": url,
                "live_type": None,
            }

        # Handle basic greetings or confirmations via the LLM
        if _SMALLTALK_RE.search(low):
            return {
                "intent": "DIRECT_LLM",
                "confidence": 0.9,
                "reason": "smalltalk",
            }

        # One‑word queries like "Roma" or "Einstein" typically
        # correspond to a general knowledge lookup.  We route these
        # through the web for the most up‑to‑date information.
        tokens = low.split()
        if len(tokens) == 1:
            return {
                "intent": "WEB_SEARCH",
                "confidence": 0.75,
                "reason": "single_token_general_knowledge",
                "url": None,
                "live_type": None,
            }

        # If the text matches our general‑knowledge patterns, send it to
        # web search rather than the LLM so the assistant can draw on
        # external sources and deliver citations.
        if _GENERAL_KNOWLEDGE_RE.search(low):
            return {
                "intent": "WEB_SEARCH",
                "confidence": 0.9,
                "reason": "general_knowledge_query",
                "url": None,
                "live_type": None,
            }

        # Determine whether the prompt contains any temporal indicators
        has_live_time = any(k in low for k in self.time_live_keywords)

        # Weather queries: if the prompt mentions weather terms or matches
        # weather patterns, send directly to web search.
        has_weather_keyword = any(k in low for k in self.weather_keywords)
        has_weather_pattern = any(re.search(p, low) for p in self.weather_patterns)
        
        if has_weather_keyword or has_weather_pattern:
            return {
                "intent": "WEB_SEARCH",
                "confidence": 0.95,  # Higher confidence with pattern matching
                "reason": "weather_query",
                "live_type": "weather",
                "url": None,
            }

        # Price/market queries: an asset keyword plus either a price
        # trigger or a temporal hint implies the user wants a live
        # quote.  Route to web search and mark the live_type.
        has_asset = any(k in low for k in self.asset_keywords)
        has_price_trigger = any(k in low for k in self.price_trigger_keywords)
        if has_asset and (has_price_trigger or has_live_time):
            return {
                "intent": "WEB_SEARCH",
                "confidence": 0.92,
                "reason": "price_or_market_live_query",
                "live_type": "price",
                "url": None,
            }
        
        # NUOVO: Asset da solo con contesto implicito di prezzo
        # Es: "bitcoin ora", "btc oggi", "ethereum" (query singola già gestita sopra)
        if has_asset and len(tokens) <= 3:
            return {
                "intent": "WEB_SEARCH",
                "confidence": 0.88,
                "reason": "asset_implicit_price_query",
                "live_type": "price",
                "url": None,
            }
        
        # PRIORITÀ: Travel keywords → check PRIMA di sports per evitare conflitti
        # Es: "volo roma parigi" non deve matchare "roma" come squadra
        has_travel = any(k in low for k in self.travel_keywords)
        if has_travel:
            return {
                "intent": "WEB_SEARCH",
                "confidence": 0.85,
                "reason": "travel_query",
                "live_type": "travel",
                "url": None,
            }

        # Live results: detect sports scores or standings requests when
        # accompanied by temporal hints (today, yesterday).  These
        # queries are best answered with a fresh web search.
        # EXTENDED: anche senza hint temporali se menziona squadre/competizioni
        has_sports_keywords = any(k in low for k in self.results_keywords)
        if has_sports_keywords:
            return {
                "intent": "WEB_SEARCH",
                "confidence": 0.90,
                "reason": "sports_results_query",
                "live_type": "sports",
                "url": None,
            }

        # Schedule/time requests: look up event times using live data.
        if any(k in low for k in self.schedule_keywords):
            return {
                "intent": "WEB_SEARCH",
                "confidence": 0.88,
                "reason": "schedule_or_time_query",
                "live_type": "schedule",
                "url": None,
            }

        # Generic news queries or references to current events trigger a
        # search for recent headlines.
        if any(k in low for k in self.news_keywords) or (
            "news" in low and has_live_time
        ):
            return {
                "intent": "WEB_SEARCH",
                "confidence": 0.85,
                "reason": "news_live_query",
                "live_type": "news",
                "url": None,
            }
        
        # NUOVO: Betting keywords → WEB_SEARCH per dati aggiornati
        if any(k in low for k in self.betting_keywords):
            return {
                "intent": "WEB_SEARCH",
                "confidence": 0.80,
                "reason": "betting_query",
                "live_type": "betting",
                "url": None,
            }
        
        # NUOVO: Trading keywords → mix LLM + context
        if any(k in low for k in self.trading_keywords):
            # Se è una domanda educativa ("cos'è lo stop loss") → LLM
            if _GENERAL_KNOWLEDGE_RE.search(low):
                return {
                    "intent": "DIRECT_LLM",
                    "confidence": 0.85,
                    "reason": "trading_educational_query",
                }
            # Altrimenti potrebbe volere dati live
            return {
                "intent": "WEB_SEARCH",
                "confidence": 0.78,
                "reason": "trading_live_query",
                "live_type": "trading",
                "url": None,
            }
        
        # NUOVO: Code generation → DIRECT_LLM con alta confidence
        # Richieste esplicite di generazione codice vanno direttamente al LLM
        if any(k in low for k in self.code_generation_keywords):
            return {
                "intent": "DIRECT_LLM",
                "confidence": 0.95,
                "reason": "code_generation_request",
                "live_type": "code",
            }
        
        # NUOVO: Health keywords → WEB_SEARCH (con nota che non è consiglio medico)
        if any(k in low for k in self.health_keywords):
            # Domande educative → LLM
            if _GENERAL_KNOWLEDGE_RE.search(low):
                return {
                    "intent": "DIRECT_LLM",
                    "confidence": 0.80,
                    "reason": "health_educational_query",
                    "live_type": "health",
                }
            # Informazioni su farmaci/malattie → WEB_SEARCH per dati aggiornati
            return {
                "intent": "WEB_SEARCH",
                "confidence": 0.75,
                "reason": "health_info_query",
                "live_type": "health",
                "url": None,
            }

        # Operational requests (coding, writing, optimisation, etc.)
        # should stay within the LLM environment.  Recognise Italian
        # verbs like "scrivi", "genera", "crea" and treat them as
        # direct commands rather than search queries.
        if re.search(
            r"\b(scrivi|genera|crea|aggiorna|ottimizza|refactor|fixa|implementa|programma|codice)\b",
            low,
        ):
            return {
                "intent": "DIRECT_LLM",
                "confidence": 0.85,
                "reason": "tooling_or_coding_request",
                "live_type": "code",
            }

        # Default fallback: for anything not matched above, use the
        # LLM directly.  This includes open‑ended chat, deep
        # reasoning, personal advice and other creative tasks.
        return {
            "intent": "DIRECT_LLM",
            "confidence": 0.6,
            "reason": "default_direct_llm",
        }
    
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
