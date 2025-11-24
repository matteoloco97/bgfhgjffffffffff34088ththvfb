#!/usr/bin/env python3
# core/smart_intent_classifier.py
#
# FASE 1 – ROUTING “TUTTOLOGO”:
# - DIRECT_LLM per tutto ciò che è concettuale / ragionamento / coding / chiacchiera.
# - WEB_SEARCH SOLO per meteo, prezzi live, risultati recenti, orari, news del momento.
# - WEB_READ quando c’è una URL esplicita.

from __future__ import annotations

import re
from typing import Dict, Optional

# URL generiche
_URL_RE = re.compile(r"(https?://\S+)", re.IGNORECASE)

# Smalltalk / ping
_SMALLTALK_RE = re.compile(
    r"""(?ix)^\s*(
        ciao|hey|hi|hello|salve|
        buongiorno|buonasera|buonanotte|
        grazie|grazie mille|thank(s)?|
        ok+|okk+|perfetto|grand(e|ioso)|
        ci\s*sei\??|sei\s*online\??
    )\b"""
)

# Pattern "general knowledge" che NON deve andare sul web
_GENERAL_KNOWLEDGE_RE = re.compile(
    r"""(?ix)
    (che\s+cos[’']?è|cos[’']?è|what\s+is|explain)|
    (chi\s+è|who\s+is)|
    (dove\s+si\s+trova|where\s+is)|
    (quando\s+è\s+stato|when\s+was)|
    (come\s+funziona|how\s+does\s+it\s+work)
    """
)

