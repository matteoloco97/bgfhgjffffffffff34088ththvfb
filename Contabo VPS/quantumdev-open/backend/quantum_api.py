#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

# ============================================================================
# CRITICAL PROXY FIX - Must be at the very top before ANY network usage
# ============================================================================

import os
import sys

# Force disable ALL proxies
for key in [
    "http_proxy",
    "https_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "all_proxy",
    "ALL_PROXY",
    "ftp_proxy",
    "FTP_PROXY",
    "socks_proxy",
    "SOCKS_PROXY",
    "no_proxy",
    "NO_PROXY",
]:
    os.environ.pop(key, None)

# Also patch requests module to never use env proxies
import requests  # noqa: E402

if hasattr(requests.sessions.Session, "__init__"):
    _original_init = requests.sessions.Session.__init__

    def _patched_init(self, *args, **kwargs):
        _original_init(self, *args, **kwargs)
        # never read proxies / certs from env
        self.trust_env = False

    requests.sessions.Session.__init__ = _patched_init

print("✓ [quantum_api] Proxies disabled globally", file=sys.stderr)

# ============================================================================

"""
backend/quantum_api.py — Smart routing + Chroma + Auto-Save + Semantic Cache
"""

import re
import asyncio
import time
import json
import hashlib
import logging
import math
from typing import Optional, List, Dict, Tuple, Any

import redis
from fastapi import FastAPI, Request, Body
from dotenv import load_dotenv
from urllib.parse import urlparse
from pydantic import BaseModel, Field

# (per /memory/debug leggero)
try:
    import chromadb
    from chromadb.config import Settings as _ChromaSettings  # type: ignore
except Exception:  # pragma: no cover
    chromadb = None  # type: ignore
    _ChromaSettings = None  # type: ignore

# ROOT nel sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# === CORE ===
from core.persona_store import get_persona, set_persona, reset_persona
from core.web_tools import fetch_and_extract

# Mini-cache web (import resiliente)
try:
    from core.web_tools import (
        minicache_stats as _webcache_stats,
        minicache_flush as _webcache_flush,
    )
except Exception:  # pragma: no cover

    def _webcache_stats() -> Dict[str, Any]:
        return {"enabled": False, "error": "web minicache not available"}

    def _webcache_flush(url: Optional[str] = None) -> Dict[str, Any]:
        base: Dict[str, Any] = {
            "flushed": 0,
            "notice": "web minicache not available",
        }
        if url:
            base["url"] = url
        return base


from core.chat_engine import reply_with_llm
from core.memory_autosave import autosave

# Web research orchestrator (Claude-style)
try:
    from agents.web_research_agent import WebResearchAgent
except Exception:  # pragma: no cover
    WebResearchAgent = None  # type: ignore

# 🌤️ Weather Agent (Open-Meteo API)
try:
    from agents.weather_open_meteo import (
        get_weather_for_query,
        is_weather_query,
        extract_city_from_query,
    )
    WEATHER_AGENT_AVAILABLE = True
except Exception:  # pragma: no cover
    get_weather_for_query = None  # type: ignore
    is_weather_query = None  # type: ignore
    extract_city_from_query = None  # type: ignore
    WEATHER_AGENT_AVAILABLE = False

# 💰 Price Agent (Crypto/Stocks/Forex)
try:
    from agents.price_agent import (
        get_price_for_query,
        is_price_query,
    )
    PRICE_AGENT_AVAILABLE = True
except Exception:  # pragma: no cover
    get_price_for_query = None  # type: ignore
    is_price_query = None  # type: ignore
    PRICE_AGENT_AVAILABLE = False

# ⚽ Sports Agent (Results/Standings)
try:
    from agents.sports_agent import (
        get_sports_for_query,
        is_sports_query,
    )
    SPORTS_AGENT_AVAILABLE = True
except Exception:  # pragma: no cover
    get_sports_for_query = None  # type: ignore
    is_sports_query = None  # type: ignore
    SPORTS_AGENT_AVAILABLE = False

# 📰 News Agent (Breaking News)
try:
    from agents.news_agent import (
        get_news_for_query,
        is_news_query,
    )
    NEWS_AGENT_AVAILABLE = True
except Exception:  # pragma: no cover
    get_news_for_query = None  # type: ignore
    is_news_query = None  # type: ignore
    NEWS_AGENT_AVAILABLE = False

# 📅 Schedule Agent (Events/Calendar)
try:
    from agents.schedule_agent import (
        get_schedule_for_query,
        is_schedule_query,
    )
    SCHEDULE_AGENT_AVAILABLE = True
except Exception:  # pragma: no cover
    get_schedule_for_query = None  # type: ignore
    is_schedule_query = None  # type: ignore
    SCHEDULE_AGENT_AVAILABLE = False

# 💻 Code Agent (Code Generation/Debug)
try:
    from agents.code_agent import (
        get_code_for_query,
        is_code_query,
    )
    CODE_AGENT_AVAILABLE = True
except Exception:  # pragma: no cover
    get_code_for_query = None  # type: ignore
    is_code_query = None  # type: ignore
    CODE_AGENT_AVAILABLE = False

# 🌐 Unified Web Handler (consistent routing)
try:
    from core.unified_web_handler import (
        handle_web_query,
        handle_web_command,
        get_unified_web_handler,
    )
    UNIFIED_WEB_HANDLER_AVAILABLE = True
except Exception:  # pragma: no cover
    handle_web_query = None  # type: ignore
    handle_web_command = None  # type: ignore
    get_unified_web_handler = None  # type: ignore
    UNIFIED_WEB_HANDLER_AVAILABLE = False

# Smart intent (rule-based)
from core.smart_intent_classifier import SmartIntentClassifier

# Intent feedback (telemetria)
try:
    from core.intent_feedback import IntentFeedbackSystem
except Exception:  # pragma: no cover

    class IntentFeedbackSystem:  # type: ignore[no-redef]
        def record_feedback(self, **kwargs: Any) -> None:
            pass


# LLM Intent Classifier (NUOVO)
try:
    from core.llm_intent_classifier import (
        get_llm_intent_classifier,
        LLM_INTENT_ENABLED,
    )
except Exception:  # pragma: no cover
    get_llm_intent_classifier = None  # type: ignore
    LLM_INTENT_ENABLED = False  # type: ignore

# Validator + Analytics (safe import, opzionali)
try:
    from core.web_validator import SourceValidator
except Exception:  # pragma: no cover
    SourceValidator = None  # type: ignore

try:
    from utils.search_analytics import SearchAnalytics
except Exception:  # pragma: no cover
    SearchAnalytics = None  # type: ignore

_VALIDATOR = SourceValidator() if SourceValidator else None
_ANALYTICS = SearchAnalytics() if SearchAnalytics else None

# ── Semantic Cache: import LAZY (evita import torch al boot) ─────────
_SEMCACHE: Optional[Any] = None
_SCM_IMPORTED = False


def _ensure_semcache_import() -> None:
    """Importa core.semantic_cache solo al primo uso."""
    global _SCM_IMPORTED
    if _SCM_IMPORTED:
        return

    try:
        from core.semantic_cache import (  # type: ignore
            get_semantic_cache as _gsc,
            SemanticCache as _SC,
        )
    except Exception as e:  # pragma: no cover
        logging.getLogger(__name__).warning(
            f"Semantic cache module not available: {e}"
        )

        def _gsc() -> Any:
            raise RuntimeError("semantic cache not available")

        class _SC:  # type: ignore
            @staticmethod
            def fingerprint(system_prompt: str, model_name: str, intent: str) -> str:
                return f"{intent}:{hashlib.sha256(system_prompt.encode('utf-8')).hexdigest()[:8]}"

        globals()["get_semantic_cache"] = _gsc
        globals()["SemanticCache"] = _SC
        _SCM_IMPORTED = True
        return

    globals()["get_semantic_cache"] = _gsc
    globals()["SemanticCache"] = _SC  # type: ignore[name-defined]
    _SCM_IMPORTED = True


# search helpers
from core.source_policy import pick_domains
from core.web_querybuilder import build_query_variants
from core.reranker import Reranker

# Search diversifier (multi-domain)
try:
    from core.search_diversifier import (
        SearchDiversifier,
        get_search_diversifier,
        DIVERSIFIER_MAX_PER_DOMAIN,
        DIVERSIFIER_PRESERVE_TOP_N,
        DIVERSIFIER_MIN_UNIQUE_DOMAINS,
    )
except Exception:  # pragma: no cover
    SearchDiversifier = None  # type: ignore

    def get_search_diversifier() -> Optional[Any]:  # type: ignore
        return None

    # fallback config se modulo non disponibile
    DIVERSIFIER_MAX_PER_DOMAIN = 2
    DIVERSIFIER_PRESERVE_TOP_N = 3
    DIVERSIFIER_MIN_UNIQUE_DOMAINS = 5

# === Token budget util ===
try:
    from core.token_budget import approx_tokens, trim_to_tokens
except Exception:  # pragma: no cover

    def approx_tokens(s: str) -> int:
        return math.ceil(len(s or "") / 4)

    def trim_to_tokens(s: str, max_tokens: int) -> str:
        if not s or max_tokens <= 0:
            return ""
        max_chars = max_tokens * 4
        return s[:max_chars]


# === MEMORY (ChromaDB) ===
from utils.chroma_handler import (
    ensure_collections,
    add_fact,
    add_pref,
    add_bet,
    search_topk,
    debug_dump,
    _substring_fallback,
    FACTS,
    PREFS,
    BETS,
    _col,
    reembed_all,
    search_topk_with_filters,
    add_bets_batch,
    cleanup_old_facts,
    cleanup_old_bets,
    cleanup_old,
    migrate_collection,
    reembed_collection,
)

# 🔥 Nuovi import (sintesi aggressiva + fetch parallelo ottimizzato)
from backend.synthesis_prompt_v2 import build_aggressive_synthesis_prompt
from backend.parallel_fetch_optimizer import parallel_fetch_and_extract

BUILD_SIGNATURE = (
    "smart-intent-2025-11-29+env-safe+lazy-semcache+token-budget+summarize-q+no-error-user+"
    "feedback-toggle+web-search-endpoint+meta-override+zero-web-guard+no-generic-fallback+"
    "parallel-fetch-v1+validator+analytics+guard-relax+warm-harden+explain-guard+"
    "analytics-endpoints+web-minicache-endpoints+web-research-agent+web-summary-direct+"
    "search-diversifier+synthesis-aggressive-v1+llm-intent+jarvis-uncensored-v1+web-deep-mode-v1+"
    "live-agents-v1+price-agent+sports-agent+news-agent+schedule-agent+live-cache-redis"
)

load_dotenv()
app = FastAPI()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ============================= ENV ===================================


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)) or str(default)
    m = re.search(r"-?\d+", raw)
    try:
        return int(m.group(0)) if m else int(default)
    except Exception:
        return int(default)


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default)) or str(default)
    m = re.search(r"-?\d+(?:\.\d+)?", raw)
    try:
        return float(m.group(0)) if m else float(default)
    except Exception:
        return float(default)


def env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name, "1" if default else "0") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


ENV_LLM_ENDPOINT = os.getenv("LLM_ENDPOINT")
ENV_TUNNEL_ENDPOINT = os.getenv("TUNNEL_ENDPOINT")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5-32b-awq")
TEMPERATURE = env_float("LLM_TEMPERATURE", 0.7)
MAX_TOKENS = env_int("LLM_MAX_TOKENS", 512)

# 🔒 Budget/contesto
LLM_MAX_CTX = env_int("LLM_MAX_CTX", 8192)
LLM_OUTPUT_BUDGET_TOK = env_int("LLM_OUTPUT_BUDGET_TOK", MAX_TOKENS)
LLM_SAFETY_MARGIN_TOK = env_int("LLM_SAFETY_MARGIN_TOK", 256)
WEB_SUMMARY_BUDGET_TOK = env_int("WEB_SUMMARY_BUDGET_TOK", 1200)
WEB_EXTRACT_PER_DOC_TOK = env_int("WEB_EXTRACT_PER_DOC_TOK", 700)
WEB_SUMMARIZE_TOP_DEFAULT = env_int("WEB_SUMMARIZE_TOP_DEFAULT", 2)

# 🔍 Deep web search toggle
WEB_SEARCH_DEEP_MODE = env_bool("WEB_SEARCH_DEEP_MODE", False)
WEB_DEEP_MAX_SOURCES = env_int("WEB_DEEP_MAX_SOURCES", 15)

# ⚡️ Parallel fetch env
WEB_FETCH_TIMEOUT_S = env_float("WEB_FETCH_TIMEOUT_S", 3.0)
WEB_FETCH_MAX_INFLIGHT = env_int("WEB_FETCH_MAX_INFLIGHT", 4)
WEB_READ_TIMEOUT_S = env_float("WEB_READ_TIMEOUT_S", 6.0)

# 🚀 Live Agent Cache TTL (in secondi)
LIVE_CACHE_TTL_WEATHER = env_int("LIVE_CACHE_TTL_WEATHER", 1800)  # 30 min
LIVE_CACHE_TTL_PRICE = env_int("LIVE_CACHE_TTL_PRICE", 60)  # 1 min (prezzi cambiano spesso)
LIVE_CACHE_TTL_SPORTS = env_int("LIVE_CACHE_TTL_SPORTS", 300)  # 5 min
LIVE_CACHE_TTL_NEWS = env_int("LIVE_CACHE_TTL_NEWS", 600)  # 10 min
LIVE_CACHE_TTL_SCHEDULE = env_int("LIVE_CACHE_TTL_SCHEDULE", 3600)  # 1 ora

# 🕐 Live Agent Timeout (in secondi)
LIVE_AGENT_TIMEOUT_S = env_float("LIVE_AGENT_TIMEOUT_S", 10.0)

# Feedback back-end (telemetria, NON addestra il modello)
INTENT_FEEDBACK_ENABLED = env_bool("INTENT_FEEDBACK_ENABLED", False)

# Semantic Cache init mode
SEMCACHE_INIT_ON_STARTUP = env_bool("SEMCACHE_INIT_ON_STARTUP", False)

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = env_int("REDIS_PORT", 6379)
REDIS_DB = env_int("REDIS_DB", 0)
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)

