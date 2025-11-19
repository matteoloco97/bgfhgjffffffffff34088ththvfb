#!/usr/bin/env python3
# core/smart_intent_classifier.py
# Sonnet 4.5 – FASE 1 (Intent Classification)
#
# Obiettivi:
# - Usare il WEB solo quando serve (meteo, prezzi, risultati, orari, news live).
# - Tutto il resto → DIRECT_LLM (tuttologo generale).
# - Gestire URL → WEB_READ.
# - Restituire sempre: intent, confidence, reason (+ opzionale live_type, url).

from __future__ import annotations

import re
from typing import Dict, Optional

# URL base
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
      - WEB_READ   quando rileva una URL esplicita.
      - WEB_SEARCH per meteo, prezzi, risultati, orari, news live.
      - DIRECT_LLM per tutto il resto (general knowledge, ragionamento, how-to).
    """

    def __init__(self) -> None:
        # keyword live (italiano+inglese)
        self.weather_keywords = [
            "meteo", "che tempo", "weather",
            "temperatura", "pioggia", "neve",
        ]
        self.price_keywords = [
            "prezzo", "quotazione", "quanto vale",
            "valore", "tasso di cambio", "cambio",
            "btc", "bitcoin", "eth", "ethereum",
            "eurusd", "eur/usd", "usd/eur",
            "azioni", "borsa", "indice", "stock", "share", "price",
        ]
        self.results_keywords = [
            "risultato", "risultati", "score",
            "partita di", "chi ha vinto", "chi ha segnato",
            "classifica", "standing", "table",
        ]
        self.schedule_keywords = [
            "orari", "a che ora", "quando gioca",
            "quando inizia", "quando esce", "what time",
        ]
        self.news_keywords = [
            "ultime notizie", "breaking news", "oggi in",
            "oggi cosa è successo", "oggi cosa succede",
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
            "live_type": str | None       # per analytics: "weather"/"price"/"results"/"schedule"/"news"
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

        # LIVE: meteo
        if any(k in low for k in self.weather_keywords):
            return {
                "intent": "WEB_SEARCH",
                "confidence": 0.92,
                "reason": "weather_query",
                "live_type": "weather",
            }

        # LIVE: prezzi / quotazioni / mercati
        if any(k in low for k in self.price_keywords):
            return {
                "intent": "WEB_SEARCH",
                "confidence": 0.9,
                "reason": "price_or_market_query",
                "live_type": "price",
            }

        # LIVE: risultati sportivi / classifiche
        if any(k in low for k in self.results_keywords):
            return {
                "intent": "WEB_SEARCH",
                "confidence": 0.88,
                "reason": "results_or_scores_query",
                "live_type": "results",
            }

        # LIVE: orari / schedule
        if any(k in low for k in self.schedule_keywords):
            return {
                "intent": "WEB_SEARCH",
                "confidence": 0.86,
                "reason": "schedule_or_time_query",
                "live_type": "schedule",
            }

        # LIVE: news molto generiche
        if any(k in low for k in self.news_keywords):
            return {
                "intent": "WEB_SEARCH",
                "confidence": 0.82,
                "reason": "news_query",
                "live_type": "news",
            }

        # Query molto operative tipo "aggiorna", "scarica", "scrivimi codice per..."
        # → DIRECT_LLM (tooling/raisonamento, niente web necessario di default)
        if re.search(r"\b(scrivi|genera|crea|aggiorna|ottimizza|refactor|fixa)\b", low):
            return {
                "intent": "DIRECT_LLM",
                "confidence": 0.8,
                "reason": "tooling_or_coding_request",
            }

        # Default: DIRECT_LLM (tuttologo)
        return {
            "intent": "DIRECT_LLM",
            "confidence": 0.6,
            "reason": "default_direct_llm",
        }
