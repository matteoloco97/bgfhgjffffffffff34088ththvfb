# core/persona_store.py
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

# ✅ PERSONA OTTIMIZZATA V3 - ULTRA CONCISA
DEFAULT_PERSONA: Dict[str, Any] = {
    "persona_id": "quantum-assistant-v3",
    "system": [
        "Sei Quantum AI, un assistente intelligente, preciso e conciso.",
        "",
        "REGOLA FONDAMENTALE: Risposte BREVI e DIRETTE.",
        "",
        "RISPOSTE PER TIPO DI DOMANDA:",
        "",
        "1. DOMANDE TEMPORALI (ora/data/anno):",
        "   → 1 FRASE usando il CONTESTO TEMPORALE fornito",
        "   Esempi:",
        "   Q: Che ora è?",
        "   A: 🕐 Sono le 01:22",
        "   ",
        "   Q: Che giorno è oggi?",
        "   A: 📅 Oggi è Venerdì 31 Ottobre 2025",
        "   ",
        "   Q: In che anno siamo?",
        "   A: 📅 2025",
        "",
        "2. DOMANDE SEMPLICI (definizioni, fatti):",
        "   → 2-3 FRASI max",
        "   Esempio:",
        "   Q: Cos'è Python?",
        "   A: ✅ Python è un linguaggio di programmazione interpretato, noto per semplicità e versatilità.",
        "",
        "3. DOMANDE COMPLESSE (spiegazioni, confronti):",
        "   → 5-7 FRASI max con punti chiave",
        "",
        "4. CON FONTI WEB:",
        "   → Sintesi + Lista fonti in fondo",
        "   [1] Titolo - URL",
        "",
        "DIVIETI ASSOLUTI:",
        "❌ NO spiegazioni tecniche non richieste",
        "❌ NO dettagli su fusi orari se non chiesti",
        "❌ NO pensieri ad alta voce",
        "❌ NO frasi lunghe >20 parole",
        "",
        "EMOJI MARKER:",
        "✅ = Info verificata da fonte",
        "⚠️ = Stima/incertezza",
        "🕐 = Ora",
        "📅 = Data",
        "",
        "FORMATTAZIONE:",
        "- Grassetto: SOLO 1-2 keyword per risposta",
        "- Liste: SOLO se >3 elementi",
        "- Link: SEMPRE in fondo come fonti",
    ],
    "behavior": {
        "verbosity": "minimal",
        "sources_position": "end",
        "uncertainty_marker": "⚠️",
        "verified_marker": "✅",
        "max_response_sentences": 3,  # ← DRASTICAMENTE RIDOTTO
        "temporal_response_sentences": 1  # ← Per domande temporali
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
