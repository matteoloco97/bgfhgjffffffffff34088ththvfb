#!/usr/bin/env python3
# backend/quantum_api.py — Smart routing + Chroma + Auto-Save + Semantic Cache
# Patch 2025-11: token budget hard-cap, /web/summarize (url|q), no-error to user, feedback toggle
# + env parsing robusto + Semantic Cache lazy (no import pesanti al boot)
# + meta-capability override (mai web) + /web/search endpoint
# + ZERO-WEB GUARD: smalltalk/very-short → blocco WEB (pipeline + endpoint + generate)
# + NO GENERIC FALLBACK (stop ANSA/Wikipedia) + note='non_web_query' per il bot
# + PATCH Step 2: Parallel fetching con timeout per-URL, early-exit, metriche fetch, timeout su /web_read
# + PATCH Step 2b: Web validator (consensus) + search analytics (p50/p90, CTR, cache-hit)
# + PATCH Guard relax: consentite query a 2 parole (es. “prezzo bitcoin”)
# + PATCH Warm hardening: niente 500, init cache garantita, errori raccolti
# + PATCH Explain-Guard: forza DIRECT_LLM per "spiega / che cos'è / what is" (no web)
# + PATCH Analytics endpoints: /analytics/search/report, /analytics/search/tail, /analytics/track_click
# + PATCH 2025-11 mini-cache web: /web/cache/stats, /web/cache/flush (LRU+TTL+ETag/Last-Modified in core/web_tools)
# + PATCH 2025-11 WebResearchAgent: /web/research orchestratore multi-step (Claude-style)
# + PATCH 2025-11 Web summary direct: LLM sempre responsivo, niente "apri la fonte"
# + PATCH 2025-11 SearchDiversifier: diversificazione domini post-rerank
# + PATCH 2025-11 Synthesis aggressive: prompt robusti per _web_search_pipeline e /web/summarize URL

import os, sys, re, asyncio
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi import FastAPI, Request, Body
import requests, json, time, hashlib, redis, logging, math
from typing import Optional, List, Dict, Tuple, Any
from dotenv import load_dotenv
from urllib.parse import urlparse

# (per /memory/debug leggero)
try:
    import chromadb
    from chromadb.config import Settings as _ChromaSettings  # type: ignore
except Exception:
    chromadb = None
    _ChromaSettings = None  # type: ignore

# === CORE ===
from core.persona_store import get_persona, set_persona, reset_persona
from core.web_tools import fetch_and_extract
# Mini-cache web (import resiliente)
try:
    from core.web_tools import minicache_stats as _webcache_stats, minicache_flush as _webcache_flush
except Exception:
    def _webcache_stats() -> Dict[str, Any]:
        return {"enabled": False, "error": "web minicache not available"}
    def _webcache_flush(url: Optional[str] = None) -> Dict[str, Any]:
        return {"flushed": 0, "notice": "web minicache not available", **({"url": url} if url else {})}

from core.chat_engine import reply_with_llm
from core.memory_autosave import autosave

# Web research orchestrator (Claude-style)
try:
    from agents.web_research_agent import WebResearchAgent
except Exception:
    WebResearchAgent = None  # type: ignore

# Smart intent
from core.smart_intent_classifier import SmartIntentClassifier
try:
    from core.intent_feedback import IntentFeedbackSystem
except Exception:
    class IntentFeedbackSystem:
        def record_feedback(self, **kwargs): pass

# Validator + Analytics (safe import, opzionali)
try:
    from core.web_validator import SourceValidator
except Exception:
    SourceValidator = None  # type: ignore
try:
    from utils.search_analytics import SearchAnalytics
except Exception:
    SearchAnalytics = None  # type: ignore

_VALIDATOR = SourceValidator() if SourceValidator else None
_ANALYTICS = SearchAnalytics() if SearchAnalytics else None

# ── Semantic Cache: import LAZY (evita import torch al boot) ─────────
_SEMCACHE: Optional[Any] = None
_SCM_IMPORTED = False
def _ensure_semcache_import():
    """Importa core.semantic_cache solo al primo uso."""
    global _SCM_IMPORTED, SemanticCache, get_semantic_cache
    if _SCM_IMPORTED:
        return
    try:
        from core.semantic_cache import get_semantic_cache as _gsc, SemanticCache as _SC
    except Exception:
        from Core.semantic_cache import get_semantic_cache as _gsc, SemanticCache as _SC  # type: ignore
    globals()['get_semantic_cache'] = _gsc
    globals()['SemanticCache'] = _SC
    _SCM_IMPORTED = True

# search helpers
from core.source_policy import pick_domains
from core.web_querybuilder import build_query_variants
from core.reranker import Reranker

# Search diversifier (multi-domain)
try:
    from core.search_diversifier import SearchDiversifier
except Exception:
    SearchDiversifier = None  # type: ignore

# === Token budget util ===
try:
    from core.token_budget import approx_tokens, trim_to_tokens
except Exception:
    def approx_tokens(s: str) -> int:
        return math.ceil(len(s or "") / 4)
    def trim_to_tokens(s: str, max_tokens: int) -> str:
        if not s or max_tokens <= 0: return ""
        max_chars = max_tokens * 4
        return s[:max_chars]

# === MEMORY (ChromaDB) ===
from pydantic import BaseModel, Field
from utils.chroma_handler import (
    ensure_collections, add_fact, add_pref, add_bet, search_topk,
    debug_dump, _substring_fallback,
    FACTS, PREFS, BETS, _col, reembed_all,
    search_topk_with_filters, add_bets_batch,
    cleanup_old_facts, cleanup_old_bets, cleanup_old,
    migrate_collection, reembed_collection,
)

BUILD_SIGNATURE = "smart-intent-2025-11-13+env-safe+lazy-semcache+token-budget+summarize-q+no-error-user+feedback-toggle+web-search-endpoint+meta-override+zero-web-guard+no-generic-fallback+parallel-fetch-v1+validator+analytics+guard-relax+warm-harden+explain-guard+analytics-endpoints+web-minicache-endpoints+web-research-agent+web-summary-direct+search-diversifier+synthesis-aggressive-v1"

load_dotenv()
app = FastAPI()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ============================= ENV ===================================

# Helpers per env robuste (tollerano commenti inline)
def env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)) or str(default)
    m = re.search(r"-?\d+", raw)
    try: return int(m.group(0)) if m else int(default)
    except Exception: return int(default)

def env_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default)) or str(default)
    m = re.search(r"-?\d+(?:\.\d+)?", raw)
    try: return float(m.group(0)) if m else float(default)
    except Exception: return float(default)

def env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name, "1" if default else "0") or "").strip().lower()
    return raw in ("1","true","yes","on")

ENV_LLM_ENDPOINT    = os.getenv("LLM_ENDPOINT")
ENV_TUNNEL_ENDPOINT = os.getenv("TUNNEL_ENDPOINT")
LLM_MODEL           = os.getenv("LLM_MODEL","qwen2.5-32b-awq")
TEMPERATURE         = env_float("LLM_TEMPERATURE", 0.7)
MAX_TOKENS          = env_int("LLM_MAX_TOKENS", 512)

