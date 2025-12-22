import os
import logging
import subprocess
import requests
import asyncio
from telegram import Bot
from dotenv import load_dotenv

# === LOAD ENV ===
load_dotenv()

# === CONFIG ===
ADMIN_CHAT_ID = int(os.getenv("TELEGRAM_ADMIN_ID"))
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)

# === LOGGING ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# === FUNZIONI CHECK ===
def is_process_running(name):
    try:
        result = subprocess.run(["pgrep", "-f", name], stdout=subprocess.PIPE)
        return result.returncode == 0
    except Exception:
        return False

def is_port_open(port):
    try:
        response = requests.post(f"http://127.0.0.1:{port}/chat", json={"message": "ping"}, timeout=2)
        return response.status_code == 200
    except Exception:
        return False

async def notify_admin(message):
    try:
        await bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"🚨 {message}")
    except Exception as e:
        logging.error(f"Errore invio Telegram: {e}")

# === MONITOR ===
async def main():
    logging.info("🩺 Avvio Monitor Agent...")
    problemi = []

    if not is_process_running("ollama"):
        problemi.append("❌ Ollama non attivo")

    if not is_port_open(8081):
        problemi.append("❌ API GPT (quantum-api) non raggiungibile")

    if not is_process_running("redis-server"):
        problemi.append("❌ Redis non attivo")

    if not is_process_running("telegram_bot_agent.py"):
        problemi.append("❌ Telegram Bot non attivo")

    if not os.path.exists("memory/chroma/chroma.sqlite3"):
        problemi.append("❌ ChromaDB non disponibile")

    if problemi:
        for p in problemi:
            logging.warning(p)
        await notify_admin("\n".join(problemi))
    else:
        logging.info("✅ Tutti i servizi sono attivi.")

if __name__ == "__main__":
    asyncio.run(main())
