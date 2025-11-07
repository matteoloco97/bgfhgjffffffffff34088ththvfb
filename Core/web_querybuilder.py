# core/web_querybuilder.py
from typing import List, Dict

def build_query_variants(q: str, policy: Dict[str, list]) -> List[str]:
    q = (q or "").strip()
    variants: List[str] = []
    prefer  = policy.get("prefer", [])
    allow   = policy.get("allow", [])

    # base + quoted (nessun -site:)
    variants.append(q)
    variants.append(f"\"{q}\"")

    # spingi prefer con site:
    for d in prefer[:6]:
        variants.append(f"{q} site:{d}")
        variants.append(f"\"{q}\" site:{d}")

    # allarga con allow (sempre senza escludere altro)
    for d in allow[:4]:
        variants.append(f"{q} site:{d}")

    # dedup e limite
    seen, uniq = set(), []
    for v in variants:
        if v not in seen:
            uniq.append(v); seen.add(v)
    return uniq[:12]