# 🔒 Budget/contesto
LLM_MAX_CTX               = env_int("LLM_MAX_CTX", 8192)
LLM_OUTPUT_BUDGET_TOK     = env_int("LLM_OUTPUT_BUDGET_TOK", MAX_TOKENS)
LLM_SAFETY_MARGIN_TOK     = env_int("LLM_SAFETY_MARGIN_TOK", 256)
WEB_SUMMARY_BUDGET_TOK    = env_int("WEB_SUMMARY_BUDGET_TOK", 1200)
WEB_EXTRACT_PER_DOC_TOK   = env_int("WEB_EXTRACT_PER_DOC_TOK", 700)
WEB_SUMMARIZE_TOP_DEFAULT = env_int("WEB_SUMMARIZE_TOP_DEFAULT", 2)

# ⚡️ Parallel fetch env
WEB_FETCH_TIMEOUT_S       = env_float("WEB_FETCH_TIMEOUT_S", 3.0)
WEB_FETCH_MAX_INFLIGHT    = env_int("WEB_FETCH_MAX_INFLIGHT", 4)
WEB_READ_TIMEOUT_S        = env_float("WEB_READ_TIMEOUT_S", 6.0)

# Feedback back-end (telemetria, NON addestra il modello)
INTENT_FEEDBACK_ENABLED   = env_bool("INTENT_FEEDBACK_ENABLED", False)

# Semantic Cache init mode
SEMCACHE_INIT_ON_STARTUP  = env_bool("SEMCACHE_INIT_ON_STARTUP", False)

REDIS_HOST = os.getenv("REDIS_HOST","localhost")
REDIS_PORT = env_int("REDIS_PORT", 6379)
REDIS_DB   = env_int("REDIS_DB", 0)
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)

USE_RERANKER    = env_bool("USE_RERANKER", True)
RERANKER_MODEL  = os.getenv("RERANKER_MODEL","BAAI/bge-reranker-base")
RERANKER_DEVICE = os.getenv("RERANKER_DEVICE","cpu")

# Diversifier
DIVERSIFIER_ENABLED        = env_bool("DIVERSIFIER_ENABLED", True)
DIVERSIFIER_MAX_PER_DOMAIN = env_int("DIVERSIFIER_MAX_PER_DOMAIN", 2)

# Chroma
MEM_HALF_LIFE_D   = env_float("MEM_HALF_LIFE_D", 7.0)
CHROMA_PERSIST_DIR= os.getenv("CHROMA_PERSIST_DIR", "/memory/chroma")
EMBED_MODEL_NAME  = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")

# Admin
QUANTUM_SHARED_SECRET = os.getenv("QUANTUM_SHARED_SECRET", "")

# Analytics file path (fallback se _ANALYTICS non disponibile)
SEARCH_ANALYTICS_LOG = os.getenv("SEARCH_ANALYTICS_LOG", "/root/quantumdev-open/logs/search_analytics.jsonl")

_SMART_INTENT = SmartIntentClassifier()
_INTENT_FB    = IntentFeedbackSystem()
_reranker: Optional[Reranker] = None

# SearchDiversifier singleton (safe init)
try:
    if SearchDiversifier and DIVERSIFIER_ENABLED:
        _SEARCH_DIVERSIFIER: Optional[Any] = SearchDiversifier(
            max_per_domain=DIVERSIFIER_MAX_PER_DOMAIN
        )
    else:
        _SEARCH_DIVERSIFIER = None
except Exception as e:
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

def get_reranker()->Optional[Reranker]:
    global _reranker
    if not USE_RERANKER: return None
    if _reranker is None:
        try:
            log.info(f"Init Reranker: {RERANKER_MODEL} on {RERANKER_DEVICE}")
            _reranker = Reranker(model=RERANKER_MODEL, device=RERANKER_DEVICE)
        except Exception as e:
            log.error(f"Reranker init failed: {e}")
            return None
    return _reranker

def _normalize_base(u:str)->str: return u.rstrip("/")
def _is_chat_url(u:str)->bool:   return "/v1/chat/completions" in u
def _build_chat_url(base_or_chat:str)->str:
    u = _normalize_base(base_or_chat)
    if _is_chat_url(u): return u
    if u.endswith("/v1"): return f"{u}/chat/completions"
    return f"{u}/v1/chat/completions"

def _get_redis_str(k:str)->Optional[str]:
    v = redis_client.get(k)
    return v.decode() if v else None

def get_endpoints()->List[str]:
    tunnel = _get_redis_str("gpu_tunnel_endpoint") or ENV_TUNNEL_ENDPOINT
    direct = _get_redis_str("gpu_active_endpoint") or ENV_LLM_ENDPOINT
    out=[]
    if tunnel: out.append(_build_chat_url(tunnel))
    if direct:
        u=_build_chat_url(direct)
        if u not in out: out.append(u)
    return out

def hash_prompt(prompt:str, system:str, temperature:float, max_tokens:int, model:str)->str:
    h=hashlib.sha256()
    for piece in (prompt.strip().lower(), system.strip().lower(), str(temperature), str(max_tokens), model):
        h.update(piece.encode("utf-8"))
    return h.hexdigest()

def _wrap(text:str, model:str)->Dict:
    now=int(time.time())
    return {
        "id":f"chatcmpl-router-{now}",
        "object":"chat.completion",
        "created":now,
        "model":model,
        "choices":[{"index":0,"message":{"role":"assistant","content":text},"finish_reason":"stop"}],
        "usage":{"prompt_tokens":0,"completion_tokens":0,"total_tokens":0}
    }

def _run_direct(payload:Dict, force:Optional[str])->Tuple[Optional[Dict],Optional[str],Optional[str]]:
    endpoints=get_endpoints()
    if force=="tunnel":
        endpoints=[e for e in endpoints if "trycloudflare.com" in e]+[e for e in endpoints if "trycloudflare.com" not in e]
    elif force=="direct":
        endpoints=[e for e in endpoints if "trycloudflare.com" not in e]+[e for e in endpoints if "trycloudflare.com" in e]
    last=None
    for url in endpoints:
        try:
            r=requests.post(url,json=payload,timeout=30); r.raise_for_status()
            return r.json(), url, None
        except Exception as e:
            last=str(e)
    return None, None, last

def _domain(u:str)->str:
    try:
        h=urlparse(u).hostname or ""
        parts=h.split("."); return ".".join(parts[-2:]) if len(parts)>=2 else h
    except Exception:
        return ""

def _boost(results:List[Dict], prefer:List[str])->List[Dict]:
    pref=set(prefer or [])
    scored=[]
    for i,r in enumerate(results):
        base=1.0/(i+1.0); boost=2.0 if _domain(r.get("url","")) in pref else 1.0
        rr=dict(r); rr["_score"]=base*boost; scored.append(rr)
    scored.sort(key=lambda x:x["_score"], reverse=True)
    return scored

def _postboost_ranked(ranked: List[Dict], prefer: List[str]) -> List[Dict]:
    pref = set(prefer or [])
    for r in ranked:
        dom = _domain(r.get("url",""))
        if dom in pref:
            r["rerank_score"] = (r.get("rerank_score") or 0.0) + 0.20
    return sorted(
        ranked,
        key=lambda x: ((x.get("rerank_score") or 0.0), (x.get("_score") or 0.0)),
        reverse=True
    )