USE_RERANKER = env_bool("USE_RERANKER", True)
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-base")
RERANKER_DEVICE = os.getenv("RERANKER_DEVICE", "cpu")

# Diversifier (flag globale)
DIVERSIFIER_ENABLED = env_bool("DIVERSIFIER_ENABLED", True)

# Chroma
MEM_HALF_LIFE_D = env_float("MEM_HALF_LIFE_D", 7.0)
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "/memory/chroma")
EMBED_MODEL_NAME = os.getenv(
    "EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2"
)

# Admin
QUANTUM_SHARED_SECRET = os.getenv("QUANTUM_SHARED_SECRET", "")

# Analytics file path (fallback se _ANALYTICS non disponibile)
SEARCH_ANALYTICS_LOG = os.getenv(
    "SEARCH_ANALYTICS_LOG", "/root/quantumdev-open/logs/search_analytics.jsonl"
)

_SMART_INTENT = SmartIntentClassifier()
_INTENT_FB = IntentFeedbackSystem()

# LLM Intent Classifier (NUOVO)
_LLM_INTENT_CLASSIFIER: Optional[Any] = None

# 🌌 DEFAULT PERSONA + LAYER INCENSURATO ==============================
DEFAULT_SYSTEM_PROMPT = os.getenv(
    "DEFAULT_SYSTEM_PROMPT",
    (
        "Sei Jarvis, l'AI personale generale di Matteo. "
        "Rispondi su QUALSIASI argomento (tecnico, pratico, personale, business, sport, crypto, betting, coding, ecc.) "
        "in modo diretto, concreto e strategico. Non usare toni da manuale scolastico: parla come un consulente "
        "molto competente e senza giri di parole."
    ),
)

INCENSURATO_PROMPT = (
    "Modalità JARVIS INCENSURATO (entro i limiti di legge e sicurezza reale):\n"
    "- Rispondi in modo diretto, concreto e tecnico, senza moralismi inutili.\n"
    "- Evita frasi tipo 'come modello di intelligenza artificiale non posso...' o 'non posso fornire consigli...'.\n"
    "- Se una richiesta è ILLEGALE o pericolosa nella realtà (autolesionismo, violenza, crimini, ecc.), dillo in modo secco "
    "('Non posso guidarti in quella cosa perché è pericolosa/illecita') e poi OFFRI subito alternative legali/sicure o una spiegazione teorica.\n"
    "- Non aggiungere disclaimer lunghi: al massimo 1 frase breve di avviso quando serve davvero.\n"
    "- Se non hai un dato specifico, dillo chiaramente e separa ciò che è generale da ciò che è reale nella sua infrastruttura."
)

# =====================================================================


def get_llm_classifier() -> Optional[Any]:
    global _LLM_INTENT_CLASSIFIER
    if _LLM_INTENT_CLASSIFIER is None and LLM_INTENT_ENABLED and get_llm_intent_classifier:
        try:
            _LLM_INTENT_CLASSIFIER = get_llm_intent_classifier()
            log.info("LLM Intent Classifier initialized")
        except Exception as e:
            log.error(f"LLM Intent Classifier init failed: {e}")
    return _LLM_INTENT_CLASSIFIER


_reranker: Optional[Reranker] = None

# SearchDiversifier singleton (safe init)
try:
    _SEARCH_DIVERSIFIER: Optional[Any] = get_search_diversifier()
except Exception as e:  # pragma: no cover
    log.error(f"SearchDiversifier init failed: {e}")
    _SEARCH_DIVERSIFIER = None

# WebResearchAgent singleton
_WEB_RESEARCH_AGENT: Optional[Any] = None


def get_web_research_agent() -> Optional[Any]:
    global _WEB_RESEARCH_AGENT
    if WebResearchAgent is None:
        return None
    if _WEB_RESEARCH_AGENT is None:
        try:
            _WEB_RESEARCH_AGENT = WebResearchAgent()
            log.info("WebResearchAgent initialized.")
        except Exception as e:
            log.error(f"WebResearchAgent init failed: {e}")
            _WEB_RESEARCH_AGENT = None
    return _WEB_RESEARCH_AGENT


# =========================== Helpers =================================
def get_reranker() -> Optional[Reranker]:
    global _reranker
    if not USE_RERANKER:
        return None
    if _reranker is None:
        try:
            log.info(f"Init Reranker: {RERANKER_MODEL} on {RERANKER_DEVICE}")
            _reranker = Reranker(model=RERANKER_MODEL, device=RERANKER_DEVICE)
        except Exception as e:
            log.error(f"Reranker init failed: {e}")
            return None
    return _reranker


def _normalize_base(u: str) -> str:
    return u.rstrip("/")


def _is_chat_url(u: str) -> bool:
    return "/v1/chat/completions" in u


def _build_chat_url(base_or_chat: str) -> str:
    u = _normalize_base(base_or_chat)
    if _is_chat_url(u):
        return u
    if u.endswith("/v1"):
        return f"{u}/chat/completions"
    return f"{u}/v1/chat/completions"


def _get_redis_str(k: str) -> Optional[str]:
    v = redis_client.get(k)
    return v.decode() if v else None


def get_endpoints() -> List[str]:
    tunnel = _get_redis_str("gpu_tunnel_endpoint") or ENV_TUNNEL_ENDPOINT
    direct = _get_redis_str("gpu_active_endpoint") or ENV_LLM_ENDPOINT
    out: List[str] = []
    if tunnel:
        out.append(_build_chat_url(tunnel))
    if direct:
        u = _build_chat_url(direct)
        if u not in out:
            out.append(u)
    return out


def hash_prompt(
    prompt: str,
    system: str,
    temperature: float,
    max_tokens: int,
    model: str,
) -> str:
    h = hashlib.sha256()
    for piece in (
        prompt.strip().lower(),
        system.strip().lower(),
        str(temperature),
        str(max_tokens),
        model,
    ):
        h.update(piece.encode("utf-8"))
    return h.hexdigest()


def _wrap(text: str, model: str) -> Dict[str, Any]:
    now = int(time.time())
    return {
        "id": f"chatcmpl-router-{now}",
        "object": "chat.completion",
        "created": now,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }


def _run_direct(
    payload: Dict[str, Any],
    force: Optional[str],
) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
    endpoints = get_endpoints()
    if force == "tunnel":
        endpoints = [e for e in endpoints if "trycloudflare.com" in e] + [
            e for e in endpoints if "trycloudflare.com" not in e
        ]
    elif force == "direct":
        endpoints = [e for e in endpoints if "trycloudflare.com" not in e] + [
            e for e in endpoints if "trycloudflare.com" in e
        ]
    last: Optional[str] = None
    for url in endpoints:
        try:
            r = requests.post(url, json=payload, timeout=30)
            r.raise_for_status()
            return r.json(), url, None
        except Exception as e:
            last = str(e)
            continue
    return None, None, last


def _domain(u: str) -> str:
    try:
        h = urlparse(u).hostname or ""
        parts = h.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else h
    except Exception:
        return ""


def _boost(results: List[Dict[str, Any]], prefer: List[str]) -> List[Dict[str, Any]]:
    pref = set(prefer or [])
    scored: List[Dict[str, Any]] = []
    for i, r in enumerate(results):
        base = 1.0 / (i + 1.0)
        boost = 2.0 if _domain(r.get("url", "")) in pref else 1.0
        rr = dict(r)
        rr["_score"] = base * boost
        scored.append(rr)
    scored.sort(key=lambda x: x["_score"], reverse=True)
    return scored


def _postboost_ranked(
    ranked: List[Dict[str, Any]],
    prefer: List[str],
) -> List[Dict[str, Any]]:
    pref = set(prefer or [])
    for r in ranked:
        dom = _domain(r.get("url", ""))
        if dom in pref:
            r["rerank_score"] = (r.get("rerank_score") or 0.0) + 0.20
    return sorted(
        ranked,
        key=lambda x: (
            (x.get("rerank_score") or 0.0),
            (x.get("_score") or 0.0),
        ),
        reverse=True,
    )


# 🔧 Fallback sicuro: solo per meteo/prezzi, se proprio
def _safe_fallback_links(q: str) -> List[Dict[str, str]]:
    s = (q or "").lower()
    out: List[Dict[str, str]] = []

    def add(u: str, t: str) -> None:
        out.append({"url": u, "title": t})

    if "meteo" in s or "che tempo" in s or "weather" in s:
        add("https://www.meteoam.it/it/roma", "Meteo Aeronautica Militare – Roma")
        add("https://www.ilmeteo.it/meteo/Roma", "ILMETEO – Roma")
        add("https://www.3bmeteo.com/meteo/roma", "3B Meteo – Roma")

    if any(
        k in s
        for k in [
            "prezzo",
            "quotazione",
            "quanto vale",
            "btc",
            "bitcoin",
            "eth",
            "ethereum",
            "eurusd",
            "eur/usd",
            "borsa",
            "azioni",
            "indice",
            "cambio",
        ]
    ):
        add(
            "https://coinmarketcap.com/currencies/bitcoin/",
            "Bitcoin (BTC) – CoinMarketCap",
        )
        add("https://www.coindesk.com/price/bitcoin/", "Bitcoin Price – CoinDesk")
        add("https://www.binance.com/en/trade/BTC_USDT", "BTC/USDT – Binance")
        add(
            "https://www.investing.com/crypto/bitcoin/btc-usd",
            "BTC/USD – Investing.com",
        )

    return out[:8]


def _cheap_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    A = set(a.lower().split())
    B = set(b.lower().split())
    if not A or not B:
        return 0.0
    inter = len(A & B)
    uni = len(A | B)
    return round(inter / uni, 4)


# ===================== LIVE AGENT CACHE =====================

async def cached_live_call(
    cache_key: str,
    ttl_seconds: int,
    coro,
) -> Optional[str]:
    """
    Wrapper generico per cache live agent con Redis.
    
    Args:
        cache_key: Chiave Redis (es: "live:weather:roma")
        ttl_seconds: TTL in secondi
        coro: Coroutine da eseguire se cache miss
    
    Returns:
        Risultato dalla cache o dalla coroutine
    """
    try:
        # Check cache
        cached = redis_client.get(cache_key)
        if cached:
            log.info(f"Live cache HIT: {cache_key}")
            return cached.decode("utf-8")
    except Exception as e:
        log.warning(f"Redis cache get error: {e}")
    
    # Cache miss → esegui coroutine
    try:
        result = await asyncio.wait_for(coro, timeout=LIVE_AGENT_TIMEOUT_S)
        
        if result:
            try:
                redis_client.setex(cache_key, ttl_seconds, result)
                log.info(f"Live cache SET: {cache_key} (TTL={ttl_seconds}s)")
            except Exception as e:
                log.warning(f"Redis cache set error: {e}")
        
        return result
    
    except asyncio.TimeoutError:
        log.warning(f"Live agent timeout for {cache_key}")
        return None
    except Exception as e:
        log.error(f"Live agent error for {cache_key}: {e}")
        return None


def _get_live_cache_key(agent_type: str, query: str) -> str:
    """Genera chiave cache per live agent."""
    q_hash = hashlib.sha256(query.lower().encode("utf-8")).hexdigest()[:12]
    return f"live:{agent_type}:{q_hash}"


# 🔎 Riconoscitore grezzo di query su hardware/setup personale
def _looks_like_personal_fact_query(q: str) -> bool:
    s = (q or "").lower()
    personal_markers = ["mia ", "mio ", "mie ", "miei ", "nostra ", "nostro "]
    tech_markers = [
        "jarvis",
        "quantumdev",
        "quantumdev-open",
        "quantum api",
        "vps",
        "server",
        "hardware",
        "cpu",
        "gpu",
        "vram",
        "llm",
        "modello",
        "ai personale",
    ]
    return any(p in s for p in personal_markers) and any(
        t in s for t in tech_markers
    )


def _semcache_dualwrite(
    prompt: str,
    system_prompt: str,
    model_name: str,
    used_intent: str,
    response_obj: Dict[str, Any],
) -> None:
    global _SEMCACHE
    try:
        if not _SEMCACHE:
            return
        _ensure_semcache_import()
        now_ts = int(time.time())
        qh = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]
        base_meta = {
            "intent": used_intent,
            "model": model_name,
            "ts": now_ts,
            "q": prompt,
            "q_hash": qh,
        }
        ctx_fp_intent = SemanticCache.fingerprint(  # type: ignore[name-defined]
            system_prompt,
            model_name,
            used_intent,
        )
        _SEMCACHE.set(prompt, response_obj, ctx_fp_intent, meta=base_meta)
        ctx_fp_auto = SemanticCache.fingerprint(  # type: ignore[name-defined]
            system_prompt,
            model_name,
            "AUTO",
        )
        _SEMCACHE.set(
            prompt,
            response_obj,
            ctx_fp_auto,
            meta={**base_meta, "dual": True},
        )
    except Exception as e:  # pragma: no cover
        log.warning(f"Semantic cache set error (dualwrite): {e}")


# --------- Meta/capability queries → mai WEB --------------------------
_META_PATTERNS = [
    r"\b(chi\s+sei|che\s+cosa\s+puoi\s+fare|cosa\s+puoi\s+fare|come\s+funzioni)\b",
    r"\b(puoi|riesci)\s+(navigare|usare|accedere)\s+(a|su)\s+internet\b",
    r"\b(collegarti|connetterti)\s+(a|su)\s+internet\b",
    r"\b(hai|possiedi)\s+(accesso|connessione)\s+a\s+internet\b",
    r"\b(quali\s+sono\s+le\s+tu(e|oi)\s+capacit[aà]|limitazioni)\b",
]

_CAPABILITIES_BRIEF = (
    "Posso accedere al web quando serve per dati aggiornati (meteo, prezzi, notizie, risultati sportivi, ecc.) "
    "tramite il comando /web o automaticamente per query live. "
    "Ho memoria a lungo termine via ChromaDB (facts, preferenze, betting history) e cache Redis. "
    "Uso il web in modo selettivo: solo quando necessario, non per ogni domanda. "
    "Non accedo a file o dispositivi dell'utente."
)



