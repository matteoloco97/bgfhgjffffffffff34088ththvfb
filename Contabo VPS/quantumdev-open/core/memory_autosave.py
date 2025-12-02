# core/memory_autosave.py — Auto-Save with extended preferences support
# 
# Ora supporta:
# - Betting (team, event, market, odds, stake, result, book, league)
# - Preferenze utente (città, exchange, rischio, orizzonte investimento, ecc.)

import re
from typing import Dict, Any, Optional, Tuple, List
from utils.chroma_handler import add_fact, add_bet, add_pref

# ===================== BETTING KEYS =====================
# Chiavi accettate per betting
_BETTING_KEYS = {"team", "event", "market", "odds", "stake", "result", "book", "league"}

_BETTING_KV_RE = re.compile(
    r"(?i)\b(team|event|market|odds|stake|result|book|league)\b\s*[:=]\s*([^\n,;|]+)"
)

# ===================== USER PREFERENCE KEYS =====================
# Pattern pre-compilati per estrarre preferenze utente
# (Chiave: subject in Chroma, Valore: regex pattern compilato)

_PREF_PATTERNS_COMPILED = [
    # Città/Residenza
    (re.compile(r"(?:vivo|abito|sono)\s+(?:a|in)\s+([A-Za-z\s]+)"), "user.city"),
    (re.compile(r"casa\s+(?:mia|nostra)\s+(?:è|sta)\s+(?:a|in)\s+([A-Za-z\s]+)"), "user.city"),
    (re.compile(r"città[:\s]+([A-Za-z\s]+)"), "user.city"),
    (re.compile(r"city[:\s]+([A-Za-z\s]+)"), "user.city"),
    
    # Exchange/Broker
    (re.compile(r"(?:uso|utilizzo|il mio)\s+exchange\s+(?:è|principale)?\s*[:\s]*([A-Za-z0-9\s]+)"), "user.exchange"),
    (re.compile(r"exchange[:\s]+([A-Za-z0-9\s]+)"), "user.exchange"),
    (re.compile(r"broker[:\s]+([A-Za-z0-9\s]+)"), "user.broker"),
    
    # Rischio
    (re.compile(r"(?:tolleranza|livello)\s+(?:di\s+)?rischio[:\s]+([A-Za-z0-9%\s]+)"), "user.risk_tolerance"),
    (re.compile(r"(?:non\s+voglio\s+rischiare\s+più\s+del?)\s+([0-9]+%?)"), "user.max_risk"),
    (re.compile(r"risk[:\s]+([A-Za-z0-9%\s]+)"), "user.risk_tolerance"),
    
    # Orizzonte
    (re.compile(r"orizzonte\s+(?:di\s+)?(?:investimento)?[:\s]+([0-9]+\s*(?:anni|mesi|anni?|months?|years?))"), "user.investment_horizon"),
    (re.compile(r"horizon[:\s]+([0-9]+\s*(?:years?|months?))"), "user.investment_horizon"),
    
    # Focus/Strategia
    (re.compile(r"(?:sono\s+focalizzato|focus)\s+(?:su|on)[:\s]+([A-Za-z0-9\s,]+)"), "user.focus"),
    (re.compile(r"strategia[:\s]+([A-Za-z0-9\s,]+)"), "user.strategy"),
]


def _norm_num(x: str) -> Optional[float]:
    """Normalizza stringa in numero float."""
    s = x.strip().replace("€", "").replace("EUR", "").replace(" ", "")
    s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None


def _extract_betting_kv(text: str) -> Dict[str, str]:
    """Estrae key-value per betting."""
    out: Dict[str, str] = {}
    for k, v in _BETTING_KV_RE.findall(text or ""):
        key = k.strip().lower()
        if key in _BETTING_KEYS:
            out[key] = v.strip().strip("*").strip()
    return out