# 🔧 Niente fallback generico: solo meteo/prezzi. Se vuoto → [].
def _safe_fallback_links(q: str) -> List[Dict]:
    s = (q or "").lower()
    out: List[Dict] = []
    def add(u,t): out.append({"url":u,"title":t})
    if "meteo" in s or "che tempo" in s or "weather" in s:
        add("https://www.meteoam.it/it/roma", "Meteo Aeronautica Militare – Roma")
        add("https://www.ilmeteo.it/meteo/Roma", "ILMETEO – Roma")
        add("https://www.3bmeteo.com/meteo/roma", "3B Meteo – Roma")
    if any(k in s for k in ["prezzo","quotazione","quanto vale","btc","bitcoin","eth","ethereum","eurusd","eur/usd","borsa","azioni","indice","cambio"]):
        add("https://coinmarketcap.com/currencies/bitcoin/","Bitcoin (BTC) – CoinMarketCap")
        add("https://www.coindesk.com/price/bitcoin/","Bitcoin Price – CoinDesk")
        add("https://www.binance.com/en/trade/BTC_USDT","BTC/USDT – Binance")
        add("https://www.investing.com/crypto/bitcoin/btc-usd","BTC/USD – Investing.com")
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

import hashlib as _hashlib
def _semcache_dualwrite(prompt: str, system_prompt: str, model_name: str, used_intent: str, response_obj: Dict):
    try:
        if not _SEMCACHE:
            return
        _ensure_semcache_import()
        now_ts = int(time.time())
        qh = _hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]
        base_meta = {"intent": used_intent, "model": model_name, "ts": now_ts, "q": prompt, "q_hash": qh}
        ctx_fp_intent = SemanticCache.fingerprint(system_prompt, model_name, used_intent)
        _SEMCACHE.set(prompt, response_obj, ctx_fp_intent, meta=base_meta)
        ctx_fp_auto = SemanticCache.fingerprint(system_prompt, model_name, "AUTO")
        _SEMCACHE.set(prompt, response_obj, ctx_fp_auto, meta={**base_meta, "dual": True})
    except Exception as e:
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
    "Rispondo diretto quando basta conoscenza generale; uso il web solo per dati live "
    "(meteo, prezzi, risultati, orari, breaking news) e cito almeno una fonte. "
    "Non accedo a file o dispositivi dell’utente."
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
    r"\bexplain\b"
]
def _is_explain_query(q: str) -> bool:
    s = (q or "").lower()
    return any(re.search(p, s) for p in _EXPLAIN_PATTERNS)

# --------- ZERO-WEB GUARD (smalltalk/very-short) ---------------------

_SMALLTALK_RE = re.compile(r"""(?ix)^\s*(  
    ciao|hey|hi|hello|salve|buongiorno|buonasera|buonanotte|  
    ci\s*sei\??|sei\s*online\??|come\s+va\??|ok+|perfetto|grazie|thanks  
)\b""")

def _is_quick_live_query(q: str) -> bool:
    s = (q or "").lower()
    return any(k in s for k in ["meteo", "che tempo", "weather", "prezzo", "quotazione", "risultati", "classifica", "orari"])

# ✅ Guard rilassata: non bloccare 2 parole, e mai bloccare live-query a 2 parole (es. “prezzo bitcoin”)
def _is_smalltalk_query(q: str) -> bool:
    s = (q or "").strip().lower()
    if _SMALLTALK_RE.search(s):
        return True
    tokens = s.split()
    if len(tokens) <= 1:
        return True
    if len(tokens) <= 2:
        return False
    return False

# ===================== Web search pipeline ===========================