def _is_meta_capability_query(q: str) -> bool:
    s = (q or "").lower()
    return any(re.search(p, s) for p in _META_PATTERNS)


# ---- Explain-guard: forzare DIRECT_LLM su "spiega/che cos'è/what is" ----
_EXPLAIN_PATTERNS = [
    r"\bspiega(mi|re)?\b",
    r"\bche\s+cos[’']?è\b",
    r"\bcos[’']?è\b",
    r"\bwhat\s+is\b",
    r"\bexplain\b",
]


def _is_explain_query(q: str) -> bool:
    s = (q or "").lower()
    return any(re.search(p, s) for p in _EXPLAIN_PATTERNS)


# --------- ZERO-WEB GUARD (smalltalk/very-short) ---------------------
_SMALLTALK_RE = re.compile(
    r"""(?ix)^\s*(         ciao|hey|hi|hello|salve|buongiorno|buonasera|buonanotte|
        ci\ssei??|sei\sonline??|
        come\s+va??|ok+|perfetto|grazie|thanks
    )\b"""
)


def _is_quick_live_query(q: str) -> bool:
    s = (q or "").lower()
    return any(
        k in s
        for k in [
            "meteo",
            "che tempo",
            "weather",
            "prezzo",
            "quotazione",
            "risultati",
            "classifica",
            "orari",
        ]
    )


# ✅ Guard rilassata + esclusione delle live query
def _is_smalltalk_query(q: str) -> bool:
    s = (q or "").strip().lower()

    # 1️⃣ Se è una live query (meteo, prezzo, risultati...), NON è smalltalk
    if _is_quick_live_query(s):
        return False

    # 2️⃣ Saluti & frasette tipo "ok", "grazie"
    if _SMALLTALK_RE.search(s):
        return True

    tokens = s.split()

    # 3️⃣ Un solo token generico → smalltalk, tranne se contiene numeri (tipo "2025")
    if len(tokens) <= 1:
        if any(ch.isdigit() for ch in s):
            return False
        return True

    # 4️⃣ Frasi con 2+ parole → in generale NON smalltalk
    return False


# ===================== Web search pipeline ===========================
async def _web_search_pipeline(
    q: str,
    src: str,
    sid: str,
    k: int = 6,
    nsum: int = 2,
) -> Dict[str, Any]:
    t_start = time.perf_counter()

    # 🔒 Guard: non cercare MAI su smalltalk
    if _is_smalltalk_query(q):
        return {
            "query": q,
            "policy_used": {},
            "results": [],
            "summary": "",
            "note": "non_web_query",
            "reranker_used": False,
            "validation": None,
            "diversity": None,
            "stats": {
                "raw_results": 0,
                "dedup_results": 0,
                "returned": 0,
                "fetch_attempted": 0,
                "fetch_ok": 0,
                "fetch_timeouts": 0,
                "fetch_errors": 0,
                "fetch_duration_ms": 0,
                "early_exit": False,
                "validation_confidence": None,
            },
        }

    pol = pick_domains(q)
    variants = build_query_variants(q, pol)

    try:
        from core.web_search import search as web_search_core
    except Exception as e:
        return {
            "error": "Backend web_search non configurato (core/web_search.py).",
            "_exception": str(e),
        }

    raw: List[Dict[str, Any]] = []
    for v in variants:
        try:
            raw.extend(web_search_core(v, num=6))
        except Exception:
            pass

    seen: set[str] = set()
    dedup: List[Dict[str, Any]] = []
    for r in raw:
        u = r.get("url")
        if not u or u in seen:
            continue
        dedup.append(
            {
                "url": u,
                "title": r.get("title", ""),
                "snippet": r.get("snippet", r.get("title", "")),
            }
        )
        seen.add(u)

    if not dedup:
        return {
            "query": q,
            "policy_used": pol,
            "results": [],
            "summary": "",
            "validation": None,
            "diversity": None,
            "note": "SERP vuota",
            "reranker_used": False,
            "stats": {
                "raw_results": len(raw),
                "dedup_results": 0,
                "returned": 0,
                "fetch_attempted": 0,
                "fetch_ok": 0,
                "fetch_timeouts": 0,
                "fetch_errors": 0,
                "fetch_duration_ms": 0,
                "early_exit": False,
                "validation_confidence": None,
            },
        }

    # === RERANKING ===
    used = False
    ranked: List[Dict[str, Any]]

    rr = get_reranker()
    if rr and len(dedup) > 1:
        try:
            ranked = rr.rerank(q, dedup, top_k=min(k * 2, len(dedup)))
            used = True
            log.info(f"Reranker: {len(dedup)} → top {len(ranked)}")
        except Exception as e:
            log.warning(f"Reranker failed: {e}")
            ranked = _boost(dedup, pol.get("prefer", []))
    else:
        ranked = _boost(dedup, pol.get("prefer", []))

    # Post-boost ranking
    ranked = _postboost_ranked(ranked, pol.get("prefer", []))
    topk: List[Dict[str, Any]] = ranked[: max(1, k)]

    # === ⭐ DIVERSIFICATION (NUOVO) ⭐
    diversity_before: Optional[Dict[str, Any]] = None
    diversity_after: Optional[Dict[str, Any]] = None

    if _SEARCH_DIVERSIFIER and DIVERSIFIER_ENABLED and len(topk) > 3:
        try:
            diversity_before = _SEARCH_DIVERSIFIER.analyze_diversity(topk)
            topk_diversified = _SEARCH_DIVERSIFIER.diversify(topk)
            diversity_after = _SEARCH_DIVERSIFIER.analyze_diversity(topk_diversified)

            log.info(
                "Diversity: %s → %s domains, score %.2f → %.2f",
                diversity_before["unique_domains"],
                diversity_after["unique_domains"],
                diversity_before["diversity_score"],
                diversity_after["diversity_score"],
            )

            topk = topk_diversified
        except Exception as e:  # pragma: no cover
            log.warning(f"Diversification failed: {e}")
            # continua con topk non diversificato

    # === ⚡ PARALLEL FETCHING (con helper ottimizzato) ⚡
    t_fetch_start = time.perf_counter()

    extracts: List[Dict[str, Any]] = []
    attempted = 0
    timeouts = 0
    errors = 0
    done_early = False
    fetch_duration_ms = 0

    if topk and nsum > 0:
        # ⚡ PARALLEL FETCH
        extracts, fetch_stats = await parallel_fetch_and_extract(
            results=topk[:nsum],
            max_concurrent=WEB_FETCH_MAX_INFLIGHT,
            timeout_per_url=WEB_FETCH_TIMEOUT_S,
            min_successful=2,
        )

        attempted = int(fetch_stats.get("attempted", 0))
        ok_count = len(extracts)
        timeouts = int(fetch_stats.get("timeouts", 0))
        errors = int(fetch_stats.get("errors", 0))
        fetch_duration_ms = int(fetch_stats.get("duration_ms", 0))
        done_early = bool(fetch_stats.get("early_exit", False))
    else:
        fetch_duration_ms = int((time.perf_counter() - t_fetch_start) * 1000)

    log.info(
        f"Parallel fetch: {len(extracts)}/{attempted} in {fetch_duration_ms}ms "
        f"(timeouts={timeouts}, errors={errors})"
    )

    # Validazione multi-fonte (consensus) — opzionale
    validation: Optional[Dict[str, Any]] = None
    if _VALIDATOR and extracts:
        try:
            validation = _VALIDATOR.validate_consensus(  # type: ignore[attr-defined]
                q,
                extracts[: max(0, nsum)],
            )
        except Exception:
            validation = None

    summary = ""
    note: Optional[str] = "live_query" if _is_quick_live_query(q) else None

    if extracts:
        persona = await get_persona(src, sid)

        # Documenti usati per la sintesi (limite nsum)
        synth_docs = extracts[: max(0, nsum)]

        # Contesto testuale per validator e retry
        ctx_parts: List[str] = []
        for e in synth_docs:
            if not e.get("text"):
                continue
            ctx_parts.append(
                f"### {e.get('title')}\nURL: {e.get('url')}\n\n{e.get('text')}"
            )
        ctx = "\n\n".join(ctx_parts)
        ctx = trim_to_tokens(ctx, WEB_SUMMARY_BUDGET_TOK)

        # ⚡ AGGRESSIVE SYNTHESIS (nuovo)
        prompt = build_aggressive_synthesis_prompt(
            q,
            [
                {
                    "idx": i + 1,
                    "title": e.get("title", ""),
                    "url": e.get("url", ""),
                    "text": e.get("text", ""),
                }
                for i, e in enumerate(synth_docs)
                if e.get("text")
            ],
        )

        try:
            summary = await reply_with_llm(prompt, persona)
        except Exception:
            summary = ""
            note = note or "llm_summary_failed"

        # === ⭐ VALIDATION + RETRY (NUOVO) ⭐
        if summary:
            try:
                from core.synthesis_validator import get_synthesis_validator

                validator = get_synthesis_validator()
                syn_validation = validator.validate(summary)

                if syn_validation["score"] < 0.5 and (
                    time.perf_counter() - t_start
                ) < 8.0:
                    log.warning(
                        f"Low quality synthesis (score={syn_validation['score']:.2f}), retrying..."
                    )

                    retry_prompt = (
                        "La risposta precedente era EVASIVA e NON ACCETTABILE.\n"
                        f"Issues: {', '.join(syn_validation['issues'])}\n"
                        f"Bad phrases: {validator.extract_bad_phrases(summary)}\n"
                        "\n"
                        "RIPROVA seguendo TUTTE le regole precedenti.\n"
                        "Non dire MAI 'non ho abbastanza info' o 'consulta le fonti'.\n"
                        "Fornisci SEMPRE almeno 3 facts concreti dagli estratti.\n"
                        "\n"
                        f"ESTRATTI:\n{ctx}\n\n"
                        f"DOMANDA:\n{q}\n\n"
                        "RISPONDI MEGLIO:"
                    )

                    try:
                        summary_retry = await reply_with_llm(
                            retry_prompt, persona
                        )
                        if summary_retry:
                            syn_validation_retry = validator.validate(
                                summary_retry
                            )
                            if (
                                syn_validation_retry["score"]
                                > syn_validation["score"]
                            ):
                                log.info(
                                    "Retry improved quality: "
                                    f"{syn_validation['score']:.2f} → {syn_validation_retry['score']:.2f}"
                                )
                                summary = summary_retry
                                syn_validation = syn_validation_retry
                    except Exception as e:
                        log.warning(f"Retry failed: {e}")

                log.info(
                    "Final synthesis quality: score=%.2f, facts=%d, valid=%s",
                    syn_validation["score"],
                    syn_validation["facts_count"],
                    syn_validation["valid"],
                )
            except Exception as e:
                log.warning(f"Synthesis validation error: {e}")
    else:
        note = note or "no_extracted_content"

    # autosave sintesi (se presente)
    try:
        if summary:
            asv = autosave(summary, source="web_search")
            if any([asv.get("facts"), asv.get("prefs"), asv.get("bet")]):
                log.info(f"[autosave:web_search] {asv}")
    except Exception as e:  # pragma: no cover
        log.warning(f"AutoSave web_search failed: {e}")

    stats = {
        "raw_results": len(raw),
        "dedup_results": len(dedup),
        "returned": len(topk),
        "fetch_attempted": attempted,
        "fetch_ok": len([e for e in extracts if e.get("text")]),
        "fetch_timeouts": timeouts,
        "fetch_errors": errors,
        "fetch_duration_ms": fetch_duration_ms,
        "early_exit": done_early,
        "validation_confidence": (validation or {}).get("confidence")
        if validation
        else None,
    }

    if _ANALYTICS:
        try:
            _ANALYTICS.track_search(  # type: ignore[attr-defined]
                query=q,
                results=topk,
                user_interaction={
                    "latency_ms": int((time.perf_counter() - t_start) * 1000),
                    "reranker_used": used,
                    "cached": False,
                },
            )
        except Exception:
            pass

    diversity_block = (
        {
            "before": diversity_before,
            "after": diversity_after,
            "enabled": DIVERSIFIER_ENABLED and _SEARCH_DIVERSIFIER is not None,
        }
        if diversity_after
        else None
    )

    return {
        "query": q,
        "policy_used": pol,
        "results": [
            {
                "url": r["url"],
                "title": r["title"],
                "rerank_score": r.get("rerank_score"),
                "_score": r.get("_score"),
            }
            for r in topk
        ],
        "summary": summary,
        "validation": validation,
        "reranker_used": used,
        "diversity": diversity_block,
        "note": note,
        "stats": stats,
    }


# ===================== DEEP Web search pipeline (nuovo) ==============
async def _web_search_pipeline_deep(
    q: str,
    src: str,
    sid: str,
    k: int = 15,
    nsum: int = 10,
) -> Dict[str, Any]:
    """
    Enhanced pipeline per ricerche DEEP con molte fonti.

    Usa un agente avanzato che fa multi-step research e restituisce
    answer + sorgenti, mantenendo un formato compatibile con /web/search.
    """
    try:
        from agents.advanced_web_research import AdvancedWebResearch
    except Exception as e:
        log.error(f"AdvancedWebResearch import failed, fallback standard: {e}")
        # Fallback: usa pipeline standard
        ws = await _web_search_pipeline(
            q=q,
            src=src,
            sid=sid,
            k=min(WEB_DEEP_MAX_SOURCES, k),
            nsum=min(WEB_DEEP_MAX_SOURCES, nsum),
        )
        ws["note"] = (ws.get("note") or "") + "|deep_fallback_standard"
        return ws

    persona = await get_persona(src, sid)

    researcher = AdvancedWebResearch(
        max_steps=4,
        min_sources=min(10, WEB_DEEP_MAX_SOURCES),
        quality_threshold=0.75,
    )

    result = await researcher.research_deep(q, persona)

    # Format per compatibilità con API esistente
    return {
        "summary": result["answer"],
        "results": result["sources"],
        "note": f"deep_research_{result['total_sources']}_sources",
        "stats": {
            "total_sources": result["total_sources"],
            "quality_score": result["quality_final"],
            "steps": len(result["steps"]),
        },
        "research_steps": result["steps"],
    }


