#!/usr/bin/env python3
# core/intent_feedback.py - Feedback + corrections persisted (Redis, fallback in-memory)

import os, time, json, hashlib
from collections import defaultdict
from typing import Optional, Dict, Any
try:
    import redis
except Exception:
    redis = None

def _h(s: str) -> str:
    return hashlib.sha256(s.strip().lower().encode("utf-8")).hexdigest()

class _KV:
    def __init__(self):
        self.enabled = False
        self.r = None
        if redis:
            host = os.getenv("REDIS_HOST", "localhost")
            port = int(os.getenv("REDIS_PORT", "6379"))
            db   = int(os.getenv("REDIS_DB", "0"))
            try:
                self.r = redis.Redis(host=host, port=port, db=db)
                self.r.ping()
                self.enabled = True
            except Exception:
                self.enabled = False
        self.local = {"list:intent_feedback": [] , "hash:corrections": {}}

    def lpush(self, key: str, val: str):
        if self.enabled:
            try:
                self.r.lpush(key, val)
                return
            except Exception:
                pass
        self.local.setdefault(key, []).insert(0, val)

    def lrange(self, key: str, start: int, end: int):
        if self.enabled:
            try:
                return self.r.lrange(key, start, end)
            except Exception:
                pass
        arr = self.local.get(key, [])
        return [json.dumps(x).encode() if isinstance(x, dict) else x for x in arr[start:end+1]]

    def hset(self, key: str, field: str, val: str):
        if self.enabled:
            try:
                self.r.hset(key, field, val)
                return
            except Exception:
                pass
        self.local.setdefault(key, {})[field] = val

    def hget(self, key: str, field: str) -> Optional[str]:
        if self.enabled:
            try:
                v = self.r.hget(key, field)
                return v.decode() if v else None
            except Exception:
                pass
        return self.local.get(key, {}).get(field)

class IntentFeedbackSystem:
    """
    Registra feedback e correzioni sul routing, e fornisce override per query future.
    """
    FEED_KEY = "list:intent_feedback"
    CORR_KEY = "hash:corrections"

    def __init__(self):
        self.kv = _KV()

    def record_feedback(self, query: str, intent_used: str,
                        satisfaction: float, response_time_s: float):
        data = {
            "query": query,
            "qhash": _h(query),
            "intent": intent_used,
            "satisfaction": float(satisfaction),
            "response_time_ms": int(max(0.0, response_time_s) * 1000),
            "ts": int(time.time())
        }
        self.kv.lpush(self.FEED_KEY, json.dumps(data))

    def record_correction(self, query: str, correct_intent: str):
        qh = _h(query)
        self.kv.hset(self.CORR_KEY, qh, correct_intent.upper())

    def get_correction(self, query: str) -> Optional[str]:
        qh = _h(query)
        return self.kv.hget(self.CORR_KEY, qh)

    # Analisi semplice
    def analyze_last(self, n: int = 500) -> Dict[str, Any]:
        raw = self.kv.lrange(self.FEED_KEY, 0, max(0, n-1))
        patterns = defaultdict(lambda: {"count": 0, "avg_sat": 0.0, "intents": defaultdict(int)})
        for rb in raw:
            try:
                d = json.loads(rb.decode() if isinstance(rb, (bytes, bytearray)) else rb)
            except Exception:
                continue
            patt = " ".join((d.get("query") or "").split()[:3]).lower()
            patterns[patt]["count"] += 1
            patterns[patt]["avg_sat"] += float(d.get("satisfaction", 0.0))
            patterns[patt]["intents"][d.get("intent","?")] += 1
        out = {}
        for patt, st in patterns.items():
            c = st["count"]
            out[patt] = {
                "count": c,
                "avg_satisfaction": (st["avg_sat"]/c) if c else 0.0,
                "intents": dict(st["intents"])
            }
        return out
