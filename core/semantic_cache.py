# core/semantic_cache.py — Simple semantic cache with similarity + stats + namespaces
from __future__ import annotations
import os, time, math, hashlib, threading
from typing import Dict, Any, Optional, List, Tuple

# === Opzionale: SentenceTransformers; fallback su BoW se assente ===
_EMBED_USE_ST = True
try:
    from sentence_transformers import SentenceTransformer  # type: ignore
except Exception:
    SentenceTransformer = None  # type: ignore
    _EMBED_USE_ST = False

# ---- Config da ENV (valori allineati a quelli che vedi in /stats/cache) ----
_SEM_NS_DEFAULT      = os.getenv("SEMCACHE_NAMESPACE", "general")
_SEM_THRESHOLD       = float(os.getenv("SEMCACHE_THRESHOLD", "0.82"))
_SEM_TTL_S           = int(os.getenv("SEMCACHE_TTL_S", "86400"))
_SEM_MAX_ITEMS       = int(os.getenv("SEMCACHE_MAX_ITEMS", "5000"))
_SEM_MODEL           = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
# Limite per-namespace (nuovo): di default 1/3 del max globale, almeno 500
_SEM_MAX_ITEMS_NS    = int(os.getenv("SEMCACHE_MAX_ITEMS_PER_NS", str(max(500, _SEM_MAX_ITEMS // 3))))
# Lazy load del modello ST (evita costo al boot)
_SEM_LAZY_EMBED      = os.getenv("SEMCACHE_LAZY_EMBED", "1").strip().lower() in ("1","true","yes","on")
# Dedup su set(): se sim >= soglia, aggiorna entry invece che append
_SEM_DEDUP_SIM       = float(os.getenv("SEMCACHE_DEDUP_SIM", "0.985"))
# Aggiornare LRU all’hit (move-to-end tramite ts refresh)
_SEM_UPDATE_ON_HIT   = os.getenv("SEMCACHE_UPDATE_ON_HIT", "1").strip().lower() in ("1","true","yes","on")

def _now() -> int:
    return int(time.time())

def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

# ------------------------- Embedder -------------------------
class _Embedder:
    """
    Wrapper per ST con lazy-init opzionale e fallback BoW.
    - kind: 'st' o 'bow'
    - encode(text) -> vettore
    - cosine(va, vb) -> [0..1]
    """
    def __init__(self, model_name: str):
        self.dim: Optional[int] = None
        self.kind = "bow"
        self.model_name = model_name
        self._lock = threading.Lock()
        self._model = None
        self._ready = False

        if _EMBED_USE_ST and SentenceTransformer is not None:
            if _SEM_LAZY_EMBED:
                # Lazy: rinvia caricamento al primo encode()
                self.kind = "st"
                self._ready = False
            else:
                try:
                    self._model = SentenceTransformer(model_name)
                    v = self._model.encode(["ok"], normalize_embeddings=True)
                    self.dim = len(v[0])
                    self.kind = "st"
                    self._ready = True
                except Exception:
                    # fallback BoW
                    self._model, self.kind, self._ready = None, "bow", True

    def _ensure_ready(self):
        if self.kind != "st" or self._ready:
            return
        with self._lock:
            if self._ready:
                return
            try:
                self._model = SentenceTransformer(self.model_name)
                v = self._model.encode(["ok"], normalize_embeddings=True)
                self.dim = len(v[0])
                self._ready = True
            except Exception:
                self._model, self.kind, self._ready = None, "bow", True

    @staticmethod
    def _tok(s: str) -> List[str]:
        out, cur = [], []
        for ch in s.lower():
            if "a" <= ch <= "z" or "0" <= ch <= "9" or ch in "àèéìíòóùú":
                cur.append(ch)
            else:
                if cur:
                    out.append("".join(cur)); cur=[]
        if cur: out.append("".join(cur))
        return out

    def _bow(self, text: str):
        toks = self._tok(text)
        if not toks: return {}
        tf: Dict[str, float] = {}
        for t in toks:
            tf[t] = tf.get(t, 0.0) + 1.0
        norm = math.sqrt(sum(v*v for v in tf.values())) or 1.0
        for k in tf.keys():
            tf[k] /= norm
        return tf

    @staticmethod
    def _cos_bow(a: Dict[str, float], b: Dict[str, float]) -> float:
        if not a or not b: return 0.0
        s = 0.0
        if len(a) < len(b):
            for k, va in a.items():
                vb = b.get(k)
                if vb: s += va * vb
        else:
            for k, vb in b.items():
                va = a.get(k)
                if va: s += va * vb
        return float(max(0.0, min(1.0, s)))

    def encode(self, text: str):
        if self.kind == "st":
            self._ensure_ready()
            if self._model is not None:
                return self._model.encode([text], normalize_embeddings=True)[0]
            # se init ST è fallita → BoW fallback
        return self._bow(text)

    def cosine(self, va, vb) -> float:
        if self.kind == "st" and isinstance(va, (list, tuple)) and isinstance(vb, (list, tuple)):
            s = 0.0
            n = min(len(va), len(vb))
            for i in range(n):
                s += float(va[i]) * float(vb[i])
            return float(max(0.0, min(1.0, s)))
        return self._cos_bow(va, vb)

# ------------------------- Entry -------------------------
class _Entry:
    __slots__ = ("q", "vec", "ts", "response", "meta")
    def __init__(self, q: str, vec, response: Dict[str, Any], meta: Optional[Dict[str, Any]]):
        self.q = q
        self.vec = vec
        self.ts = _now()
        self.response = response
        self.meta = meta or {}

# ------------------------- Cache -------------------------
class SemanticCache:
    """
    Namespaced semantic cache con:
    - get/set con threshold, TTL, max_items (globale) e max_items per-namespace
    - dedup semantico in set() (configurabile), LRU refresh on-hit (configurabile)
    - stats(), stats_ns(ns), stats_all(), count()
    - flush(ns)/clear(ns)
    """
    def __init__(self,
                 namespace_default: str = _SEM_NS_DEFAULT,
                 threshold: float = _SEM_THRESHOLD,
                 ttl_s: int = _SEM_TTL_S,
                 max_items: int = _SEM_MAX_ITEMS,
                 model_name: str = _SEM_MODEL,
                 max_items_per_ns: int = _SEM_MAX_ITEMS_NS):
        self.ns_default = namespace_default
        self.threshold = float(threshold)
        self.ttl_s = int(ttl_s)
        self.max_items = int(max_items)
        self.max_items_per_ns = int(max_items_per_ns)

        self._emb = _Embedder(model_name)
        self.dim = self._emb.dim
        self._lock = threading.Lock()

        self._store: Dict[str, List[_Entry]] = {}
        self._hits = 0
        self._miss = 0
        self._evictions = 0

    # ---------- Namespace helpers ----------
    def _ensure_ns(self, ns: Optional[str]) -> str:
        if not ns: ns = self.ns_default
        if ns not in self._store:
            self._store[ns] = []
        return ns

    def _prune_ns_ttl(self, ns: str, now_ts: int) -> None:
        """Rimuove nel namespace gli elementi scaduti (TTL)"""
        lst = self._store.get(ns, [])
        if not lst: return
        alive = [e for e in lst if now_ts - e.ts <= self.ttl_s]
        if len(alive) != len(lst):
            self._store[ns] = alive

    # ---------- Public API ----------
    @staticmethod
    def fingerprint(system_prompt: str, model_name: str, intent: str) -> str:
        base = f"{(system_prompt or '').strip()}|{(model_name or '').strip()}|{(intent or '').strip()}"
        return _sha256(base)

    def set(self, prompt: str, response_obj: Dict[str, Any], ctx_fp: Optional[str], meta: Optional[Dict[str, Any]] = None) -> None:
        ns = self._ensure_ns(ctx_fp)
        vec = self._emb.encode(prompt)
        now_ts = _now()
        with self._lock:
            # 1) TTL prune locale al namespace
            self._prune_ns_ttl(ns, now_ts)

            # 2) Dedup semantico: se una entry molto simile esiste, aggiorna/rinfresca
            if _SEM_DEDUP_SIM > 0.0:
                best_i, best_sim = -1, 0.0
                for i, e in enumerate(self._store[ns]):
                    try:
                        sim = self._emb.cosine(vec, e.vec)
                    except Exception:
                        sim = 0.0
                    if sim > best_sim:
                        best_sim, best_i = sim, i
                if best_i >= 0 and best_sim >= _SEM_DEDUP_SIM:
                    e = self._store[ns][best_i]
                    e.q = prompt
                    e.vec = vec
                    e.response = response_obj
                    e.meta = (meta or {})
                    e.ts = now_ts
                    # sposta in coda (LRU)
                    self._store[ns].append(self._store[ns].pop(best_i))
                else:
                    self._store[ns].append(_Entry(prompt, vec, response_obj, meta))
            else:
                self._store[ns].append(_Entry(prompt, vec, response_obj, meta))

            # 3) Enforce per-namespace cap (LRU nel namespace)
            if len(self._store[ns]) > self.max_items_per_ns:
                overflow = len(self._store[ns]) - self.max_items_per_ns
                if overflow > 0:
                    del self._store[ns][:overflow]
                    self._evictions += overflow

            # 4) Enforce cap globale (LRU globale: entry più vecchia tra i namespace)
            total = self.count()
            if total > self.max_items:
                oldest_ns, oldest_idx, oldest_ts = None, None, 1 << 60
                for n, lst in self._store.items():
                    if lst and lst[0].ts < oldest_ts:
                        oldest_ns, oldest_idx, oldest_ts = n, 0, lst[0].ts
                if oldest_ns is not None and oldest_idx is not None and self._store.get(oldest_ns):
                    self._store[oldest_ns].pop(oldest_idx)
                    self._evictions += 1

    def get(self, prompt: str, ctx_fp: Optional[str]) -> Optional[Dict[str, Any]]:
        ns = self._ensure_ns(ctx_fp)
        vec_q = self._emb.encode(prompt)
        best_sim, best_idx, best_entry = 0.0, -1, None
        now = _now()
        with self._lock:
            lst = self._store.get(ns, [])
            # TTL cleanup in-read & best match
            alive: List[_Entry] = []
            for i, e in enumerate(lst):
                if now - e.ts <= self.ttl_s:
                    alive.append(e)
                    try:
                        sim = self._emb.cosine(vec_q, e.vec)
                    except Exception:
                        sim = 0.0
                    if sim > best_sim:
                        best_sim, best_idx, best_entry = sim, i, e
            if len(alive) != len(lst):
                self._store[ns] = alive
                # attenzione: best_idx potrebbe invalidarsi, ma solo se entry scaduta

            if best_entry and best_sim >= self.threshold:
                self._hits += 1
                # LRU refresh on-hit (opzionale)
                if _SEM_UPDATE_ON_HIT and best_idx >= 0 and best_idx < len(self._store[ns]):
                    best_entry.ts = now
                    # move to end
                    try:
                        self._store[ns].append(self._store[ns].pop(best_idx))
                    except Exception:
                        pass
                return {
                    "response": best_entry.response,
                    "similarity": float(best_sim),
                    "meta": {"ns": ns, **(best_entry.meta or {})}
                }
            else:
                self._miss += 1
                return None

    # ---------- Stats ----------
    def count(self) -> int:
        return sum(len(v) for v in self._store.values())

    def stats(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "namespace": self.ns_default,
            "threshold": self.threshold,
            "ttl_s": self.ttl_s,
            "max_items": self.max_items,
            "max_items_per_ns": self.max_items_per_ns,
            "size_items": self.count(),
            "dim": self.dim,
            "embedder": {"kind": self._emb.kind, "model": self._emb.model_name},
            "hits": self._hits,
            "miss": self._miss,
            "hit_rate": (self._hits / (self._hits + self._miss)) if (self._hits + self._miss) else 0.0,
            "evictions": self._evictions
        }

    def stats_ns(self, ns: str) -> Dict[str, Any]:
        ns = self._ensure_ns(ns)
        size_ns = len(self._store.get(ns, []))
        latest_ts = max((e.ts for e in self._store.get(ns, [])), default=0)
        return {
            "enabled": True,
            "namespace": ns,
            "threshold": self.threshold,
            "ttl_s": self.ttl_s,
            "max_items": self.max_items,
            "max_items_per_ns": self.max_items_per_ns,
            "size_items": size_ns,
            "latest_ts": latest_ts,
            "dim": self.dim,
            "embedder": {"kind": self._emb.kind, "model": self._emb.model_name},
            "hits": self._hits,
            "miss": self._miss,
            "hit_rate": (self._hits / (self._hits + self._miss)) if (self._hits + self._miss) else 0.0,
            "evictions": self._evictions
        }

    def stats_all(self) -> Dict[str, Any]:
        per_ns = {}
        for ns, lst in self._store.items():
            per_ns[ns] = {
                "size_items": len(lst),
                "latest_ts": max((e.ts for e in lst), default=0)
            }
        return {
            "enabled": True,
            "threshold": self.threshold,
            "ttl_s": self.ttl_s,
            "max_items": self.max_items,
            "max_items_per_ns": self.max_items_per_ns,
            "dim": self.dim,
            "embedder": {"kind": self._emb.kind, "model": self._emb.model_name},
            "namespaces": per_ns,
            "total": {
                "size_items": self.count(),
                "hits": self._hits,
                "miss": self._miss,
                "hit_rate": (self._hits / (self._hits + self._miss)) if (self._hits + self._miss) else 0.0,
                "evictions": self._evictions
            }
        }

    # ---------- Manutenzione ----------
    def flush(self, ns: Optional[str] = None) -> int:
        with self._lock:
            if ns:
                ns = self._ensure_ns(ns)
                n = len(self._store.get(ns, []))
                self._store[ns] = []
                return n
            n = self.count()
            self._store = {}
            return n

    # Alias compatibilità
    def clear(self, ns: Optional[str] = None) -> int:
        return self.flush(ns)

# ------------------------- Singleton factory -------------------------
_SINGLETON: Optional[SemanticCache] = None

def get_semantic_cache() -> SemanticCache:
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = SemanticCache(
            namespace_default=_SEM_NS_DEFAULT,
            threshold=_SEM_THRESHOLD,
            ttl_s=_SEM_TTL_S,
            max_items=_SEM_MAX_ITEMS,
            model_name=_SEM_MODEL,
            max_items_per_ns=_SEM_MAX_ITEMS_NS
        )
    return _SINGLETON
