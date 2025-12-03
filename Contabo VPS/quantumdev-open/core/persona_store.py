# core/persona_store.py
import os, json, asyncio
from typing import Any, Dict, Optional

from dotenv import load_dotenv

# Redis è opzionale: se non disponibile, si usa solo la persona di default.
try:
    import redis  # type: ignore
except Exception:
    redis = None  # type: ignore

load_dotenv()
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB   = int(os.getenv("REDIS_DB", 0))

def _mk_redis() -> Optional["redis.Redis"]:  # type: ignore[name-defined]
    if not redis:
        return None
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, socket_timeout=0.5)
        # ping leggero; se fallisce, usiamo fallback in memoria
        try: r.ping()
        except Exception: return None
        return r
    except Exception:
        return None

_r = _mk_redis()

# Keying
_KEY = "persona:{src}:{sid}"
_DEFAULT_KEY = "persona:global:default"
def _k(src: str, sid: str) -> str: return _KEY.format(src=src, sid=sid)

# ——— Riassunto capability condiviso ———
CAPABILITIES_BRIEF = (
    "Posso accedere al web quando serve per dati aggiornati (meteo, prezzi, notizie, risultati sportivi, ecc.) "
    "tramite il comando /web o automaticamente per query live. "
    "Ho memoria a lungo termine via ChromaDB (facts, preferenze, betting history) e cache Redis. "
    "Uso il web in modo selettivo: solo quando necessario, non per ogni domanda. "
    "Non accedo a file o dispositivi dell'utente."
)


# Pattern utili per instradamento meta (facoltativi; la quantum_api ha già un suo set)
META_IGNORE_PATTERNS = [
    r"\b(chi\s+sei|cosa\s+puoi\s+fare|come\s+funzioni)\b",
    r"\b(puoi|riesci)\s+(navigare|usare|accedere)\s+(a|su)\s+internet\b",
    r"\b(collegarti|connetterti)\s+(a|su)\s+internet\b",
]

# ✅ PERSONA ULTRA CONCISA + policy web/sorgenti
DEFAULT_PERSONA: Dict[str, Any] = {
    "persona_id": "quantum-assistant-v3",
    "system": [
        "Sei Jarvis (Quantum AI), l'assistente personale di Matteo, generalista con focus su betting, trading, crypto e tech.",
        "Lingua di default: italiano. Puoi rispondere in altre lingue se richiesto.",
        "Stile: diretto, tecnico ma comprensibile, zero filtri inutili.",
        "",
        "CAPACITÀ REALI:",
        "- Web: consulto il web per dati aggiornati (meteo, prezzi, news, risultati sportivi) via comando /web o automaticamente.",
        "- Memoria: ho accesso a memoria persistente ChromaDB (facts, preferenze, betting history) e cache Redis.",
        "- Contesto: mantengo il contesto della conversazione corrente, ma non ricordo tutte le chat precedenti parola per parola.",
        "",
        "REGOLE DI OUTPUT:",
        "- Risposte brevi e dirette (2–5 frasi max, 1 per domande temporali).",
        "- Niente pensieri ad alta voce o disclaimer inutili.",
        "- Se uso il web, chiudo con: «Fonti: URL1[, URL2]».",
        "- Se mancano dati specifici, lo dico chiaramente invece di inventare.",
        "",
        "Esempi temporali:",
        "Q: Che ora è?  A: 🕐 Sono le 01:22",
        "Q: Che giorno è oggi?  A: 📅 Oggi è Venerdì 31 Ottobre 2025",
    ],
    "behavior": {
        "verbosity": "minimal",
        "sources_position": "end",
        "uncertainty_marker": "⚠️",
        "verified_marker": "✅",
        "max_response_sentences": 5,
        "temporal_response_sentences": 1
    },
    "tool_prefs": {
        "web": {"timeout_ms": 12000, "max_chars": 4000},
        "ocr": {"timeout_ms": 15000, "lang": "ita+eng"}
    },
    "version": 3
}

# --- Helpers ---

def _wrap_legacy(value: str) -> Dict[str, Any]:
    v = (value or "").strip()
    if not v:
        return DEFAULT_PERSONA
    return {**DEFAULT_PERSONA, "system": [v], "version": 1}

def _loads_or_wrap(blob: Optional[bytes]) -> Dict[str, Any]:
    if not blob:
        return DEFAULT_PERSONA
    try:
        return json.loads(blob.decode("utf-8"))
    except Exception:
        try:
            return _wrap_legacy(blob.decode("utf-8", errors="ignore"))
        except Exception:
            return DEFAULT_PERSONA

def build_system_prompt(persona: Dict[str, Any]) -> str:
    sys_msgs = persona.get("system") or []
    if isinstance(sys_msgs, str):
        sys_msgs = [sys_msgs]
    return "\n".join(m.strip() for m in sys_msgs if m and isinstance(m, str))

# --- API async (non bloccare l'event loop) ---

async def get_persona_struct(src: str, sid: str) -> Dict[str, Any]:
    if _r is None:
        return DEFAULT_PERSONA
    blob = await asyncio.to_thread(_r.get, _k(src, sid))
    if blob is None:
        blob = await asyncio.to_thread(_r.get, _DEFAULT_KEY)
    return _loads_or_wrap(blob)

async def set_persona_struct(src: str, sid: str, data: Dict[str, Any]) -> None:
    if _r is None:
        return  # nessun Redis: niente persistenza, ma non alziamo errori
    data = dict(data or {})
    data.setdefault("persona_id", f"{src}:{sid}")
    data.setdefault("version", 1)
    await asyncio.to_thread(_r.set, _k(src, sid), json.dumps(data, ensure_ascii=False))

async def reset_persona(src: str, sid: str) -> None:
    if _r is None:
        return
    await asyncio.to_thread(_r.delete, _k(src, sid))

async def get_default_persona() -> Dict[str, Any]:
    if _r is None:
        return DEFAULT_PERSONA
    blob = await asyncio.to_thread(_r.get, _DEFAULT_KEY)
    return _loads_or_wrap(blob)

async def set_default_persona(data: Dict[str, Any]) -> None:
    if _r is None:
        return
    data = dict(data or {})
    data.setdefault("persona_id", "default")
    data.setdefault("version", 1)
    await asyncio.to_thread(_r.set, _DEFAULT_KEY, json.dumps(data, ensure_ascii=False))

async def get_effective_system(src: str, sid: str) -> str:
    persona = await get_persona_struct(src, sid)
    return build_system_prompt(persona)

# --- Backward-compat shims (usati da quantum_api.py) ---

async def get_persona(src: str, sid: str) -> str:
    return await get_effective_system(src, sid)

async def set_persona(src: str, sid: str, text: str) -> None:
    data = {
        **DEFAULT_PERSONA,
        "persona_id": f"{src}:{sid}",
        "system": [ (text or "").strip() ],
        "version": 1,
    }
    await set_persona_struct(src, sid, data)

# --- Extra util per altri moduli (facoltativi) ---

def get_capabilities_brief() -> str:
    """Breve descrizione delle capacità, coerente con la quantum_api."""
    return CAPABILITIES_BRIEF

__all__ = [
    "DEFAULT_PERSONA",
    "CAPABILITIES_BRIEF",
    "META_IGNORE_PATTERNS",
    "build_system_prompt",
    "get_persona_struct",
    "set_persona_struct",
    "reset_persona",
    "get_default_persona",
    "set_default_persona",
    "get_effective_system",
    "get_persona",
    "set_persona",
    "get_capabilities_brief",
]
