#!/usr/bin/env python3
# core/source_policy.py
# Robust loader + query normalization + union global/rules

from __future__ import annotations
import os
import yaml
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Set

_DEFAULT: Dict = {"global": {"prefer": [], "allow": [], "block": []}, "rules": []}

def _norm(text: str) -> str:
    """
    Normalizza la stringa per il matching:
    - lowercase
    - rimozione accenti
    - mantiene solo alfanumerici e spazi
    """
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", text)
    t = t.encode("ascii", "ignore").decode()
    t = t.lower()
    return "".join(c for c in t if c.isalnum() or c.isspace())

def _project_root() -> Path:
    """
    Determina la root del progetto:
    1) QUANTUM_ROOT (se settata)
    2) <repo>/ (genitore di core/)
    """
    env_root = os.getenv("QUANTUM_ROOT")
    if env_root:
        return Path(env_root).expanduser().expandvars().resolve()
    # __file__ ... /core/source_policy.py -> parents[1] = repo root
    return Path(__file__).resolve().parents[1]

def _resolve_policy_path() -> Path:
    """
    Risolve il path del file YAML della source policy in modo robusto.
    PRIORITY:
    - SOURCE_POLICY_FILE (assoluto o relativo alla root)
    - <root>/config/source_policy.yaml
    """
    root = _project_root()
    env_path = os.getenv("SOURCE_POLICY_FILE")
    if env_path:
        p = Path(env_path).expanduser().expandvars()
        if not p.is_absolute():
            p = (root / p).resolve()
        else:
            p = p.resolve()
        return p
    return (root / "config" / "source_policy.yaml").resolve()

def _coalesce_policy(data: Dict | None) -> Dict:
    """
    Garantisce la presenza delle chiavi e dei default necessari.
    """
    if not isinstance(data, dict):
        return _DEFAULT
    out = {
        "global": {
            "prefer": list(data.get("global", {}).get("prefer", []) or []),
            "allow":  list(data.get("global", {}).get("allow",  []) or []),
            "block":  list(data.get("global", {}).get("block",  []) or []),
        },
        "rules": list(data.get("rules", []) or []),
    }
    return out

@lru_cache(maxsize=1)
def _load_policy_from(path_str: str) -> Dict:
    """
    Carica il file YAML dal path specificato (string) e normalizza la struttura.
    Memoizzata per performance; usare reload_policy() per invalidare.
    """
    p = Path(path_str)
    if not p.exists():
        return _DEFAULT
    try:
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception:
        return _DEFAULT
    return _coalesce_policy(data)

def reload_policy() -> None:
    """Resetta la cache del file policy (chiamare dopo modifiche al YAML)."""
    _load_policy_from.cache_clear()  # type: ignore[attr-defined]

def load_policy() -> Dict:
    """
    Mantiene la compatibilità con la tua API precedente.
    """
    return _load_policy_from(str(_resolve_policy_path()))

def _uniq_preserve(seq: List[str]) -> List[str]:
    """Deduplica preservando l'ordine."""
    seen: Set[str] = set()
    out: List[str] = []
    for s in seq:
        if not s:
            continue
        if s not in seen:
            out.append(s)
            seen.add(s)
    return out

def pick_domains(query: str) -> Dict[str, List[str]]:
    """
    Unisce i domini globali con quelli delle regole che matchano la query.
    - Matching su query normalizzata (_norm)
    - Regole: when_any (OR), when_all (AND)
    - 'prefer' vince su 'allow' solo come ranking: non filtra
    - 'block' è ignorato by design (OPEN policy), ma viene comunque letto
    """
    qn = _norm(query or "")
    pol = load_policy()

    prefer: List[str] = list(pol.get("global", {}).get("prefer", []) or [])
    allow:  List[str] = list(pol.get("global", {}).get("allow",  []) or [])
    # block è caricato ma non usato come filtro (OPEN)
    # block: List[str] = list(pol.get("global", {}).get("block",  []) or [])

    for rule in pol.get("rules", []):
        any_kw = [_norm(w) for w in rule.get("when_any", [])]
        all_kw = [_norm(w) for w in rule.get("when_all", [])]

        if any_kw and not any(k in qn for k in any_kw):
            continue
        if all_kw and not all(k in qn for k in all_kw):
            continue

        prefer += list(rule.get("prefer", []) or [])
        allow  += list(rule.get("allow",  []) or [])

    # Dedup e rimozione overlap: prefer ha priorità nel ranking
    prefer = _uniq_preserve(prefer)
    allow  = [d for d in _uniq_preserve(allow) if d not in set(prefer)]

    return {"prefer": prefer, "allow": allow}
