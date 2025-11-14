#!/usr/bin/env python3
# core/intent_feedback.py - Feedback + corrections persisted (Redis, fallback in-memory)
import os, time, json, hashlib
from collections import defaultdict
from typing import Optional, Dict, Any, List, Tuple

try:
    import redis  # type: ignore
except Exception:
    redis = None  # type: ignore

# ------------------------- Config -------------------------
_FEED_KEY = os.getenv("INTENT_FEEDBACK_LIST_KEY", "list:intent_feedback")
_CORR_KEY = os.getenv("INTENT_FEEDBACK_CORR_KEY", "hash:corrections")
_FEED_TRIM = int(os.getenv("INTENT_FEEDBACK_TRIM_LEN", "5000"))           # max lunghezza lista
_PRIVACY   = os.getenv("INTENT_FEEDBACK_PRIVACY", "off").strip().lower()  # off|hash|short
_CORR_TTL  = int(os.getenv("INTENT_CORRECTION_TTL_S", str(30*24*3600)))   # 30 giorni default

def _h(s: str) -> str:
    return hashlib.sha256((s or "").strip().lower().encode("utf-8")).hexdigest()

def _shorten(q: str, n_words: int = 6) -> str:
    parts = (q or "").split()
    return " ".join(parts[:n_words])

def _apply_privacy(query: str) -> Tuple[str, str]:
    """
    Ritorna (query_to_store, qhash).
    - off   -> salva testo intero
    - short -> salva prime 6 parole
    - hash  -> salva solo hash (query_to_store = "")
    """
    qhash = _h(query)
    if _PRIVACY == "hash":
        return ("", qhash)
    if _PRIVACY == "short":
        return (_shorten(query), qhash)
    return (query, qhash)

def _pctl(arr: List[float], p: float) -> float:
    if not arr:
        return 0.0
    a = sorted(arr)
    k = max(0, min(len(a) - 1, int(round((len(a) - 1) * p))))
    return float(a[k])

# ------------------------- KV backend -------------------------
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
        # local fallback
        self.local_lists: Dict[str, List[str]] = { _FEED_KEY: [] }
        self.local_hashes: Dict[str, Dict[str, str]] = { _CORR_KEY: {} }

    # -------- Lists --------
    def lpush(self, key: str, val: str):
        if self.enabled:
            try:
                pipe = self.r.pipeline()
                pipe.lpush(key, val)
                if _FEED_TRIM > 0:
                    pipe.ltrim(key, 0, _FEED_TRIM - 1)
                pipe.execute()
                return
            except Exception:
                pass
        # fallback
        self.local_lists.setdefault(key, []).insert(0, val)
        if _FEED_TRIM > 0 and len(self.local_lists[key]) > _FEED_TRIM:
            self.local_lists[key] = self.local_lists[key][: _FEED_TRIM]

    def lrange(self, key: str, start: int, end: int):
        if self.enabled:
            try:
                return self.r.lrange(key, start, end)
            except Exception:
                pass
        arr = self.local_lists.get(key, [])
        # normalizza end
        if end < 0:
            end = len(arr) - 1
        return [x.encode() if isinstance(x, str) else x for x in arr[start:end+1]]

    # -------- Hashes --------
    def hset(self, key: str, field: str, val: str):
        if self.enabled:
            try:
                self.r.hset(key, field, val)
                return
            except Exception:
                pass
        self.local_hashes.setdefault(key, {})[field] = val

    def hget(self, key: str, field: str) -> Optional[str]:
        if self.enabled:
            try:
                v = self.r.hget(key, field)
                return v.decode() if v else None
            except Exception:
                pass
        return self.local_hashes.get(key, {}).get(field)

    def hdel(self, key: str, field: str):
        if self.enabled:
            try:
                self.r.hdel(key, field)
                return
            except Exception:
                pass
        if key in self.local_hashes and field in self.local_hashes[key]:
            del self.local_hashes[key][field]

