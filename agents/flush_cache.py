import redis
import logging

# === Setup logging ===
logging.basicConfig(level=logging.INFO)

def flush_redis():
    try:
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.flushall()
        logging.info("✅ Redis cache svuotata con successo.")
    except Exception as e:
        logging.error(f"❌ Errore durante lo svuotamento della cache: {e}")

if __name__ == "__main__":
    logging.info("🧹 Avvio Flush Cache Agent...")
    flush_redis()
