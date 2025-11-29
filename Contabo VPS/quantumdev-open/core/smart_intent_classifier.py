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
        self.asset_keywords = [
            "btc", "bitcoin", "eth", "ethereum",
            "eurusd", "eur/usd", "usd/eur",
            "oro", "gold", "argento", "silver",
            "azioni", "stock", "indice", "index",
            "dow jones", "nasdaq", "s&p", "ftse",
        ]

        # Triggers for price or value queries.  Used in conjunction
        # with asset keywords to detect requests like "prezzo del bitcoin"
        # or "quanto vale l'oro adesso".
        self.price_trigger_keywords = [
            "prezzo", "quotazione", "quanto vale",
            "valore", "tasso di cambio", "cambio",
            "price", "exchange rate",
        ]

        # Words that suggest the user is asking for the result of a
        # sporting event or league table.  When present alongside
        # temporal hints (oggi, ieri, etc.) we route to web search for
        # fresh scores and standings.
        self.results_keywords = [
            "risultato", "risultati", "score",
            "quanto è finita", "com'è finita",
            "chi ha vinto", "chi ha segnato",
            "classifica", "standing", "table",
        ]

        # Terms indicating a schedule or time query, such as asking
        # when a match starts or what time an event occurs.
        self.schedule_keywords = [
            "orari", "orario", "a che ora",
            "quando gioca", "quando inizia", "quando parte",
            "what time",
        ]

        # High‑level news triggers.  These capture phrases like
        # "ultime notizie" or "breaking news" and cause the query to be
        # handled via web search to fetch the most recent headlines.
        self.news_keywords = [
            "ultime notizie", "breaking news",
            "oggi in", "oggi cosa è successo", "oggi cosa succede",
            "ultime news", "news oggi",
            "cosa è successo oggi",
        ]

        # Temporal indicators implying that the user expects live or
        # recent information.  Combined with other keywords, these
        # encourage the classifier to choose web search.
        self.time_live_keywords = [
            "oggi", "stamattina", "stasera", "adesso", "ora",
            "in tempo reale", "in real time", "live",
            "ultimi", "ieri", "pochi minuti fa",
            "ultima ora", "ultimo aggiornamento",
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
                "confidence": 0.9,
                "reason": "price_or_market_live_query",
                "live_type": "price",
                "url": None,
            }

        # Live results: detect sports scores or standings requests when
        # accompanied by temporal hints (today, yesterday).  These
        # queries are best answered with a fresh web search.
        if any(k in low for k in self.results_keywords) and (
            has_live_time or "oggi" in low or "ieri" in low
        ):
            return {
                "intent": "WEB_SEARCH",
                "confidence": 0.88,
                "reason": "results_or_scores_recent_query",
                "live_type": "results",
                "url": None,
            }

        # Schedule/time requests: look up event times using live data.
        if any(k in low for k in self.schedule_keywords):
            return {
                "intent": "WEB_SEARCH",
                "confidence": 0.86,
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
                "confidence": 0.82,
                "reason": "news_live_query",
                "live_type": "news",
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
                "confidence": 0.8,
                "reason": "tooling_or_coding_request",
            }

        # Default fallback: for anything not matched above, use the
        # LLM directly.  This includes open‑ended chat, deep
        # reasoning, personal advice and other creative tasks.
        return {
            "intent": "DIRECT_LLM",
            "confidence": 0.6,
            "reason": "default_direct_llm",
        }
