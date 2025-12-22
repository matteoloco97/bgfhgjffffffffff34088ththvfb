#!/usr/bin/env python3
"""
core/llm_intent_classifier.py — Classificatore intent basato su LLM + fallback rule-based

Obiettivo:
- Decidere se una query va a:
  - WEB_SEARCH  → dati live / aggiornati (meteo, prezzi now, risultati, news del giorno)
  - WEB_READ    → c'è una URL esplicita da leggere/riassumere
  - DIRECT_LLM  → basta la conoscenza del modello (storia, concetti, codice, dati storici)

Funzioni esposte:
- LLM_INTENT_ENABLED  (bool da .env)
- get_llm_intent_classifier() → singleton
"""

import os
import re
import json
import time
import logging
from typing import Any, Dict, Optional

import requests

try:
    from core.smart_intent_classifier import SmartIntentClassifier
except Exception:  # retro-compat
    from Core.smart_intent_classifier import SmartIntentClassifier  # type: ignore

log = logging.getLogger(__name__)

# ========================= ENV HELPERS =========================


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name, "1" if default else "0") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)) or str(default)
    m = re.search(r"-?\d+", raw)
    try:
        return int(m.group(0)) if m else int(default)
    except Exception:
        return int(default)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default)) or str(default)
    m = re.search(r"-?\d+(?:\.\d+)?", raw)
    try:
        return float(m.group(0)) if m else float(default)
    except Exception:
        return float(default)


# ========================= CONFIG ENV ==========================

LLM_INTENT_ENABLED: bool = _env_bool("LLM_INTENT_ENABLED", True)
LLM_INTENT_CONFIDENCE_THRESHOLD: float = _env_float(
    "LLM_INTENT_CONFIDENCE_THRESHOLD", 0.75
)
LLM_INTENT_TIMEOUT_S: float = _env_float("LLM_INTENT_TIMEOUT_S", 3.0)
LLM_INTENT_MAX_TOKENS: int = _env_int("LLM_INTENT_MAX_TOKENS", 200)

# LLM endpoint (OpenAI-compatible /v1)
_ENV_LLM_ENDPOINT = os.getenv("LLM_ENDPOINT") or ""
_ENV_TUNNEL_ENDPOINT = os.getenv("TUNNEL_ENDPOINT") or ""


def _normalize_base(u: str) -> str:
    return u.rstrip("/") if u else ""


def _is_chat_url(u: str) -> bool:
    return "/v1/chat/completions" in (u or "")


def _build_chat_url(base_or_chat: str) -> str:
    u = _normalize_base(base_or_chat)
    if _is_chat_url(u):
        return u
    if u.endswith("/v1"):
        return f"{u}/chat/completions"
    return f"{u}/v1/chat/completions"


def _resolve_chat_url() -> Optional[str]:
    """
    Usa prima TUNNEL_ENDPOINT (se esiste), altrimenti LLM_ENDPOINT.
    È lo stesso schema logico usato da quantum_api, ma qui teniamo
    una versione minimale per evitare import circolari.
    """
    candidates = []
    if _ENV_TUNNEL_ENDPOINT:
        candidates.append(_build_chat_url(_ENV_TUNNEL_ENDPOINT))
    if _ENV_LLM_ENDPOINT:
        url = _build_chat_url(_ENV_LLM_ENDPOINT)
        if url not in candidates:
            candidates.append(url)
    return candidates[0] if candidates else None


# ========================= CLASSIFIER ==========================

_ALLOWED_INTENTS = {"WEB_SEARCH", "WEB_READ", "DIRECT_LLM"}


