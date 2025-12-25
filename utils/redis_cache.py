import redis
import hashlib
import json
import time

# Connessione locale a Redis (default porta 6379)
r = redis.Redis(host='localhost', port=6379, db=0)

TTL_SECONDS = 86400  # Cache valida per 24h

def hash_key(prompt: str) -> str:
    """Genera una chiave hash SHA256 dal prompt"""
    return hashlib.sha256(prompt.strip().lower().encode()).hexdigest()

def save_to_cache(prompt: str, response: str):
    """Salva la risposta associata al prompt nella cache"""
    key = hash_key(prompt)
    value = json.dumps({
        "response": response,
        "timestamp": int(time.time())
    })
    r.setex(key, TTL_SECONDS, value)

def load_from_cache(prompt: str):
    """Recupera la risposta dalla cache, se esiste"""
    key = hash_key(prompt)
    cached = r.get(key)
    if cached:
        return json.loads(cached).get("response")
    return None

def flush_cache():
    """Elimina tutta la cache"""
    r.flushdb()
