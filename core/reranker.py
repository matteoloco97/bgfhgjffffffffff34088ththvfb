#!/usr/bin/env python3
# core/reranker.py — CPU reranker per risultati web (robusto + fallback)
# Patch 2025-11:
# - Import lazy di FlagEmbedding (nessun crash se non installato)
# - Fallback lessicale (cosine su BoW) quando il modello non è disponibile
# - Limite candidati e limite testo per stabilità su CPU
# - API compatibile: Reranker(model, device).rerank(query, results, top_k)

from __future__ import annotations
import os, math, re
from typing import List, Dict, Tuple, Optional

# ==== ENV ====
_RR_MAX_CANDS = int(os.getenv("RERANKER_MAX_CANDIDATES", "32"))      # lim. risultati in input
_RR_TEXT_LIM  = int(os.getenv("RERANKER_TEXT_LIMIT_CHARS", "600"))   # lim. testo (titolo+snippet)
_RR_NORMALIZE = (os.getenv("RERANKER_NORMALIZE", "1").strip().lower() in ("1","true","yes","on"))

# ==== Import opzionale ====
_FlagReranker = None  # type: ignore
try:
    from FlagEmbedding import FlagReranker as _FlagReranker  # type: ignore
    _FlagReranker = _FlagReranker
except Exception:
    _FlagReranker = None  # non disponibile → fallback lessicale


# ==== Utils lessicali (fallback) ====
_TOK = re.compile(r"[a-z0-9àèéìíòóùú]+", re.I)

def _tok(s: str) -> List[str]:
    return _TOK.findall((s or "").lower())

def _bow_norm(tokens: List[str]) -> Dict[str, float]:
    tf: Dict[str, float] = {}
    for t in tokens:
        tf[t] = tf.get(t, 0.0) + 1.0
    if _RR_NORMALIZE:
        norm = math.sqrt(sum(v*v for v in tf.values())) or 1.0
        for k in list(tf.keys()):
            tf[k] = tf[k] / norm
    return tf

def _cos_bow(a: Dict[str, float], b: Dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    # dot su intersezione
    if len(a) < len(b):
        return sum(va * b.get(k, 0.0) for k, va in a.items())
    else:
        return sum(a.get(k, 0.0) * vb for k, vb in b.items())


class Reranker:
    """
    Wrapper robusto:
      - se FlagEmbedding è installato → usa il modello BGE reranker
      - altrimenti → fallback lessicale (cosine BoW) su CPU
    """
    def __init__(self, model: str = "BAAI/bge-reranker-base", device: str = "cpu"):
        self.model = model
        self.device = device
        self._rr = None
        if _FlagReranker is not None:
            try:
                # base è più leggero e ok su CPU
                self._rr = _FlagReranker(model, use_fp16=False, device=device)
            except Exception:
                self._rr = None  # se fallisce, useremo fallback

    def _prep_text(self, r: Dict) -> str:
        title = (r.get("title") or "").strip()
        snip  = (r.get("snippet") or "").strip()
        txt = (f"{title} {snip}").strip() or (title or snip) or "Untitled"
        if len(txt) > _RR_TEXT_LIM:
            txt = txt[:_RR_TEXT_LIM]
        return txt

    def _fallback_scores(self, query: str, texts: List[str]) -> List[float]:
        q_bow = _bow_norm(_tok(query))
        scores: List[float] = []
        for t in texts:
            t_bow = _bow_norm(_tok(t))
            scores.append(float(max(0.0, min(1.0, _cos_bow(q_bow, t_bow)))))
        return scores

    def rerank(self, query: str, results: List[Dict], top_k: int = 8) -> List[Dict]:
        if not results:
            return results

        # limita candidati per stabilità/latency
        cand = results[:max(1, min(_RR_MAX_CANDS, len(results)))]

        texts: List[str] = [self._prep_text(r) for r in cand]

        scores: List[float]
        if self._rr is not None:
            try:
                pairs: List[Tuple[str, str]] = [(query, t) for t in texts]
                # normalize=True produce punteggi comparabili
                scores = self._rr.compute_score(pairs, normalize=True)
            except Exception:
                # se il modello fallisce a runtime, usa fallback
                scores = self._fallback_scores(query, texts)
        else:
            # nessun modello → fallback lessicale
            scores = self._fallback_scores(query, texts)

        order = sorted(range(len(cand)), key=lambda i: scores[i], reverse=True)
        out: List[Dict] = []
        for i in order[:max(1, top_k)]:
            item = dict(cand[i])
            item["rerank_score"] = float(scores[i])
            out.append(item)
        return out
