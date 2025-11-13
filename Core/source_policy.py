#!/usr/bin/env python3
# core/source_policy.py — Policy picker da trust YAML

from __future__ import annotations
import os, re, json
from typing import Dict, List, Tuple
try:
    import yaml  # pip install pyyaml
except Exception as e:
    raise RuntimeError("Installa pyyaml: pip install pyyaml") from e

_SRC_FILE = os.getenv("SOURCE_POLICY_FILE", "config/source_trust.yaml")

_CAT_PATTERNS = {
    "scores": re.compile(r"(?i)\b(risultat[oi]|score|final|live|classifica|tabellone)\b"),
    "odds":   re.compile(r"(?i)\b(quote|odds|linee|handicap|moneyline|over/under|spread)\b"),
    "stats":  re.compile(r"(?i)\b(statistiche|xg|xga|formazione|lineup|head to head|h2h|expected)\b"),
    "news":   re.compile(r"(?i)\b(ultim[ei]|breaking|notiz|rumor|infortun|transfer|mercato)\b"),
}

def _load_cfg() -> Dict:
    with open(_SRC_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def _pick_category(q: str) -> str:
    s = (q or "").strip().lower()
    for cat, rgx in _CAT_PATTERNS.items():
        if rgx.search(s):
            return cat
    return "odds" if "pronostico" in s or "quota" in s else "news"

def pick_domains(query: str) -> Dict[str, List[str]]:
    """
    Ritorna una policy: {"prefer":[...], "allow":[...], "category": "...", "trust": {...}}
    """
    cfg = _load_cfg()
    cat = _pick_category(query)
    node = (cfg.get("categories") or {}).get(cat) or {}
    fb   = (cfg.get("fallback") or {})

    def order_keys(d: Dict[str, float]) -> List[str]:
        return [k for k,_ in sorted((d or {}).items(), key=lambda kv: kv[1], reverse=True)]

    prefer = order_keys(node.get("prefer", {})) or order_keys(fb.get("prefer", {}))
    allow  = order_keys(node.get("allow", {}))  or order_keys(fb.get("allow", {}))

    return {
        "category": cat,
        "prefer": prefer[:16],
        "allow": allow[:16],
        "trust": {"prefer": node.get("prefer", {}), "allow": node.get("allow", {})}
    }