class SmartIntentClassifier:
    """
    Classificatore rule-based leggero:
      - WEB_READ   se c’è una URL esplicita.
      - WEB_SEARCH SOLO per vere query "live" (meteo, prezzi, risultati, orari, news oggi).
      - DIRECT_LLM per tutto il resto (conoscenza nativa del modello, ragionamento, coding).
    """

    def __init__(self) -> None:
        # keyword live (italiano+inglese)
        self.weather_keywords = [
            "meteo", "che tempo", "weather",
            "temperatura", "pioggia", "neve",
        ]

        # asset/symbol: li useremo SOLO in combo con parole tipo "prezzo / oggi / ora"
        self.asset_keywords = [
            "btc", "bitcoin", "eth", "ethereum",
            "eurusd", "eur/usd", "usd/eur",
            "oro", "gold", "argento", "silver",
            "azioni", "stock", "indice", "index",
            "dow jones", "nasdaq", "s&p", "ftse",
        ]

        # parole che indicano chiaramente richiesta di prezzo / quotazione
        self.price_trigger_keywords = [
            "prezzo", "quotazione", "quanto vale",
            "valore", "tasso di cambio", "cambio",
            "price", "exchange rate",
        ]

        self.results_keywords = [
            "risultato", "risultati", "score",
            "quanto è finita", "com'è finita", "chi ha vinto", "chi ha segnato",
            "classifica", "standing", "table",
        ]

        self.schedule_keywords = [
            "orari", "orario", "a che ora", "quando gioca",
            "quando inizia", "quando parte", "what time",
        ]

        self.news_keywords = [
            "ultime notizie", "breaking news",
            "oggi in", "oggi cosa è successo", "oggi cosa succede",
            "ultime news", "news oggi", "cosa è successo oggi",
        ]

        # indicatori temporali che rendono probabile che la richiesta sia “live”
        self.time_live_keywords = [
            "oggi", "stamattina", "stasera", "adesso", "ora",
            "in tempo reale", "in real time", "live", "ultimi",
            "ieri", "pochi minuti fa", "ultima ora", "ultimo aggiornamento",
        ]

    # ---------- helper interni ----------

    @staticmethod
    def _clean(text: str) -> str:
        return (text or "").strip()

    @staticmethod
    def _lower(text: str) -> str:
        return SmartIntentClassifier._clean(text).lower()

    @staticmethod
    def _extract_url(text: str) -> Optional[str]:
        m = _URL_RE.search(text or "")
        return m.group(1) if m else None

    # ---------- classificatore principale ----------

    def classify(self, text: str) -> Dict[str, object]:
        """
        Ritorna:
          {
            "intent": "DIRECT_LLM" | "WEB_SEARCH" | "WEB_READ",
            "confidence": float 0..1,
            "reason": str,
            "url": str | None,            # solo per WEB_READ
            "live_type": str | None       # "weather"|"price"|"results"|"schedule"|"news"
          }
        """
        raw = self._clean(text)
        low = self._lower(text)

        if not raw:
            return {
                "intent": "DIRECT_LLM",
                "confidence": 0.0,
                "reason": "empty",
            }

        # URL → WEB_READ
        url = self._extract_url(raw)
        if url:
            return {
                "intent": "WEB_READ",
                "confidence": 0.95,
                "reason": "url_detected",
                "url": url,
                "live_type": None,
            }

        tokens = low.split()
        n_tokens = len(tokens)

        # Smalltalk / ping → DIRECT_LLM
        if _SMALLTALK_RE.search(low):
            return {
                "intent": "DIRECT_LLM",
                "confidence": 0.9,
                "reason": "smalltalk",
            }

        # Query ultra-corte (1 parola, tipo “Roma?”, “Einstein?”) → general knowledge
        if n_tokens == 1:
            return {
                "intent": "DIRECT_LLM",
                "confidence": 0.7,
                "reason": "single_token_general",
            }

        # Pattern espliciti di "general knowledge" (dove si trova, chi è, che cos'è...)
        if _GENERAL_KNOWLEDGE_RE.search(low):
            return {
                "intent": "DIRECT_LLM",
                "confidence": 0.85,
                "reason": "general_knowledge_pattern",
            }

        # Flag temporale “live?”
        has_live_time = any(k in low for k in self.time_live_keywords)

        # ------- LIVE: METEO -------
        if any(k in low for k in self.weather_keywords):
            # Per il meteo basta che sia una query e non una cosa completamente astratta
            return {
                "intent": "WEB_SEARCH",
                "confidence": 0.92,
                "reason": "weather_query",
                "live_type": "weather",
            }

        # ------- LIVE: PREZZI / QUOTAZIONI / MERCATI -------
        # Per non mandare sul web ogni volta che nomini "bitcoin", richiedo:
        #   (asset + parola tipo "prezzo / quanto vale / quotazione")  oppure
        #   (asset + indicatore temporale "oggi / adesso / ora / live")
        has_asset = any(k in low for k in self.asset_keywords)
        has_price_trigger = any(k in low for k in self.price_trigger_keywords)

        if has_asset and (has_price_trigger or has_live_time):
            return {
                "intent": "WEB_SEARCH",
                "confidence": 0.9,
                "reason": "price_or_market_live_query",
                "live_type": "price",
            }

        # ------- LIVE: RISULTATI SPORTIVI / CLASSIFICHE RECENTI -------
        if any(k in low for k in self.results_keywords) and (has_live_time or "oggi" in low or "ieri" in low):
            return {
                "intent": "WEB_SEARCH",
                "confidence": 0.88,
                "reason": "results_or_scores_recent_query",
                "live_type": "results",
            }

        # ------- LIVE: ORARI / SCHEDULE -------
        if any(k in low for k in self.schedule_keywords):
            return {
                "intent": "WEB_SEARCH",
                "confidence": 0.86,
                "reason": "schedule_or_time_query",
                "live_type": "schedule",
            }

        # ------- LIVE: NEWS MOLTO GENERICHE / OGGI -------
        if any(k in low for k in self.news_keywords) or ("news" in low and has_live_time):
            return {
                "intent": "WEB_SEARCH",
                "confidence": 0.82,
                "reason": "news_live_query",
                "live_type": "news",
            }

        # ------- RICHIESTE OPERATIVE / CODICE / GENERAZIONE TESTO -------
        if re.search(r"\b(scrivi|genera|crea|aggiorna|ottimizza|refactor|fixa|implementa|programma|codice)\b", low):
            return {
                "intent": "DIRECT_LLM",
                "confidence": 0.8,
                "reason": "tooling_or_coding_request",
            }

        # Default totale: DIRECT_LLM (tuttologo base)
        return {
            "intent": "DIRECT_LLM",
            "confidence": 0.6,
            "reason": "default_direct_llm",
        }
