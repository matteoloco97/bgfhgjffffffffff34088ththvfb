# scripts/telegram_bot.py
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from telegram.error import Conflict
import logging, os, redis, json, sys, fcntl, re
from dotenv import load_dotenv
import aiohttp

# === single-instance lock ===
LOCK_PATH = "/tmp/telegram-bot.lock"
_lock_f = open(LOCK_PATH, "w")
try:
    fcntl.lockf(_lock_f, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError:
    print("⚠️  Un'altra istanza del bot è già in esecuzione. Esco.")
    sys.exit(0)

# === ENV ===
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or ""
ADMIN_CHAT_ID_ENV = os.getenv("TELEGRAM_ADMIN_ID", "")
ADMIN_CHAT_ID = int(ADMIN_CHAT_ID_ENV) if ADMIN_CHAT_ID_ENV.isdigit() else None

# Modalità: webhook | polling (default: polling per semplicità)
MODE = (os.getenv("TELEGRAM_MODE", "polling") or "polling").lower()

# Webhook settings (usati se MODE=webhook)
WEBHOOK_URL_BASE  = os.getenv("TELEGRAM_WEBHOOK_URL", "").rstrip("/")
WEBHOOK_LISTEN    = os.getenv("TELEGRAM_WEBHOOK_LISTEN", "127.0.0.1")
WEBHOOK_PORT      = int(os.getenv("TELEGRAM_WEBHOOK_PORT", 9000))
WEBHOOK_PATH      = os.getenv("TELEGRAM_WEBHOOK_PATH") or f"/tg-webhook/{BOT_TOKEN}"
WEBHOOK_SECRET    = os.getenv("TELEGRAM_WEBHOOK_SECRET") or None

# === Quantum Core endpoints ===
QUANTUM_API_URL           = os.getenv("QUANTUM_API_URL", "http://127.0.0.1:8081/generate")
QUANTUM_CHAT_URL          = os.getenv("QUANTUM_CHAT_URL", "http://127.0.0.1:8081/chat")
QUANTUM_WEB_SEARCH_URL    = os.getenv("QUANTUM_WEB_SEARCH_URL", "http://127.0.0.1:8081/web/search")
QUANTUM_WEB_SUMMARY_URL   = os.getenv("QUANTUM_WEB_SUMMARY_URL", "http://127.0.0.1:8081/web/summarize")
QUANTUM_PERSONA_SET_URL   = os.getenv("QUANTUM_PERSONA_SET_URL", "http://127.0.0.1:8081/persona/set")
QUANTUM_PERSONA_GET_URL   = os.getenv("QUANTUM_PERSONA_GET_URL", "http://127.0.0.1:8081/persona/get")
QUANTUM_PERSONA_RESET_URL = os.getenv("QUANTUM_PERSONA_RESET_URL", "http://127.0.0.1:8081/persona/reset")
QUANTUM_HEALTH_URL        = os.getenv("QUANTUM_HEALTH_URL", "http://127.0.0.1:8081/healthz")

# Redis (per /flushcache)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB   = int(os.getenv("REDIS_DB", 0))

# === LOGGING ===
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# === Utility ===
TG_MAX = 4096
def split_text(s: str, size: int = TG_MAX):
    if not s: return []
    return [s[i:i+size] for i in range(0, len(s), size)]

def argstr(update: Update) -> str:
    txt = update.message.text if update.message else ""
    parts = txt.split(maxsplit=1)
    return (parts[1] if len(parts) > 1 else "").strip()

def first_url(s: str) -> str | None:
    if not s: return None
    m = re.search(r'(https?://\S+)', s)
    return m.group(1) if m else None

def md_safe(s: str) -> str:
    # escape minimo per Markdown V2 (evita errori su punti/elenco)
    return (
        s.replace('\\', '\\\\')
         .replace('_', '\\_')
         .replace('*', '\\*')
         .replace('[', '\\[')
         .replace(']', '\\]')
         .replace('(', '\\(')
         .replace(')', '\\)')
         .replace('~', '\\~')
         .replace('`', '\\`')
         .replace('>', '\\>')
         .replace('#', '\\#')
         .replace('+', '\\+')
         .replace('-', '\\-')
         .replace('=', '\\=')
         .replace('|', '\\|')
         .replace('{', '\\{')
         .replace('}', '\\}')
         .replace('.', '\\.')
         .replace('!', '\\!')
    )

def fmt_results(results):
    lines = []
    for i, r in enumerate(results, 1):
        url = (r.get("url") or "").strip()
        title = (r.get("title") or "").strip() or url
        lines.append(f"{i}. {title}\n{url}")
    return "\n".join(lines)

# === Hook startup/shutdown (sessione HTTP riusabile) ===
async def on_startup(app):
    app.bot_data["http"] = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120))
    logger.info("🌐 HTTP session pronta; core chat=%s", QUANTUM_CHAT_URL)

