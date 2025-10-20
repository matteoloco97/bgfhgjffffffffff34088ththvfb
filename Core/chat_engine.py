# core/chat_engine.py
import json, asyncio, os
import requests
from dotenv import load_dotenv

load_dotenv()
# Usiamo il nostro stesso endpoint /generate per riusare tutta la logica esistente
GENERATE_URL = os.getenv("QUANTUM_API_URL", "http://127.0.0.1:8081/generate")

async def _post(url: str, payload: dict, timeout: int = 30):
    return await asyncio.to_thread(
        lambda: requests.post(url, json=payload, timeout=timeout)
    )

def _extract_text(result: dict) -> str:
    # Prova lo schema OpenAI-compat del tuo /generate
    try:
        return result["response"]["choices"][0]["message"]["content"].strip()
    except Exception:
        # fallback: prova a ritornare l’intero json (troncato)
        return json.dumps(result, ensure_ascii=False)[:4000]

async def reply_with_llm(user_text: str, persona: str) -> str:
    payload = {
        "prompt": user_text,
        "system": persona or "Sei una GPT neutra e modulare.",
    }
    try:
        r = await _post(GENERATE_URL, payload)
        if r.status_code != 200:
            return f"❌ Backend {r.status_code}: {r.text[:300]}"
        data = r.json()
        return _extract_text(data)
    except Exception as e:
        return f"❌ Errore backend: {e}"
