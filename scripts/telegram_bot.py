#!/usr/bin/env python3
# scripts/telegram_bot.py - Bot Telegram con AI Autonoma + Calculator

from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
import logging, os, sys, fcntl, re, asyncio
from dotenv import load_dotenv
import aiohttp

# Aggiungi path per imports
sys.path.insert(0, '/root/quantumdev-open')

# ✅ Import Calculator
from core.calculator import safe_eval, is_calculator_query

# Import Intent Classifier
from core.intent_classifier import IntentClassifier, Intent

# === Lock single instance ===
LOCK_PATH = "/tmp/telegram-bot.lock"
_lock_f = open(LOCK_PATH, "w")
try:
    fcntl.lockf(_lock_f, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError:
    print("⚠️  Bot già in esecuzione")
    sys.exit(0)

# === ENV ===
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_CHAT_ID = int(os.getenv("TELEGRAM_ADMIN_ID", "0"))

# Endpoints
QUANTUM_CHAT_URL = os.getenv("QUANTUM_CHAT_URL", "http://127.0.0.1:8081/chat")
QUANTUM_WEB_SEARCH_URL = os.getenv("QUANTUM_WEB_SEARCH_URL", "http://127.0.0.1:8081/web/search")
QUANTUM_WEB_SUMMARY_URL = os.getenv("QUANTUM_WEB_SUMMARY_URL", "http://127.0.0.1:8081/web/summarize")
QUANTUM_HEALTH_URL = os.getenv("QUANTUM_HEALTH_URL", "http://127.0.0.1:8081/healthz")
QUANTUM_PERSONA_SET_URL = os.getenv("QUANTUM_PERSONA_SET_URL", "http://127.0.0.1:8081/persona/set")
QUANTUM_PERSONA_GET_URL = os.getenv("QUANTUM_PERSONA_GET_URL", "http://127.0.0.1:8081/persona/get")
QUANTUM_PERSONA_RESET_URL = os.getenv("QUANTUM_PERSONA_RESET_URL", "http://127.0.0.1:8081/persona/reset")

# === LOGGING ===
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)

# === Intent Classifier (globale) ===
classifier = IntentClassifier()

# === Utils ===
TG_MAX = 4096

def split_text(s: str, size: int = TG_MAX):
    return [s[i:i+size] for i in range(0, len(s), size)] if s else []

def first_url(s: str):
    if not s: return None
    m = re.search(r'(https?://\S+)', s)
    return m.group(1) if m else None

# === Startup/Shutdown ===
async def on_startup(app):
    app.bot_data["http"] = aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=180)
    )
    log.info("🌐 HTTP session pronta; core chat=%s", QUANTUM_CHAT_URL)

async def on_shutdown(app):
    sess = app.bot_data.get("http")
    if sess and not sess.closed:
        await sess.close()
    log.info("👋 HTTP session chiusa")

# === Comandi Base ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧠 *Quantum AI Autonoma*\n\n"
        "Sono un'intelligenza artificiale che decide autonomamente:\n"
        "• 🌐 Quando cercare su internet\n"
        "• 💬 Quando rispondere direttamente\n"
        "• 🧮 Calcoli matematici istantanei\n\n"
        "Scrivi normalmente, penso io al resto!\n\n"
        "Usa /help per i comandi disponibili.",
        parse_mode="Markdown"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """🤖 *QuantumDev comandi*

*Autonomia Totale:*
Scrivi normalmente e decido io se serve internet!

Esempi:
- "meteo roma" → 🌐 cerca automaticamente
- "cos'è un buco nero?" → 💬 risponde direttamente
- "risultati serie a oggi" → 🌐 cerca
- "2+2" → 🧮 calcola istantaneamente

*Comandi manuali:*
- /health — stato del core
- /web <query> — forza ricerca web
- /read <url> — leggi/riassumi pagina
- /persona — mostra personalità
- /persona_set <testo> — imposta personalità
- /persona_reset — resetta personalità
- /flushcache — svuota cache (solo admin)"""
    
    await update.message.reply_text(help_text, parse_mode="Markdown")

# === Core Functions ===
async def call_llm_direct(text: str, http: aiohttp.ClientSession, chat_id: int) -> str:
    """Risposta LLM diretta (no web)"""
    payload = {"source": "tg", "source_id": str(chat_id), "text": text}
    try:
        async with http.post(QUANTUM_CHAT_URL, json=payload) as r:
            if r.status == 200:
                data = await r.json()
                reply = data.get("reply", "").strip()
                if reply.startswith("❌"):
                    log.error(f"LLM error in reply: {reply[:200]}")
                return reply
            txt = await r.text()
            log.error(f"LLM HTTP {r.status}: {txt[:300]}")
            return f"❌ Errore LLM {r.status}"
    except asyncio.TimeoutError:
        log.error("LLM timeout")
        return "❌ Timeout: la GPU sta ancora caricando, riprova tra 30s"
    except Exception as e:
        log.error(f"LLM exception: {e}")
        return f"❌ Errore: {e}"

