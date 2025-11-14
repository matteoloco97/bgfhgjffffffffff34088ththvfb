#!/usr/bin/env python3
# scripts/telegram_bot.py — LLM-only chat + web manuale (PATCH 2025-11-14)
# - Tutti i messaggi vanno a /chat (nessun fallback web automatico)
# - /web usa /web/research (motore avanzato) con fallback su /web/summarize
# - /read usa /web/summarize con url
# - Calculator locale (se disponibile)
# - Attribution pulita: fonti reali quando si usa il web + badge cache opzionale
# - Log puliti, lock single-instance
# - Ritento automatico 1 volta su timeout/502/504

from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
import logging, os, sys, fcntl, re, asyncio, json
from dotenv import load_dotenv
import aiohttp
from urllib.parse import urlparse

# Path progetto (adatta se diverso)
sys.path.insert(0, "/root/quantumdev-open")

# Calculator (opzionale)
try:
    try:
        from core.calculator import safe_eval, is_calculator_query
    except Exception:
        from Core.calculator import safe_eval, is_calculator_query  # type: ignore
except Exception:
    safe_eval = None
    def is_calculator_query(_): return False

# === Single-instance lock ===
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
ADMIN_CHAT_ID = int(os.getenv("TELEGRAM_ADMIN_ID", "0") or "0")

QUANTUM_CHAT_URL            = os.getenv("QUANTUM_CHAT_URL", "http://127.0.0.1:8081/chat").strip()
QUANTUM_WEB_SUMMARY_URL     = os.getenv("QUANTUM_WEB_SUMMARY_URL", "http://127.0.0.1:8081/web/summarize").strip()
QUANTUM_WEB_RESEARCH_URL    = os.getenv("QUANTUM_WEB_RESEARCH_URL", "http://127.0.0.1:8081/web/research").strip()
QUANTUM_HEALTH_URL          = os.getenv("QUANTUM_HEALTH_URL", "http://127.0.0.1:8081/healthz").strip()
QUANTUM_PERSONA_SET_URL     = os.getenv("QUANTUM_PERSONA_SET_URL", "http://127.0.0.1:8081/persona/set").strip()
QUANTUM_PERSONA_GET_URL     = os.getenv("QUANTUM_PERSONA_GET_URL", "http://127.0.0.1:8081/persona/get").strip()
QUANTUM_PERSONA_RESET_URL   = os.getenv("QUANTUM_PERSONA_RESET_URL", "http://127.0.0.1:8081/persona/reset").strip()

# UI flags
SOURCE_PREVIEW     = os.getenv("TELEGRAM_SOURCE_PREVIEW", "0").strip() != "0"    # anteprime Telegram
SHOW_SOURCES       = os.getenv("TELEGRAM_SHOW_SOURCES",   "1").strip() != "0"    # mostra elenco fonti
SHOW_CACHE_BADGE   = os.getenv("TELEGRAM_SHOW_CACHE_BADGE", "1").strip() != "0"

# === LOGGING ===
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

# === Utils ===
TG_MAX = 4096
def split_text(s: str, size: int = TG_MAX):
    return [s[i:i+size] for i in range(0, len(s), size)] if s else []

def first_url(s: str):
    if not s: return None
    m = re.search(r'(https?://\S+)', s)
    return m.group(1) if m else None

def _domain(u: str) -> str:
    try:
        return urlparse(u).netloc or u
    except Exception:
        return u

async def typing(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    try:
        await context.bot.send_chat_action(chat_id, "typing")
    except Exception:
        pass

# === HTTP lifecycle ===
async def on_startup(app):
    app.bot_data["http"] = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180))
    log.info(
        "🌐 HTTP session pronta; /chat=%s | /web/summarize=%s | /web/research=%s",
        QUANTUM_CHAT_URL, QUANTUM_WEB_SUMMARY_URL, QUANTUM_WEB_RESEARCH_URL
    )

async def on_shutdown(app):
    sess = app.bot_data.get("http")
    if sess and not sess.closed:
        await sess.close()
    log.info("👋 HTTP session chiusa")

# === Core calls ===
async def _post_json(http: aiohttp.ClientSession, url: str, payload: dict) -> tuple[int, dict | None, str | None]:
    try:
        async with http.post(url, json=payload) as r:
            status = r.status
            try:
                data = await r.json()
            except Exception:
                data = None
            txt = None if data is not None else (await r.text())
            return status, data, txt
    except asyncio.TimeoutError:
        return 599, None, "timeout"
    except Exception as e:
        return 598, None, str(e)