async def _web_search_pipeline(q:str, src:str, sid:str, k:int, nsum:int)->Dict:
    t_start = time.perf_counter()
    # 🔒 Guard: non cercare MAI su smalltalk
    if _is_smalltalk_query(q):
        return {"query": q, "policy_used": {}, "results": [], "summary": "",
                "note": "non_web_query", "reranker_used": False,
                "stats": {"raw_results": 0, "dedup_results": 0, "returned": 0}}

    pol = pick_domains(q)
    variants = build_query_variants(q, pol)

    try:
        from core.web_search import search as web_search_core
    except Exception as e:
        return {"error":"Backend web_search non configurato (core/web_search.py).","_exception":str(e)}

    raw=[]
    for v in variants:
        try: raw.extend(web_search_core(v, num=6))
        except Exception: pass

    seen=set(); dedup=[]
    for r in raw:
        u=r.get("url")
        if not u or u in seen: continue
        dedup.append({"url":u,"title":r.get("title",""),"snippet":r.get("snippet", r.get("title",""))}); seen.add(u)

    if not dedup:
        return {"query":q,"policy_used":pol,"results":[],"summary":"",
                "note":"SERP vuota","reranker_used":False,
                "stats":{"raw_results":len(raw),"dedup_results":0,"returned":0}}

    reranker=get_reranker()
    if reranker:
        try:
            ranked=reranker.rerank(query=q, results=dedup, top_k=k); used=True
        except Exception:
            ranked=_boost(dedup, pol.get("prefer",[])); used=False
    else:
        ranked=_boost(dedup, pol.get("prefer",[])); used=False

    # Post-boost + Diversifier
    ranked = _postboost_ranked(ranked, pol.get("prefer", []))
    if _SEARCH_DIVERSIFIER and len(ranked) > 0:
        try:
            ranked = _SEARCH_DIVERSIFIER.diversify(ranked, top_k=k)
        except Exception as e:
            log.warning(f"Search diversifier error: {e}")

    topk=ranked[:max(1,k)]

    # ====== Parallel fetching con timeout + early-exit (robusto a CancelledError) ======
    candidates = topk[:max(1, min(len(topk), nsum*2))]
    extracts: List[Dict[str, str]] = []
    timeouts = 0
    errors = 0
    attempted = 0

    async def _fetch_with_timeout(item: Dict[str, str]) -> Optional[Dict[str, str]]:
        nonlocal timeouts, errors, attempted
        attempted += 1
        try:
            text, _ = await asyncio.wait_for(fetch_and_extract(item["url"]), timeout=WEB_FETCH_TIMEOUT_S)
            if text:
                trimmed = trim_to_tokens(text, WEB_EXTRACT_PER_DOC_TOK)
                return {"url": item["url"], "title": item["title"], "text": trimmed}
            return None
        except asyncio.TimeoutError:
            timeouts += 1
            return None
        except asyncio.CancelledError:
            # Trattiamo la cancellazione come un fetch fallito/timeout, NON propaghiamo
            timeouts += 1
            return None
        except Exception:
            errors += 1
            return None

    t_fetch0 = time.perf_counter()
    inflight_limit = max(1, WEB_FETCH_MAX_INFLIGHT)
    max_docs = max(0, nsum)

    sem = asyncio.Semaphore(inflight_limit)

    async def _worker(item: Dict[str, str]) -> Optional[Dict[str, str]]:
        async with sem:
            return await _fetch_with_timeout(item)

    tasks: List[asyncio.Task] = [asyncio.create_task(_worker(it)) for it in candidates]

    if tasks:
        try:
            for t in asyncio.as_completed(tasks):
                try:
                    res = await t
                except asyncio.CancelledError:
                    # Task cancellato (es. early-exit o chiusura connessione) → ignora
                    continue
                except Exception:
                    errors += 1
                    continue

                if isinstance(res, dict) and "text" in res:
                    extracts.append(res)
                    if len(extracts) >= max_docs and max_docs > 0:
                        # early-exit: cancella i task ancora pendenti
                        for other in tasks:
                            if not other.done():
                                other.cancel()
                        break
        finally:
            # Assicura che eventuali cancellazioni vengano "drainate"
            await asyncio.gather(*tasks, return_exceptions=True)

    fetch_duration_ms = int((time.perf_counter() - t_fetch0) * 1000)

    # Validazione multi-fonte (consensus) — opzionale
    validation = None
    if _VALIDATOR and extracts:
        try:
            validation = _VALIDATOR.validate_consensus(q, extracts[:max(0, nsum)])  # type: ignore[attr-defined]
        except Exception:
            validation = None

    # 🔎 Sintesi generale: risposta diretta, niente "apri la fonte"
    summary = ""
    # teniamo traccia se la query è "live" (solo per analytics / note, non per il testo)
    note = "live_query" if _is_quick_live_query(q) else None

    if extracts:
        persona = await get_persona(src, sid)
        ctx = "\n\n".join(
            [f"### {e['title']}\nURL: {e['url']}\n\n{e['text']}" for e in extracts[:max(0, nsum)]]
        )
        ctx = trim_to_tokens(ctx, WEB_SUMMARY_BUDGET_TOK)

        prompt = (
            "RUOLO: sei un assistente che risponde usando SOLO le informazioni negli estratti dal web qui sotto.\n"
            "\n"
            "OBIETTIVO: rispondere alla DOMANDA in modo chiaro, concreto e utile.\n"
            "\n"
            "REGOLE CRITICHE (seguile alla lettera):\n"
            "1. Usa SOLO informazioni presenti negli estratti: non aggiungere fatti, numeri o dettagli che non compaiono nei testi.\n"
            "2. Se ci sono numeri (prezzi, date, percentuali, quantità, ecc.), riportali chiaramente specificando l'unità.\n"
            "3. Se i dati sono parziali o non rispondono perfettamente alla domanda, dillo esplicitamente MA riassumi comunque ciò che è disponibile.\n"
            "4. NON usare frasi come: 'le fonti non contengono abbastanza informazioni', 'consulta le fonti', "
            "'apri il link', 'cerca su Google': devi fornire tu la migliore risposta possibile sulla base degli estratti.\n"
            "5. Se le fonti sono discordanti, spiega brevemente le differenze e, se possibile, indica quale sembra più affidabile "
            "(es. fonte ufficiale, sito principale, documentazione tecnica).\n"
            "6. Tono: professionale ma semplice, niente frasi vaghe o generiche. Vai dritto al punto.\n"
            "7. Lunghezza: di solito 3–8 frasi; allungala solo se serve davvero per essere chiaro.\n"
            "\n"
            "ESEMPI DI RISPOSTE DA EVITARE (NON SCRIVERLE MAI):\n"
            "- 'Le fonti non contengono informazioni sufficienti, ti consiglio di aprirle.'\n"
            "- 'Non posso rispondere perché non vedo abbastanza dati nelle fonti.'\n"
            "- 'Per dettagli aggiornati apri il sito o consulta altre fonti.'\n"
            "\n"
            "Se gli estratti NON parlano affatto della domanda, spiega in modo diretto cosa contengono invece "
            "(es. 'Le fonti parlano di X e Y, ma non contengono informazioni su Z').\n"
            "\n"
            f"DOMANDA: {q}\n\n"
            f"ESTRATTI DAL WEB (riassumili e usali per rispondere):\n{ctx}"
        )

        try:
            summary = await reply_with_llm(prompt, persona)
        except Exception:
            summary = ""
            note = note or "llm_summary_failed"
    else:
        # nessun contenuto testuale estratto dalle fonti
        note = note or "no_extracted_content"

    try:
        if summary:
            asv = autosave(summary, source="web_search")
            if any([asv.get("facts"), asv.get("prefs"), asv.get("bet")]):
                log.info(f"[autosave:web_search] {asv}")
    except Exception as e:
        log.warning(f"AutoSave web_search failed: {e}")

    stats = {
        "raw_results": len(raw),
        "dedup_results": len(dedup),
        "returned": len(topk),
        "fetch_attempted": attempted,
        "fetch_ok": len([e for e in extracts if "text" in e]),
        "fetch_timeouts": timeouts,
        "fetch_errors": errors,
        "fetch_duration_ms": fetch_duration_ms,
        "validation_confidence": (validation or {}).get("confidence") if validation else None
    }

    # Analytics file-based (opzionale)
    if _ANALYTICS:
        try:
            _ANALYTICS.track_search(
                query=q,
                results=topk,
                user_interaction={
                    "latency_ms": int((time.perf_counter() - t_start) * 1000),
                    "reranker_used": used,
                    "cached": False
                }
            )
        except Exception:
            pass

    return {
        "query": q,
        "policy_used": pol,
        "results":[{"url":r["url"],"title":r["title"],"rerank_score":r.get("rerank_score"),"_score":r.get("_score")} for r in topk],
        "summary": summary,
        "validation": validation,
        "reranker_used": used,
        "note": note,
        "stats": stats
    }

# ========================= API Endpoints =============================

@app.on_event("startup")
def _init_memory():
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
            _SEMCACHE = get_semantic_cache()
            log.info(f"Semantic cache ready: {json.dumps(_SEMCACHE.stats())}")
        except Exception as e:
            log.error(f"Semantic cache init failed: {e}")

@app.get("/healthz")
def healthz():
    rer_status="disabled"
    if USE_RERANKER:
        rer_status="ready" if get_reranker() else "failed"

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

    return {
        "ok": True,
        "model": LLM_MODEL,
        "endpoints_to_try": get_endpoints(),
        "reranker": {"enabled": USE_RERANKER, "status": rer_status, "model": RERANKER_MODEL if USE_RERANKER else None},
        "redis": {"gpu_tunnel_endpoint": _get_redis_str("gpu_tunnel_endpoint"), "gpu_active_endpoint": _get_redis_str("gpu_active_endpoint")},
        "semantic_cache": cache_info,
        "smart_intent": True,
        "feedback_enabled": INTENT_FEEDBACK_ENABLED,
        "router_build": BUILD_SIGNATURE
    }

# --------- Cache stats (ns / all) + flush ---------

@app.get("/stats/cache")
def cache_stats(ns: Optional[str] = None, all: bool = False):  # noqa: A002
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
def cache_flush(req: FlushReq):
    global _SEMCACHE
    try:
        if _SEMCACHE is None:
            try:
                _ensure_semcache_import()
                _SEMCACHE = get_semantic_cache()
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
def endpoints_list():
    return {
        "active_env": ENV_LLM_ENDPOINT,
        "tunnel_env": ENV_TUNNEL_ENDPOINT,
        "active_redis": _get_redis_str("gpu_active_endpoint"),
        "tunnel_redis": _get_redis_str("gpu_tunnel_endpoint"),
        "resolved": get_endpoints()
    }

class EndpointsUpdateReq(BaseModel):
    active: Optional[str] = None
    tunnel: Optional[str] = None
    secret: Optional[str] = None

