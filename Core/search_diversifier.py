# Core/search_diversifier.py

from __future__ import annotations
from collections import defaultdict
from typing import List, Dict, Any, Tuple
from urllib.parse import urlparse


def _extract_domain(url: str) -> str:
    try:
        h = urlparse(url or "").hostname or ""
        parts = h.split(".")
        if len(parts) >= 2:
            return ".".join(parts[-2:])
        return h
    except Exception:
        return ""


def _sorted_by_score(groups: Dict[str, List[Dict[str, Any]]], score_key: str) -> List[Tuple[str, List[Dict[str, Any]]]]:
    """
    Ritorna la lista (dominio, items) ordinata per best score decrescente.
    """
    scored: List[Tuple[str, float]] = []
    for dom, items in groups.items():
        if not items:
            continue
        best = max(items, key=lambda x: float(x.get(score_key, 0.0)))
        scored.append((dom, float(best.get(score_key, 0.0))))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [(dom, groups[dom]) for dom, _ in scored]


def _detect_content_type(url: str) -> str:
    """
    Euristica semplice per tipo di contenuto (puoi raffinarla in futuro).
    """
    u = (url or "").lower()
    if "youtube." in u or "vimeo." in u:
        return "video"
    if any(x in u for x in ("reddit.", "forum.", "/forum/", "/thread/")):
        return "forum"
    if any(x in u for x in ("docs.", "/docs/", "developer.", "manpages")):
        return "docs"
    if any(x in u for x in ("/blog", "blog.")):
        return "blog"
    if any(x in u for x in ("/news", "news.")):
        return "news"
    return "other"


def _balance_content_types(results: List[Dict[str, Any]], max_per_type: int = 3) -> List[Dict[str, Any]]:
    """
    Piccolo bilanciamento per tipo di contenuto (news, docs, blog, forum, video, other).
    """
    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in results:
        t = _detect_content_type(str(r.get("url", "")))
        buckets[t].append(r)

    # Mantieni ordine globale ma limiterai i tipi troppo dominanti
    out: List[Dict[str, Any]] = []
    type_counts: Dict[str, int] = defaultdict(int)

    for r in results:
        t = _detect_content_type(str(r.get("url", "")))
        if type_counts[t] >= max_per_type:
            continue
        out.append(r)
        type_counts[t] += 1

    return out


class SearchDiversifier:
    """
    Diversifica i risultati post-reranking:
    - massimo N per dominio
    - round-robin sulle fonti principali
    - piccolo bilanciamento dei tipi di contenuto
    """

    def __init__(self, max_per_domain: int = 2, score_key: str = "rerank_score") -> None:
        self.max_per_domain = max_per_domain
        self.score_key = score_key

    def diversify(self, results: List[Dict[str, Any]], top_k: int = 8) -> List[Dict[str, Any]]:
        if not results:
            return []

        by_domain: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for r in results:
            url = str(r.get("url") or "")
            dom = _extract_domain(url)
            by_domain[dom].append(r)

        # Passo 1: un risultato per dominio, ordinati per best score
        diversified: List[Dict[str, Any]] = []
        domain_counts: Dict[str, int] = defaultdict(int)

        for dom, items in _sorted_by_score(by_domain, self.score_key):
            if not items:
                continue
            best = max(items, key=lambda x: float(x.get(self.score_key, 0.0)))
            diversified.append(best)
            domain_counts[dom] = 1
            if len(diversified) >= top_k:
                break

        if len(diversified) >= top_k:
            return diversified[:top_k]

        # Passo 2: riempi fino a top_k rispettando max_per_domain
        for dom, items in by_domain.items():
            # Ordina gli items per score decrescente
            sorted_items = sorted(items, key=lambda x: float(x.get(self.score_key, 0.0)), reverse=True)
            for item in sorted_items:
                if item in diversified:
                    continue
                if domain_counts[dom] >= self.max_per_domain:
                    continue
                diversified.append(item)
                domain_counts[dom] += 1
                if len(diversified) >= top_k:
                    break
            if len(diversified) >= top_k:
                break

        # Passo 3: piccolo bilanciamento tipi di contenuto
        diversified = _balance_content_types(diversified, max_per_type=3)

        return diversified[:top_k]