async def call_web_search(query: str, http: aiohttp.ClientSession, chat_id: int) -> list[str]:
    """Ricerca web + sintesi"""
    payload = {
        "source": "tg",
        "source_id": str(chat_id),
        "q": query,
        "k": 6,
        "summarize_top": 2
    }
    
    try:
        async with http.post(QUANTUM_WEB_SEARCH_URL, json=payload) as r:
            if r.status != 200:
                txt = await r.text()
                log.error(f"Web search {r.status}: {txt[:300]}")
                return [f"❌ Web search error {r.status}"]
            data = await r.json()
    except Exception as e:
        log.error(f"Web search exception: {e}")
        return [f"❌ Errore: {e}"]
    
    msgs = []
    summary = data.get("summary", "").strip()
    
    if summary and not summary.startswith('{"error"') and not summary.startswith("❌"):
        msgs.append(f"{summary}")
    
    results = data.get("results", [])
    if results:
        lines = ["\n📎 Fonti:"]
        for i, r in enumerate(results[:5], 1):
            title = r.get("title", "").strip() or "Senza titolo"
            url = r.get("url", "")
            lines.append(f"{i}. {title}\n   {url}")
        msgs.append("\n".join(lines))
    
    return msgs if msgs else ["😕 Nessun risultato trovato"]

async def call_web_read(url: str, http: aiohttp.ClientSession, chat_id: int) -> str:
    """Leggi e riassumi URL"""
    payload = {"source": "tg", "source_id": str(chat_id), "url": url}
    try:
        async with http.post(QUANTUM_WEB_SUMMARY_URL, json=payload) as r:
            if r.status == 200:
                data = await r.json()
                summary = data.get("summary", "Nessun contenuto estratto")
                if summary.startswith("❌"):
                    log.error(f"Web read error in summary: {summary[:200]}")
                return summary
            txt = await r.text()
            log.error(f"Web read {r.status}: {txt[:300]}")
            return f"❌ Errore lettura {r.status}"
    except Exception as e:
        log.error(f"Web read exception: {e}")
        return f"❌ Errore: {e}"

# === MAIN MESSAGE HANDLER (AUTONOMOUS + CALCULATOR) ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler principale con decisione autonoma + calculator"""
    msg = update.message
    if not msg or not msg.text:
        return
    
    text = msg.text.strip()
    chat_id = update.effective_chat.id
    http = context.application.bot_data["http"]
    
    # Ping rapido
    if text.lower() in {"ping", "pong"}:
        await msg.reply_text("pong")
        return
    
    # ✅ CALCULATOR CHECK (PRIORITÀ MASSIMA)
    if is_calculator_query(text):
        result = safe_eval(text)
        if result:
            await msg.reply_text(f"🧮 `{text}` = `{result}`", parse_mode="Markdown")
            log.info(f"🧮 Calculator: {text} = {result}")
            return
    
    # 🧠 AUTONOMOUS DECISION
    decision = classifier.classify(text)
    intent = decision["intent"]
    confidence = decision["confidence"]
    analysis = decision.get("analysis")
    
    # Log decisione dettagliato
    if analysis:
        reasons_str = ", ".join(analysis['reasons'])
        log.info(
            f"🎯 {intent.value.upper()} (conf: {confidence:.0%}) | "
            f"Scores: W={analysis['web_score']} L={analysis['stable_score']} | "
            f"{reasons_str} | '{text[:50]}'"
        )
    else:
        log.info(f"🎯 {intent.value.upper()} (URL detected) | '{text[:50]}'")
    
    # Esegui azione
    try:
        if intent == Intent.WEB_READ:
            url = decision["params"]["url"]
            await msg.reply_text(f"📄 Leggo {url}...")
            reply = await call_web_read(url, http, chat_id)
            for part in split_text(reply):
                await msg.reply_text(part)
        
        elif intent == Intent.WEB_SEARCH:
            query = decision["params"]["query"]
            await msg.reply_text("🌐 Cerco informazioni aggiornate...")
            replies = await call_web_search(query, http, chat_id)
            for reply in replies:
                for part in split_text(reply):
                    await msg.reply_text(part, disable_web_page_preview=True)
        
        else:  # DIRECT_LLM
            reply = await call_llm_direct(text, http, chat_id)
            for part in split_text(reply):
                await msg.reply_text(part)
    
    except Exception as e:
        log.exception(f"Handler error: {e}")
        await msg.reply_text(f"❌ Errore interno: {e}")