# ------------------------- Main system -------------------------
class IntentFeedbackSystem:
    """
    Registra feedback e correzioni sul routing, e fornisce override per query future.

    METODI STABILI:
      - record_feedback(query, intent_used, satisfaction, response_time_s, **extra)
      - record_correction(query, correct_intent)
      - get_correction(query) -> Optional[str]
      - analyze_last(n=500) -> Dict
    AGGIUNTE:
      - stats(n=1000) -> p50/p90 latenze + breakdown per intent
      - apply_correction(query, predicted_intent) -> intent finale
    """
    FEED_KEY = _FEED_KEY
    CORR_KEY = _CORR_KEY

    def __init__(self):
        self.kv = _KV()

    # ---------- Feedback ----------
    def record_feedback(self, query: str, intent_used: str,
                        satisfaction: float, response_time_s: float,
                        **extra: Any):
        qstore, qhash = _apply_privacy(query)
        data = {
            "query": qstore,
            "qhash": qhash,
            "intent": (intent_used or "").upper(),
            "satisfaction": float(satisfaction),
            "response_time_ms": int(max(0.0, response_time_s) * 1000),
            "ts": int(time.time())
        }
        # campi extra opzionali (endpoint, model, cached, similarity, reranker_used, etc.)
        for k, v in (extra or {}).items():
            try:
                # evitiamo oggetti non serializzabili
                json.dumps(v)
                data[k] = v
            except Exception:
                data[k] = str(v)
        self.kv.lpush(self.FEED_KEY, json.dumps(data))

    # ---------- Correzioni ----------
    def record_correction(self, query: str, correct_intent: str):
        qh = _h(query)
        payload = {"intent": (correct_intent or "").upper(), "ts": int(time.time())}
        # salva JSON (retro-compatibile: se vecchie entry sono plain string, get_correction gestisce entrambi)
        self.kv.hset(self.CORR_KEY, qh, json.dumps(payload))

    def get_correction(self, query: str) -> Optional[str]:
        qh = _h(query)
        raw = self.kv.hget(self.CORR_KEY, qh)
        if raw is None:
            return None
        # supporta sia vecchio formato (string intent) che nuovo (json)
        try:
            d = json.loads(raw)
            if isinstance(d, dict):
                its = int(d.get("ts") or 0)
                if _CORR_TTL > 0 and (int(time.time()) - its) > _CORR_TTL:
                    # scaduto
                    self.kv.hdel(self.CORR_KEY, qh)
                    return None
                return (d.get("intent") or "").upper() or None
        except Exception:
            # vecchio formato: era solo l'intent come stringa
            return (raw or "").upper() or None
        return None

    def apply_correction(self, query: str, predicted_intent: str) -> str:
        corr = self.get_correction(query)
        return corr if corr else predicted_intent

    # ---------- Analisi ----------
    def analyze_last(self, n: int = 500) -> Dict[str, Any]:
        raw = self.kv.lrange(self.FEED_KEY, 0, max(0, n-1))
        patterns = defaultdict(lambda: {"count": 0, "avg_sat": 0.0, "intents": defaultdict(int)})
        for rb in raw:
            try:
                d = json.loads(rb.decode() if isinstance(rb, (bytes, bytearray)) else rb)
            except Exception:
                continue
            # pattern = prime 3 parole (se privacy=hash, il campo query sarà vuoto → fallback qhash)
            qtxt = (d.get("query") or "").strip()
            patt = " ".join(qtxt.split()[:3]).lower() if qtxt else d.get("qhash","")[:8]
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

    def stats(self, n: int = 1000) -> Dict[str, Any]:
        raw = self.kv.lrange(self.FEED_KEY, 0, max(0, n-1))
        lat: List[float] = []
        intents: Dict[str, int] = defaultdict(int)
        sat_sum, cnt = 0.0, 0
        for rb in raw:
            try:
                d = json.loads(rb.decode() if isinstance(rb, (bytes, bytearray)) else rb)
            except Exception:
                continue
            intents[(d.get("intent") or "?")] += 1
            lat.append(float(d.get("response_time_ms") or 0.0))
            sat_sum += float(d.get("satisfaction", 0.0))
            cnt += 1
        return {
            "count_considered": cnt,
            "avg_satisfaction": (sat_sum/cnt) if cnt else 0.0,
            "p50_latency_ms": _pctl(lat, 0.50),
            "p90_latency_ms": _pctl(lat, 0.90),
            "intents": dict(intents),
            "trim_len": _FEED_TRIM,
            "privacy_mode": _PRIVACY,
            "correction_ttl_s": _CORR_TTL
        }