async def _post_json_retry(http, url, payload):
    status, data, txt = await _post_json(http, url, payload)
    if status in (502, 504, 598, 599):
        log.warning("⚠️ Retry %s per %s: %s", status, url, payload.get("q") or payload.get("url") or "")
        status, data, txt = await _post_json(http, url, payload)
    return status, data, txt

async def call_chat(text: str, http: aiohttp.ClientSession, chat_id: int) -> dict:
    payload = {"source": "tg", "source_id": str(chat_id), "text": text}
    status, data, txt = await _post_json_retry(http, QUANTUM_CHAT_URL, payload)
    if status == 200 and isinstance(data, dict):
        return data
    return {"ok": False, "error": f"/chat {status}: {txt or ''}"}

# === Formatting WEB results (attribution + cache badge) ===
def _format_sources_block(data: dict, max_sources: int = 3) -> str:
    if not SHOW_SOURCES:
        return ""
    sources = data.get("used_sources") or data.get("sources") or []
    if not isinstance(sources, list) or not sources:
        return ""
    lines = []
    for s in sources[:max_sources]:
        title = (s.get("title") or "").strip() or s.get("url") or "Link"
        url = (s.get("url") or "").strip()
        if url:
            lines.append(f"• {title} — {url}")
        else:
            lines.append(f"• {title}")
    return "\n\n📚 Fonti:\n" + "\n".join(lines)

def _cache_badge(data: dict) -> str:
    return "\n\n💾 (da cache)" if SHOW_CACHE_BADGE and bool(data.get("cached")) else ""

# === /web/summarize (RESTO come fallback) ===
async def call_web_summary_query(query: str, http: aiohttp.ClientSession, chat_id: int) -> str:
    payload = {"q": query, "k": 6, "summarize_top": 2, "source": "tg", "source_id": str(chat_id)}
    status, data, _ = await _post_json_retry(http, QUANTUM_WEB_SUMMARY_URL, payload)
    if status != 200 or not isinstance(data, dict):
        return "Non riesco a sintetizzare ora."
    note = (data.get("note") or "").lower()

    # Messaggi UX chiari su non-web o zero risultati
    if note == "non_web_query":
        return "Richiesta breve/smalltalk: non serve il web. Scrivimi direttamente senza /web 🙂"
    if note in {"no_results", "empty_serp"}:
        tips = "Suggerimenti: prova ad aggiungere `site:dominio` o dettagli temporali (es. anno/oggi)."
        return f"Nessun risultato affidabile trovato.\n{tips}"

    summary = (data.get("summary") or "").strip()
    if not summary:
        results = data.get("results") or []
        if results:
            bullets = "\n".join(f"- {it.get('title','').strip() or it.get('url','')}" for it in results[:4])
            return f"Sintesi rapida:\n{bullets}" + _format_sources_block(data) + _cache_badge(data)
        return "Nessun risultato utile."

    # Summary + (fonti + cache badge opzionali)
    return summary + _format_sources_block(data) + _cache_badge(data)

# === /web/research — motore principale per /web =======================
_BAD_PATTERNS = [
    "le fonti fornite non contengono",
    "consulta le fonti specifiche",
    "aprire una fonte attendibile",
]

def _looks_bad_summary(text: str) -> bool:
    s = text.lower()
    if len(s) < 40:
        return True
    return any(p in s for p in _BAD_PATTERNS)

async def call_web_research(query: str, http: aiohttp.ClientSession, chat_id: int) -> str:
    """
    Usa il motore avanzato /web/research (WebResearchAgent).
    Se il risultato è scarso o fallisce, fallback su /web/summarize.
    """
    payload = {"q": query, "source": "tg", "source_id": str(chat_id)}
    status, data, _ = await _post_json_retry(http, QUANTUM_WEB_RESEARCH_URL, payload)

    if status == 200 and isinstance(data, dict):
        answer = (data.get("answer") or "").strip()
        if answer and not _looks_bad_summary(answer):
            # Risposta buona
            return answer + _format_sources_block(data)
        # Se l'answer è vuota o palesemente "scarica barile", facciamo fallback sotto

    # Fallback su /web/summarize
    return await call_web_summary_query(query, http, chat_id)

# === /read URL (rimane su /web/summarize con url) =====================
async def call_web_read(url: str, http: aiohttp.ClientSession, chat_id: int) -> str:
    payload = {"source": "tg", "source_id": str(chat_id), "url": url, "return_sources": True}
    status, data, _ = await _post_json_retry(http, QUANTUM_WEB_SUMMARY_URL, payload)
    if status != 200 or not isinstance(data, dict):
        return f"❌ Errore lettura ({status})"
    summary = (data.get("summary") or data.get("answer") or "Nessun contenuto estratto").strip()
    return summary + _format_sources_block(data) + _cache_badge(data)

