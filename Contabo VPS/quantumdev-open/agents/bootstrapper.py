import os
import requests
import redis
import logging
import yaml
from chromadb import PersistentClient
from dotenv import load_dotenv

load_dotenv()

# === Caricamento config ===
with open("/root/quantumdev-open/config/settings.yaml", "r") as f:
    cfg = yaml.safe_load(f)

# === Setup logging ===
log_path = "/root/quantumdev-open/logs/bootstrapper.log"
os.makedirs(os.path.dirname(log_path), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_path),
        logging.StreamHandler()
    ]
)

logging.info("🧠 Avvio Quantum Bootstrapper...")

# === Test Redis ===
def test_redis():
    try:
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.set("test", "ok", ex=5)
        val = r.get("test")
        return val == b"ok"
    except Exception as e:
        logging.error(f"Redis FAIL: {e}")
        return False

# === Test Chroma ===
def test_chroma():
    try:
        chroma_client = PersistentClient(path="/root/quantumdev-open/memory/chroma")
        chroma_client.list_collections()
        return True
    except Exception as e:
        logging.error(f"ChromaDB FAIL: {e}")
        return False

# === Test API GPT ===
def test_gpt():
    try:
        url = cfg.get("llm", {}).get("endpoint", "").rstrip("/")
        r = requests.post(f"{url}/chat", json={"message": "ping"})
        return r.ok
    except Exception as e:
        logging.error(f"GPT API FAIL: {e}")
        return False

# === Test Telegram Bot ===
def test_telegram():
    try:
        r = requests.get(f"https://api.telegram.org/bot{cfg['telegram']['bot_token']}/getMe")
        return r.ok
    except Exception as e:
        logging.error(f"Telegram FAIL: {e}")
        return False

# === Test Wasabi (tramite env) ===
def test_wasabi():
    try:
        access_key = os.getenv("AWS_ACCESS_KEY_ID")
        secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        return bool(access_key and secret_key)
    except Exception as e:
        logging.error(f"Wasabi FAIL: {e}")
        return False

# === Avvio test ===
results = {
    "🧠 Redis": test_redis(),
    "🧠 ChromaDB": test_chroma(),
    "🤖 Telegram Bot": test_telegram(),
    "🛰️  GPT API": test_gpt(),
    "☁️ Wasabi": test_wasabi(),
}

# === Report finale ===
logging.info("\n📋 STATO SISTEMA – QuantumDev Bootstrapper\n")
for k, v in results.items():
    stato = "✅ OK" if v else "❌ FAIL"
    logging.info(f"{k.ljust(20)} → {stato}")

logging.info("🔚 Bootstrap completato.\n")
