# core/chat_engine.py
import json, asyncio, os
import requests
from dotenv import load_dotenv

load_dotenv()

# URL diretto all'endpoint GPU
LLM_ENDPOINT = os.getenv("LLM_ENDPOINT", "http://127.0.0.1:18001/v1/chat/completions")
LLM_MODEL = os.getenv("LLM_MODEL", "mixtral-8x7b")

async def _post(url: str, payload: dict, timeout: int = 30):
    return await asyncio.to_thread(
        lambda: requests.post(url, json=payload, timeout=timeout)
    )

async def reply_with_llm(user_text: str, persona: str) -> str:
    """
    Chiama direttamente l'LLM con formato OpenAI-compatible
    """
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": persona or "Sei un assistente conciso e pratico."},
            {"role": "user", "content": user_text}
        ],
        "temperature": 0.7,
        "max_tokens": 1024
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
