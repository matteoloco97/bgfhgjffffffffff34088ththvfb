#!/usr/bin/env python3
# core/reranker.py - CPU reranker per risultati web

from typing import List, Dict, Tuple
try:
    from FlagEmbedding import FlagReranker
except Exception as e:
    raise RuntimeError("Installa FlagEmbedding: pip install -U FlagEmbedding") from e

class Reranker:
    def __init__(self, model: str = "BAAI/bge-reranker-base", device: str = "cpu"):
        # base è più leggero e stabile su CPU
        self.rr = FlagReranker(model, use_fp16=False, device=device)

    def rerank(self, query: str, results: List[Dict], top_k: int = 8) -> List[Dict]:
        if not results:
            return results
        pairs: List[Tuple[str, str]] = []
        texts: List[str] = []
        for r in results:
            title = (r.get("title") or "").strip()
            # se manca snippet, usa solo il titolo
            snippet = (r.get("snippet") or "").strip()
            txt = (title + " " + snippet).strip()
            texts.append(txt or title or "Untitled")
            pairs.append((query, texts[-1]))
        scores = self.rr.compute_score(pairs, normalize=True)
        order = sorted(range(len(results)), key=lambda i: scores[i], reverse=True)
        out = []
        for i in order[:top_k]:
            item = dict(results[i])
            item["rerank_score"] = float(scores[i])
            out.append(item)
        return out
