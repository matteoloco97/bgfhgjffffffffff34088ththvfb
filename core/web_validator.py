"""
core/web_validator.py

Validator sui risultati multi-fonte della ricerca web.

Idea:
- Dato un elenco di documenti (snippet/estratti), calcola quanto sono
  tra loro "allineati" a livello di contenuto (Jaccard sui token).
- Evidenzia eventuali outlier → fonti minoritarie / fuori coro.

Non è una verità assoluta, ma un segnale utile per la UI e per la GPT.
"""

from __future__ import annotations

import re
from typing import List, Dict, Any


def _tokenize(text: str) -> List[str]:
    # Tokenizzazione super semplice, niente dipendenze esterne.
    tokens = re.findall(r"\w+", text.lower())
    return [t for t in tokens if len(t) > 3]


def _jaccard(a: List[str], b: List[str]) -> float:
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    inter = len(sa & sb)
    union = len(sa | sb)
    if union == 0:
        return 0.0
    return inter / union


def _avg_similarity(idx: int, tokenized: List[List[str]]) -> float:
    sims: List[float] = []
    for j, tj in enumerate(tokenized):
        if j == idx:
            continue
        sims.append(_jaccard(tokenized[idx], tj))
    if not sims:
        return 0.0
    return sum(sims) / len(sims)


def evaluate_multi_source_consensus(
    items: List[Dict[str, Any]],
    text_key: str = "snippet",
    outlier_threshold: float = 0.18,
) -> Dict[str, Any]:
    """
    Analizza una lista di risultati web e prova a capire se:
    - c'è un consenso "forte" (tutti più o meno d'accordo);
    - ci sono 1+ fonti outlier (minoritarie).

    `items` è pensato per avere chiavi tipo:
      { "url": ..., "title": ..., "snippet": "testo estratto", ... }

    Ritorna un dict JSON-friendly:
    {
        "consensus": "strong" / "mixed" / "weak" / "unknown",
        "outliers": [index, ...],
        "outlier_urls": [...],
        "avg_similarity": float,
    }
    """
    if not items:
        return {
            "consensus": "unknown",
            "outliers": [],
            "outlier_urls": [],
            "avg_similarity": 0.0,
        }

    texts: List[str] = []
    for it in items:
        txt = str(it.get(text_key) or it.get("summary") or it.get("content") or "")
        texts.append(txt)

    tokenized = [_tokenize(t) for t in texts]

    if len(tokenized) == 1:
        # con una sola fonte non possiamo parlare di consenso
        return {
            "consensus": "unknown",
            "outliers": [],
            "outlier_urls": [],
            "avg_similarity": 0.0,
        }

    # Similarità media complessiva
    pair_sims: List[float] = []
    for i in range(len(tokenized)):
        for j in range(i + 1, len(tokenized)):
            pair_sims.append(_jaccard(tokenized[i], tokenized[j]))

    if not pair_sims:
        global_avg = 0.0
    else:
        global_avg = sum(pair_sims) / len(pair_sims)

    # Individua outlier confrontando la similarità media per documento.
    outliers_idx: List[int] = []
    for i in range(len(tokenized)):
        avg_i = _avg_similarity(i, tokenized)
        if avg_i < outlier_threshold:
            outliers_idx.append(i)

    if global_avg >= 0.40 and not outliers_idx:
        consensus = "strong"
    elif global_avg >= 0.25:
        consensus = "mixed"
    else:
        consensus = "weak"

    outlier_urls: List[str] = []
    for i in outliers_idx:
        url = str(items[i].get("url") or "")
        outlier_urls.append(url)

    return {
        "consensus": consensus,
        "outliers": outliers_idx,
        "outlier_urls": outlier_urls,
        "avg_similarity": round(global_avg, 3),
    }
