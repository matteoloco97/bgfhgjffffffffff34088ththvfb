# core/memory_autosave.py — Auto-Save hard-filter (chat K/V only, no web noise)

import re
from typing import Dict, Any, Optional, Tuple
from utils.chroma_handler import add_fact, add_bet

# Chiavi accettate per input chat/utente
_VALID_KEYS = {"team","event","market","odds","stake","result","book","league"}

_KV_RE = re.compile(
    r"(?i)\b(team|event|market|odds|stake|result|book|league)\b\s*[:=]\s*([^\n,;|]+)"
)

def _norm_num(x: str) -> Optional[float]:
    s = x.strip().replace("€","").replace("EUR","").replace(" ", "")
    s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None

def _extract_kv(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k, v in _KV_RE.findall(text or ""):
        key = k.strip().lower()
        if key in _VALID_KEYS:
            out[key] = v.strip().strip("*").strip()
    return out

def _save_from_chat_kv(kv: Dict[str, str]) -> Dict[str, Any]:
    saved: Dict[str, Any] = {"facts": [], "bet": None, "prefs": []}

    # Normalizza numeri
    odds  = _norm_num(kv.get("odds","")) if "odds" in kv else None
    stake = _norm_num(kv.get("stake","")) if "stake" in kv else None

    team   = kv.get("team")
    event  = kv.get("event") or (f"Team: {team}" if team else None)
    market = kv.get("market") or "N/A"
    result = kv.get("result") or "open"

    # Se abbiamo odds & stake → salva come bet
    if odds is not None and stake is not None:
        _id = add_bet(
            event=event or "AUTO:unknown",
            market=market,
            odds=odds,
            stake=stake,
            result=result,
            source="chat_user",
            metadata={k: v for k, v in kv.items() if k not in ("odds","stake","result")}
        )
        saved["bet"] = _id

    # Salva alcuni fact utili (solo whitelisted)
    if team:
        saved["facts"].append(add_fact("team", team, source="chat_user"))
    if "league" in kv:
        saved["facts"].append(add_fact("league", kv["league"], source="chat_user"))
    if "book" in kv:
        saved["facts"].append(add_fact("book", kv["book"], source="chat_user"))

    return saved

def autosave(text: str, source: str = "chat_user") -> Dict[str, Any]:
    """
    Regole:
    - chat_user / chat_reply / generate_input: estrai SOLO K/V whitelisted; salva bet se odds+stake; salva pochi fact utili
    - web_* / direct_llm: NON salvare nulla automaticamente (evita rumore tipo 'fonti', 'https', URL ecc.)
    """
    src = (source or "").lower()

    if src in {"chat_user","chat_reply","generate_input"}:
        kv = _extract_kv(text or "")
        if kv:
            return _save_from_chat_kv(kv)
        # niente K/V → non salvare
        return {"facts": [], "prefs": [], "bet": None}

    # Blocca autosave dalle fonti web / modello per evitare rumore
    if src.startswith("web_") or src in {"web_search","web_read","web_summarize","direct_llm"}:
        return {"facts": [], "prefs": [], "bet": None}

    # Default: non salvare
    return {"facts": [], "prefs": [], "bet": None}
