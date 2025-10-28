#/root/quantumdev-open/core/persona_store.py <<'PY'
import os, redis, asyncio, json
from typing import Any, Dict
from dotenv import load_dotenv

load_dotenv()
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB   = int(os.getenv("REDIS_DB", 0))
_r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)

# Keying
_KEY = "persona:{src}:{sid}"
_DEFAULT_KEY = "persona:global:default"

def _k(src: str, sid: str) -> str:
    return _KEY.format(src=src, sid=sid)

# Persona di default (strutturata)
DEFAULT_PERSONA: Dict[str, Any] = {
    "persona_id": "default",
    "system": [
        "Parla in italiano. Tono chiaro e professionale, conciso di default.",
        "Sii SINCERO: se non sei sicuro, dillo esplicitamente e proponi come verificare.",
        "Sii ANALITICO: struttura la risposta in punti; metti sempre una sezione finale `Perché` con le 2–3 ragioni chiave.",
        "RAGIONA ma NON rivelare passaggi interni: pensa passo-passo e poi dai solo la sintesi finale. Evita frasi del tipo “sto pensando…”.",
        "Usa markdown con misura (titoletti brevi, liste, codice quando serve).",
        "Se la domanda è attuale/variabile o richiede fonti → proponi/usa l’Agente Web.",
        "Se c’è immagine/PDF o si chiede estrazione testo → proponi/usa l’Agente OCR.",
        "Non inventare link/dati. Se servono fonti e non le hai, chiedi permesso per usare Web."
    ],
    "behavior": {
        "verbosity_default": "short",
        "formatting": "markdown",
        "ask_before_tool_use": True
    },
    "tool_prefs": {
        "web": {"timeout_ms": 12000, "max_chars": 4000},
        "ocr": {"timeout_ms": 15000, "lang": "ita+eng"}
    },
    "version": 1
}

# --- Helpers ---

def _wrap_legacy(value: str) -> Dict[str, Any]:
    v = (value or "").strip()
    if not v:
        return DEFAULT_PERSONA
    return {
        **DEFAULT_PERSONA,
        "system": [v],
        "version": 1
    }

def _loads_or_wrap(blob: bytes | None) -> Dict[str, Any]:
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

# --- API async (operazioni su thread per non bloccare l'event loop) ---

async def get_persona_struct(src: str, sid: str) -> Dict[str, Any]:
    blob = await asyncio.to_thread(_r.get, _k(src, sid))
    if blob is None:
        blob = await asyncio.to_thread(_r.get, _DEFAULT_KEY)
    return _loads_or_wrap(blob)

async def set_persona_struct(src: str, sid: str, data: Dict[str, Any]) -> None:
    data = dict(data or {})
    data.setdefault("persona_id", f"{src}:{sid}")
    data.setdefault("version", 1)
    await asyncio.to_thread(_r.set, _k(src, sid), json.dumps(data, ensure_ascii=False))

async def reset_persona(src: str, sid: str) -> None:
    await asyncio.to_thread(_r.delete, _k(src, sid))

async def get_default_persona() -> Dict[str, Any]:
    blob = await asyncio.to_thread(_r.get, _DEFAULT_KEY)
    return _loads_or_wrap(blob)

async def set_default_persona(data: Dict[str, Any]) -> None:
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

__all__ = [
    "DEFAULT_PERSONA",
    "build_system_prompt",
    "get_persona_struct",
    "set_persona_struct",
    "reset_persona",
    "get_default_persona",
    "set_default_persona",
    "get_effective_system",
    "get_persona",
    "set_persona",
]
PY
