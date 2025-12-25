# agents/telegram_bot_agent.py

import logging
import asyncio
import os
from dotenv import load_dotenv

# Import async HTTP client
from core.async_http_client import get_http_client

# === Load .env ===
load_dotenv()

# === Config logging ===
logging.basicConfig(level=logging.INFO)

class TelegramBotAgent:
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.bot_token:
            raise ValueError("❌ TELEGRAM_BOT_TOKEN non trovato nel .env")
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"

    async def send_message(self, chat_id, message):
        try:
            # Se viene passato come stringa da .env, converti in int
            if isinstance(chat_id, str) and chat_id.isdigit():
                chat_id = int(chat_id)

            url = f"{self.api_url}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }

            logging.info(f"📨 Invio messaggio a {chat_id} → '{message}'")
            
            client = await get_http_client()
            if not client:
                logging.error("❌ HTTP client not available")
                return False
            
            async with client.post(url, json=payload) as response:
                if response.ok:
                    logging.info("✅ Messaggio inviato con successo.")
                    return True
                else:
                    text = await response.text()
                    logging.error(f"❌ Errore Telegram: {response.status} - {text}")
                    return False

        except Exception as e:
            logging.error(f"❌ Eccezione durante invio Telegram: {e}")
            return False
