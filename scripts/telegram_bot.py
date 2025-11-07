#!/usr/bin/env python3
# scripts/telegram_bot.py - Bot Telegram con Smart Routing (/generate) + Calculator + Feedback

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, CallbackQueryHandler, filters
)
import logging, os, sys, fcntl, re, asyncio, time
from dotenv import load_dotenv
import aiohttp
import json

# Aggiungi path per imports locali
sys.path.insert(0, '/root/quantumdev-open')

# ✅ Calculator (fast path locale)
try:
    from core.calculator import safe_eval, is_calculator_query
except Exception:
    safe_eval = None
    def is_calculator_query(_): return False

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

# Endpoints principali (preferenza a /generate con smart routing)
QUANTUM_GENERATE_URL   = os.getenv("QUANTUM_GENERATE_URL", "http://127.0.0.1:8081/generate")
QUANTUM_CHAT_URL       = os.getenv("QUANTUM_CHAT_URL", "http://127.0.0.1:8081/chat")  # fallback legacy
QUANTUM_WEB_SEARCH_URL = os.getenv("QUANTUM_WEB_SEARCH_URL", "http://127.0.0.1:8081/web/search")
QUANTUM_WEB_SUMMARY_URL= os.getenv("QUANTUM_WEB_SUMMARY_URL", "http://127.0.0.1:8081/web/summarize")
QUANTUM_HEALTH_URL     = os.getenv("QUANTUM_HEALTH_URL", "http://127.0.0.1:8081/healthz")
QUANTUM_PERSONA_SET_URL= os.getenv("QUANTUM_PERSONA_SET_URL", "http://127.0.0.1:8081/persona/set")
QUANTUM_PERSONA_GET_URL= os.getenv("QUANTUM_PERSONA_GET_URL", "http://127.0.0.1:8081/persona/get")
QUANTUM_PERSONA_RESET_URL=os.getenv("QUANTUM_PERSONA_RESET_URL", "http://127.0.0.1:8081/persona/reset")

# Intent Router (per feedback/correzioni esplicite)
INTENT_ROUTER_URL = os.getenv("INTENT_ROUTER_URL", "http://127.0.0.1:8090")

# === LOGGING ===
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)

# === Utils ===
TG_MAX = 4096

def split_text(s: str, size: int = TG_MAX):
    return [s[i:i+size] for i in range(0, len(s), size)] if s else []

def first_url(s: str):
    if not s: return None
    m = re.search(r'(https?://\S+)', s)
    return m.group(1) if m else None

def extract_openai_like_text(data: dict) -> str:
    """
    Estrae testo da risposta OpenAI-like: data['response']['choices'][0]['message']['content']
    Se non presente, ritorna stringa grezza o errore.
    """
    try:
        resp = data.get("response") or {}
        choices = resp.get("choices") or []
        if choices and "message" in choices[0]:
            return (choices[0]["message"].get("content") or "").strip()
    except Exception:
        pass
    # fallback generico
    if "reply" in data:
        return (data.get("reply") or "").strip()
    return ""

# === Startup/Shutdown ===
async def on_startup(app):
    app.bot_data["http"] = aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=180)
    )
    app.bot_data["fb_map"] = {}  # message_id -> {query, intent, elapsed_ms}
    log.info("🌐 HTTP session pronta; /generate=%s", QUANTUM_GENERATE_URL)

async def on_shutdown(app):
    sess = app.bot_data.get("http")
    if sess and not sess.closed:
        await sess.close()
    log.info("👋 HTTP session chiusa")

# === Comandi Base ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧠 *Quantum AI Autonoma*\n\n"
        "Decido in autonomia come rispondere:\n"
        "• 🌐 Web search quando servono dati live\n"
        "• 💬 Risposta diretta quando basta knowledge\n"
        "• 🧮 Calcoli istantanei localmente\n\n"
        "Scrivi normalmente, penso io al resto!\n\n"
        "Usa /help per i comandi disponibili.",
        parse_mode="Markdown"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """🤖 *QuantumDev comandi*

*Autonomia Totale:* scrivi normale — uso /generate con routing intelligente.

Esempi:
- "meteo roma" → 🌐 web search
- "cos'è un buco nero?" → 💬 direct LLM
- "risultati serie a oggi" → 🌐 web search
- "2+2" → 🧮 calcolo istantaneo (locale)

*Comandi manuali:*
- /health — stato del core
- /web <query> — forza ricerca web
- /read <url> — leggi/riassumi pagina
- /persona — mostra personalità
- /persona_set <testo> — imposta personalità
- /persona_reset — resetta personalità
- /flushcache — svuota cache (solo admin)"""
    await update.message.reply_text(help_text, parse_mode="Markdown")

