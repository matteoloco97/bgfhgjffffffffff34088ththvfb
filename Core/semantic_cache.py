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
_SEM_NS_DEFAULT = os.getenv("SEMCACHE_NAMESPACE", "general")
_SEM_THRESHOLD  = float(os.getenv("SEMCACHE_THRESHOLD", "0.82"))
_SEM_TTL_S      = int(os.getenv("SEMCACHE_TTL_S", "86400"))
_SEM_MAX_ITEMS  = int(os.getenv("SEMCACHE_MAX_ITEMS", "5000"))
_SEM_MODEL      = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")

def _now() -> int:
    return int(time.time())

def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

# ------------------------- Embedder -------------------------
class _Embedder:
    def __init__(self, model_name: str):
        self.dim = None
        self.kind = "bow"
        self._lock = threading.Lock()
        self._model = None
        if _EMBED_USE_ST and SentenceTransformer is not None:
            try:
                self._model = SentenceTransformer(model_name)
                # calcola dimensione
                v = self._model.encode(["ok"], normalize_embeddings=True)
                self.dim = len(v[0])
                self.kind = "st"
            except Exception:
                self._model = None
                self.kind = "bow"

    @staticmethod
    def _tok(s: str) -> List[str]:
        # tokenizer semplice, lower + split su non-lettere
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
        # tf
        tf: Dict[str, float] = {}
        for t in toks:
            tf[t] = tf.get(t, 0.0) + 1.0
        # l2 normalize
        norm = math.sqrt(sum(v*v for v in tf.values())) or 1.0
        for k in tf.keys():
            tf[k] /= norm
        return tf

    @staticmethod
    def _cos_bow(a: Dict[str, float], b: Dict[str, float]) -> float:
        if not a or not b: return 0.0
        # intersect only
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
        if self.kind == "st" and self._model is not None:
            # returns normalized vector
            return self._model.encode([text], normalize_embeddings=True)[0]
        # fallback bow
        return self._bow(text)

    def cosine(self, va, vb) -> float:
        if self.kind == "st":
            # vectors are normalized already
            # manual dot
            s = 0.0
            # assume list-like
            n = min(len(va), len(vb))
            for i in range(n):
                s += float(va[i]) * float(vb[i])
            return float(max(0.0, min(1.0, s)))
        # bow dict cosine already normalized
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
    - get/set con threshold, TTL, max_items
    - stats(), stats_ns(ns), stats_all(), count()
    """
    def __init__(self,
                 namespace_default: str = _SEM_NS_DEFAULT,
                 threshold: float = _SEM_THRESHOLD,
                 ttl_s: int = _SEM_TTL_S,
                 max_items: int = _SEM_MAX_ITEMS,
                 model_name: str = _SEM_MODEL):
        self.ns_default = namespace_default
        self.threshold = float(threshold)
        self.ttl_s = int(ttl_s)
        self.max_items = int(max_items)

        self._emb = _Embedder(model_name)
        self.dim = self._emb.dim  # può essere None in fallback bow
        self._lock = threading.Lock()

        # ns -> list of entries
        self._store: Dict[str, List[_Entry]] = {}
        # stats globali
        self._hits = 0
        self._miss = 0
        self._evictions = 0

    # ---------- Namespace helpers ----------
    def _ensure_ns(self, ns: Optional[str]) -> str:
        if not ns: ns = self.ns_default
        if ns not in self._store:
            self._store[ns] = []
        return ns

    # ---------- Public API ----------
    @staticmethod
    def fingerprint(system_prompt: str, model_name: str, intent: str) -> str:
        # Usato come namespace logico dal router
        base = f"{(system_prompt or '').strip()}|{(model_name or '').strip()}|{(intent or '').strip()}"
        return _sha256(base)

    def set(self, prompt: str, response_obj: Dict[str, Any], ctx_fp: Optional[str], meta: Optional[Dict[str, Any]] = None) -> None:
        ns = self._ensure_ns(ctx_fp)
        vec = self._emb.encode(prompt)
        with self._lock:
            self._store[ns].append(_Entry(prompt, vec, response_obj, meta))
            # Evict LRU globale se necessario
            total = self.count()
            if total > self.max_items:
                # trova l'entry più vecchia tra tutti i namespace
                oldest_ns, oldest_idx, oldest_ts = None, None, 1 << 60
                for n, lst in self._store.items():
                    if lst:
                        if lst[0].ts < oldest_ts:
                            oldest_ns, oldest_idx, oldest_ts = n, 0, lst[0].ts
                if oldest_ns is not None and oldest_idx is not None and self._store.get(oldest_ns):
                    self._store[oldest_ns].pop(oldest_idx)
                    self._evictions += 1

    def get(self, prompt: str, ctx_fp: Optional[str]) -> Optional[Dict[str, Any]]:
        ns = self._ensure_ns(ctx_fp)
        vec_q = self._emb.encode(prompt)
        best_sim, best_entry = 0.0, None
        now = _now()
        with self._lock:
            lst = self._store.get(ns, [])
            # TTL cleanup in-read & best match
            alive: List[_Entry] = []
            for e in lst:
                if now - e.ts <= self.ttl_s:
                    alive.append(e)
                    try:
                        sim = self._emb.cosine(vec_q, e.vec)
                    except Exception:
                        sim = 0.0
                    if sim > best_sim:
                        best_sim, best_entry = sim, e
            # compattazione TTL se necessario
            if len(alive) != len(lst):
                self._store[ns] = alive

            if best_entry and best_sim >= self.threshold:
                self._hits += 1
                # ritorna payload coerente con quantum_api
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
        # struttura compatibile con /stats/cache corrente
        return {
            "enabled": True,
            "namespace": self.ns_default,
            "threshold": self.threshold,
            "ttl_s": self.ttl_s,
            "max_items": self.max_items,
            "size_items": self.count(),
            "dim": self.dim,
            "hits": self._hits,
            "miss": self._miss,
            "hit_rate": (self._hits / (self._hits + self._miss)) if (self._hits + self._miss) else 0,
            "evictions": self._evictions
        }

    def stats_ns(self, ns: str) -> Dict[str, Any]:
        ns = self._ensure_ns(ns)
        return {
            "enabled": True,
            "namespace": ns,
            "threshold": self.threshold,
            "ttl_s": self.ttl_s,
            "max_items": self.max_items,
            "size_items": len(self._store.get(ns, [])),
            "dim": self.dim,
            # per-NS hits/miss non tracciati separatamente (semplice): riportiamo global
            "hits": self._hits,
            "miss": self._miss,
            "hit_rate": (self._hits / (self._hits + self._miss)) if (self._hits + self._miss) else 0,
            "evictions": self._evictions
        }

    def stats_all(self) -> Dict[str, Any]:
        per_ns = {ns: {"size_items": len(lst)} for ns, lst in self._store.items()}
        return {
            "enabled": True,
            "threshold": self.threshold,
            "ttl_s": self.ttl_s,
            "max_items": self.max_items,
            "dim": self.dim,
            "namespaces": per_ns,
            "total": {
                "size_items": self.count(),
                "hits": self._hits,
                "miss": self._miss,
                "hit_rate": (self._hits / (self._hits + self._miss)) if (self._hits + self._miss) else 0,
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
            model_name=_SEM_MODEL
        )
    return _SINGLETON
