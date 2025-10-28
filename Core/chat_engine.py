# core/chat_engine.py
import json, asyncio, os
import requests
from dotenv import load_dotenv

load_dotenv()

# Leggi endpoint dal .env e costruisci URL completo
LLM_ENDPOINT_BASE = os.getenv("LLM_ENDPOINT", "http://127.0.0.1:9001/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.1-70b")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", 0.7))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", 512))

# Costruisci URL completo per chat/completions
if LLM_ENDPOINT_BASE.endswith("/chat/completions"):
    LLM_ENDPOINT = LLM_ENDPOINT_BASE
elif LLM_ENDPOINT_BASE.endswith("/v1"):
    LLM_ENDPOINT = f"{LLM_ENDPOINT_BASE}/chat/completions"
else:
    LLM_ENDPOINT = f"{LLM_ENDPOINT_BASE}/v1/chat/completions"

async def _post(url: str, payload: dict, timeout: int = 60):
    return await asyncio.to_thread(
        lambda: requests.post(url, json=payload, timeout=timeout)
    )

async def reply_with_llm(user_text: str, persona: str) -> str:
    """
    Chiama LLM con formato OpenAI-compatible
    """
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": persona or "Sei un assistente conciso e pratico."},
            {"role": "user", "content": user_text}
        ],
        "temperature": LLM_TEMPERATURE,
        "max_tokens": LLM_MAX_TOKENS
    }
    
    try:
        r = await _post(LLM_ENDPOINT, payload, timeout=60)
        if r.status_code != 200:
            return f"❌ LLM error {r.status_code}: {r.text[:300]}"
        
        data = r.json()
        
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as e:
            return f"❌ Formato risposta inatteso: {e}\n{json.dumps(data, ensure_ascii=False)[:500]}"
    
    except Exception as e:
        return f"❌ Errore LLM: {e}"
