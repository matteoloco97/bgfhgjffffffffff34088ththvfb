from telegram_bot_agent import TelegramBotAgent

# === Inserisci il tuo chat_id personale
CHAT_ID = 5015947009  # ← già corretto

# === Messaggio di test
testo = "✅ Test riuscito! Il tuo agente Telegram funziona correttamente."

# === Avvia agente
bot = TelegramBotAgent()
bot.send_message(CHAT_ID, testo)