async def on_shutdown(app):
    sess = app.bot_data.get("http")
    if sess and not sess.closed:
        await sess.close()
    logger.info("👋 HTTP session chiusa")

# === /start & /help ===
HELP_TEXT = (
    "🤖 *Quantum AI – comandi*\n"
    "• /health — stato del core\n"
    "• /web <query> — cerca sul web e sintetizza\n"
    "• /read <url> — riassume una pagina\n"
    "• /meteo <città> — meteo attuale (Open-Meteo)\n"
    "• /persona — mostra la personalità attuale\n"
    "• /persona_set <testo> — imposta la personalità\n"
    "• /persona_reset — resetta la personalità\n"
    "• Oppure scrivi normalmente per la risposta LLM\n"
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Quantum AI è attivo.\nDigita /help per i comandi.")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for chunk in split_text(HELP_TEXT, 1000):
        await update.message.reply_text(chunk, disable_web_page_preview=True)

# === /health ===
async def health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    http = context.application.bot_data["http"]
    try:
        async with http.get(QUANTUM_HEALTH_URL) as r:
            txt = await r.text()
        for chunk in split_text(txt, 900):
            await update.message.reply_text(chunk)
    except Exception as e:
        await update.message.reply_text(f"❌ Health fallita: {e}")

# === /flushcache ===
async def flush_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if ADMIN_CHAT_ID is None or chat_id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ Non sei autorizzato.")
        return
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
        r.flushall()
        await update.message.reply_text("✅ Cache Redis svuotata.")
        logger.info("✅ Cache Redis svuotata da Telegram")
    except Exception as e:
        logger.error(f"Errore flush: {e}")
        await update.message.reply_text(f"❌ Errore: {e}")

# === Core calls ===
async def call_chat(text: str, http: aiohttp.ClientSession, chat_id: int) -> str:
    payload = {"source": "tg", "source_id": str(chat_id), "text": text}
    try:
        async with http.post(QUANTUM_CHAT_URL, json=payload) as r:
            if r.status != 200:
                return f"❌ Core chat {r.status}: {(await r.text())[:400]}"
            data = await r.json()
        return (data.get("reply") or "").strip() or json.dumps(data, ensure_ascii=False)[:4000]
    except Exception as e:
        # fallback /generate se /chat ha problemi
        try:
            async with http.post(QUANTUM_API_URL, json={"prompt": text}) as r:
                if r.status != 200:
                    return f"❌ Backend {r.status}: {(await r.text())[:400]}"
                data = await r.json()
            return data["response"]["choices"][0]["message"]["content"].strip()
        except Exception as e2:
            return f"❌ Errore core: {e} / fallback: {e2}"

async def call_web_search(query: str, http: aiohttp.ClientSession, chat_id: int, k: int = 6, summarize_top: int = 3) -> str:
    payload = {"source": "tg", "source_id": str(chat_id), "q": query, "k": k, "summarize_top": summarize_top}
    try:
        async with http.post(QUANTUM_WEB_SEARCH_URL, json=payload) as r:
            data = await r.json()
    except Exception as e:
        return f"❌ web/search errore: {e}"

    # Non esporre errori interni all’utente
    if isinstance(data, dict) and "error" in data:
        logging.warning("web_search internal error: %s", data.get("error"))

    results = (data or {}).get("results", []) or []
    summary = (data or {}).get("summary", "").strip()

    blocks = []
    if results:
        blocks.append("📎 *Top risultati:*\n" + fmt_results(results))
    if summary:
        blocks.append("📝 *Sintesi:*\n" + summary)

    if not blocks:
        return "😕 Nessun risultato trovato."
    return "\n\n".join(blocks)

async def call_web_summary(url: str, http: aiohttp.ClientSession, chat_id: int) -> str:
    payload = {"source": "tg", "source_id": str(chat_id), "url": url}
    try:
        async with http.post(QUANTUM_WEB_SUMMARY_URL, json=payload) as r:
            if r.status != 200:
                return f"❌ web/summarize {r.status}: {(await r.text())[:400]}"
            data = await r.json()
    except Exception as e:
        return f"❌ Summarize errore: {e}"

    summary = (data.get("summary") or "").strip()
    return summary or "Nessun contenuto estratto dalla pagina."

# === Persona handlers ===
async def persona_get(update: Update, context: ContextTypes.DEFAULT_TYPE):
    http = context.application.bot_data["http"]
    chat_id = update.effective_chat.id
    payload = {"source": "tg", "source_id": str(chat_id)}
    try:
        async with http.post(QUANTUM_PERSONA_GET_URL, json=payload) as r:
            if r.status != 200:
                return await update.message.reply_text(f"❌ persona/get {r.status}: {(await r.text())[:400]}")
            data = await r.json()
        persona = data.get("persona") or "(vuota)"
        for chunk in split_text(f"🧠 Persona attuale:\n{persona}", 1000):
            await update.message.reply_text(chunk)
    except Exception as e:
        await update.message.reply_text(f"❌ Errore persona/get: {e}")

async def persona_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    http = context.application.bot_data["http"]
    chat_id = update.effective_chat.id
    text = argstr(update)
    if not text:
        return await update.message.reply_text("Uso: /persona_set <testo>")
    payload = {"source": "tg", "source_id": str(chat_id), "text": text}
    try:
        async with http.post(QUANTUM_PERSONA_SET_URL, json=payload) as r:
            if r.status != 200:
                return await update.message.reply_text(f"❌ persona/set {r.status}: {(await r.text())[:400]}")
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
                return await update.message.reply_text(f"❌ persona/reset {r.status}: {(await r.text())[:400]}")
        await update.message.reply_text("✅ Persona resettata.")
    except Exception as e:
        await update.message.reply_text(f"❌ Errore persona/reset: {e}")

# === /web ===
async def web_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    http = context.application.bot_data["http"]
    chat_id = update.effective_chat.id
    q = argstr(update)
    if not q:
        return await update.message.reply_text("Uso: /web <query>")
    reply = await call_web_search(q, http, chat_id, k=6, summarize_top=2)
    # usa Markdown V2 sicuro
    text = f"🔎 *Risultati per:* `{md_safe(q)}`\n\n{reply}"
    for part in split_text(text):
        await update.message.reply_markdown_v2(part, disable_web_page_preview=False)

# === /read ===
async def read_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    http = context.application.bot_data["http"]
    chat_id = update.effective_chat.id
    args = argstr(update)
    url = first_url(args)
    if not url:
        return await update.message.reply_text("Uso: /read <url>")
    reply = await call_web_summary(url, http, chat_id)
    for part in split_text(reply):
        await update.message.reply_text(part, disable_web_page_preview=False)

# === /meteo <città> (Open-Meteo, senza API key) ===
async def meteo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    http = context.application.bot_data["http"]
    query = argstr(update)
    if not query:
        return await update.message.reply_text("Uso: /meteo <città>")

    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={query}&count=1&language=it&format=json"
        async with http.get(geo_url) as r:
            g = await r.json()
        if not g or not g.get("results"):
            return await update.message.reply_text(f"Non trovo la località “{query}”.")

        loc = g["results"][0]
        lat, lon = loc["latitude"], loc["longitude"]
        name = loc.get("name","")
        country = loc.get("country","")
        tz = loc.get("timezone","auto")

        w_url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            "&current=temperature_2m,relative_humidity_2m,apparent_temperature,is_day,weather_code,wind_speed_10m"
            "&hourly=temperature_2m,precipitation_probability,weather_code"
            f"&timezone={tz}"
        )
        async with http.get(w_url) as r:
            w = await r.json()

        cur = w.get("current", {})
        t = cur.get("temperature_2m")
        app = cur.get("apparent_temperature")
        wind = cur.get("wind_speed_10m")
        hum = cur.get("relative_humidity_2m")
        code = cur.get("weather_code")

        desc = {
            0:"sereno",1:"perlopiù sereno",2:"parz. nuvoloso",3:"coperto",
            45:"nebbia",48:"nebbia ghiaccio",
            51:"pioviggine debole",53:"pioviggine",55:"pioviggine intensa",
            61:"pioggia debole",63:"pioggia",65:"pioggia forte",
            71:"neve debole",73:"neve",75:"neve forte",
            80:"rovesci deboli",81:"rovesci",82:"rovesci forti",
            95:"temporali",96:"temporali (grandine)",99:"temporali forti (grandine)"
        }.get(int(code) if code is not None else -1, "meteo variabile")

        text = (
            f"🌍 *{md_safe(name)}, {md_safe(country)}*\n"
            f"• Stato: {md_safe(desc)}\n"
            f"• Temp: {t}°C (percepita {app}°C)\n"
            f"• Vento: {wind} km/h  • Umidità: {hum}%\n"
            f"Fonte: open-meteo.com"
        )
        for part in split_text(text):
            await update.message.reply_markdown_v2(part)
    except Exception as e:
        logger.exception("meteo error", exc_info=e)
        await update.message.reply_text(f"❌ Errore meteo: {e}")

