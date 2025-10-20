# scripts/telegram_bot.py
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
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

MODE = (os.getenv("TELEGRAM_MODE", "polling") or "polling").lower()

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

# === Redis ===
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB   = int(os.getenv("REDIS_DB", 0))

# === Web search behaviour ===
# Di default NON chiediamo la sintesi LLM per evitare l'errore 400 che vedi nel summary.
WEB_SUMMARIZE_TOP = int(os.getenv("WEB_SUMMARIZE_TOP", "0"))  # metti 2/3 quando l'LLM sarà OK

# Trigger che fanno scattare la ricerca web automatica
AUTO_WEB_PATTERNS = [
    r"\b(meteo|previsioni|bollettino)\b",
    r"\b(cerca|trova|ricerca|googla|su internet|sul web)\b",
    r"\b(notizie|news|ultime|oggi|adesso|uscito|rilasciato|aggiornamento)\b",
]

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

def looks_like_error_summary(s: str) -> bool:
    if not s: return False
    t = s.strip()
    return t.startswith('{"error"') or "Nessun endpoint raggiungibile" in t or "Client Error" in t

# === Hook startup/shutdown ===
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
    "🤖 *QuantumDev comandi*\n"
    "- /health — stato del core\n"
    "- /web <query> — cerca sul web e (opz.) sintetizza\n"
    "- /read <url> — leggi/riassumi una pagina\n"
    "- /persona — mostra la personalità attuale\n"
    "- /persona_set <testo> — imposta la personalità\n"
    "- /persona_reset — resetta la personalità\n"
    "- Messaggi con URL → /read automatico\n"
    "- Messaggi tipo “meteo roma”, “cercalo su internet” → ricerca web automatica\n"
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 QuantumDev è attivo. Digita /help per i comandi.")

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
        try:
            async with http.post(QUANTUM_API_URL, json={"prompt": text}) as r:
                if r.status != 200:
                    return f"❌ Backend {r.status}: {(await r.text())[:400]}"
                data = await r.json()
            return data["response"]["choices"][0]["message"]["content"].strip()
        except Exception as e2:
            return f"❌ Errore core: {e} / fallback: {e2}"

async def call_web_search(query: str, http: aiohttp.ClientSession, chat_id: int, k: int = 6, summarize_top: int | None = None) -> list[str]:
    if summarize_top is None:
        summarize_top = WEB_SUMMARIZE_TOP
    payload = {"source": "tg", "source_id": str(chat_id), "q": query, "k": k, "summarize_top": summarize_top}
    try:
        async with http.post(QUANTUM_WEB_SEARCH_URL, json=payload) as r:
            if r.status != 200:
                return [f"❌ web/search {r.status}: {(await r.text())[:400]}"]
            data = await r.json()
    except Exception as e:
        return [f"❌ web/search errore: {e}"]

    msgs: list[str] = []
    summary = (data.get("summary") or "").strip()
    if summary and not looks_like_error_summary(summary):
        for chunk in split_text(summary, 1000):
            msgs.append(chunk)

    results = data.get("results") or []
    if results:
        lines = ["🔎 Top risultati:"]
        for i, it in enumerate(results, 1):
            title = (it.get("title") or "").strip() or "(senza titolo)"
            url = it.get("url") or ""
            lines.append(f"{i}. {title}\n{url}")
        for chunk in split_text("\n".join(lines), 1000):
            msgs.append(chunk)
    else:
        msgs.append("Nessun risultato utile.")
    return msgs

async def call_web_summary(url: str, http: aiohttp.ClientSession, chat_id: int) -> list[str]:
    payload = {"source": "tg", "source_id": str(chat_id), "url": url}
    try:
        async with http.post(QUANTUM_WEB_SUMMARY_URL, json=payload) as r:
            if r.status != 200:
                return [f"❌ web/summarize {r.status}: {(await r.text())[:400]}"]
            data = await r.json()
    except Exception as e:
        return [f"❌ web/summarize errore: {e}"]

    summary = (data.get("summary") or "").strip()
    if not summary:
        return ["Nessun contenuto estratto dalla pagina."]
    return split_text(summary, 1000)

# === Persona ===
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

# === Comandi Web ===
async def web_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    http = context.application.bot_data["http"]
    chat_id = update.effective_chat.id
    q = argstr(update)
    if not q:
        return await update.message.reply_text("Uso: /web <query>")
    msgs = await call_web_search(q, http, chat_id, k=6, summarize_top=WEB_SUMMARIZE_TOP)
    # 1 msg per blocco: summary (se valido) e lista risultati
    for i, part in enumerate(msgs):
        await update.message.reply_text(part, disable_web_page_preview=(i == 0))

async def read_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    http = context.application.bot_data["http"]
    chat_id = update.effective_chat.id
    args = argstr(update)
    url = first_url(args)
    if not url:
        return await update.message.reply_text("Uso: /read <url>")
    msgs = await call_web_summary(url, http, chat_id)
    for part in msgs:
        await update.message.reply_text(part, disable_web_page_preview=False)

# === Messaggi normali (con euristiche auto-web/auto-read) ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return
    text = msg.text.strip()
    http = context.application.bot_data["http"]
    chat_id = update.effective_chat.id

    # Ping rapido
    if text.lower() in {"ping", "pong"}:
        await msg.reply_text("pong"); return

    # URL → riassunto pagina
    url = first_url(text)
    if url:
        msgs = await call_web_summary(url, http, chat_id)
        for part in msgs:
            await msg.reply_text(part, disable_web_page_preview=False)
        return

    # Trigger “usa il web”
    if any(re.search(pat, text, re.I) for pat in AUTO_WEB_PATTERNS):
        msgs = await call_web_search(text, http, chat_id, k=6, summarize_top=WEB_SUMMARIZE_TOP)
        for i, part in enumerate(msgs):
            await msg.reply_text(part, disable_web_page_preview=(i == 0))
        return

    # Default → chat LLM
    reply = await call_chat(text, http, chat_id)
    for part in split_text(reply):
        await msg.reply_text(part, disable_web_page_preview=False)

# === Error handler ===
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

    logging.info("🤖 Avvio Telegram Bot… (mode=%s)", MODE)

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