class LLMIntentClassifier:
    """
    Classificatore ibrido:
    - LLM (Qwen, ecc.) con prompt JSON-only
    - Fallback su SmartIntentClassifier (rule-based)
    - Heuristics aggiuntive per casi noti (es. prezzi storici)
    """

    def __init__(self) -> None:
        self.enabled: bool = bool(LLM_INTENT_ENABLED)
        self.conf_threshold: float = float(LLM_INTENT_CONFIDENCE_THRESHOLD)
        self.timeout_s: float = float(LLM_INTENT_TIMEOUT_S)
        self.max_tokens: int = int(LLM_INTENT_MAX_TOKENS)

        self.chat_url: Optional[str] = _resolve_chat_url()
        self.model: str = os.getenv("LLM_MODEL", "qwen2.5-32b-awq")

        self._rule = SmartIntentClassifier()

        # Stats
        self._total = 0
        self._llm_ok = 0
        self._fallback = 0
        self._cache_hits = 0

        # Cache in-memory (query normalizzata → risultato)
        self._cache: Dict[str, Dict[str, Any]] = {}

        log.info(
            "LLMIntentClassifier init: enabled=%s, chat_url=%s, model=%s, thr=%.2f",
            self.enabled,
            self.chat_url,
            self.model,
            self.conf_threshold,
        )

    # ------------- UTILITIES -----------------

    @staticmethod
    def _norm_query(q: str) -> str:
        return (q or "").strip().lower()

    @staticmethod
    def _has_url(q: str) -> bool:
        return "http://" in q or "https://" in q

    @staticmethod
    def _is_historical_price_query(q: str) -> bool:
        """
        Riconosce pattern tipo:
        - "prezzo bitcoin nel 2020"
        - "quotazione oro nel 2018"
        - "valore euro/dollaro nel 2015"
        Idea: se c'è un anno e parole prezzo/quotazione/valore → trattiamo come DIRECT_LLM.
        """
        s = (q or "").lower()
        if not any(k in s for k in ("prezzo", "quotazione", "valore", "price")):
            return False
        # anno 19xx o 20xx
        if re.search(r"\b(19|20)\d{2}\b", s):
            return True
        # pattern generico "storico"/"storicamente"
        if "storico" in s or "storicamente" in s:
            return True
        return False

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict[str, Any]]:
        """
        Prova a estrarre un oggetto JSON da una risposta LLM.
        Gestisce casi tipo:
        - puro JSON
        - ```json { ... } ```
        - testo + { ... } + testo
        """
        if not text:
            return None

        # Prima togliamo fence tipo ```json ... ```
        fenced = re.search(r"```json(.*?)```", text, re.DOTALL | re.IGNORECASE)
        if fenced:
            candidate = fenced.group(1).strip()
            try:
                return json.loads(candidate)
            except Exception:
                pass  # fallback sotto

        # Cerca il primo blocco {...}
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            # Ultimo tentativo: forse è già JSON puro
            try:
                return json.loads(text.strip())
            except Exception:
                return None

        raw = m.group(0).strip()
        try:
            return json.loads(raw)
        except Exception:
            return None

    # ------------- LLM CALL ------------------

    def _build_prompt(self, query: str) -> Dict[str, Any]:
        """
        Costruisce payload per /v1/chat/completions.
        Prompt super rigido: deve produrre SOLO JSON.
        """
        sys_prompt = (
            "Sei un classificatore di intent. "
            "Il tuo compito è decidere se una query richiede il WEB o basta la conoscenza del modello.\n"
            "DEVI rispondere SOLO con un oggetto JSON valido, senza testo fuori dal JSON, "
            "senza commenti, senza ```.\n"
        )

        user_prompt = f"""
Classifica l'intent di questa query:

Query: "{query}"

Intent possibili:
- "WEB_SEARCH": serve il web per dati LIVE o aggiornati (meteo di oggi, prezzi in tempo reale, risultati sportivi, orari, breaking news, valori "adesso", "oggi", "in questo momento").
- "WEB_READ": il messaggio contiene una o più URL (http:// o https://) e l'utente vuole che il contenuto venga letto/riassunto.
- "DIRECT_LLM": basta la tua conoscenza interna (spiegazioni, concetti, storia, programmazione, analisi logica, dati STORICI non live).

Regole speciali IMPORTANTI:
- Se la domanda chiede un PREZZO o una QUOTAZIONE in un ANNO PASSATO (es. "nel 2020", "nel 2018", "storico"):
  → usa SEMPRE "DIRECT_LLM", anche se parla di prezzo/quotazione.
- Se la domanda parla chiaramente di "oggi", "adesso", "in questo momento", "ultime notizie", "meteo", "risultati di oggi":
  → usa "WEB_SEARCH".
- Se nella query è presente un URL (http:// o https://):
  → usa "WEB_READ".

Rispondi SOLO con JSON valido, per esempio:
{{
  "intent": "WEB_SEARCH",
  "confidence": 0.92,
  "reason": "meteo e tempo attuale → servono dati live dal web"
}}

NON AGGIUNGERE altro testo fuori dal JSON.
"""

        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.0,
            "max_tokens": self.max_tokens,
        }

    def _call_llm(self, query: str) -> Optional[Dict[str, Any]]:
        if not self.chat_url:
            return None

        payload = self._build_prompt(query)
        try:
            r = requests.post(
                self.chat_url, json=payload, timeout=self.timeout_s
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            log.warning(f"[LLMIntent] HTTP error: {e}")
            return None

        try:
            content = (
                (data.get("choices") or [{}])[0]
                .get("message", {})
                .get("content", "")
            )
        except Exception as e:
            log.warning(f"[LLMIntent] invalid choices structure: {e}")
            return None

        parsed = self._extract_json(content)
        if not parsed:
            log.warning(f"[LLMIntent] unable to parse JSON from: {content!r}")
        return parsed

    # ------------- PUBLIC API ----------------

    async def classify(
        self, query: str, use_fallback_on_low_confidence: bool = True
    ) -> Dict[str, Any]:
        """
        Ritorna sempre un dict con almeno:
        - intent
        - confidence
        - reason
        - method
        - latency_ms
        """
        t0 = time.perf_counter()
        self._total += 1

        q_norm = self._norm_query(query)
        if not q_norm:
            return {
                "intent": "DIRECT_LLM",
                "confidence": 1.0,
                "reason": "empty_query",
                "method": "rule_based",
                "latency_ms": int((time.perf_counter() - t0) * 1000),
            }

        # Cache
        if q_norm in self._cache:
            self._cache_hits += 1
            cached = dict(self._cache[q_norm])
            cached["method"] = "cache"
            cached["latency_ms"] = int((time.perf_counter() - t0) * 1000)
            return cached

        # Rule-based di base (fallback)
        rb = self._rule.classify(query)
        rb_intent = (rb.get("intent") or "DIRECT_LLM").upper()
        rb_conf = float(rb.get("confidence") or 0.9)
        rb_reason = rb.get("reason") or "rule_based"

        # Heuristica forte: URL → WEB_READ
        if self._has_url(q_norm):
            res = {
                "intent": "WEB_READ",
                "confidence": 0.99,
                "reason": "url_detected",
                "method": "heuristic",
                "latency_ms": int((time.perf_counter() - t0) * 1000),
            }
            self._cache[q_norm] = dict(res)
            return res

        # Heuristica forte: prezzo storico → DIRECT_LLM
        if self._is_historical_price_query(q_norm):
            res = {
                "intent": "DIRECT_LLM",
                "confidence": 0.96,
                "reason": "historical_price_direct_llm",
                "method": "heuristic",
                "latency_ms": int((time.perf_counter() - t0) * 1000),
            }
            self._cache[q_norm] = dict(res)
            return res

        # Se il classificatore LLM è disabilitato → solo rule-based
        if not self.enabled:
            res = {
                "intent": rb_intent,
                "confidence": rb_conf,
                "reason": f"llm_disabled|{rb_reason}",
                "method": "rule_based",
                "latency_ms": int((time.perf_counter() - t0) * 1000),
            }
            self._cache[q_norm] = dict(res)
            return res

        # Chiamata LLM vera e propria
        parsed = self._call_llm(query)

        if not parsed or "intent" not in parsed:
            # Fallback completo
            self._fallback += 1
            res = {
                "intent": rb_intent,
                "confidence": rb_conf,
                "reason": f"fallback:invalid_llm_response|{rb_reason}",
                "method": "rule_based_fallback",
                "latency_ms": int((time.perf_counter() - t0) * 1000),
            }
            self._cache[q_norm] = dict(res)
            return res

        # Normalizza output LLM
        llm_intent = str(parsed.get("intent") or rb_intent).upper().strip()
        llm_conf_raw = parsed.get("confidence")
        try:
            llm_conf = float(llm_conf_raw)
        except Exception:
            llm_conf = rb_conf

        llm_conf = max(0.0, min(1.0, llm_conf))  # clamp 0–1
        llm_reason = (parsed.get("reason") or "").strip() or "llm_intent"

        # Validazione intent
        if llm_intent not in _ALLOWED_INTENTS:
            self._fallback += 1
            res = {
                "intent": rb_intent,
                "confidence": rb_conf,
                "reason": f"fallback:invalid_intent_label|{rb_reason}",
                "method": "rule_based_fallback",
                "latency_ms": int((time.perf_counter() - t0) * 1000),
            }
            self._cache[q_norm] = dict(res)
            return res

        # Se conf bassa → fallback su rule-based
        if use_fallback_on_low_confidence and llm_conf < self.conf_threshold:
            self._fallback += 1
            res = {
                "intent": rb_intent,
                "confidence": rb_conf,
                "reason": f"fallback:low_confidence_llm|{rb_reason}",
                "method": "rule_based_fallback",
                "latency_ms": int((time.perf_counter() - t0) * 1000),
            }
            self._cache[q_norm] = dict(res)
            return res

        # Qui il risultato LLM è accettato
        self._llm_ok += 1
        res = {
            "intent": llm_intent,
            "confidence": llm_conf,
            "reason": llm_reason,
            "method": "llm_intent",
            "latency_ms": int((time.perf_counter() - t0) * 1000),
        }
        self._cache[q_norm] = dict(res)
        return res

    # ------------- STATS / ADMIN ----------------

    def get_stats(self) -> Dict[str, Any]:
        total = max(1, self._total)
        return {
            "enabled": self.enabled,
            "total_classifications": int(self._total),
            "llm_success_rate": float(self._llm_ok) / float(total),
            "fallback_rate": float(self._fallback) / float(total),
            "cache_hit_rate": float(self._cache_hits) / float(total),
            "cache_size": int(len(self._cache)),
            "confidence_threshold": float(self.conf_threshold),
        }

    def clear_cache(self) -> int:
        n = len(self._cache)
        self._cache.clear()
        self._cache_hits = 0
        return n


# ======================= SINGLETON =============================

_CLASSIFIER_SINGLETON: Optional[LLMIntentClassifier] = None


def get_llm_intent_classifier() -> Optional[LLMIntentClassifier]:
    global _CLASSIFIER_SINGLETON
    if _CLASSIFIER_SINGLETON is None:
        try:
            _CLASSIFIER_SINGLETON = LLMIntentClassifier()
        except Exception as e:
            log.error(f"LLMIntentClassifier init failed: {e}")
            _CLASSIFIER_SINGLETON = None
    return _CLASSIFIER_SINGLETON