# === Messaggi normali ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return
    text = msg.text.strip()

    if text.lower() in {"ping", "pong"}:
        await msg.reply_text("pong")
        return

    http = context.application.bot_data["http"]
    reply = await call_chat(text, http, update.effective_chat.id)
    for part in split_text(reply):
        await msg.reply_text(part, disable_web_page_preview=False)

# === Error handler (evita crash su 409) ===
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    err = context.error
    if isinstance(err, Conflict):
        logger.warning("🔁 Conflict 409 da Telegram: ignoro e continuo…")
        return
    logger.exception("❌ Errore non gestito nel bot:", exc_info=err)

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

    # comandi
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("health", health))
    app.add_handler(CommandHandler("flushcache", flush_cache))
    app.add_handler(CommandHandler("web", web_cmd))
    app.add_handler(CommandHandler("read", read_cmd))
    app.add_handler(CommandHandler("meteo", meteo_cmd))
    app.add_handler(CommandHandler("persona", persona_get))
    app.add_handler(CommandHandler("persona_set", persona_set))
    app.add_handler(CommandHandler("persona_reset", persona_reset))

    # messaggi normali → /chat
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    logger.info("🤖 Avvio Telegram Bot… (mode=%s)", MODE)

    if MODE == "webhook":
        if not WEBHOOK_URL_BASE:
            raise SystemExit("❌ TELEGRAM_WEBHOOK_URL mancante nel .env (es: https://tuodominio.it)")
        webhook_url = f"{WEBHOOK_URL_BASE}{WEBHOOK_PATH}"
        app.run_webhook(
            listen=WEBHOOK_LISTEN,
            port=WEBHOOK_PORT,
            url_path=WEBHOOK_PATH,
            webhook_url=webhook_url,
            secret_token=WEBHOOK_SECRET,
            drop_pending_updates=True,
        )
    else:
        app.run_polling(drop_pending_updates=True, poll_interval=1.0)