# === Core Calls ===
async def call_generate(text: str, http: aiohttp.ClientSession, chat_id: int) -> dict:
    """
    Chiama /generate con prompt=text. Restituisce il JSON completo.
    Server-side farà smart routing (calculator/web_read/web_search/direct).
    """
    payload = {"prompt": text, "temperature": 0.3, "model": None}
    try:
        async with http.post(QUANTUM_GENERATE_URL, json=payload) as r:
            if r.status == 200:
                return await r.json()
            txt = await r.text()
            log.error(f"/generate HTTP {r.status}: {txt[:300]}")
            return {"ok": False, "error": f"/generate {r.status}", "raw": txt[:300]}
    except asyncio.TimeoutError:
        log.error("/generate timeout")
        return {"ok": False, "error": "Timeout: GPU/LLM lento"}
    except Exception as e:
        log.error(f"/generate exception: {e}")
        return {"ok": False, "error": str(e)}

async def call_web_search(query: str, http: aiohttp.ClientSession, chat_id: int) -> list[str]:
    """Ricerca web + sintesi (manuale /web)."""
    payload = {"source": "tg", "source_id": str(chat_id), "q": query, "k": 6, "summarize_top": 2}
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
    summary = (data.get("summary") or "").strip()
    if summary and not summary.startswith('{"error"') and not summary.startswith("❌"):
        msgs.append(summary)

    results = data.get("results", [])
    if results:
        lines = ["\n📎 Fonti:"]
        for i, r in enumerate(results[:5], 1):
            title = (r.get("title") or "").strip() or "Senza titolo"
            url = r.get("url", "")
            lines.append(f"{i}. {title}\n   {url}")
        msgs.append("\n".join(lines))

    return msgs if msgs else ["😕 Nessun risultato trovato"]

async def call_web_read(url: str, http: aiohttp.ClientSession, chat_id: int) -> str:
    """Leggi e riassumi URL (manuale /read)."""
    payload = {"source": "tg", "source_id": str(chat_id), "url": url}
    try:
        async with http.post(QUANTUM_WEB_SUMMARY_URL, json=payload) as r:
            if r.status == 200:
                data = await r.json()
                return data.get("summary", "Nessun contenuto estratto")
            txt = await r.text()
            log.error(f"Web read {r.status}: {txt[:300]}")
            return f"❌ Errore lettura {r.status}"
    except Exception as e:
        log.error(f"Web read exception: {e}")
        return f"❌ Errore: {e}"

# === Feedback / Corrections (Intent Router) ===
async def send_feedback(http: aiohttp.ClientSession, query: str, used_intent: str, ok: bool, elapsed_ms: int):
    try:
        payload = {
            "query": query,
            "intent_used": used_intent,
            "satisfaction": 1.0 if ok else 0.0,
            "response_time_ms": int(elapsed_ms)
        }
        async with http.post(f"{INTENT_ROUTER_URL}/feedback", json=payload) as r:
            if r.status != 200:
                log.warning(f"feedback HTTP {r.status}")
    except Exception as e:
        log.debug(f"feedback err: {e}")

async def send_correction(http: aiohttp.ClientSession, query: str, correct_intent: str):
    try:
        payload = {"query": query, "correct_intent": correct_intent}
        async with http.post(f"{INTENT_ROUTER_URL}/correct", json=payload) as r:
            if r.status != 200:
                log.warning(f"correct HTTP {r.status}")
    except Exception as e:
        log.debug(f"correct err: {e}")

