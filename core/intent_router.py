#!/usr/bin/env python3
# backend/intent_router.py — Smart Intent Router (allineato con SmartIntentClassifier)

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, Dict, Any
import os, re, time, json

# ----------------- Redis (feedback opzionale) -----------------

try:
    import redis  # opzionale: feedback storage
    _REDIS = redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        db=int(os.getenv("REDIS_DB", "0")),
    )
    _HAS_REDIS = True
except Exception:
    _REDIS = None
    _HAS_REDIS = False

# ----------------- Import SmartIntentClassifier -----------------

from core.smart_intent_classifier import SmartIntentClassifier

_SMART = SmartIntentClassifier()

app = FastAPI()

# ----------------- Pattern helper locali -----------------

_TEMPORAL_FAST = [
    r"(^|\s)che\s+ora\s+e'?(\s|\?|$)",
    r"(^|\s)che\s+giorno\s+e'?(\s|\?|$)",
    r"(^|\s)che\s+data\s+e'?(\s|\?|$)",
    r"(^|\s)quale\s+giorno\s+del\s+.*\?$",
]

_CALC_PATTERN = re.compile(r"^[\s0-9\.\,\+\-\*\/\^\(\)%\s]+$")
_URL_PATTERN  = re.compile(r"(https?://\S+)", re.IGNORECASE)


class ClassifyIn(BaseModel):
    query: str


@app.get("/healthz")
def healthz():
    return {
        "ok": True,
        "router": "smart-intent",
        "redis": _HAS_REDIS,
        "uses_smart_classifier": True,
        "rules": {
            "temporal_fast": [p for p in _TEMPORAL_FAST],
            "calculator_fast": True,
        },
    }


@app.post("/classify")
def classify(payload: ClassifyIn):
    q_raw = (payload.query or "").strip()
    q = q_raw.lower()

    # 0) URL → WEB_READ (fast path a livello router)
    m = _URL_PATTERN.search(q_raw)
    if m:
        return {
            "ok": True,
            "intent": "WEB_READ",
            "confidence": 1.0,
            "reason": "url_detected_router",
            "params": {"url": m.group(1)},
        }

    # 1) Calculator fast path (solo se è *puro* calcolo)
    if _CALC_PATTERN.match(q) and any(c.isdigit() for c in q):
        return {
            "ok": True,
            "intent": "CALCULATOR",
            "confidence": 1.0,
            "reason": "calculator_fast_path",
            "params": {"expr": q_raw},
        }

    # 2) Temporal fast path (ora/data/giorno) → DIRECT_LLM
    if any(re.search(p, q) for p in _TEMPORAL_FAST):
        return {
            "ok": True,
            "intent": "DIRECT_LLM",
            "confidence": 1.0,
            "reason": "temporal_fast_path",
            "params": {},
        }

    # 3) Tutto il resto → delega allo SmartIntentClassifier (unica fonte di verità)
    smart: Dict[str, Any] = _SMART.classify(q_raw)

    smart_intent = smart.get("intent", "DIRECT_LLM")
    conf = float(smart.get("confidence", 0.7))
    reason = str(smart.get("reason", "smart_default"))
    live_type = smart.get("live_type")
    url_from_smart = smart.get("url")

    # Mappiamo negli intent del router
    if smart_intent == "WEB_READ":
        # In teoria l’URL l’abbiamo già gestito sopra, ma per sicurezza mappiamo anche qui
        params = {}
        if url_from_smart:
            params["url"] = url_from_smart
        else:
            m2 = _URL_PATTERN.search(q_raw)
            if m2:
                params["url"] = m2.group(1)

        return {
            "ok": True,
            "intent": "WEB_READ",
            "confidence": max(conf, 0.9),
            "reason": f"smart:{reason}",
            "params": params,
        }

    if smart_intent == "WEB_SEARCH":
        params = {}
        if live_type:
            params["live_type"] = live_type

        return {
            "ok": True,
            "intent": "WEB_SEARCH",
            "confidence": conf,
            "reason": f"smart:{reason}",
            "params": params,
        }

    # Default: DIRECT_LLM
    return {
        "ok": True,
        "intent": "DIRECT_LLM",
        "confidence": conf,
        "reason": f"smart:{reason}",
        "params": {},
    }


# ----------------- Feedback endpoints (opzionali) -----------------

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
        _REDIS.setex(key, 7 * 24 * 3600, payload.correct_intent.upper())
    return {"ok": True}