# ========================= API Endpoints =============================
@app.on_event("startup")
def _init_memory() -> None:
    global _SEMCACHE
    try:
        ensure_collections()
        log.info("ChromaDB collections ensured.")
    except Exception as e:
        log.error(f"Chroma ensure_collections failed: {e}")

    # Semantic Cache: opzionale al boot (lazy per default)
    if SEMCACHE_INIT_ON_STARTUP:
        try:
            _ensure_semcache_import()
            _SEMCACHE = get_semantic_cache()  # type: ignore[name-defined]
            log.info(f"Semantic cache ready: {json.dumps(_SEMCACHE.stats())}")
        except Exception as e:
            log.error(f"Semantic cache init failed: {e}")


@app.get("/healthz")
def healthz() -> Dict[str, Any]:
    rer_status = "disabled"
    if USE_RERANKER:
        rer_status = "ready" if get_reranker() else "failed"

    cache_info: Dict[str, Any] = {"enabled": False}
    try:
        if _SEMCACHE:
            cache_info = _SEMCACHE.stats()
            if hasattr(_SEMCACHE, "stats_all"):
                all_stats = _SEMCACHE.stats_all()  # type: ignore[attr-defined]
                total = (all_stats or {}).get("total", {})
                cache_info["total_size_items"] = total.get("size_items")
    except Exception:
        pass

    # 🚀 Live Agents status
    live_agents = {
        "weather": WEATHER_AGENT_AVAILABLE,
        "price": PRICE_AGENT_AVAILABLE,
        "sports": SPORTS_AGENT_AVAILABLE,
        "news": NEWS_AGENT_AVAILABLE,
        "schedule": SCHEDULE_AGENT_AVAILABLE,
        "code": CODE_AGENT_AVAILABLE,
        "unified_web": UNIFIED_WEB_HANDLER_AVAILABLE,
    }

    return {
        "ok": True,
        "model": LLM_MODEL,
        "endpoints_to_try": get_endpoints(),
        "reranker": {
            "enabled": USE_RERANKER,
            "status": rer_status,
            "model": RERANKER_MODEL if USE_RERANKER else None,
        },
        "redis": {
            "gpu_tunnel_endpoint": _get_redis_str("gpu_tunnel_endpoint"),
            "gpu_active_endpoint": _get_redis_str("gpu_active_endpoint"),
        },
        "semantic_cache": cache_info,
        "live_agents": live_agents,
        "live_cache_ttl": {
            "weather": LIVE_CACHE_TTL_WEATHER,
            "price": LIVE_CACHE_TTL_PRICE,
            "sports": LIVE_CACHE_TTL_SPORTS,
            "news": LIVE_CACHE_TTL_NEWS,
            "schedule": LIVE_CACHE_TTL_SCHEDULE,
        },
        "smart_intent": True,
        "feedback_enabled": INTENT_FEEDBACK_ENABLED,
        "router_build": BUILD_SIGNATURE,
    }


# --------- Cache stats (ns / all) + flush ---------
@app.get("/stats/cache")
def cache_stats(ns: Optional[str] = None, all: bool = False) -> Dict[str, Any]:  # noqa: A002
    try:
        if not _SEMCACHE:
            return {"enabled": False}
        if all and hasattr(_SEMCACHE, "stats_all"):
            return _SEMCACHE.stats_all()  # type: ignore[attr-defined]
        if ns and hasattr(_SEMCACHE, "stats_ns"):
            return _SEMCACHE.stats_ns(ns)  # type: ignore[attr-defined]
        return _SEMCACHE.stats()
    except Exception as e:
        return {"enabled": False, "error": str(e)}


class FlushReq(BaseModel):
    ns: Optional[str] = None


@app.post("/cache/flush")
def cache_flush(req: FlushReq) -> Dict[str, Any]:
    global _SEMCACHE
    try:
        if _SEMCACHE is None:
            try:
                _ensure_semcache_import()
                _SEMCACHE = get_semantic_cache()  # type: ignore[name-defined]
            except Exception:
                pass
        if not _SEMCACHE:
            return {"ok": False, "error": "semantic cache not initialized"}
        n = 0
        if hasattr(_SEMCACHE, "flush"):
            n = _SEMCACHE.flush(ns=req.ns)  # type: ignore[attr-defined]
        elif hasattr(_SEMCACHE, "clear"):
            n = _SEMCACHE.clear(ns=req.ns)  # type: ignore[attr-defined]
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "flushed_items": int(n or 0), "namespace": (req.ns or "ALL")}


# --------- Endpoints admin (list/update) ---------
@app.get("/endpoints")
def endpoints_list() -> Dict[str, Any]:
    return {
        "active_env": ENV_LLM_ENDPOINT,
        "tunnel_env": ENV_TUNNEL_ENDPOINT,
        "active_redis": _get_redis_str("gpu_active_endpoint"),
        "tunnel_redis": _get_redis_str("gpu_tunnel_endpoint"),
        "resolved": get_endpoints(),
    }


class EndpointsUpdateReq(BaseModel):
    active: Optional[str] = None
    tunnel: Optional[str] = None
    secret: Optional[str] = None


@app.post("/endpoints/update")
def endpoints_update(req: EndpointsUpdateReq, request: Request) -> Dict[str, Any]:
    provided = (
        req.secret
        or request.headers.get("x-quantum-secret")
        or ""
    )
    if QUANTUM_SHARED_SECRET and provided != QUANTUM_SHARED_SECRET:
        return {"ok": False, "error": "unauthorized"}

    changed: Dict[str, Any] = {}
    try:
        if req.active:
            redis_client.set("gpu_active_endpoint", req.active)
            changed["active"] = req.active
        if req.tunnel:
            redis_client.set("gpu_tunnel_endpoint", req.tunnel)
            changed["tunnel"] = req.tunnel
    except Exception as e:
        return {"ok": False, "error": str(e)}

    return {"ok": True, "changed": changed, "resolved": get_endpoints()}


# --------- Cache warm -------------------------------------------------
class WarmReq(BaseModel):
    prompts: List[str]
    system: Optional[str] = None
    model: Optional[str] = None


@app.post("/cache/warm")
async def cache_warm(req: WarmReq) -> Dict[str, Any]:
    try:
        sys_prompt = (
            req.system
            or (await get_persona("global", "default"))
            or DEFAULT_SYSTEM_PROMPT
        )
        # layer incensurato anche per warm
        sys_prompt = (sys_prompt.strip() + "\n\n" + INCENSURATO_PROMPT).strip()

        model = (req.model or LLM_MODEL).strip()

        global _SEMCACHE
        _ensure_semcache_import()
        if _SEMCACHE is None:
            _SEMCACHE = get_semantic_cache()  # type: ignore[name-defined]

        done = 0
        errors: List[str] = []

        for p in (req.prompts or []):
            p = (p or "").strip()
            if not p:
                continue
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": p},
                ],
                "temperature": TEMPERATURE,
                "max_tokens": 256,
            }
            result, _, last_err = _run_direct(payload, force=None)
            if result:
                try:
                    _semcache_dualwrite(
                        p,
                        sys_prompt,
                        model,
                        "DIRECT_LLM",
                        result,
                    )
                    done += 1
                except Exception as e:
                    errors.append(f"semcache_write:{str(e)}")
            else:
                errors.append(f"llm_call:{last_err or 'unknown'}")

        return {"ok": True, "warmed": done, "errors": errors}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ------------------------- Generate -------------------------
def _fb_record(**kw: Any) -> None:
    if INTENT_FEEDBACK_ENABLED:
        try:
            _INTENT_FB.record_feedback(**kw)
        except Exception:
            pass


