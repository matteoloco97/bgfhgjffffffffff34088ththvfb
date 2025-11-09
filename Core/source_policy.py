# core/source_policy.py — YAML policy con auto-reload e fallback multi-categoria
import os, unicodedata, time
from typing import Dict, List

try:
    import yaml  # PyYAML
except Exception:
    yaml = None

_SOURCE_FILE = os.getenv("SOURCE_POLICY_FILE", "config/source_policy.yaml")
_POLICY: Dict = {}
_LAST_MTIME: float | None = None

# Fallback ricco (mai più solo "sport")
_FALLBACK = {
    "categories": {
        "default": {
            "triggers": [],
            "prefer": ["ansa.it", "ilsole24ore.com", "bbc.com", "theguardian.com", "repubblica.it"],
            "allow":  ["wikipedia.org", "treccani.it", "x.com"],
        },
        "weather": {
            "triggers": ["meteo","weather","che tempo","pioggia","vento","temperature","previsioni"],
            "prefer": ["meteoam.it","3bmeteo.com","ilmeteo.it","ilmeteo.net","meteo5.com"],
            "allow":  ["oggiroma.it","ansa.it","ilsole24ore.com"],
        },
        "crypto_fx": {
            "triggers": ["bitcoin","btc","crypto","cripto","prezzo","quotazione","eur/usd","eurusd","forex","borsa","indice","azioni"],
            "prefer": ["coindesk.com","coinmarketcap.com","binance.com","investing.com","tradingview.com","coinbase.com","kraken.com","yahoo.com"],
            "allow":  ["bloomberg.com","reuters.com","ilsole24ore.com"],
        },
        "sports": {
            "triggers": ["serie a","calcio","partite","risultati","odds","quote","scommesse","match"],
            "prefer": ["bet365.com","betfair.com","flashscore.com","flashscore.it","sofascore.com","gazzetta.it",
                       "corrieredellosport.it","skysport.it","uefa.com","fifa.com","legaseriea.it","whoscored.com",
                       "oddschecker.com","oddsportal.com","premierleague.com","soccerway.com","transfermarkt.com","tuttosport.com"],
            "allow":  ["livescore.com","eurobet.it","goldbet.it","planetwin365.it","sportmediaset.it","calciomercato.com",
                       "tuttomercatoweb.com","ansa.it","bbc.com","theguardian.com","x.com"],
        },
    }
}

def _normalize(txt: str) -> str:
    if not txt: return ""
    txt = txt.lower()
    txt = unicodedata.normalize("NFKD", txt)
    return "".join(ch for ch in txt if not unicodedata.combining(ch))

def _load_from_yaml(path: str) -> Dict:
    if not yaml or not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}

def _ensure_policy_loaded():
    global _POLICY, _LAST_MTIME
    try:
        mtime = os.path.getmtime(_SOURCE_FILE) if os.path.exists(_SOURCE_FILE) else None
    except Exception:
        mtime = None

    # Carica o ricarica se cambia il file
    if (_POLICY == {} and _LAST_MTIME is None) or (_LAST_MTIME != mtime):
        data = _load_from_yaml(_SOURCE_FILE)
        if "categories" in data:
            _POLICY = data
        else:
            _POLICY = _FALLBACK
        _LAST_MTIME = mtime

def _match_category(query: str) -> str:
    qn = _normalize(query or "")
    cats = _POLICY.get("categories", {})
    for name, spec in cats.items():
        for trig in spec.get("triggers", []) or []:
            if _normalize(trig) and _normalize(trig) in qn:
                return name
    return "default" if "default" in cats else next(iter(cats.keys()), "default")

def pick_domains(query: str) -> Dict[str, List[str]]:
    _ensure_policy_loaded()
    cats = _POLICY.get("categories", {})
    cname = _match_category(query)
    spec = cats.get(cname, cats.get("default", {}))
    return {
        "prefer": spec.get("prefer", []),
        "allow":  spec.get("allow", []),
        "category": cname,
    }