# === UI ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧠 Quantum AI\n"
        "• 💬 Chatta con l’AI (no web automatico)\n"
        "• 🌐 Usa il web con /web <query> (motore avanzato)\n"
        "• 📄 Riassumi una pagina con /read <url>\n"
        "• 🧮 Calcoli locali se riconosciuti\n"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Comandi: /health, /web <query>, /read <url>, /persona, /persona_set, /persona_reset, /flushcache (admin)"
    )

# === Handler principale (LLM-only) ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return
    text = msg.text.strip()
    chat_id = update.effective_chat.id
    http = context.application.bot_data["http"]

    # Ping
    if text.lower() in {"ping", "pong"}:
        await msg.reply_text("pong")
        return

    # Calculator
    if is_calculator_query(text) and safe_eval:
        try:
            result = safe_eval(text)
        except Exception:
            result = None
        if result is not None:
            await msg.reply_text(f"🧮 {text} = {result}")
            return

    await typing(context, chat_id)
    data = await call_chat(text, http, chat_id)
    reply = (data.get("reply") or "").strip()
    if not reply:
        await msg.reply_text("Non riesco a rispondere ora. Se vuoi cercare online usa /web <query>.")
        return
    for part in split_text(reply):
        await msg.reply_text(part, disable_web_page_preview=True)

# === Comandi manuali ===
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
    text = update.message.text
    query = text.split(maxsplit=1)[1] if len(text.split()) > 1 else ""
    if not query:
        await update.message.reply_text("Uso: /web <query>")
        return
    http = context.application.bot_data["http"]
    await update.message.reply_text(f"🌐 Cerco: {query}")
    final = await call_web_research(query, http, update.effective_chat.id)
    for part in split_text(final):
        await update.message.reply_text(part, disable_web_page_preview=not SOURCE_PREVIEW)

async def read_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    args = text.split(maxsplit=1)[1] if len(text.split()) > 1 else ""
    url = first_url(args)
    if not url:
        await update.message.reply_text("Uso: /read <url>")
        return
    http = context.application.bot_data["http"]
    await update.message.reply_text(f"📄 Leggo {url}...")
    final = await call_web_read(url, http, update.effective_chat.id)
    for part in split_text(final):
        await update.message.reply_text(part, disable_web_page_preview=not SOURCE_PREVIEW)

async def flush_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not ADMIN_CHAT_ID or chat_id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ Non sei autorizzato.")
        return
    try:
        import redis as _r
        r = _r.Redis(host='localhost', port=6379, db=0)
        r.flushall()
        await update.message.reply_text("✅ Cache Redis svuotata.")
    except Exception as e:
        await update.message.reply_text(f"❌ Errore: {e}")

# Persona
async def persona_get(update: Update, context: ContextTypes.DEFAULT_TYPE):
    http = context.application.bot_data["http"]
    payload = {"source": "tg", "source_id": str(update.effective_chat.id)}
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
    args = update.message.text.split(maxsplit=1)[1] if len(update.message.text.split()) > 1 else ""
    if not args:
        return await update.message.reply_text("Uso: /persona_set <testo>")
    payload = {"source": "tg", "source_id": str(update.effective_chat.id), "text": args}
    try:
        async with http.post(QUANTUM_PERSONA_SET_URL, json=payload) as r:
            if r.status != 200:
                return await update.message.reply_text(f"❌ persona/set {r.status}")
        await update.message.reply_text("✅ Persona aggiornata.")
    except Exception as e:
        await update.message.reply_text(f"❌ Errore persona/set: {e}")

async def persona_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    http = context.application.bot_data["http"]
    payload = {"source": "tg", "source_id": str(update.effective_chat.id)}
    try:
        async with http.post(QUANTUM_PERSONA_RESET_URL, json=payload) as r:
            if r.status != 200:
                return await update.message.reply_text(f"❌ persona/reset {r.status}")
        await update.message.reply_text("✅ Persona resettata.")
    except Exception as e:
        await update.message.reply_text(f"❌ Errore persona/reset: {e}")

# Error handler
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.exception("❌ Errore non gestito nel bot:", exc_info=context.error)

# Main
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

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    log.info("🤖 Avvio Telegram Bot (LLM-only chat | web manuale avanzato) | polling")
    app.run_polling(drop_pending_updates=True, poll_interval=1.0)