# === MAIN MESSAGE HANDLER (AUTONOMOUS + CALCULATOR) ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler principale: fast calculator -> /generate (smart routing) + feedback buttons"""
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

    # ✅ CALCOLATRICE (fast path locale)
    if is_calculator_query(text) and safe_eval:
        try:
            result = safe_eval(text)
        except Exception as e:
            result = None
        if result is not None:
            await msg.reply_text(f"🧮 `{text}` = `{result}`", parse_mode="Markdown")
            log.info(f"🧮 Calculator: {text} = {result}")
            # feedback opzionale
            await send_feedback(http, text, "CALCULATOR", True, 0)
            return

    # 🧠 /generate (smart routing lato server)
    t0 = time.perf_counter()
    data = await call_generate(text, http, chat_id)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    if not data.get("ok", True) and not data.get("response"):
        await msg.reply_text(f"❌ Errore: {data.get('error','unknown')}")
        # segnalo feedback negativo
        await send_feedback(http, text, data.get("intent","DIRECT_LLM"), False, elapsed_ms)
        return

    # Estrai testo
    reply_text = extract_openai_like_text(data) or "❌ Nessuna risposta testuale"
    used_intent = (data.get("intent") or "DIRECT_LLM").upper()
    conf = data.get("confidence")
    cached = data.get("cached")
    meta = []
    if used_intent: meta.append(f"intent={used_intent}")
    if conf is not None: meta.append(f"conf={conf:.2f}")
    if cached: meta.append("cached")

    # Invio risposta
    for part in split_text(reply_text):
        await msg.reply_text(part, disable_web_page_preview=True)

    # Feedback inline
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👍", callback_data="fb_good"),
            InlineKeyboardButton("👎", callback_data="fb_bad")
        ],
        [
            InlineKeyboardButton("🌐 Serve web", callback_data="force_web"),
            InlineKeyboardButton("🧠 Non serve web", callback_data="force_direct")
        ]
    ])
    fb_msg = await msg.reply_text(
        f"⏱ {elapsed_ms}ms | " + (" ".join(meta) if meta else "ok"),
        reply_markup=kb
    )

    # Mappa per callback → salviamo query/intent/elapsed
    context.application.bot_data["fb_map"][fb_msg.message_id] = {
        "query": text,
        "intent": used_intent,
        "elapsed_ms": elapsed_ms
    }

    # feedback automatico di esito (positivo se ha risposto)
    await send_feedback(http, text, used_intent, True, elapsed_ms)

# === CALLBACK FEEDBACK ===
async def feedback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()  # ack veloce
    http = context.application.bot_data["http"]
    fb_map = context.application.bot_data.get("fb_map", {})
    msg_id = q.message.message_id
    meta = fb_map.get(msg_id, {"query": "", "intent": "DIRECT_LLM", "elapsed_ms": 0})
    query_txt = meta["query"]
    used_intent = meta["intent"]
    elapsed_ms = meta["elapsed_ms"]

    if q.data == "fb_good":
        await send_feedback(http, query_txt, used_intent, True, elapsed_ms)
        await q.edit_message_text("👍 Grazie! (feedback registrato)")
    elif q.data == "fb_bad":
        await send_feedback(http, query_txt, used_intent, False, elapsed_ms)
        await q.edit_message_text("👎 Grazie per il feedback (migliorerò)")
    elif q.data == "force_web":
        await send_correction(http, query_txt, "WEB_SEARCH")
        await q.edit_message_text("🌐 Ok, userò il web la prossima volta")
    elif q.data == "force_direct":
        await send_correction(http, query_txt, "DIRECT_LLM")
        await q.edit_message_text("🧠 Ok, risponderò direttamente")

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
    """Forza ricerca web (bypassa routing)."""
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
    """Forza lettura URL (bypassa routing)."""
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
        import redis as _r
        r = _r.Redis(host='localhost', port=6379, db=0)
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

    # Comandi
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("health", health))
    app.add_handler(CommandHandler("flushcache", flush_cache))
    app.add_handler(CommandHandler("web", web_cmd))
    app.add_handler(CommandHandler("read", read_cmd))
    app.add_handler(CommandHandler("persona", persona_get))
    app.add_handler(CommandHandler("persona_set", persona_set))
    app.add_handler(CommandHandler("persona_reset", persona_reset))

    # Callback feedback/correzioni
    app.add_handler(CallbackQueryHandler(feedback_callback))

    # Messaggi normali → smart routing
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.add_error_handler(error_handler)

    log.info("🤖 Avvio Telegram Bot (smart routing via /generate) | polling")
    app.run_polling(drop_pending_updates=True, poll_interval=1.0)
