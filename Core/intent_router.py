#!/usr/bin/env python3
# backend/intent_router.py — Smart Intent Router (patched)
from fastapi import FastAPI, Body
from pydantic import BaseModel
from typing import Optional, Dict
import os, re, time, json

try:
    import redis  # opzionale: feedback storage
    _REDIS = redis.Redis(host=os.getenv("REDIS_HOST","localhost"),
                         port=int(os.getenv("REDIS_PORT","6379")),
                         db=int(os.getenv("REDIS_DB","0")))
    _HAS_REDIS = True
except Exception:
    _REDIS = None
    _HAS_REDIS = False

app = FastAPI()

# --- Heuristic keyword sets ---
_REALTIME_WEATHER = {"meteo", "weather", "previsioni"}
_REALTIME_PRICES  = {"prezzo", "prezzi", "price", "quotazione", "quote", "cambio", "tasso", "valuta",
                     "bitcoin", "btc", "eth", "eur/usd", "borsa", "azioni", "stock", "ticker"}
_REALTIME_SCORES  = {"risultati", "risultato", "score", "partite", "live", "oggi", "stamattina", "stasera"}
_DOMAIN_NEWS      = {"news", "ultime", "oggi", "adesso"}

# NB: “oggi” da solo NON basta: serve in combo con categorie sopra.
_TEMPORAL_FAST    = [
    r"(^|\s)che\s+ora\s+e'?(\s|\?|$)",
    r"(^|\s)che\s+giorno\s+e'?(\s|\?|$)",
    r"(^|\s)che\s+data\s+e'?(\s|\?|$)",
    r"(^|\s)quale\s+giorno\s+del\s+.*\?$",
]

_CALC_PATTERN = re.compile(r"^[\s0-9\.\,\+\-\*\/\^\(\)%\s]+$")

_URL_PATTERN  = re.compile(r"(https?://\S+)")

class ClassifyIn(BaseModel):
    query: str

@app.get("/healthz")
def healthz():
    return {
        "ok": True,
        "router": "smart-intent",
        "redis": _HAS_REDIS,
        "rules": {
            "temporal_fast": [p for p in _TEMPORAL_FAST],
            "realtime_weather": list(_REALTIME_WEATHER),
            "realtime_prices": list(_REALTIME_PRICES),
            "realtime_scores": list(_REALTIME_SCORES),
        }
    }

@app.post("/classify")
def classify(payload: ClassifyIn):
    q_raw = (payload.query or "").strip()
    q = q_raw.lower()

    # 0) URL → WEB_READ
    m = _URL_PATTERN.search(q_raw)
    if m:
        return {
            "ok": True, "intent": "WEB_READ", "confidence": 1.0,
            "reason": "url_detected", "params": {"url": m.group(1)}
        }

    # 1) Calculator fast path (solo se è *puro* calcolo)
    if _CALC_PATTERN.match(q) and any(c.isdigit() for c in q):
        return {
            "ok": True, "intent": "CALCULATOR", "confidence": 1.0,
            "reason": "calculator_fast_path", "params": {"expr": q_raw}
        }

    # 2) Temporal fast path (solo domande su ora/data/giorno)
    if any(re.search(p, q) for p in _TEMPORAL_FAST):
        return {
            "ok": True, "intent": "DIRECT_LLM", "confidence": 1.0,
            "reason": "temporal_fast_path"
        }

    # 3) Real-time categories → WEB_SEARCH
    tokens = set(re.findall(r"[a-zàèéìòóù]+", q))
    if (_REALTIME_WEATHER & tokens) \
       or (_REALTIME_PRICES & tokens) \
       or (("risultati" in tokens or "score" in tokens) and ("oggi" in tokens or "live" in tokens)):
        return {
            "ok": True, "intent": "WEB_SEARCH", "confidence": 0.98,
            "reason": "realtime_category_match"
        }

    # 4) Definitions / stable knowledge → DIRECT_LLM (default sicuro)
    # Esempi: “cos’è…”, “spiegami…”, “storia di…”
    if any(q.startswith(p) for p in ["cos'", "cos’è", "cos e", "cos e'", "cos’è", "spiegami", "definizione", "storia", "che cos", "che cosa e", "che cosa è"]):
        return {"ok": True, "intent": "DIRECT_LLM", "confidence": 0.9, "reason": "definition_like"}

    # 5) Fallthrough → chiediamo al LLM? In questo router teniamo semplice:
    # di default andiamo DIRECT_LLM con conf media; /generate farà comunque sanity-check.
    return {"ok": True, "intent": "DIRECT_LLM", "confidence": 0.7, "reason": "fallback_default"}

# --- Feedback endpoints (opzionali) ---
class FeedbackIn(BaseModel):
    query: str
    intent_used: str
    satisfaction: float
    response_time_ms: Optional[int] = None

@app.post("/feedback")
def feedback(payload: FeedbackIn):
    data = payload.dict() | {"ts": time.time()}
    if _HAS_REDIS:
        _REDIS.lpush("intent_feedback", json.dumps(data))
        _REDIS.ltrim("intent_feedback", 0, 9999)
    return {"ok": True}

class CorrectionIn(BaseModel):
    query: str
    correct_intent: str

@app.post("/correct")
def correct(payload: CorrectionIn):
    if _HAS_REDIS:
        key = f"intent_corrections:{payload.query.strip().lower()}"
        _REDIS.setex(key, 7*24*3600, payload.correct_intent.upper())
    return {"ok": True}
