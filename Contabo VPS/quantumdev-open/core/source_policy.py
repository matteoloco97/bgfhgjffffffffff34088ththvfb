#!/usr/bin/env python3
# core/source_policy.py — Policy picker da trust YAML

from __future__ import annotations

import os
import re
from typing import Dict, List, Any
from collections.abc import Mapping

try:
    import yaml  # pip install pyyaml
except Exception as e:
    raise RuntimeError("Installa pyyaml: pip install pyyaml") from e

_SRC_FILE = os.getenv("SOURCE_POLICY_FILE", "config/source_trust.yaml")

_CAT_PATTERNS = {
    "scores": re.compile(
        r"(?i)\b(risultat[oi]|score|final|live|classifica|tabellone)\b"
    ),
    "odds": re.compile(
        r"(?i)\b(quote|odds|linee|handicap|moneyline|over/under|spread)\b"
    ),
    "stats": re.compile(
        r"(?i)\b(statistiche|xg|xga|formazione|lineup|head to head|h2h|expected)\b"
    ),
    "news": re.compile(
        r"(?i)\b(ultim[ei]|breaking|notiz|rumor|infortun|transfer|mercato)\b"
    ),
}


def _load_cfg() -> Dict:
    with open(_SRC_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _pick_category(q: str) -> str:
    s = (q or "").strip().lower()
    for cat, rgx in _CAT_PATTERNS.items():
        if rgx.search(s):
            return cat
    # default: se parla di quote/pronostici → "odds", altrimenti "news"
    return "odds" if ("pronostico" in s or "quota" in s) else "news"


def _order_keys(d: Any) -> List[str]:
    """
    Normalizza l'ordinamento delle chiavi di prefer/allow.

    - Se `d` è un dict {dominio: peso} → ordina per peso desc.
    - Se `d` è una lista/tupla → restituisce la lista così com'è, normalizzata a stringhe.
    - Altrimenti (None, stringhe, ecc.) → lista vuota.
    """
    if d is None:
        return []

    # Caso: lista/tupla di domini
    if isinstance(d, (list, tuple)):
        return [str(x).strip() for x in d if x]

    # Caso: mapping tipo dict
    if isinstance(d, Mapping):
        items = list(d.items())
        try:
            items_sorted = sorted(items, key=lambda kv: kv[1], reverse=True)
        except Exception:
            # se i valori non sono ordinabili tra loro, non forzare il sort
            items_sorted = items
        return [str(k).strip() for k, _ in items_sorted if k]

    # Fallback sicuro
    return []


def pick_domains(query: str) -> Dict[str, Any]:
    """
    Ritorna una policy:

    {
        "category": "<scores|odds|stats|news>",
        "prefer": [...],
        "allow": [...],
        "trust": {
            "prefer": <raw from YAML>,
            "allow":  <raw from YAML>,
        }
    }
    """
    cfg = _load_cfg()
    cat = _pick_category(query)

    categories = cfg.get("categories") or {}
    node = categories.get(cat) or {}

    fb = cfg.get("fallback") or {}

    prefer = _order_keys(node.get("prefer")) or _order_keys(fb.get("prefer"))
    allow = _order_keys(node.get("allow")) or _order_keys(fb.get("allow"))

    return {
        "category": cat,
        "prefer": prefer[:16],
        "allow": allow[:16],
        "trust": {
            "prefer": node.get("prefer", {}),
            "allow": node.get("allow", {}),
        },
    }
