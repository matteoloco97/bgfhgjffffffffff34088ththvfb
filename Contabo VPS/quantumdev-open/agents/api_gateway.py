# agents/api_gateway.py

import os
import logging
import requests
from fastapi import FastAPI, Request
from dotenv import load_dotenv
import redis
import hashlib

# === Load env ===
load_dotenv()

# === Config ===
app = FastAPI()
LLM_ENDPOINT = os.getenv("LLM_ENDPOINT", "http://localhost:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "mistral")
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", 0.7))
MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", 1024))

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

# === Redis ===
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)

# === Logging ===
log_path = "/root/quantumdev-open/logs/api_gateway.log"
os.makedirs(os.path.dirname(log_path), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_path),
        logging.StreamHandler()
    ]
)

# === Utils ===
def hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.strip().lower().encode()).hexdigest()

# === Endpoint /ask ===
@app.post("/ask")
async def ask_gpt(request: Request):
    data = await request.json()
    prompt = data.get("prompt", "").strip()

    if not prompt:
        return {"error": "Prompt mancante."}

    cache_key = hash_prompt(prompt)
    cached = redis_client.get(cache_key)
    if cached:
        logging.info("✅ Risposta da cache.")
        return {"cached": True, "response": cached.decode()}

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "Sei una GPT neutra e modulare."},
            {"role": "user", "content": prompt}
        ],
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS
    }

    try:
        logging.info("🔁 Invio prompt alla LLM...")
        r = requests.post(f"{LLM_ENDPOINT}/chat/completions", json=payload, timeout=15)
        r.raise_for_status()
        res = r.json()
        text = res["choices"][0]["message"]["content"]

        redis_client.setex(cache_key, 86400, text)  # Cache 24h
        logging.info("✅ Risposta ricevuta.")
        return {"cached": False, "response": text}

    except Exception as e:
        logging.error(f"❌ Errore LLM: {e}")
        return {"error": f"LLM non disponibile o errore: {e}"}
