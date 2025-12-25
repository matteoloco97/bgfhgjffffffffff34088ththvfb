# flush_cache.py

import redis
import os

def flush_cache():
    try:
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.flushdb()
        print("🧹 Redis cache svuotata con successo.")
    except Exception as e:
        print(f"❌ Errore durante lo svuotamento della cache Redis: {e}")

if __name__ == "__main__":
    flush_cache()