@app.post("/endpoints/update")
def endpoints_update(req: EndpointsUpdateReq, request: Request):
    provided = req.secret or request.headers.get("x-quantum-secret") or ""
    if QUANTUM_SHARED_SECRET and provided != QUANTUM_SHARED_SECRET:
        return {"ok": False, "error": "unauthorized"}

    changed = {}
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
async def cache_warm(req: WarmReq):
    try:
        sys_prompt = req.system or (await get_persona("global", "default")) or "Sei una GPT neutra e modulare."
        model = (req.model or LLM_MODEL).strip()

        # Assicura inizializzazione semantic cache
        global _SEMCACHE
        _ensure_semcache_import()
        if _SEMCACHE is None:
            _SEMCACHE = get_semantic_cache()

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
                    {"role": "user", "content": p}
                ],
                "temperature": TEMPERATURE,
                "max_tokens": 256
            }
            result, _, last_err = _run_direct(payload, force=None)
            if result:
                try:
                    _semcache_dualwrite(p, sys_prompt, model, "DIRECT_LLM", result)
                    done += 1
                except Exception as e:
                    errors.append(f"semcache_write:{str(e)}")
            else:
                errors.append(f"llm_call:{last_err or 'unknown'}")

        return {"ok": True, "warmed": done, "errors": errors}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ------------------------- Generate -------------------------

def _fb_record(**kw):
    if INTENT_FEEDBACK_ENABLED:
        try: _INTENT_FB.record_feedback(**kw)
        except Exception: pass