@app.post("/generate")
async def generate(
    request: Request,
    force: Optional[str] = None,
) -> Dict[str, Any]:
    global _SEMCACHE
    try:
        _ensure_semcache_import()
        if _SEMCACHE is None:
            _SEMCACHE = get_semantic_cache()  # type: ignore[name-defined]
    except Exception:
        pass

    data = await request.json()
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return {"error": "Prompt mancante."}

    if force not in (None, "tunnel", "direct"):
        return {"error": "Parametro 'force' non valido. Usa 'tunnel' o 'direct'."}

    try:
        system_prompt = (
            data.get("system")
            or await get_persona("global", "default")
            or DEFAULT_SYSTEM_PROMPT
        ).strip()
    except Exception:
        system_prompt = DEFAULT_SYSTEM_PROMPT

    # 🔥 Modalità Jarvis incensurato su generate
    system_prompt = (system_prompt + "\n\n" + INCENSURATO_PROMPT).strip()

    temperature = (
        env_float("LLM_TEMPERATURE", TEMPERATURE)
        if "temperature" not in data
        else float(data.get("temperature"))
    )
    max_tokens = (
        env_int("LLM_MAX_TOKENS", MAX_TOKENS)
        if "max_tokens" not in data
        else int(data.get("max_tokens"))
    )
    model_name = (data.get("model") or LLM_MODEL).strip()

    # Auto-save input
    try:
        asv_in = autosave(prompt, source="generate_input")
        if any([asv_in.get("facts"), asv_in.get("prefs"), asv_in.get("bet")]):
            log.info(f"[autosave:generate_input] {asv_in}")
    except Exception as e:
        log.warning(f"AutoSave generate_input failed: {e}")

    # === Semantic cache (pre-routing) ===
    try:
        if _SEMCACHE:
            _ensure_semcache_import()
            ctx_fp_auto = SemanticCache.fingerprint(  # type: ignore[name-defined]
                system_prompt,
                model_name,
                "AUTO",
            )
            hit = _SEMCACHE.get(prompt, ctx_fp_auto)
            if hit:
                sim = hit.get("similarity")
                if sim is None:
                    meta_q = ((hit.get("meta") or {}).get("q") or "")
                    sim = _cheap_similarity(prompt, meta_q)
                out = {
                    "ok": True,
                    "intent": "CACHE_SEMANTIC",
                    "confidence": 1.0,
                    "reason": "semantic_hit_pre_route",
                    "router_build": BUILD_SIGNATURE,
                    "cached": True,
                    "similarity": sim,
                    "response": hit["response"],
                }
                _fb_record(
                    query=prompt,
                    intent_used="CACHE_SEMANTIC",
                    satisfaction=1.0,
                    response_time_s=0.005,
                )
                return out
    except Exception as e:
        log.warning(f"Semantic cache pre-route error: {e}")

    # ===============================
    # === ROUTING con LLM Intent ===
    # ===============================
    route: Optional[Dict[str, Any]] = None
    used_intent = "DIRECT_LLM"

    # 1. Correzioni utente salvate in Redis (override forte)
    corr = _get_redis_str(f"intent_corrections:{prompt.strip().lower()}")
    if corr:
        used_intent = corr.upper()
        route = {
            "intent": used_intent,
            "confidence": 1.0,
            "reason": "user_correction",
        }
        log.info(f"Using user correction for intent: {used_intent}")

    # 2. Meta queries → sempre DIRECT_LLM (niente web)
    if route is None and _is_meta_capability_query(prompt):
        used_intent = "DIRECT_LLM"
        route = {
            "intent": used_intent,
            "confidence": 1.0,
            "reason": "meta_query_override",
        }
        system_prompt = (
            system_prompt
            + "\n\n"
            "Contesto: l'utente chiede delle TUE capacità. "
            "Rispondi in modo conciso e non usare il web. "
            f"Breve sommario: {_CAPABILITIES_BRIEF}"
        ).strip()

    # 3. Explain/definition queries → DIRECT_LLM (mai web)
    if route is None and _is_explain_query(prompt):
        used_intent = "DIRECT_LLM"
        route = {
            "intent": used_intent,
            "confidence": 0.95,
            "reason": "explain_query_direct",
        }

    # 4. ⭐ LLM Intent Classification (nuovo percorso principale) ⭐
    if route is None:
        llm_classifier = get_llm_classifier()
        if llm_classifier:
            route = await llm_classifier.classify(
                prompt,
                use_fallback_on_low_confidence=True,
            )
            used_intent = (route.get("intent") or "DIRECT_LLM").upper()
            log.info(
                "LLM Intent: %s (conf=%.2f, method=%s, latency=%dms)",
                used_intent,
                float(route.get("confidence") or 0.0),
                route.get("method"),
                int(route.get("latency_ms", 0) or 0),
            )
        else:
            route = _SMART_INTENT.classify(prompt)
            used_intent = (route.get("intent") or "DIRECT_LLM").upper()
            log.info(
                "Rule-based Intent: %s (conf=%.2f)",
                used_intent,
                float(route.get("confidence") or 0.0),
            )

    # 5. Zero-web guard: smalltalk/very-short → forza DIRECT_LLM
    if _is_smalltalk_query(prompt) and used_intent in ("WEB_SEARCH", "WEB_READ"):
        used_intent = "DIRECT_LLM"
        if route is None:
            route = {
                "intent": used_intent,
                "confidence": 1.0,
                "reason": "smalltalk_guard",
            }
        else:
            route["intent"] = used_intent
            route["reason"] = (route.get("reason") or "") + "|smalltalk_guard"

    # 6. 🔥 Live query (meteo, prezzi, risultati): forza WEB_SEARCH
    if _is_quick_live_query(prompt) and used_intent != "WEB_SEARCH":
        used_intent = "WEB_SEARCH"
        if route is None:
            route = {
                "intent": used_intent,
                "confidence": 0.95,
                "reason": "force_web_live",
            }
        else:
            route["intent"] = used_intent
            route["reason"] = (route.get("reason") or "") + "|force_web_live"

    if route is None:
        route = {
            "intent": used_intent,
            "confidence": 0.0,
            "reason": "fallback_intent",
        }

    out: Dict[str, Any] = {
        "ok": True,
        "intent": used_intent,
        "confidence": route.get("confidence"),
        "reason": route.get("reason"),
        "router_build": BUILD_SIGNATURE,
    }

    # Cache key basata su prompt + system + intent
    cache_key = (
        "cache:"
        + hash_prompt(prompt, system_prompt, temperature, max_tokens, model_name)
        + f":{used_intent}"
    )
    cached = redis_client.get(cache_key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    t0 = time.perf_counter()

    # === Semantic cache (post-route, pre-LLM) ===
    try:
        if _SEMCACHE:
            _ensure_semcache_import()
            ctx_fp = SemanticCache.fingerprint(  # type: ignore[name-defined]
                system_prompt,
                model_name,
                used_intent,
            )
            hit2 = _SEMCACHE.get(prompt, ctx_fp)
            if hit2:
                sim2 = hit2.get("similarity")
                if sim2 is None:
                    meta_q2 = ((hit2.get("meta") or {}).get("q") or "")
                    sim2 = _cheap_similarity(prompt, meta_q2)
                out.update(
                    {
                        "cached": True,
                        "intent": "CACHE_SEMANTIC",
                        "reason": (out.get("reason") or "")
                        + "|semantic_hit_pre_llm",
                        "similarity": sim2,
                        "response": hit2["response"],
                    }
                )
                _fb_record(
                    query=prompt,
                    intent_used="CACHE_SEMANTIC",
                    satisfaction=1.0,
                    response_time_s=0.005,
                )
                redis_client.setex(cache_key, 86400, json.dumps(out))
                return out
    except Exception as e:
        log.warning(f"Semantic cache pre-llm error: {e}")

    try:
        # WEB_READ
        if used_intent == "WEB_READ":
            url = route.get("url")
            if url:
                try:
                    text, _ = await asyncio.wait_for(
                        fetch_and_extract(url),
                        timeout=WEB_READ_TIMEOUT_S,
                    )
                except asyncio.TimeoutError:
                    text = ""
                trimmed = trim_to_tokens(text or "", WEB_SUMMARY_BUDGET_TOK)
                persona = system_prompt
                msg = (
                    "RUOLO: stai leggendo il contenuto di una singola pagina web.\n\n"
                    "OBIETTIVO: riassumere la pagina in modo utile per l'utente.\n\n"
                    "REGOLE CRITICHE:\n"
                    "1. Riassumi in 5–10 punti chiave molto concreti (usa elenco puntato).\n"
                    "2. Usa SOLO le informazioni presenti nel testo fornito: non inventare dati.\n"
                    "3. Se ci sono numeri importanti (prezzi, date, percentuali, quantità), riportali indicando l'unità.\n"
                    "4. Se il contenuto è incompleto o poco chiaro, dillo esplicitamente ma riassumi comunque ciò che è disponibile.\n"
                    "5. NON dire all'utente di 'aprire la fonte' o 'consultare il sito' per avere i dettagli.\n"
                    "6. Alla fine, se utile, proponi in 1–2 frasi eventuali prossimi passi pratici.\n\n"
                    f"URL: {url}\n\n"
                    f"TESTO PAGINA:\n{trimmed}"
                )
                try:
                    summary = await reply_with_llm(msg, persona)
                except Exception:
                    summary = (
                        "Non sono riuscito a generare un riassunto strutturato, ma il contenuto "
                        "potrebbe comunque essere utile se consultato direttamente."
                    )

                try:
                    if summary:
                        asv = autosave(summary, source="web_read")
                        if any(
                            [
                                asv.get("facts"),
                                asv.get("prefs"),
                                asv.get("bet"),
                            ]
                        ):
                            log.info(f"[autosave:web_read] {asv}")
                except Exception as e:
                    log.warning(f"AutoSave web_read failed: {e}")

                out.update(
                    {
                        "cached": False,
                        "response": _wrap(summary, model_name),
                        "source_url": url,
                    }
                )
                _fb_record(
                    query=prompt,
                    intent_used="WEB_READ",
                    satisfaction=1.0,
                    response_time_s=time.perf_counter() - t0,
                )
                _ensure_semcache_import()
                if _SEMCACHE is None:
                    try:
                        _SEMCACHE = get_semantic_cache()  # type: ignore[name-defined]
                    except Exception:
                        pass
                _semcache_dualwrite(
                    prompt,
                    system_prompt,
                    model_name,
                    used_intent,
                    out["response"],
                )
                redis_client.setex(cache_key, 86400, json.dumps(out))
                return out
            else:
                used_intent = "DIRECT_LLM"
                out["intent"] = used_intent
                out["reason"] = (out.get("reason") or "") + "|url_missing_fallback"

        # 🌤️ WEATHER AGENT: intercetta query meteo prima del WEB_SEARCH generico
        if used_intent == "WEB_SEARCH" and WEATHER_AGENT_AVAILABLE and is_weather_query(prompt):
            log.info(f"🌤️ Weather query detected: {prompt}")
            try:
                cache_key_weather = _get_live_cache_key("weather", prompt)
                weather_answer = await cached_live_call(
                    cache_key_weather,
                    LIVE_CACHE_TTL_WEATHER,
                    get_weather_for_query(prompt),
                )
                if weather_answer:
                    out.update(
                        {
                            "cached": False,
                            "response": _wrap(weather_answer, model_name),
                            "live_agent": "weather",
                            "note": "weather_agent_response",
                        }
                    )
                    _fb_record(
                        query=prompt,
                        intent_used="WEATHER_AGENT",
                        satisfaction=1.0,
                        response_time_s=time.perf_counter() - t0,
                    )
                    redis_client.setex(cache_key, LIVE_CACHE_TTL_WEATHER, json.dumps(out))
                    return out
            except Exception as e:
                log.warning(f"Weather agent failed, fallback to WEB_SEARCH: {e}")

        # 💰 PRICE AGENT: intercetta query prezzi crypto/azioni/forex
        if used_intent == "WEB_SEARCH" and PRICE_AGENT_AVAILABLE and is_price_query(prompt):
            log.info(f"💰 Price query detected: {prompt}")
            try:
                cache_key_price = _get_live_cache_key("price", prompt)
                price_answer = await cached_live_call(
                    cache_key_price,
                    LIVE_CACHE_TTL_PRICE,
                    get_price_for_query(prompt),
                )
                if price_answer:
                    out.update(
                        {
                            "cached": False,
                            "response": _wrap(price_answer, model_name),
                            "live_agent": "price",
                            "note": "price_agent_response",
                        }
                    )
                    _fb_record(
                        query=prompt,
                        intent_used="PRICE_AGENT",
                        satisfaction=1.0,
                        response_time_s=time.perf_counter() - t0,
                    )
                    redis_client.setex(cache_key, LIVE_CACHE_TTL_PRICE, json.dumps(out))
                    return out
            except Exception as e:
                log.warning(f"Price agent failed, fallback to WEB_SEARCH: {e}")

        # ⚽ SPORTS AGENT: intercetta query risultati/classifiche sportive
        if used_intent == "WEB_SEARCH" and SPORTS_AGENT_AVAILABLE and is_sports_query(prompt):
            log.info(f"⚽ Sports query detected: {prompt}")
            try:
                cache_key_sports = _get_live_cache_key("sports", prompt)
                sports_answer = await cached_live_call(
                    cache_key_sports,
                    LIVE_CACHE_TTL_SPORTS,
                    get_sports_for_query(prompt),
                )
                if sports_answer:
                    out.update(
                        {
                            "cached": False,
                            "response": _wrap(sports_answer, model_name),
                            "live_agent": "sports",
                            "note": "sports_agent_response",
                        }
                    )
                    _fb_record(
                        query=prompt,
                        intent_used="SPORTS_AGENT",
                        satisfaction=1.0,
                        response_time_s=time.perf_counter() - t0,
                    )
                    redis_client.setex(cache_key, LIVE_CACHE_TTL_SPORTS, json.dumps(out))
                    return out
            except Exception as e:
                log.warning(f"Sports agent failed, fallback to WEB_SEARCH: {e}")

        # 📰 NEWS AGENT: intercetta query breaking news
        if used_intent == "WEB_SEARCH" and NEWS_AGENT_AVAILABLE and is_news_query(prompt):
            log.info(f"📰 News query detected: {prompt}")
            try:
                cache_key_news = _get_live_cache_key("news", prompt)
                news_answer = await cached_live_call(
                    cache_key_news,
                    LIVE_CACHE_TTL_NEWS,
                    get_news_for_query(prompt),
                )
                if news_answer:
                    out.update(
                        {
                            "cached": False,
                            "response": _wrap(news_answer, model_name),
                            "live_agent": "news",
                            "note": "news_agent_response",
                        }
                    )
                    _fb_record(
                        query=prompt,
                        intent_used="NEWS_AGENT",
                        satisfaction=1.0,
                        response_time_s=time.perf_counter() - t0,
                    )
                    redis_client.setex(cache_key, LIVE_CACHE_TTL_NEWS, json.dumps(out))
                    return out
            except Exception as e:
                log.warning(f"News agent failed, fallback to WEB_SEARCH: {e}")

        # 📅 SCHEDULE AGENT: intercetta query orari/calendario
        if used_intent == "WEB_SEARCH" and SCHEDULE_AGENT_AVAILABLE and is_schedule_query(prompt):
            log.info(f"📅 Schedule query detected: {prompt}")
            try:
                cache_key_schedule = _get_live_cache_key("schedule", prompt)
                schedule_answer = await cached_live_call(
                    cache_key_schedule,
                    LIVE_CACHE_TTL_SCHEDULE,
                    get_schedule_for_query(prompt),
                )
                if schedule_answer:
                    out.update(
                        {
                            "cached": False,
                            "response": _wrap(schedule_answer, model_name),
                            "live_agent": "schedule",
                            "note": "schedule_agent_response",
                        }
                    )
                    _fb_record(
                        query=prompt,
                        intent_used="SCHEDULE_AGENT",
                        satisfaction=1.0,
                        response_time_s=time.perf_counter() - t0,
                    )
                    redis_client.setex(cache_key, LIVE_CACHE_TTL_SCHEDULE, json.dumps(out))
                    return out
            except Exception as e:
                log.warning(f"Schedule agent failed, fallback to WEB_SEARCH: {e}")

        # WEB_SEARCH
        if used_intent == "WEB_SEARCH":
            ws = await _web_search_pipeline(
                q=prompt,
                src="global",
                sid="default",
                k=int(data.get("k", 8)),
                nsum=int(
                    data.get("summarize_top", WEB_SUMMARIZE_TOP_DEFAULT)
                ),
            )
            results = ws.get("results") or []
            summary = (ws.get("summary") or "").strip()
            note = ws.get("note")
            diversity = ws.get("diversity")

            # 🔁 Fallback: nessun risultato
            if not results:
                safe_msg = summary or "Non ho trovato risultati utili per questa ricerca."
                out.update(
                    {
                        "cached": False,
                        "response": _wrap(safe_msg, model_name),
                        "web": {
                            "results": [],
                            "reranker_used": False,
                            "stats": ws.get("stats", {}),
                            "diversity": diversity,
                        },
                        "note": note or "non_web_query",
                    }
                )
                _fb_record(
                    query=prompt,
                    intent_used="WEB_SEARCH",
                    satisfaction=0.6,
                    response_time_s=time.perf_counter() - t0,
                )
                _ensure_semcache_import()
                if _SEMCACHE is None:
                    try:
                        _SEMCACHE = get_semantic_cache()  # type: ignore[name-defined]
                    except Exception:
                        pass
                _semcache_dualwrite(
                    prompt,
                    system_prompt,
                    model_name,
                    used_intent,
                    out["response"],
                )
                redis_client.setex(cache_key, 600, json.dumps(out))
                return out

            # 🔁 Fallback testuale: se la sintesi LLM è vuota ma ci sono risultati,
            # costruisco un messaggio leggibile a partire dai risultati SERP.
            if not summary and results:
                lines: List[str] = []
                for idx, r in enumerate(results[:5], start=1):
                    title = (r.get("title") or "").strip() or (r.get("url") or "")
                    url = (r.get("url") or "").strip()
                    if url:
                        lines.append(f"{idx}. {title}\n   {url}")
                    else:
                        lines.append(f"{idx}. {title}")
                if lines:
                    summary = (
                        "Ho trovato questi risultati principali:\n\n"
                        + "\n".join(lines)
                    )
                else:
                    summary = (
                        "Ho effettuato la ricerca, ma non sono riuscito a estrarre "
                        "un contenuto testuale utile dalle pagine trovate."
                    )

            # Auto-save della sintesi (LLM o fallback)
            try:
                if summary:
                    asv = autosave(summary, source="web_search")
                    if any(
                        [asv.get("facts"), asv.get("prefs"), asv.get("bet")]
                    ):
                        log.info(f"[autosave:web_search] {asv}")
            except Exception as e:
                log.warning(f"AutoSave web_search failed: {e}")

            out.update(
                {
                    "cached": False,
                    "response": _wrap(summary, model_name),
                    "web": {
                        "results": results,
                        "reranker_used": ws.get("reranker_used", False),
                        "stats": ws.get("stats", {}),
                        "diversity": diversity,
                    },
                }
            )
            _fb_record(
                query=prompt,
                intent_used="WEB_SEARCH",
                satisfaction=1.0,
                response_time_s=time.perf_counter() - t0,
            )
            _ensure_semcache_import()
            if _SEMCACHE is None:
                try:
                    _SEMCACHE = get_semantic_cache()  # type: ignore[name-defined]
                except Exception:
                    pass
            _semcache_dualwrite(
                prompt,
                system_prompt,
                model_name,
                used_intent,
                out["response"],
            )
            redis_client.setex(cache_key, 86400, json.dumps(out))
            return out

        # DIRECT LLM con budget
        sys_trim = trim_to_tokens(system_prompt, min(600, LLM_MAX_CTX // 8))
        user_trim = prompt
        input_budget = (
            LLM_MAX_CTX - LLM_OUTPUT_BUDGET_TOK - LLM_SAFETY_MARGIN_TOK
        )
        tokens_now = approx_tokens(sys_trim) + approx_tokens(user_trim)
        if tokens_now > input_budget:
            keep = max(128, input_budget - approx_tokens(sys_trim))
            user_trim = trim_to_tokens(user_trim[-keep * 4 :], keep)

        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": sys_trim},
                {"role": "user", "content": user_trim},
            ],
            "temperature": temperature,
            "max_tokens": LLM_OUTPUT_BUDGET_TOK,
        }
        result, endpoint_used, last_err = _run_direct(payload, force)
        if not result:
            fail = {
                "ok": False,
                "error": "Nessun endpoint raggiungibile.",
                "last_error": last_err,
                "endpoints_tried": get_endpoints(),
                "intent": used_intent,
                "confidence": route.get("confidence"),
                "reason": route.get("reason"),
                "router_build": BUILD_SIGNATURE,
            }
            redis_client.setex(cache_key, 300, json.dumps(fail))
            return fail

        try:
            msg = (
                (result.get("choices") or [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            if msg:
                asv = autosave(msg, source="direct_llm")
                if any([asv.get("facts"), asv.get("prefs"), asv.get("bet")]):
                    log.info(f"[autosave:direct_llm] {asv}")
        except Exception as e:
            log.warning(f"AutoSave direct_llm failed: {e}")

        out.update(
            {
                "cached": False,
                "endpoint_used": endpoint_used,
                "response": result,
            }
        )
        _fb_record(
            query=prompt,
            intent_used="DIRECT_LLM",
            satisfaction=1.0,
            response_time_s=time.perf_counter() - t0,
        )
        _ensure_semcache_import()
        if _SEMCACHE is None:
            try:
                _SEMCACHE = get_semantic_cache()  # type: ignore[name-defined]
            except Exception:
                pass
        _semcache_dualwrite(
            prompt,
            system_prompt,
            model_name,
            out["intent"],
            out["response"],
        )
        redis_client.setex(cache_key, 86400, json.dumps(out))
        return out
    except Exception:
        err = {
            "ok": False,
            "error": (
                "Richiesta troppo lunga o sorgente non disponibile. "
                "Le fonti non sono accessibili in questo momento."
            ),
            "intent": used_intent,
            "confidence": route.get("confidence"),
            "reason": (route.get("reason") or "") + "|exception",
            "router_build": BUILD_SIGNATURE,
        }
        redis_client.setex(cache_key, 300, json.dumps(err))
        return err


# ================= Persona & Web utils ===================
@app.post("/chat")
async def chat(payload: dict = Body(...)) -> Dict[str, Any]:
    """
    Chat avanzata (v2).
    """
    global _SEMCACHE

    # ======== Normalizzazione input: messages vs legacy ========
    messages = payload.get("messages")
    text: str = ""
    explicit_sys_from_messages: str = ""

    if isinstance(messages, list) and messages:
        # Nuovo stile OpenAI-like
        for m in reversed(messages):
            if isinstance(m, dict) and m.get("role") == "user":
                text = (m.get("content") or "").strip()
                break

        # System messages espliciti nel payload
        sys_parts: List[str] = []
        for m in messages:
            if isinstance(m, dict) and m.get("role") == "system":
                c = (m.get("content") or "").strip()
                if c:
                    sys_parts.append(c)
        if sys_parts:
            explicit_sys_from_messages = "\n\n".join(sys_parts)

        src = payload.get("source") or "gui"
        sid = str(payload.get("source_id") or "default")
    else:
        # Payload legacy (usato dal bot Telegram esistente)
        src = payload.get("source", "tg")
        sid = str(payload.get("source_id") or "")
        text = (payload.get("text") or "").strip()
        explicit_sys_from_messages = ""

    user_sys_prompt = (payload.get("system_prompt") or "").strip()

    if not text:
        return {"error": "text mancante"}
    if not sid:
        sid = "default"

    # Autosave input utente
    try:
        asv_in = autosave(text, source="chat_user")
        if any([asv_in.get("facts"), asv_in.get("prefs"), asv_in.get("bet")]):
            log.info(f"[autosave:chat_user] {asv_in}")
    except Exception as e:
        log.warning(f"AutoSave chat_user failed: {e}")

    # Persona di base
    try:
        persona_store = await get_persona(src, sid)
    except Exception:
        persona_store = None

    base_sys = user_sys_prompt or persona_store or DEFAULT_SYSTEM_PROMPT
    if explicit_sys_from_messages:
        base_sys = explicit_sys_from_messages + "\n\n" + base_sys

    # Regole dure anti-hallucination + priorità ai facts interni
    strict_rules = (
        "Regole interne dure (ANTI-HALLUCINATION & FACT-FIRST):\n"
        "1. Non inventare mai numeri, date, nomi di modello hardware o importi se NON sono nella domanda o nei facts interni.\n"
        "2. Se ti mancano dettagli specifici, dillo esplicitamente ('non ho questo dato in memoria' / 'qui sto parlando in generale').\n"
        "3. Quando rispondi su Jarvis, QuantumDev, Quantum Edge AI o il mio ecosistema, considera i facts in memoria (Chroma) "
        "come fonte primaria e non contraddirli.\n"
        "4. Se usi conoscenza generale, chiarisci che è 'in generale', non riferita alla mia infrastruttura reale.\n"
        "5. Evita frasi vaghe tipo 'potrebbe' / 'forse' quando parli di configurazioni reali: se non sai, dillo.\n"
    )

    # =================== Semantic Cache (chat) – pre-check ===================
    try:
        _ensure_semcache_import()
        if _SEMCACHE is None:
            _SEMCACHE = get_semantic_cache()  # type: ignore[name-defined]
    except Exception as e:
        log.warning(f"Semantic cache init error in /chat: {e}")
        _SEMCACHE = None

    if _SEMCACHE:
        try:
            ctx_fp = SemanticCache.fingerprint(  # type: ignore[name-defined]
                base_sys,
                LLM_MODEL,
                "CHAT",
            )
            hit = _SEMCACHE.get(text, ctx_fp)
        except Exception as e:
            log.warning(f"Semantic cache get error in /chat: {e}")
            hit = None

        if hit:
            sim = hit.get("similarity")
            if sim is None:
                meta_q = ((hit.get("meta") or {}).get("q") or "")
                sim = _cheap_similarity(text, meta_q)
            if sim is None:
                sim = 0.0

            # soglia alta
            if sim >= 0.88:
                resp = hit.get("response")
                if isinstance(resp, dict) and "reply" in resp:
                    reply_cached = resp["reply"]
                elif isinstance(resp, str):
                    reply_cached = resp
                else:
                    reply_cached = str(resp)

                try:
                    asv_out = autosave(
                        reply_cached, source="chat_reply_cache"
                    )
                    if any(
                        [
                            asv_out.get("facts"),
                            asv_out.get("prefs"),
                            asv_out.get("bet"),
                        ]
                    ):
                        log.info(f"[autosave:chat_reply_cache] {asv_out}")
                except Exception as e:
                    log.warning(
                        f"AutoSave chat_reply_cache failed: {e}"
                    )

                return {"reply": reply_cached}

    # =================== Helper: query su hardware Jarvis ===================
    def _is_jarvis_hw_query(q: str) -> bool:
        s = (q or "").lower()
        hw_keywords = [
            "hardware",
            "cpu",
            "gpu",
            "vram",
            "scheda video",
            "scheda grafica",
            "server",
            "macchina",
            "nodo",
        ]
        jarvis_keywords = [
            "jarvis",
            "mia ai",
            "mio jarvis",
            "quantumdev",
            "la mia ai",
            "ai personale",
        ]
        return any(k in s for k in hw_keywords) and any(
            k in s for k in jarvis_keywords
        )

    # =================== Memory search (Chroma) ===================
    mem_items: List[Dict[str, Any]] = []
    try:
        mem_items = search_topk(text, k=10, half_life_days=MEM_HALF_LIFE_D)
    except Exception as e:
        log.warning(f"memory search in /chat failed: {e}")
        mem_items = []

    # Estrazione facts specifici su hardware Jarvis (CPU/GPU)
    cpu_val: Optional[str] = None
    gpu_val: Optional[str] = None

    for it in mem_items:
        md = (it.get("metadata") or {}) or {}
        subj = (
            md.get("subject")
            or md.get("key")
            or md.get("label")
            or ""
        ).lower()
        val = (md.get("value") or "").strip()
        doc = (it.get("document") or "").strip()
        content = val or doc
        if not content:
            continue

        if "jarvis.hardware.cpu" in subj:
            cpu_val = content
        if "jarvis.hardware.gpu" in subj:
            gpu_val = content

    # =================== Caso speciale: hardware Jarvis ===================
    if _is_jarvis_hw_query(text):
        if cpu_val or gpu_val:
            parts: List[str] = []
            if cpu_val:
                parts.append(cpu_val)
            if gpu_val:
                parts.append(gpu_val)
            reply_hw = " | ".join(parts)
        else:
            reply_hw = (
                "Non ho nessun fact salvato sull'hardware reale del tuo Jarvis "
                "(CPU/GPU) in Chroma. Finché questi dati non sono registrati, "
                "qualsiasi risposta specifica su modelli o VRAM sarebbe inventata e quindi non te la do.\n\n"
                "Per fissare l'hardware reale, aggiungi almeno due facts via API /memory/fact:\n"
                "- subject: jarvis.hardware.cpu → value: descrizione CPU reale (es. 'CPU reale Jarvis: ...')\n"
                "- subject: jarvis.hardware.gpu → value: descrizione GPU reale (es. 'GPU reale Jarvis: ...')\n"
                "Poi rifai la domanda."
            )

        try:
            asv_out = autosave(reply_hw, source="chat_reply")
            if any(
                [asv_out.get("facts"), asv_out.get("prefs"), asv_out.get("bet")]
            ):
                log.info(f"[autosave:chat_reply] {asv_out}")
        except Exception as e:
            log.warning(f"AutoSave chat_reply (hw) failed: {e}")

        if _SEMCACHE:
            try:
                _semcache_dualwrite(
                    text,
                    base_sys,
                    LLM_MODEL,
                    "CHAT",
                    {"reply": reply_hw},
                )
            except Exception as e:
                log.warning(f"Semantic cache write (hw) failed: {e}")

        return {"reply": reply_hw}

    # =================== Costruzione contesto dai facts ===================
    mem_context = ""
    if mem_items:
        lines: List[Dict[str, Any]] = []
        for it in mem_items[:5]:
            md = (it.get("metadata") or {}) or {}
            subj = (
                md.get("subject")
                or md.get("key")
                or md.get("event")
                or md.get("label")
                or ""
            )
            val = (md.get("value") or "").strip()
            doc = (it.get("document") or "").strip()
            content = val or doc
            if not content:
                continue
            if subj:
                lines.append(f"- {subj}: {content}")
            else:
                lines.append(f"- {content}")
        if lines:
            mem_context = "Facts interni (Chroma) rilevanti:\n" + "\n".join(
                lines
            )

    # =================== System prompt finale ===================
    full_sys = (
        base_sys.strip()
        + "\n\n"
        + INCENSURATO_PROMPT
        + "\n\n"
        + strict_rules
    )
    if mem_context:
        full_sys += "\n\n" + mem_context

    sys_trim = trim_to_tokens(full_sys, 600)

    # =================== Chiamata LLM ===================
    reply_text = await reply_with_llm(text, sys_trim)

    # Autosave output
    try:
        if reply_text:
            asv_out = autosave(reply_text, source="chat_reply")
            if any(
                [
                    asv_out.get("facts"),
                    asv_out.get("prefs"),
                    asv_out.get("bet"),
                ]
            ):
                log.info(f"[autosave:chat_reply] {asv_out}")
    except Exception as e:
        log.warning(f"AutoSave chat_reply failed: {e}")

    # Scrivi in semantic cache per future richieste simili
    if _SEMCACHE and reply_text:
        try:
            _semcache_dualwrite(
                text,
                base_sys,
                LLM_MODEL,
                "CHAT",
                {"reply": reply_text},
            )
        except Exception as e:
            log.warning(f"Semantic cache write (/chat) failed: {e}")

    return {"reply": reply_text}


# ========================= /unified endpoint (Master Orchestrator) =========================
@app.post("/unified")
async def unified_endpoint(payload: dict = Body(...)) -> Dict[str, Any]:
    """
    Unified endpoint using Master Orchestrator.
    Automatically decides whether to use tools/web or direct LLM.
    
    Payload:
        - q: query string (required)
        - source: source identifier (default: "api")
        - source_id: user/chat identifier (required)
    """
    try:
        # Import master orchestrator
        from core.master_orchestrator import get_master_orchestrator
        from core.chat_engine import reply_with_llm
        
        # Extract params
        query = (payload.get("q") or "").strip()
        source = payload.get("source", "api")
        source_id = str(payload.get("source_id") or "default")
        
        if not query:
            return {
                "error": "q parameter is required",
                "success": False,
            }
        
        # Get orchestrator instance with LLM function
        orchestrator = get_master_orchestrator(llm_func=reply_with_llm)
        
        # Process through orchestrator
        result = await orchestrator.process(
            query=query,
            source=source,
            source_id=source_id,
            show_reasoning=True,
            create_artifacts=False,  # Disable artifacts for now
        )
        
        # Return response in format compatible with telegram bot
        return {
            "reply": result.response,
            "query_type": result.context.query_type.value,
            "strategy": result.context.strategy.value,
            "tool_results": result.context.tool_results,
            "duration_ms": result.duration_ms,
            "success": result.success,
        }
        
    except Exception as e:
        log.error(f"/unified error: {e}")
        return {
            "error": str(e),
            "success": False,
        }


@app.post("/persona/set")
async def persona_set(payload: dict = Body(...)) -> Dict[str, Any]:
    src = payload.get("source", "tg")
    sid = str(payload.get("source_id"))
    text = (payload.get("text") or "").strip()
    if not sid or not text:
        return {"error": "source_id o text mancanti"}
    await set_persona(src, sid, text)
    return {"ok": True}


@app.post("/persona/get")
async def persona_get(payload: dict = Body(...)) -> Dict[str, Any]:
    src = payload.get("source", "tg")
    sid = str(payload.get("source_id"))
    if not sid:
        return {"error": "source_id mancante"}
    p = await get_persona(src, sid)
    return {"persona": p}


@app.post("/persona/reset")
async def persona_reset(payload: dict = Body(...)) -> Dict[str, Any]:
    src = payload.get("source", "tg")
    sid = str(payload.get("source_id"))
    if not sid:
        return {"error": "source_id mancante"}
    await reset_persona(src, sid)
    return {"ok": True}


# ---------- /web/summarize : URL o Query -----------------
class WebSummarizeQueryReq(BaseModel):
    q: Optional[str] = None
    url: Optional[str] = None
    source: str = "tg"
    source_id: str
    k: int = 6
    summarize_top: int = WEB_SUMMARIZE_TOP_DEFAULT
    return_sources: bool = True


@app.post("/web/summarize")
async def web_summarize(payload: WebSummarizeQueryReq) -> Dict[str, Any]:
    if payload.q:
        if _is_smalltalk_query(payload.q):
            return {
                "summary": "",
                "results": [],
                "note": "non_web_query",
            }

        # 🌤️ Weather Agent: intercetta query meteo
        if WEATHER_AGENT_AVAILABLE and is_weather_query and is_weather_query(payload.q):
            try:
                weather_answer = await get_weather_for_query(payload.q)
                if weather_answer:
                    return {
                        "summary": weather_answer,
                        "results": [],
                        "note": "weather_agent",
                    }
            except Exception as e:
                log.warning(f"Weather agent failed in /web/summarize: {e}")

        # 💰 Price Agent: intercetta query prezzi
        if PRICE_AGENT_AVAILABLE and is_price_query(payload.q):
            try:
                price_answer = await get_price_for_query(payload.q)
                if price_answer:
                    return {
                        "summary": price_answer,
                        "results": [],
                        "note": "price_agent",
                    }
            except Exception as e:
                log.warning(f"Price agent failed in /web/summarize: {e}")

        # ⚽ Sports Agent: intercetta query sportive
        if SPORTS_AGENT_AVAILABLE and is_sports_query(payload.q):
            try:
                sports_answer = await get_sports_for_query(payload.q)
                if sports_answer:
                    return {
                        "summary": sports_answer,
                        "results": [],
                        "note": "sports_agent",
                    }
            except Exception as e:
                log.warning(f"Sports agent failed in /web/summarize: {e}")

        # 📰 News Agent: intercetta query news
        if NEWS_AGENT_AVAILABLE and is_news_query(payload.q):
            try:
                news_answer = await get_news_for_query(payload.q)
                if news_answer:
                    return {
                        "summary": news_answer,
                        "results": [],
                        "note": "news_agent",
                    }
            except Exception as e:
                log.warning(f"News agent failed in /web/summarize: {e}")

        # 📅 Schedule Agent: intercetta query calendario
        if SCHEDULE_AGENT_AVAILABLE and is_schedule_query(payload.q):
            try:
                schedule_answer = await get_schedule_for_query(payload.q)
                if schedule_answer:
                    return {
                        "summary": schedule_answer,
                        "results": [],
                        "note": "schedule_agent",
                    }
            except Exception as e:
                log.warning(f"Schedule agent failed in /web/summarize: {e}")

        # Fallback a web search standard
        ws = await _web_search_pipeline(
            q=payload.q,
            src=payload.source,
            sid=str(payload.source_id),
            k=int(payload.k or 6),
            nsum=int(
                payload.summarize_top or WEB_SUMMARIZE_TOP_DEFAULT
            ),
        )

        if not ws.get("results"):
            return {
                "summary": ws.get("summary", ""),
                "results": [],
                "note": ws.get("note") or "non_web_query",
            }

        return {
            "summary": ws.get("summary", ""),
            "results": ws.get("results", []),
        }

    if not payload.url:
        return {"error": "url o q mancante"}

    url = payload.url.strip()
    persona = await get_persona(payload.source, str(payload.source_id))
    try:
        text, og_img = await asyncio.wait_for(
            fetch_and_extract(url),
            timeout=WEB_READ_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        text, og_img = "", None

    trimmed = trim_to_tokens(text or "", WEB_SUMMARY_BUDGET_TOK)
    prompt = (
        "RUOLO: stai leggendo il contenuto di una singola pagina web.\n\n"
        "OBIETTIVO: riassumere la pagina in modo utile per l'utente.\n\n"
        "REGOLE CRITICHE:\n"
        "1. Riassumi in 5–10 punti chiave molto concreti (usa elenco puntato).\n"
        "2. Usa SOLO le informazioni presenti nel testo fornito: non inventare dati.\n"
        "3. Se ci sono numeri importanti (prezzi, date, percentuali, quantità), riportali indicando l'unità.\n"
        "4. Se il contenuto è incompleto o poco chiaro, dillo esplicitamente ma riassumi comunque ciò che è disponibile.\n"
        "5. NON dire all'utente di 'aprire la fonte' o 'consultare il sito' per avere i dettagli.\n"
        "6. Alla fine, se utile, proponi 1–2 prossimi passi pratici.\n\n"
        f"URL: {url}\n\n"
        f"TESTO PAGINA:\n{trimmed}"
    )
    try:
        summary = await reply_with_llm(prompt, persona)
    except Exception:
        summary = (
            "Non sono riuscito a generare un riassunto strutturato, ma il contenuto della "
            "pagina potrebbe comunque esserti utile se consultato."
        )

    try:
        if summary:
            asv = autosave(summary, source="web_summarize")
            if any([asv.get("facts"), asv.get("prefs"), asv.get("bet")]):
                log.info(f"[autosave:web_summarize] {asv}")
    except Exception as e:
        log.warning(f"AutoSave web_summarize failed: {e}")

    return {
        "summary": summary,
        "og_image": og_img,
        "results": [{"url": url, "title": url}],
    }


# -------------------------- /web/search -------------------------------
class WebSearchReq(BaseModel):
    q: str
    k: int = 6
    summarize_top: int = WEB_SUMMARIZE_TOP_DEFAULT
    source: str = "tg"
    source_id: str = "default"


@app.post("/web/search")
async def web_search(req: WebSearchReq) -> Dict[str, Any]:
    if _is_smalltalk_query(req.q):
        return {
            "summary": "",
            "results": [],
            "note": "non_web_query",
            "stats": {},
        }

    # Se query complessa o flag deep, usa deep pipeline
    is_complex = len(req.q.split()) > 8 or "?" in req.q

    if WEB_SEARCH_DEEP_MODE or is_complex:
        ws = await _web_search_pipeline_deep(
            q=req.q,
            src=req.source,
            sid=str(req.source_id),
            k=WEB_DEEP_MAX_SOURCES,
            nsum=min(10, WEB_DEEP_MAX_SOURCES),
        )
    else:
        ws = await _web_search_pipeline(
            q=req.q,
            src=req.source,
            sid=str(req.source_id),
            k=int(req.k or 6),
            nsum=int(
                req.summarize_top or WEB_SUMMARIZE_TOP_DEFAULT
            ),
        )

    out: Dict[str, Any] = {
        "summary": (ws.get("summary") or ""),
        "results": (ws.get("results") or []),
        "note": ws.get("note"),
        "stats": ws.get("stats", {}),
        "reranker_used": ws.get("reranker_used", False),
        "diversity": ws.get("diversity"),
    }
    if ws.get("validation") is not None:
        out["validation"] = ws["validation"]
    return out


# -------------------------- /web/research -----------------------------
class WebResearchReq(BaseModel):
    q: str
    source: str = "tg"
    source_id: str = "default"


@app.post("/web/research")
async def web_research(req: WebResearchReq) -> Dict[str, Any]:
    """Ricerca orchestrata multi-step (Claude-style)."""
    if _is_smalltalk_query(req.q):
        return {
            "answer": "",
            "sources": [],
            "steps": [],
            "total_steps": 0,
            "note": "non_web_query",
        }

    agent = get_web_research_agent()
    if agent is None:
        ws = await _web_search_pipeline(
            q=req.q,
            src=req.source,
            sid=str(req.source_id),
            k=6,
            nsum=WEB_SUMMARIZE_TOP_DEFAULT,
        )
        return {
            "answer": ws.get("summary") or "",
            "sources": ws.get("results") or [],
            "steps": [],
            "total_steps": 1,
            "note": "fallback_standard_search",
        }

    persona = (
        await get_persona(req.source, str(req.source_id))
        or DEFAULT_SYSTEM_PROMPT
    )
    persona = (persona.strip() + "\n\n" + INCENSURATO_PROMPT).strip()
    try:
        result = await agent.research(
            query=req.q,
            persona=persona,
        )
        return result
    except Exception as e:
        log.error(f"/web/research error: {e}")
        ws = await _web_search_pipeline(
            q=req.q,
            src=req.source,
            sid=str(req.source_id),
            k=6,
            nsum=WEB_SUMMARIZE_TOP_DEFAULT,
        )
        return {
            "answer": ws.get("summary")
            or "Errore nel motore di ricerca avanzato. Ho usato una ricerca standard.",
            "sources": ws.get("results") or [],
            "steps": [],
            "total_steps": 1,
            "note": "web_research_error_fallback",
            "error": str(e),
        }


# -------------------------- /web/deep ---------------------------------
class WebDeepReq(BaseModel):
    q: str
    source: str = "tg"
    source_id: str = "default"


@app.post("/web/deep")
async def web_deep(req: WebDeepReq) -> Dict[str, Any]:
    """
    Ricerca approfondita multi-step (comando /webdeep).
    Usa AdvancedWebResearch per coverage completo.
    """
    if _is_smalltalk_query(req.q):
        return {
            "answer": "",
            "sources": [],
            "steps": [],
            "quality": 0.0,
            "note": "non_web_query",
        }

    try:
        from agents.advanced_web_research import get_advanced_research

        researcher = get_advanced_research()
        persona = (
            await get_persona(req.source, str(req.source_id))
            or DEFAULT_SYSTEM_PROMPT
        )
        persona = (persona.strip() + "\n\n" + INCENSURATO_PROMPT).strip()

        result = await researcher.research_deep(req.q, persona)

        return {
            "answer": result.get("answer", ""),
            "sources": result.get("sources", []),
            "steps": result.get("steps", []),
            "quality": result.get("quality_final", 0.0),
            "total_sources": result.get("total_sources", 0),
            "note": "deep_research",
        }

    except Exception as e:
        log.error(f"/web/deep error: {e}")
        # Fallback a ricerca standard
        ws = await _web_search_pipeline_deep(
            q=req.q,
            src=req.source,
            sid=str(req.source_id),
        )
        return {
            "answer": ws.get("summary") or "",
            "sources": ws.get("results") or [],
            "steps": [],
            "quality": 0.5,
            "note": "deep_fallback_standard",
            "error": str(e),
        }


# -------------------------- /code -------------------------------------
class CodeReq(BaseModel):
    q: str
    language: Optional[str] = None
    source: str = "tg"
    source_id: str = "default"


@app.post("/code")
async def code_generate(req: CodeReq) -> Dict[str, Any]:
    """
    Generazione codice dedicata (comando /code).
    Usa il Code Agent per risposte strutturate.
    """
    if not CODE_AGENT_AVAILABLE:
        return {
            "ok": False,
            "error": "Code Agent non disponibile.",
            "code": "",
        }

    try:
        persona = (
            await get_persona(req.source, str(req.source_id))
            or DEFAULT_SYSTEM_PROMPT
        )
        persona = (persona.strip() + "\n\n" + INCENSURATO_PROMPT).strip()

        result = await get_code_for_query(
            req.q,
            llm_func=reply_with_llm,
            persona=persona,
        )

        return {
            "ok": True,
            "code": result or "",
            "language": req.language,
            "note": "code_agent_response",
        }

    except Exception as e:
        log.error(f"/code error: {e}")
        return {
            "ok": False,
            "error": str(e),
            "code": "",
        }


# -------------------------- /unified-web ------------------------------
class UnifiedWebReq(BaseModel):
    q: str
    deep: bool = False
    source: str = "api"


@app.post("/unified-web")
async def unified_web_endpoint(req: UnifiedWebReq) -> Dict[str, Any]:
    """
    Endpoint unificato per tutte le richieste web.
    Garantisce consistenza di routing e formato risposta.
    """
    if not UNIFIED_WEB_HANDLER_AVAILABLE:
        # Fallback a pipeline standard
        ws = await _web_search_pipeline(
            q=req.q,
            src=req.source,
            sid="default",
        )
        return {
            "response": ws.get("summary") or "",
            "intent": "general_web",
            "cached": False,
            "note": "unified_handler_not_available",
        }

    try:
        result = await handle_web_query(
            query=req.q,
            source=req.source,
            deep=req.deep,
        )
        return result

    except Exception as e:
        log.error(f"/unified-web error: {e}")
        return {
            "response": f"Errore: {e}",
            "intent": "error",
            "cached": False,
            "error": str(e),
        }


# -------------------------- /web/cache --------------------------------
@app.get("/web/cache/stats")
def web_cache_stats() -> Dict[str, Any]:
    try:
        st = _webcache_stats()
        return {"ok": True, "cache": st}
    except Exception as e:
        return {"ok": False, "error": str(e)}


class WebCacheFlushReq(BaseModel):
    url: Optional[str] = None


@app.post("/web/cache/flush")
def web_cache_flush(req: WebCacheFlushReq) -> Dict[str, Any]:
    try:
        res = _webcache_flush(req.url)
        return {"ok": True, **res}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ======================= Memory API (ChromaDB) =======================
class FactIn(BaseModel):
    subject: str
    value: str
    source: str = "system"
    metadata: dict | None = None


class PrefIn(BaseModel):
    key: str
    value: str
    scope: str = "global"
    source: str = "user"
    metadata: dict | None = None


class BetIn(BaseModel):
    event: str
    market: str
    odds: float
    stake: float
    result: str | None = None
    source: str = "bet"
    metadata: dict | None = None


@app.post("/memory/fact")
def memory_add_fact(payload: FactIn) -> Dict[str, Any]:
    _id = add_fact(
        payload.subject,
        payload.value,
        payload.source,
        payload.metadata,
    )
    return {"ok": True, "id": _id}


@app.post("/memory/pref")
def memory_add_pref(payload: PrefIn) -> Dict[str, Any]:
    _id = add_pref(
        payload.key,
        payload.value,
        payload.scope,
        payload.source,
        payload.metadata,
    )
    return {"ok": True, "id": _id}


@app.post("/memory/bet")
def memory_add_bet(payload: BetIn) -> Dict[str, Any]:
    _id = add_bet(
        payload.event,
        payload.market,
        payload.odds,
        payload.stake,
        payload.result,
        payload.source,
        payload.metadata,
    )
    return {"ok": True, "id": _id}


# --- Fallback-aware search base ---
def _recency_score(ts: int, half_life_days: float) -> float:
    if not ts:
        return 0.0
    age_days = max(0.0, (int(time.time()) - ts) / 86400.0)
    return math.exp(-math.log(2) * (age_days / max(1e-9, half_life_days)))


def _src_prior(md: dict) -> float:
    src = (md or {}).get("source") or ""
    table = {
        "system": 1.00,
        "admin": 0.98,
        "user": 0.95,
        "web": 0.92,
        "model": 0.85,
        "bet": 0.90,
    }
    return table.get(src, 0.9)


@app.get("/memory/search")
def memory_search(
    q: str,
    k: int = 5,
    half_life_days: float = MEM_HALF_LIFE_D,
) -> Dict[str, Any]:
    items = search_topk(q, k=k, half_life_days=half_life_days)
    if items:
        return {"q": q, "k": k, "items": items}

    pool: List[Dict[str, Any]] = []
    for name in (FACTS, PREFS, BETS):
        try:
            pool.extend(
                _substring_fallback(name, q, limit=max(256, k * 10))
            )
        except Exception:
            pass

    ranked: List[Dict[str, Any]] = []
    for it in pool:
        md = it.get("metadata", {}) or {}
        rec = _recency_score(
            int(md.get("ts") or 0),
            half_life_days=half_life_days,
        )
        srcp = _src_prior(md)
        it["sim"] = 0.0
        it["recency"] = round(rec, 6)
        it["src_prior"] = round(srcp, 3)
        it["score"] = round(0.6 * rec + 0.4 * srcp, 6)
        ranked.append(it)

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return {"q": q, "k": k, "items": ranked[:k]}


# ---- /memory/debug: versione leggera ----
def _light_debug_dump() -> Dict[str, Any]:
    if chromadb is None or _ChromaSettings is None:
        try:
            return debug_dump()
        except Exception as e:
            return {
                "persist_dir": CHROMA_PERSIST_DIR,
                "embed_model": EMBED_MODEL_NAME,
                "collections": [],
                "error": str(e),
            }

    try:
        client = None
        try:
            PersistentClient = getattr(chromadb, "PersistentClient", None)
            if PersistentClient:
                client = PersistentClient(
                    path=CHROMA_PERSIST_DIR,
                    settings=_ChromaSettings(
                        persist_directory=CHROMA_PERSIST_DIR,
                        anonymized_telemetry=False,
                    ),
                )
        except Exception:
            client = None

        if client is None:
            client = chromadb.Client(
                _ChromaSettings(
                    persist_directory=CHROMA_PERSIST_DIR,
                    anonymized_telemetry=False,
                )
            )
        cols = []
        for c in client.list_collections():
            try:
                col = client.get_collection(name=c.name)
                try:
                    cnt = col.count()  # type: ignore[attr-defined]
                except Exception:
                    data = col.get()
                    cnt = len((data or {}).get("ids") or [])
                cols.append({"name": c.name, "count": int(cnt)})
            except Exception:
                cols.append({"name": c.name, "count": -1})
        return {
            "persist_dir": CHROMA_PERSIST_DIR,
            "embed_model": EMBED_MODEL_NAME,
            "collections": cols,
        }
    except Exception as e:
        return {
            "persist_dir": CHROMA_PERSIST_DIR,
            "embed_model": EMBED_MODEL_NAME,
            "collections": [],
            "error": str(e),
        }


@app.get("/memory/debug")
def memory_debug() -> Dict[str, Any]:
    try:
        return {"ok": True, "debug": _light_debug_dump()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/memory/list")
def memory_list(
    collection: str,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    try:
        col = _col(collection)
        try:
            cnt = col.count()  # type: ignore[attr-defined]
        except Exception:
            data_all = col.get()
            cnt = len(data_all.get("ids") or [])
        try:
            data = col.get(
                include=["documents", "metadatas"],
                limit=limit,
                offset=offset,
            )
        except Exception:
            data = col.get()
        ids = data.get("ids") or []
        docs = data.get("documents") or []
        metas = data.get("metadatas") or []
        items: List[Dict[str, Any]] = []
        for i, _id in enumerate(ids):
            items.append(
                {
                    "id": _id,
                    "document": docs[i] if i < len(docs) else None,
                    "metadata": metas[i] if i < len(metas) else None,
                }
            )
        return {
            "ok": True,
            "collection": collection,
            "count": int(cnt),
            "items": items,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ======================= CHROMA ADVANCED API =========================
class SearchAdvancedReq(BaseModel):
    q: str = Field(..., description="Query testuale")
    k: int = Field(5, ge=1, le=100)
    where: Optional[Dict[str, Any]] = Field(
        None,
        description="Filtri Chroma where{}",
    )
    collections: Optional[List[str]] = Field(
        None,
        description="Override collezioni",
    )


class BetsBatchReq(BaseModel):
    items: List[Dict[str, Any]]


class CleanupReq(BaseModel):
    collection: str = Field(..., description=f"Una tra: {FACTS}, {PREFS}, {BETS}")
    days: int = Field(..., ge=1)
    dry_run: bool = True


class MigrateReq(BaseModel):
    old_name: str
    new_name: str
    new_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    batch_size: int = 500
    delete_old: bool = False


class ReembedReq(BaseModel):
    name: Optional[str] = Field(None, description="Nome collection o 'all'")
    batch: int = 512


@app.post("/memory/search/advanced")
def memory_search_advanced(req: SearchAdvancedReq) -> Dict[str, Any]:
    cols = tuple(req.collections) if req.collections else (FACTS, PREFS, BETS)
    items = search_topk_with_filters(
        query=req.q,
        k=req.k,
        where=req.where,
        collections=cols,
    )
    return {
        "ok": True,
        "q": req.q,
        "k": req.k,
        "where": req.where,
        "collections": list(cols),
        "items": items,
    }


@app.post("/memory/bets/batch")
def memory_bets_batch(req: BetsBatchReq) -> Dict[str, Any]:
    res = add_bets_batch(req.items)
    return {"ok": True, **res}


@app.post("/memory/cleanup")
def memory_cleanup(req: CleanupReq) -> Dict[str, Any]:
    if req.collection == FACTS:
        res = cleanup_old_facts(days=req.days, dry_run=req.dry_run)
    elif req.collection == BETS:
        res = cleanup_old_bets(days=req.days, dry_run=req.dry_run)
    else:
        res = cleanup_old(  # type: ignore[arg-type]
            collection=req.collection,
            older_than_days=req.days,
            dry_run=req.dry_run,
        )
    return {"ok": True, "collection": req.collection, **res}


@app.post("/memory/migrate")
def memory_migrate(req: MigrateReq) -> Dict[str, Any]:
    res = migrate_collection(
        old_name=req.old_name,
        new_name=req.new_name,
        new_model=req.new_model,
        batch_size=req.batch_size,
        delete_old=req.delete_old,
    )
    return {"ok": True, **res}


@app.post("/memory/reembed")
def memory_reembed(req: Optional[ReembedReq] = None) -> Dict[str, Any]:
    try:
        if req is None or (req.name in (None, "", "all")):
            processed = reembed_all(batch=(req.batch if req else 512))
            return {"ok": True, "reembedded": processed}
        count = reembed_collection(req.name, batch=req.batch)
        return {"ok": True, "collection": req.name, "count": count}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ======================= Analytics endpoints =========================
@app.get("/analytics/search/report")
def analytics_report(days: int = 7) -> Dict[str, Any]:
    try:
        if not _ANALYTICS:
            return {"ok": False, "error": "SearchAnalytics non inizializzato."}
        rep = _ANALYTICS.report(days=days)  # type: ignore[attr-defined]
        return {"ok": True, "report": rep, "days": int(days)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/analytics/search/tail")
def analytics_tail(n: int = 100) -> Dict[str, Any]:
    try:
        path = getattr(_ANALYTICS, "path", SEARCH_ANALYTICS_LOG)
        if not os.path.isfile(path):
            return {"ok": True, "path": path, "events": []}
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        tail: List[Any] = []
        for line in lines[-max(1, int(n)) :]:
            try:
                tail.append(json.loads(line))
            except Exception:
                tail.append({"raw": line.strip()})
        return {"ok": True, "path": path, "events": tail}
    except Exception as e:
        return {"ok": False, "error": str(e)}


class ClickTrackReq(BaseModel):
    url: str
    query: Optional[str] = None
    ts: Optional[int] = None


@app.post("/analytics/track_click")
def analytics_track_click(req: ClickTrackReq) -> Dict[str, Any]:
    """Registra un evento di click su una sorgente."""
    try:
        path = getattr(_ANALYTICS, "path", SEARCH_ANALYTICS_LOG)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        ev = {
            "ts": int(req.ts or time.time()),
            "type": "click",
            "url": (req.url or "").strip(),
            "query": (req.query or "").strip(),
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        return {"ok": True, "logged": ev}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ==================== STATS ENDPOINT per LLM Intent (NUOVO) ====================
@app.get("/stats/intent_classifier")
async def intent_classifier_stats() -> Dict[str, Any]:
    """Statistiche LLM Intent Classifier + comparazione con rule-based."""
    result: Dict[str, Any] = {
        "llm": {
            "enabled": bool(LLM_INTENT_ENABLED),
            "available": False,
            "stats": None,
        },
        "rule_based": {
            "enabled": True,
            "available": True,
        },
        "comparison": {
            "note": "LLM provides semantic understanding, rule-based is fallback",
        },
    }
    llm_classifier = get_llm_classifier()
    if llm_classifier:
        result["llm"]["available"] = True
        try:
            result["llm"]["stats"] = llm_classifier.get_stats()
        except Exception as e:
            log.warning(f"LLM Intent get_stats failed: {e}")

    return result


@app.post("/admin/intent_classifier/clear_cache")
async def clear_intent_cache(secret: str = Body(...)) -> Dict[str, Any]:
    """Svuota la cache interna del LLM Intent Classifier."""
    if secret != QUANTUM_SHARED_SECRET:
        return {"ok": False, "error": "unauthorized"}
    llm_classifier = get_llm_classifier()
    if llm_classifier:
        try:
            cleared = llm_classifier.clear_cache()
        except Exception as e:
            log.warning(f"LLM Intent clear_cache failed: {e}")
            return {"ok": False, "error": str(e)}
        return {"ok": True, "cleared_entries": cleared}

    return {"ok": False, "error": "llm_classifier_not_available"}


# ==================== DIVERSITY STATS ENDPOINT (NUOVO) ====================
@app.get("/stats/search_diversity")
async def search_diversity_stats() -> Dict[str, Any]:
    """Statistiche diversità ricerche web."""
    result: Dict[str, Any] = {
        "diversifier": {
            "enabled": DIVERSIFIER_ENABLED,
            "available": _SEARCH_DIVERSIFIER is not None,
            "config": {
                "max_per_domain": DIVERSIFIER_MAX_PER_DOMAIN,
                "preserve_top_n": DIVERSIFIER_PRESERVE_TOP_N,
                "min_unique_domains": DIVERSIFIER_MIN_UNIQUE_DOMAINS,
            },
        },
        "recent_searches": None,
    }
    if not _ANALYTICS:
        return result

    try:
        recent = _ANALYTICS.tail(50)  # type: ignore[attr-defined]
    except Exception as e:
        log.error(f"Diversity stats error (tail): {e}")
        return result

    if not recent:
        return result

    diversity_scores: List[float] = []
    unique_domains_counts: List[int] = []

    for search in recent:
        urls = search.get("result_urls", [])
        if not urls:
            continue
        diversifier = _SEARCH_DIVERSIFIER or get_search_diversifier()
        if not diversifier:
            break
        mock_results = [{"url": u} for u in urls[:10]]
        try:
            analysis = diversifier.analyze_diversity(mock_results)
        except Exception as e:
            log.warning(f"Diversity analyze error: {e}")
            continue
        diversity_scores.append(analysis["diversity_score"])
        unique_domains_counts.append(analysis["unique_domains"])

    if diversity_scores:
        result["recent_searches"] = {
            "samples": len(diversity_scores),
            "avg_diversity_score": round(
                sum(diversity_scores) / len(diversity_scores), 3
            ),
            "avg_unique_domains": round(
                sum(unique_domains_counts) / len(unique_domains_counts), 1
            ),
            "min_unique_domains": min(unique_domains_counts),
            "max_unique_domains": max(unique_domains_counts),
        }

    return result


@app.post("/admin/test_diversity")
async def test_diversity_endpoint(
    query: str = Body(...),
    secret: str = Body(...),
) -> Dict[str, Any]:
    """Test diversification su query specifica (admin only)."""
    if secret != QUANTUM_SHARED_SECRET:
        return {"ok": False, "error": "unauthorized"}
    try:
        try:
            from core.web_search import search as web_search_core
        except Exception as e:
            return {"ok": False, "error": f"web_search_import_failed:{e}"}

        results = web_search_core(query, num=16) or []

        if not results:
            return {"ok": False, "error": "no_results"}

        diversifier = _SEARCH_DIVERSIFIER or get_search_diversifier()
        if not diversifier:
            return {"ok": False, "error": "diversifier_not_available"}

        before = diversifier.analyze_diversity(results[:10])
        after_results = diversifier.diversify(results[:10])
        after = diversifier.analyze_diversity(after_results)

        return {
            "ok": True,
            "query": query,
            "total_results": len(results),
            "before": before,
            "after": after,
            "improvement": {
                "unique_domains": after["unique_domains"]
                - before["unique_domains"],
                "diversity_score": round(
                    after["diversity_score"] - before["diversity_score"],
                    3,
                ),
            },
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
