# core/web_querybuilder.py — Variants builder (betting-aware + recency + site filters)
from __future__ import annotations
from typing import List, Dict, Set
from datetime import datetime

# --- helpers & dictionaries -------------------------------------------------

BETTING_SYNONYMS: Dict[str, List[str]] = {
    "quote":       ["odds", "prezzo"],
    "pronostico":  ["prediction", "forecast", "preview"],
    "risultato":   ["result", "final", "score"],
    "formazione":  ["lineup", "starting xi", "team sheet"],
}

RECENCY_TRIGGERS: tuple = (
    "oggi", "adesso", "ora", "in tempo reale", "live",
    "ultime", "breaking", "aggiornati", "latest", "now",
)

BETTING_CUES: tuple = (
    "quote", "odds", "pronostico", "match", "partita", "risultato",
    "formazione", "lineup", "starting xi", "vs", " v ", " - "
)

def _contains_any(s: str, words: List[str] | tuple) -> bool:
    s = (s or "").lower()
    return any(w in s for w in words)

def _add(variants: List[str], s: str, seen: Set[str], limit: int):
    if len(variants) >= limit:
        return
    s = (s or "").strip()
    if not s:
        return
    k = s.lower()
    if k not in seen:
        variants.append(s)
        seen.add(k)

def _has_year(q: str) -> bool:
    y = datetime.now().year
    ql = q.lower()
    # se già contiene un anno recente (dal 2018 ad oggi), non aggiungere
    for yy in range(2018, y + 1):
        if str(yy) in ql:
            return True
    return False

def _year_tag_needed(q: str) -> bool:
    """Aggiunge l'anno se potenzialmente time-sensitive (betting/match/odds) e l'anno non è già presente."""
    if _has_year(q):
        return False
    ql = q.lower()
    return any(c in ql for c in BETTING_CUES)

def _normalize_vs(q: str) -> str:
    """Uniforma separatori di match: 'A - B', 'A v B' → 'A vs B' (senza toccare il resto)."""
    qn = q.replace(" v ", " vs ").replace(" V ", " vs ")
    qn = qn.replace(" - ", " vs ").replace(" — ", " vs ").replace(" – ", " vs ")
    return qn

def _build_betting_expansions(q: str) -> List[str]:
    """Espande la query con sinonimi utili nel dominio betting."""
    out: List[str] = []
    ql = q.lower()

    # Se contiene "quote/odds" → aggiungi anno corrente come variante
    if "quote" in ql or "odds" in ql:
        out.append(f"{q} {datetime.now().year}")

    # Se è query su match/partita ma non cita 'risultato' → aggiungi variante con 'risultato'
    if any(k in ql for k in ("match", "partita", "vs", " v ", " - ")) and not _contains_any(ql, ("risultato", "result", "score")):
        out.append(f"{q} risultato")

    # Sinonimi mirati (IT/EN)
    for key, syns in BETTING_SYNONYMS.items():
        if key in ql:
            for s in syns:
                out.append(ql.replace(key, s))
    return out

def _maybe_recency_suffix(q: str) -> List[str]:
    """Se la query suggerisce urgenza/live, aggiungi piccole varianti 'oggi' / 'live'."""
    ql = q.lower()
    if _contains_any(ql, RECENCY_TRIGGERS):
        return []
    # Non appesantire troppo: massimo due micro-varianti
    return [f"{q} oggi", f"{q} live"]

# --- public -----------------------------------------------------------------

def build_query_variants(q: str, policy: Dict[str, list]) -> List[str]:
    """
    Genera varianti di query:
      - base (+ normalizzazione vs) + quoted (se multi-parola)
      - espansioni betting-aware (sinonimi, 'risultato', anno corrente se utile)
      - iniezione anno se sensata e mancante
      - piccoli trigger di recency ('oggi', 'live') se assenti
      - site: prefer/allow (con priorità ai prefer)
    Ritorna al massimo 16 varianti deduplicate (case-insensitive) e ordinate per priorità.
    """
    q = (q or "").strip()
    q_norm = _normalize_vs(q)

    prefer  = list(policy.get("prefer", []) or [])
    allow   = list(policy.get("allow", []) or [])

    MAX_VARIANTS = 16
    variants: List[str] = []
    seen: Set[str] = set()

    # 1) Base (normalizzata) + quoted solo se contiene spazio
    _add(variants, q_norm, seen, MAX_VARIANTS)
    if " " in q_norm:
        _add(variants, f"\"{q_norm}\"", seen, MAX_VARIANTS)

    # 2) Betting-aware expansions
    if _contains_any(q_norm, BETTING_CUES):
        for v in _build_betting_expansions(q_norm):
            _add(variants, v, seen, MAX_VARIANTS)

    # 3) Anno corrente se sensato e mancante
    if _year_tag_needed(q_norm):
        _add(variants, f"{q_norm} {datetime.now().year}", seen, MAX_VARIANTS)

    # 4) Recency micro-varianti (solo se non già presenti trigger)
    for v in _maybe_recency_suffix(q_norm):
        _add(variants, v, seen, MAX_VARIANTS)

    # 5) site: prefer (spingi domini forti)
    for d in prefer[:6]:
        _add(variants, f"{q_norm} site:{d}", seen, MAX_VARIANTS)
        if " " in q_norm:
            _add(variants, f"\"{q_norm}\" site:{d}", seen, MAX_VARIANTS)

    # 6) site: allow (apri ma mirato, una sola variante per dominio)
    for d in allow[:6]:
        _add(variants, f"{q_norm} site:{d}", seen, MAX_VARIANTS)

    # 7) site: anche per varianti informative (cap per non esplodere)
    informative: List[str] = []
    for v in variants:
        vl = v.lower()
        if any(k in vl for k in (" 20", "risultato", "odds", "quote", "lineup", "starting xi", "oggi", " live")):
            informative.append(v)
    for v in informative[:3]:
        for d in prefer[:3]:
            _add(variants, f"{v} site:{d}", seen, MAX_VARIANTS)

    # 8) ritorna entro il limite
    return variants[:MAX_VARIANTS]