# === COMANDI MANUALI ===
async def health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    http = context.application.bot_data["http"]
    try:
        async with http.get(QUANTUM_HEALTH_URL) as r:
            txt = await r.text()
        for chunk in split_text(txt, 900):
            await update.message.reply_text(chunk)
    except Exception as e:
        await update.message.reply_text(f"❌ Health fallita: {e}")

async def web_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forza ricerca web"""
    text = update.message.text
    query = text.split(maxsplit=1)[1] if len(text.split()) > 1 else ""
    
    if not query:
        await update.message.reply_text("Uso: /web <query>")
        return
    
    http = context.application.bot_data["http"]
    chat_id = update.effective_chat.id
    
    await update.message.reply_text(f"🌐 Cerco: {query}")
    replies = await call_web_search(query, http, chat_id)
    
    for reply in replies:
        for part in split_text(reply):
            await update.message.reply_text(part, disable_web_page_preview=True)

async def read_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Forza lettura URL"""
    text = update.message.text
    args = text.split(maxsplit=1)[1] if len(text.split()) > 1 else ""
    url = first_url(args)
    
    if not url:
        await update.message.reply_text("Uso: /read <url>")
        return
    
    http = context.application.bot_data["http"]
    chat_id = update.effective_chat.id
    
    await update.message.reply_text(f"📄 Leggo {url}...")
    reply = await call_web_read(url, http, chat_id)
    
    for part in split_text(reply):
        await update.message.reply_text(part)

async def flush_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if ADMIN_CHAT_ID is None or chat_id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ Non sei autorizzato.")
        return
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.flushall()
        await update.message.reply_text("✅ Cache Redis svuotata.")
        log.info("✅ Cache Redis svuotata da Telegram")
    except Exception as e:
        log.error(f"Errore flush: {e}")
        await update.message.reply_text(f"❌ Errore: {e}")

# Persona commands
async def persona_get(update: Update, context: ContextTypes.DEFAULT_TYPE):
    http = context.application.bot_data["http"]
    chat_id = update.effective_chat.id
    payload = {"source": "tg", "source_id": str(chat_id)}
    try:
        async with http.post(QUANTUM_PERSONA_GET_URL, json=payload) as r:
            if r.status != 200:
                return await update.message.reply_text(f"❌ persona/get {r.status}")
            data = await r.json()
        persona = data.get("persona") or "(vuota)"
        for chunk in split_text(f"🧠 Persona attuale:\n{persona}", 1000):
            await update.message.reply_text(chunk)
    except Exception as e:
        await update.message.reply_text(f"❌ Errore persona/get: {e}")

async def persona_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    http = context.application.bot_data["http"]
    chat_id = update.effective_chat.id
    text = update.message.text
    args = text.split(maxsplit=1)[1] if len(text.split()) > 1 else ""
    
    if not args:
        return await update.message.reply_text("Uso: /persona_set <testo>")
    
    payload = {"source": "tg", "source_id": str(chat_id), "text": args}
    try:
        async with http.post(QUANTUM_PERSONA_SET_URL, json=payload) as r:
            if r.status != 200:
                return await update.message.reply_text(f"❌ persona/set {r.status}")
        await update.message.reply_text("✅ Persona aggiornata.")
    except Exception as e:
        await update.message.reply_text(f"❌ Errore persona/set: {e}")

async def persona_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    http = context.application.bot_data["http"]
    chat_id = update.effective_chat.id
    payload = {"source": "tg", "source_id": str(chat_id)}
    try:
        async with http.post(QUANTUM_PERSONA_RESET_URL, json=payload) as r:
            if r.status != 200:
                return await update.message.reply_text(f"❌ persona/reset {r.status}")
        await update.message.reply_text("✅ Persona resettata.")
    except Exception as e:
        await update.message.reply_text(f"❌ Errore persona/reset: {e}")

# === Error Handler ===
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.exception("❌ Errore non gestito nel bot:", exc_info=context.error)

# === AVVIO ===
if __name__ == "__main__":
    if not BOT_TOKEN:
        raise SystemExit("❌ TELEGRAM_BOT_TOKEN non impostato nel .env")

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(on_startup)
        .post_shutdown(on_shutdown)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("health", health))
    app.add_handler(CommandHandler("flushcache", flush_cache))
    app.add_handler(CommandHandler("web", web_cmd))
    app.add_handler(CommandHandler("read", read_cmd))
    app.add_handler(CommandHandler("persona", persona_get))
    app.add_handler(CommandHandler("persona_set", persona_set))
    app.add_handler(CommandHandler("persona_reset", persona_reset))

    # HANDLER AUTONOMO per messaggi normali
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    app.add_error_handler(error_handler)

    log.info("🤖 Avvio Telegram Bot con AI Autonoma + Calculator (mode=polling)")
    app.run_polling(drop_pending_updates=True, poll_interval=1.0)