@app.post("/generate")
async def generate(request: Request, force: Optional[str] = None):
    # >>> PATCH: evita UnboundLocalError — dichiara e inizializza la semcache all'inizio <<<
    global _SEMCACHE
    try:
        _ensure_semcache_import()
        if _SEMCACHE is None:
            _SEMCACHE = get_semantic_cache()
    except Exception:
        pass
    # -------------------------------------------------------------------

    data = await request.json()
    prompt = (data.get("prompt") or "").strip()
    if not prompt: return {"error":"Prompt mancante."}
    if force not in (None,"tunnel","direct"): return {"error":"Parametro 'force' non valido. Usa 'tunnel' o 'direct'."}

    try:
        system_prompt = (data.get("system") or await get_persona("global","default") or "Sei una GPT neutra e modulare.").strip()
    except Exception:
        system_prompt = "Sei una GPT neutra e modulare."
    temperature=env_float("LLM_TEMPERATURE", TEMPERATURE) if "temperature" not in data else float(data.get("temperature"))
    max_tokens=env_int("LLM_MAX_TOKENS", MAX_TOKENS) if "max_tokens" not in data else int(data.get("max_tokens"))
    model_name=(data.get("model") or LLM_MODEL).strip()

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
            ctx_fp_auto = SemanticCache.fingerprint(system_prompt, model_name, "AUTO")
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
                _fb_record(query=prompt, intent_used="CACHE_SEMANTIC", satisfaction=1.0, response_time_s=0.005)
                return out
    except Exception as e:
        log.warning(f"Semantic cache pre-route error: {e}")

    route = _SMART_INTENT.classify(prompt)
    used_intent = (route.get("intent") or "DIRECT_LLM").upper()

    # 🔒 Guard: se smalltalk/very-short, forza DIRECT_LLM
    if _is_smalltalk_query(prompt) and used_intent in ("WEB_SEARCH", "WEB_READ"):
        used_intent = "DIRECT_LLM"

    # 🔒 Explain-guard: se è una richiesta di spiegazione e NON è una live-query, forza DIRECT_LLM
    if _is_explain_query(prompt) and not _is_quick_live_query(prompt):
        used_intent = "DIRECT_LLM"

    # Override: domande meta/capability → mai web (e aggiungi breve sommario capacità)
    if _is_meta_capability_query(prompt):
        used_intent = "DIRECT_LLM"
        system_prompt = (system_prompt + "\n\n"
                         "Contesto: l'utente chiede delle TUE capacità. "
                         "Rispondi in modo conciso e non usare il web. "
                         f"Breve sommario: {_CAPABILITIES_BRIEF}").strip()

    cache_key = "cache:"+hash_prompt(prompt, system_prompt, temperature, max_tokens, model_name)+f":{used_intent}"
    cached = redis_client.get(cache_key)
    if cached:
        try: return json.loads(cached)
        except Exception: pass

    out = {"ok": True, "intent": used_intent, "confidence": route.get("confidence"), "reason": route.get("reason"), "router_build": BUILD_SIGNATURE}
    t0 = time.perf_counter()

    # === Semantic cache (post-route, pre-LLM) ===
    try:
        if _SEMCACHE:
            _ensure_semcache_import()
            ctx_fp = SemanticCache.fingerprint(system_prompt, model_name, used_intent)
            hit2 = _SEMCACHE.get(prompt, ctx_fp)
            if hit2:
                sim2 = hit2.get("similarity")
                if sim2 is None:
                    meta_q2 = ((hit2.get("meta") or {}).get("q") or "")
                    sim2 = _cheap_similarity(prompt, meta_q2)
                out.update({
                    "cached": True,
                    "intent": "CACHE_SEMANTIC",
                    "reason": (out.get("reason") or "") + "|semantic_hit_pre_llm",
                    "similarity": sim2,
                    "response": hit2["response"],
                })
                _fb_record(query=prompt, intent_used="CACHE_SEMANTIC", satisfaction=1.0, response_time_s=0.005)
                redis_client.setex(cache_key, 86400, json.dumps(out))
                return out
    except Exception as e:
        log.warning(f"Semantic cache pre-llm error: {e}")

    try:
        if used_intent=="WEB_READ":
            url = route.get("url")
            if url:
                try:
                    text,_=await asyncio.wait_for(fetch_and_extract(url), timeout=WEB_READ_TIMEOUT_S)
                except asyncio.TimeoutError:
                    text = ""
                trimmed = trim_to_tokens(text or "", WEB_SUMMARY_BUDGET_TOK)
                persona = system_prompt
                msg = (
                    "RUOLO: stai leggendo il contenuto di una singola pagina web.\n"
                    "\n"
                    "OBIETTIVO: riassumere la pagina in modo utile per l'utente.\n"
                    "\n"
                    "REGOLE CRITICHE:\n"
                    "1. Riassumi in 5–10 punti chiave molto concreti (usa elenco puntato).\n"
                    "2. Usa SOLO le informazioni presenti nel testo fornito: non inventare dati.\n"
                    "3. Se ci sono numeri importanti (prezzi, date, percentuali, quantità), riportali indicando l'unità.\n"
                    "4. Se il contenuto è incompleto o poco chiaro, dillo esplicitamente ma riassumi comunque ciò che è disponibile.\n"
                    "5. NON dire all'utente di 'aprire la fonte' o 'consultare il sito' per avere i dettagli: la tua risposta deve essere autosufficiente.\n"
                    "6. Alla fine, se utile, proponi in 1–2 frasi eventuali prossimi passi pratici (es. 'puoi confrontare X con Y', 'verifica la sezione Z se ti interessa...').\n"
                    "\n"
                    "EVITA frasi vaghe come 'le informazioni potrebbero non essere aggiornate' "
                    "se il testo non lo dice esplicitamente.\n"
                    "\n"
                    f"URL: {url}\n\n"
                    f"TESTO PAGINA:\n{trimmed}"
                )
                try:
                    summary = await reply_with_llm(msg, persona)
                except Exception:
                    summary = "Non sono riuscito a generare un riassunto strutturato, ma il contenuto potrebbe comunque essere utile se consultato direttamente."

                try:
                    if summary:
                        asv = autosave(summary, source="web_read")
                        if any([asv.get("facts"), asv.get("prefs"), asv.get("bet")]):
                            log.info(f"[autosave:web_read] {asv}")
                except Exception as e:
                    log.warning(f"AutoSave web_read failed: {e}")

                out.update({"cached":False, "response":_wrap(summary, model_name), "source_url": url})
                _fb_record(query=prompt, intent_used="WEB_READ", satisfaction=1.0, response_time_s=time.perf_counter()-t0)
                _ensure_semcache_import()
                if _SEMCACHE is None:
                    try: _SEMCACHE = get_semantic_cache()
                    except Exception: pass
                _semcache_dualwrite(prompt, system_prompt, model_name, used_intent, out["response"])
                redis_client.setex(cache_key, 86400, json.dumps(out))
                return out
            else:
                used_intent="DIRECT_LLM"
                out["intent"]=used_intent
                out["reason"]=(out.get("reason") or "")+"|url_missing_fallback"

        if used_intent=="WEB_SEARCH":
            ws = await _web_search_pipeline(q=prompt, src="global", sid="default",
                                            k=int(data.get("k",8)), nsum=int(data.get("summarize_top", WEB_SUMMARIZE_TOP_DEFAULT)))
            results = ws.get("results") or []
            summary = (ws.get("summary") or "").strip()
            note = ws.get("note")

            # ❌ Niente fallback generico: se vuoto, segnala e basta
            if not results:
                out.update({
                    "cached": False,
                    "response": _wrap(summary or "", model_name),
                    "web": {"results": [], "reranker_used": False, "stats": ws.get("stats", {})},
                    "note": note or "non_web_query"
                })
                _fb_record(query=prompt, intent_used="WEB_SEARCH", satisfaction=0.6, response_time_s=time.perf_counter()-t0)
                _ensure_semcache_import()
                if _SEMCACHE is None:
                    try: _SEMCACHE = get_semantic_cache()
                    except Exception: pass
                _semcache_dualwrite(prompt, system_prompt, model_name, used_intent, out["response"])
                redis_client.setex(cache_key, 600, json.dumps(out))
                return out

            try:
                if summary:
                    asv = autosave(summary, source="web_search")
                    if any([asv.get("facts"), asv.get("prefs"), asv.get("bet")]):
                        log.info(f"[autosave:web_search] {asv}")
            except Exception as e:
                log.warning(f"AutoSave web_search failed: {e}")

            out.update({
                "cached": False,
                "response": _wrap(summary, model_name),
                "web": {
                    "results": results,
                    "reranker_used": ws.get("reranker_used", False),
                    "stats": ws.get("stats", {})
                }
            })
            _fb_record(query=prompt, intent_used="WEB_SEARCH", satisfaction=1.0, response_time_s=time.perf_counter()-t0)
            _ensure_semcache_import()
            if _SEMCACHE is None:
                try: _SEMCACHE = get_semantic_cache()
                except Exception: pass
            _semcache_dualwrite(prompt, system_prompt, model_name, used_intent, out["response"])
            redis_client.setex(cache_key, 86400, json.dumps(out))
            return out

        # DIRECT LLM con budget
        sys_trim = trim_to_tokens(system_prompt, min(600, LLM_MAX_CTX//8))
        user_trim = prompt
        input_budget = LLM_MAX_CTX - LLM_OUTPUT_BUDGET_TOK - LLM_SAFETY_MARGIN_TOK
        tokens_now = approx_tokens(sys_trim) + approx_tokens(user_trim)
        if tokens_now > input_budget:
            keep = max(128, input_budget - approx_tokens(sys_trim))
            user_trim = trim_to_tokens(user_trim[-keep*4:], keep)

        payload={"model":model_name,"messages":[
            {"role":"system","content":sys_trim},
            {"role":"user","content":user_trim}],
            "temperature":temperature, "max_tokens":LLM_OUTPUT_BUDGET_TOK}
        result, endpoint_used, last_err = _run_direct(payload, force)
        if not result:
            fail={"ok":False,"error":"Nessun endpoint raggiungibile.","last_error":last_err,"endpoints_tried":get_endpoints(),
                  "intent":used_intent,"confidence":route.get("confidence"),"reason":route.get("reason"),"router_build":BUILD_SIGNATURE}
            redis_client.setex(cache_key, 300, json.dumps(fail))
            return fail

        try:
            msg = (result.get("choices") or [{}])[0].get("message", {}).get("content", "")
            if msg:
                asv = autosave(msg, source="direct_llm")
                if any([asv.get("facts"), asv.get("prefs"), asv.get("bet")]):
                    log.info(f"[autosave:direct_llm] {asv}")
        except Exception as e:
            log.warning(f"AutoSave direct_llm failed: {e}")

        out.update({"cached":False,"endpoint_used":endpoint_used,"response":result})
        _fb_record(query=prompt, intent_used="DIRECT_LLM", satisfaction=1.0, response_time_s=time.perf_counter()-t0)
        _ensure_semcache_import()
        if _SEMCACHE is None:
            try: _SEMCACHE = get_semantic_cache()
            except Exception: pass
        _semcache_dualwrite(prompt, system_prompt, model_name, used_intent, out["response"])
        redis_client.setex(cache_key, 86400, json.dumps(out))
        return out

    except Exception:
        err={"ok":False,"error":"Richiesta troppo lunga o sorgente non disponibile. Le fonti non sono accessibili in questo momento.",
             "intent":used_intent,"confidence":route.get("confidence"),
             "reason":(route.get("reason") or "")+"|exception", "router_build": BUILD_SIGNATURE}
        redis_client.setex(cache_key, 300, json.dumps(err))
        return err

# ================= Persona & Web utils ===================

@app.post("/chat")
async def chat(payload: dict = Body(...)):
    src = payload.get("source", "tg")
    sid = str(payload.get("source_id"))
    text = (payload.get("text") or "").strip()
    if not sid or not text:
        return {"error": "source_id o text mancanti"}

    try:
        asv_in = autosave(text, source="chat_user")
        if any([asv_in.get("facts"), asv_in.get("prefs"), asv_in.get("bet")]):
            log.info(f"[autosave:chat_user] {asv_in}")
    except Exception as e:
        log.warning(f"AutoSave chat_user failed: {e}")

    persona = await get_persona(src, sid)
    sys_trim = trim_to_tokens(persona or "Sei una GPT neutra e modulare.", 600)
    reply = await reply_with_llm(text, sys_trim)

    try:
        if reply:
            asv_out = autosave(reply, source="chat_reply")
            if any([asv_out.get("facts"), asv_out.get("prefs"), asv_out.get("bet")]):
                log.info(f"[autosave:chat_reply] {asv_out}")
    except Exception as e:
        log.warning(f"AutoSave chat_reply failed: {e}")

    return {"reply": reply}

@app.post("/persona/set")
async def persona_set(payload: dict = Body(...)):
    src = payload.get("source", "tg")
    sid = str(payload.get("source_id"))
    text = (payload.get("text") or "").strip()
    if not sid or not text:
        return {"error": "source_id o text mancanti"}
    await set_persona(src, sid, text)
    return {"ok": True}

@app.post("/persona/get")
async def persona_get(payload: dict = Body(...)):
    src = payload.get("source", "tg")
    sid = str(payload.get("source_id"))
    if not sid:
        return {"error": "source_id mancante"}
    p = await get_persona(src, sid)
    return {"persona": p}

@app.post("/persona/reset")
async def persona_reset(payload: dict = Body(...)):
    src = payload.get("source", "tg")
    sid = str(payload.get("source_id"))
    if not sid:
        return {"error": "source_id mancante"}
    await reset_persona(src, sid)
    return {"ok": True}

# ---------- /web/summarize : URL **o** Query (nuovo) -----------------

class WebSummarizeQueryReq(BaseModel):
    q: Optional[str] = None
    url: Optional[str] = None
    source: str = "tg"
    source_id: str
    k: int = 6
    summarize_top: int = WEB_SUMMARIZE_TOP_DEFAULT
    return_sources: bool = True

@app.post("/web/summarize")
async def web_summarize(payload: WebSummarizeQueryReq):
    if payload.q:
        # 🔒 Guard smalltalk/very-short
        if _is_smalltalk_query(payload.q):
            return {"summary": "", "results": [], "note": "non_web_query"}
        ws = await _web_search_pipeline(
            q=payload.q, src=payload.source, sid=str(payload.source_id),
            k=int(payload.k or 6), nsum=int(payload.summarize_top or WEB_SUMMARIZE_TOP_DEFAULT)
        )
        if not ws.get("results"):
            return {"summary": ws.get("summary",""), "results": [], "note": ws.get("note") or "non_web_query"}
        return {"summary": ws.get("summary",""), "results": ws.get("results", [])}

    if not payload.url:
        return {"error": "url o q mancante"}
    url = payload.url.strip()
    persona = await get_persona(payload.source, str(payload.source_id))
    try:
        text, og_img = await asyncio.wait_for(fetch_and_extract(url), timeout=WEB_READ_TIMEOUT_S)
    except asyncio.TimeoutError:
        text, og_img = "", None
    trimmed = trim_to_tokens(text or "", WEB_SUMMARY_BUDGET_TOK)
    prompt = (
        "RUOLO: stai leggendo il contenuto di una singola pagina web.\n"
        "\n"
        "OBIETTIVO: riassumere la pagina in modo utile per l'utente.\n"
        "\n"
        "REGOLE CRITICHE:\n"
        "1. Riassumi in 5–10 punti chiave molto concreti (usa elenco puntato).\n"
        "2. Usa SOLO le informazioni presenti nel testo fornito: non inventare dati.\n"
        "3. Se ci sono numeri importanti (prezzi, date, percentuali, quantità), riportali indicando l'unità.\n"
        "4. Se il contenuto è incompleto o poco chiaro, dillo esplicitamente ma riassumi comunque ciò che è disponibile.\n"
        "5. NON dire all'utente di 'aprire la fonte' o 'consultare il sito' per avere i dettagli: la tua risposta deve essere autosufficiente.\n"
        "6. Alla fine, se utile, proponi in 1–2 frasi eventuali prossimi passi pratici (es. 'puoi confrontare X con Y', 'verifica la sezione Z se ti interessa...').\n"
        "\n"
        "EVITA frasi vaghe come 'le informazioni potrebbero non essere aggiornate' "
        "se il testo non lo dice esplicitamente.\n"
        "\n"
        f"URL: {url}\n\n"
        f"TESTO PAGINA:\n{trimmed}"
    )
    try:
        summary = await reply_with_llm(prompt, persona)
    except Exception:
        summary = "Non sono riuscito a generare un riassunto strutturato, ma il contenuto della pagina potrebbe comunque esserti utile se consultato."

    try:
        if summary:
            asv = autosave(summary, source="web_summarize")
            if any([asv.get("facts"), asv.get("prefs"), asv.get("bet")]):
                log.info(f"[autosave:web_summarize] {asv}")
    except Exception as e:
        log.warning(f"AutoSave web_summarize failed: {e}")

    return {"summary": summary, "og_image": og_img, "results": [{"url": url, "title": url}]}

# -------------------------- /web/search -------------------------------

class WebSearchReq(BaseModel):
    q: str
    k: int = 6
    summarize_top: int = WEB_SUMMARIZE_TOP_DEFAULT
    source: str = "tg"
    source_id: str = "default"

@app.post("/web/search")
async def web_search(req: WebSearchReq):
    # 🔒 Guard smalltalk/very-short
    if _is_smalltalk_query(req.q):
        return {"summary": "", "results": [], "note": "non_web_query", "stats": {}}
    ws = await _web_search_pipeline(
        q=req.q, src=req.source, sid=str(req.source_id),
        k=int(req.k or 6), nsum=int(req.summarize_top or WEB_SUMMARIZE_TOP_DEFAULT)
    )
    # Esponi sempre note/stats/reranker/validation
    return {
        "summary": (ws.get("summary") or ""),
        "results": (ws.get("results") or []),
        "note": ws.get("note"),
        "stats": ws.get("stats", {}),
        "reranker_used": ws.get("reranker_used", False),
        **({"validation": ws["validation"]} if ws.get("validation") is not None else {})
    }

# -------------------------- /web/research -----------------------------

class WebResearchReq(BaseModel):
    q: str
    source: str = "tg"
    source_id: str = "default"

@app.post("/web/research")
async def web_research(req: WebResearchReq):
    """
    Ricerca orchestrata multi-step (Claude-style):
    - multi search → read → novelty → stop
    - sintesi finale con fonti
    """
    if _is_smalltalk_query(req.q):
        return {
            "answer": "",
            "sources": [],
            "steps": [],
            "total_steps": 0,
            "note": "non_web_query"
        }

    agent = get_web_research_agent()
    if agent is None:
        # fallback soft: usa pipeline standard
        ws = await _web_search_pipeline(
            q=req.q,
            src=req.source,
            sid=str(req.source_id),
            k=6,
            nsum=WEB_SUMMARIZE_TOP_DEFAULT
        )
        return {
            "answer": ws.get("summary") or "",
            "sources": ws.get("results") or [],
            "steps": [],
            "total_steps": 1,
            "note": "fallback_standard_search"
        }

    persona = await get_persona(req.source, str(req.source_id)) or "Sei una GPT neutra e modulare."
    try:
        result = await agent.research(
            query=req.q,
            persona=persona
        )
        return result
    except Exception as e:
        log.error(f"/web/research error: {e}")
        # fallback soft su _web_search_pipeline
        ws = await _web_search_pipeline(
            q=req.q,
            src=req.source,
            sid=str(req.source_id),
            k=6,
            nsum=WEB_SUMMARIZE_TOP_DEFAULT
        )
        return {
            "answer": ws.get("summary") or "Errore nel motore di ricerca avanzato. Ho usato una ricerca standard.",
            "sources": ws.get("results") or [],
            "steps": [],
            "total_steps": 1,
            "note": "web_research_error_fallback",
            "error": str(e)
        }

# -------------------------- /web/cache --------------------------------

@app.get("/web/cache/stats")
def web_cache_stats():
    try:
        st = _webcache_stats()
        return {"ok": True, "cache": st}
    except Exception as e:
        return {"ok": False, "error": str(e)}

class WebCacheFlushReq(BaseModel):
    url: Optional[str] = None

@app.post("/web/cache/flush")
def web_cache_flush(req: WebCacheFlushReq):
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
def memory_add_fact(payload: FactIn):
    _id = add_fact(payload.subject, payload.value, payload.source, payload.metadata)
    return {"ok": True, "id": _id}

@app.post("/memory/pref")
def memory_add_pref(payload: PrefIn):
    _id = add_pref(payload.key, payload.value, payload.scope, payload.source, payload.metadata)
    return {"ok": True, "id": _id}

@app.post("/memory/bet")
def memory_add_bet(payload: BetIn):
    _id = add_bet(payload.event, payload.market, payload.odds, payload.stake, payload.result, payload.source, payload.metadata)
    return {"ok": True, "id": _id}

# --- Fallback-aware search base ---
def _recency_score(ts: int, half_life_days: float) -> float:
    if not ts: return 0.0
    age_days = max(0.0, (int(time.time()) - ts) / 86400.0)
    return math.exp(-math.log(2) * (age_days / max(1e-9, half_life_days)))

def _src_prior(md: dict) -> float:
    src = (md or {}).get("source") or ""
    table = {"system":1.00,"admin":0.98,"user":0.95,"web":0.92,"model":0.85,"bet":0.90}
    return table.get(src, 0.9)

@app.get("/memory/search")
def memory_search(q: str, k: int = 5, half_life_days: float = MEM_HALF_LIFE_D):
    items = search_topk(q, k=k, half_life_days=half_life_days)
    if items:
        return {"q": q, "k": k, "items": items}
    pool: List[Dict] = []
    for name in (FACTS, PREFS, BETS):
        try:
            pool.extend(_substring_fallback(name, q, limit=max(256, k*10)))
        except Exception:
            pass
    ranked = []
    for it in pool:
        md = it.get("metadata", {}) or {}
        rec = _recency_score(int(md.get("ts") or 0), half_life_days=half_life_days)
        srcp= _src_prior(md)
        it["sim"] = 0.0
        it["recency"] = round(rec,6)
        it["src_prior"] = round(srcp,3)
        it["score"] = round(0.6*rec + 0.4*srcp, 6)
        ranked.append(it)
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return {"q": q, "k": k, "items": ranked[:k]}

# ---- /memory/debug: versione leggera ----
def _light_debug_dump() -> Dict:
    if chromadb is None or _ChromaSettings is None:
        try:
            return debug_dump()
        except Exception as e:
            return {"persist_dir": CHROMA_PERSIST_DIR, "embed_model": EMBED_MODEL_NAME, "collections": [], "error": str(e)}
    try:
        client = None
        try:
            PersistentClient = getattr(chromadb, "PersistentClient", None)
            if PersistentClient:
                client = PersistentClient(path=CHROMA_PERSIST_DIR, settings=_ChromaSettings(persist_directory=CHROMA_PERSIST_DIR, anonymized_telemetry=False))
        except Exception:
            client = None
        if client is None:
            client = chromadb.Client(_ChromaSettings(persist_directory=CHROMA_PERSIST_DIR, anonymized_telemetry=False))
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
        return {"persist_dir": CHROMA_PERSIST_DIR, "embed_model": EMBED_MODEL_NAME, "collections": cols}
    except Exception as e:
        return {"persist_dir": CHROMA_PERSIST_DIR, "embed_model": EMBED_MODEL_NAME, "collections": [], "error": str(e)}

@app.get("/memory/debug")
def memory_debug():
    try:
        return {"ok": True, "debug": _light_debug_dump()}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/memory/list")
def memory_list(collection: str, limit: int = 50, offset: int = 0):
    try:
        col = _col(collection)
        try:
            cnt = col.count()  # type: ignore[attr-defined]
        except Exception:
            data_all = col.get()
            cnt = len(data_all.get("ids") or [])
        try:
            data = col.get(include=["documents", "metadatas"], limit=limit, offset=offset)
        except Exception:
            data = col.get()
        ids  = data.get("ids") or []
        docs = data.get("documents") or []
        metas= data.get("metadatas") or []
        items = []
        for i, _id in enumerate(ids):
            items.append({"id": _id, "document": docs[i] if i < len(docs) else None,
                          "metadata": metas[i] if i < len(metas) else None})
        return {"ok": True, "collection": collection, "count": int(cnt), "items": items}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ======================= CHROMA ADVANCED API =========================

class SearchAdvancedReq(BaseModel):
    q: str = Field(..., description="Query testuale")
    k: int = Field(5, ge=1, le=100)
    where: Optional[Dict[str, Any]] = Field(None, description="Filtri Chroma where{}")
    collections: Optional[List[str]] = Field(None, description="Override collezioni")

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
def memory_search_advanced(req: SearchAdvancedReq):
    cols = tuple(req.collections) if req.collections else (FACTS, PREFS, BETS)
    items = search_topk_with_filters(
        query=req.q,
        k=req.k,
        where=req.where,
        collections=cols
    )
    return {"ok": True, "q": req.q, "k": req.k, "where": req.where, "collections": list(cols), "items": items}

@app.post("/memory/bets/batch")
def memory_bets_batch(req: BetsBatchReq):
    res = add_bets_batch(req.items)
    return {"ok": True, **res}

@app.post("/memory/cleanup")
def memory_cleanup(req: CleanupReq):
    if req.collection == FACTS:
        res = cleanup_old_facts(days=req.days, dry_run=req.dry_run)
    elif req.collection == BETS:
        res = cleanup_old_bets(days=req.days, dry_run=req.dry_run)
    else:
        res = cleanup_old(collection=req.collection, older_than_days=req.days, dry_run=req.dry_run)  # type: ignore
    return {"ok": True, "collection": req.collection, **res}

@app.post("/memory/migrate")
def memory_migrate(req: MigrateReq):
    res = migrate_collection(
        old_name=req.old_name,
        new_name=req.new_name,
        new_model=req.new_model,
        batch_size=req.batch_size,
        delete_old=req.delete_old
    )
    return {"ok": True, **res}

@app.post("/memory/reembed")
def memory_reembed(req: Optional[ReembedReq] = None):
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
def analytics_report(days: int = 7):
    try:
        if not _ANALYTICS:
            return {"ok": False, "error": "SearchAnalytics non inizializzato."}
        rep = _ANALYTICS.report(days=days)  # type: ignore[attr-defined]
        return {"ok": True, "report": rep, "days": int(days)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/analytics/search/tail")
def analytics_tail(n: int = 100):
    try:
        path = getattr(_ANALYTICS, "path", SEARCH_ANALYTICS_LOG)
        if not os.path.isfile(path):
            return {"ok": True, "path": path, "events": []}
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        # restituisci ultimi n eventi già json-parsati quando possibile
        tail = []
        for line in lines[-max(1, int(n)):]:
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
def analytics_track_click(req: ClickTrackReq):
    """
    Registra un evento di click su una sorgente.
    Non richiede SearchAnalytics.track_search: scrive direttamente una riga JSONL con type='click'.
    """
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
