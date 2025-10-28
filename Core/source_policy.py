# core/source_policy.py
import os, yaml
from functools import lru_cache
from typing import Dict, List, Set

_DEFAULT = {"global": {"prefer": [], "allow": [], "block": []}, "rules": []}

@lru_cache(maxsize=1)
def load_policy() -> Dict:
    path = os.getenv("SOURCE_POLICY_FILE", "config/source_policy.yaml")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or _DEFAULT
    return _DEFAULT

def pick_domains(query: str) -> Dict[str, List[str]]:
    q = (query or "").lower()
    pol = load_policy()
    prefer: Set[str] = set(pol.get("global", {}).get("prefer", []))
    allow:  Set[str] = set(pol.get("global", {}).get("allow",  []))
    # OPEN: ignoriamo completamente eventuali "block"
    for rule in pol.get("rules", []):
        any_kw = [w.lower() for w in rule.get("when_any", [])]
        all_kw = [w.lower() for w in rule.get("when_all", [])]
        if (not any_kw or any(k in q for k in any_kw)) and all(k in q for k in all_kw):
            prefer |= set(rule.get("prefer", []))
            allow  |= set(rule.get("allow",  []))
    # prefer vince su allow solo come ranking (non filtro)
    allow -= prefer
    return {"prefer": sorted(prefer), "allow": sorted(allow)}