def _extract_user_prefs(text: str) -> List[Dict[str, str]]:
    """
    Estrae preferenze utente dal testo usando pattern matching pre-compilati.
    Ritorna lista di dict con {'key': subject, 'value': valore}.
    """
    if not text:
        return []
    
    prefs: List[Dict[str, str]] = []
    text_lower = text.lower()
    seen_subjects: set = set()  # Evita duplicati per stesso subject
    
    for compiled_pattern, subject in _PREF_PATTERNS_COMPILED:
        # Skip se già trovato un valore per questo subject
        if subject in seen_subjects:
            continue
            
        match = compiled_pattern.search(text_lower)
        if match:
            value = match.group(1).strip()
            # Pulisci valore da punteggiatura finale
            while value and value[-1] in ".,;:!?":
                value = value[:-1]
            value = value.strip()
            
            if value and len(value) > 1:
                prefs.append({"key": subject, "value": value})
                seen_subjects.add(subject)
    
    return prefs


def _save_from_chat_kv(kv: Dict[str, str]) -> Dict[str, Any]:
    """Salva dati betting da K/V estratti."""
    saved: Dict[str, Any] = {"facts": [], "bet": None, "prefs": []}

    # Normalizza numeri
    odds = _norm_num(kv.get("odds", "")) if "odds" in kv else None
    stake = _norm_num(kv.get("stake", "")) if "stake" in kv else None

    team = kv.get("team")
    event = kv.get("event") or (f"Team: {team}" if team else None)
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
            metadata={k: v for k, v in kv.items() if k not in ("odds", "stake", "result")}
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


def _save_user_prefs(prefs: List[Dict[str, str]], source: str) -> List[str]:
    """
    Salva preferenze utente in Chroma.
    Ritorna lista di ID salvati.
    """
    saved_ids: List[str] = []
    
    for pref in prefs:
        key = pref.get("key", "")
        value = pref.get("value", "")
        
        if not key or not value:
            continue
        
        try:
            # Usa add_pref per preferenze utente
            _id = add_pref(
                key=key,
                value=value,
                scope="user",
                source=source,
                metadata={"category": "user_preference"}
            )
            saved_ids.append(_id)
        except (ValueError, TypeError, RuntimeError) as e:
            # Fallback: salva come fact se add_pref non è disponibile o fallisce
            import logging
            logging.getLogger(__name__).debug(f"add_pref failed for {key}, trying fact: {e}")
            try:
                _id = add_fact(key, value, source=source)
                saved_ids.append(_id)
            except Exception as inner_e:
                logging.getLogger(__name__).warning(f"Failed to save pref {key}: {inner_e}")
    
    return saved_ids


def autosave(text: str, source: str = "chat_user") -> Dict[str, Any]:
    """
    Auto-save intelligente per dati chat/utente.
    
    Regole:
    - chat_user / chat_reply / generate_input: 
      1. Estrai K/V betting (team, odds, stake, ecc.)
      2. Estrai preferenze utente (città, exchange, rischio, ecc.)
      3. Salva bet se odds+stake
      4. Salva facts/prefs rilevanti
    - web_* / direct_llm: NON salvare nulla (evita rumore)
    - chat_reply_autoweb: NON salvare (dati live, non preferenze)
    """
    src = (source or "").lower()
    result: Dict[str, Any] = {"facts": [], "prefs": [], "bet": None}

    # Blocca autosave da fonti web/modello
    if src.startswith("web_") or src in {
        "web_search", "web_read", "web_summarize", "direct_llm", "chat_reply_autoweb"
    }:
        return result

    if src in {"chat_user", "chat_reply", "generate_input"}:
        # 1. Prova a estrarre K/V betting
        kv = _extract_betting_kv(text or "")
        if kv:
            bet_result = _save_from_chat_kv(kv)
            result["facts"].extend(bet_result.get("facts", []))
            result["bet"] = bet_result.get("bet")
        
        # 2. Estrai preferenze utente (anche se non ci sono K/V betting)
        user_prefs = _extract_user_prefs(text or "")
        if user_prefs:
            saved_pref_ids = _save_user_prefs(user_prefs, source=src)
            result["prefs"].extend(saved_pref_ids)
        
        return result

    # Default: non salvare
    return result
