#!/usr/bin/env python3
# scripts/telegram_bot.py - Bot Telegram con Smart Routing (/generate) + Calculator
# Patch 2025-11:
# - Usa /generate come via principale (routing LLM/WEB lato backend)
# - Fallback web: /web/summarize (q|url) con fonte inline
# - SE /web segnala note=non_web_query o 0 risultati → ricade su /generate?force=direct
# - Mai mostrare "Nessun risultato utile." ai piccoli saluti / query brevi
# - Feedback opzionale, meta opzionale

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, CallbackQueryHandler, filters
)
import logging, os, sys, fcntl, re, asyncio, time
from html import escape as hesc
from dotenv import load_dotenv
import aiohttp
from urllib.parse import urlparse

# path locale al progetto
sys.path.insert(0, '/root/quantumdev-open')

# Calculator (fast path)
try:
    try:
        from core.calculator import safe_eval, is_calculator_query
    except Exception:
        from Core.calculator import safe_eval, is_calculator_query
except Exception:
    safe_eval = None
    def is_calculator_query(_): return False

# === single-instance lock ===
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

QUANTUM_GENERATE_URL      = os.getenv("QUANTUM_GENERATE_URL", "http://127.0.0.1:8081/generate")
QUANTUM_CHAT_URL          = os.getenv("QUANTUM_CHAT_URL", "http://127.0.0.1:8081/chat")
# NOTA: /web/search non usato → /web/summarize supporta q e url
QUANTUM_WEB_SUMMARY_URL   = os.getenv("QUANTUM_WEB_SUMMARY_URL", "http://127.0.0.1:8081/web/summarize")
QUANTUM_HEALTH_URL        = os.getenv("QUANTUM_HEALTH_URL", "http://127.0.0.1:8081/healthz")
QUANTUM_PERSONA_SET_URL   = os.getenv("QUANTUM_PERSONA_SET_URL", "http://127.0.0.1:8081/persona/set")
QUANTUM_PERSONA_GET_URL   = os.getenv("QUANTUM_PERSONA_GET_URL", "http://127.0.0.1:8081/persona/get")
QUANTUM_PERSONA_RESET_URL = os.getenv("QUANTUM_PERSONA_RESET_URL", "http://127.0.0.1:8081/persona/reset")

INTENT_ROUTER_URL = os.getenv("INTENT_ROUTER_URL", "http://127.0.0.1:8090")

# UI flags
INLINE_SOURCE     = os.getenv("TELEGRAM_INLINE_SOURCE", "1").strip() != "0"
SOURCE_PREVIEW    = os.getenv("TELEGRAM_SOURCE_PREVIEW", "0").strip() != "0"
FEEDBACK_ENABLED  = os.getenv("TELEGRAM_FEEDBACK", "0").strip() != "0"   # 🔕 default OFF
SHOW_META         = os.getenv("TELEGRAM_SHOW_META", "0").strip() != "0"  # 🔕 default OFF

# === LOGGING ===
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

# === Utils ===
TG_MAX = 4096
CTX_ERR_RE = re.compile(r"(maximum context length|context\s+length\s+exceeded|This model's maximum context length)", re.I)
FONTI_RE = re.compile(r"\n+Fonti\s*:.*", flags=re.IGNORECASE | re.DOTALL)

# smalltalk guard (coerente con backend)
SMALLTALK_RE = re.compile(r"""(?ix)^\s*(
    ciao|hey|hi|hello|salve|buongiorno|buonasera|buonanotte|
    ci\s*sei\??|sei\s*online\??|come\s+va\??|ok+|perfetto|grazie|thanks
)\b""")

def is_smalltalk(txt: str) -> bool:
    s = (txt or "").strip().lower()
    return bool(SMALLTALK_RE.search(s)) or len(s.split()) <= 2

def split_text(s: str, size: int = TG_MAX):
    return [s[i:i+size] for i in range(0, len(s), size)] if s else []

def first_url(s: str):
    if not s: return None
    m = re.search(r'(https?://\S+)', s)
    return m.group(1) if m else None

def _domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""

def _harvest_sources(payload: dict) -> list[dict]:
    """Estrae un elenco normalizzato di fonti da diverse shape del payload."""
    if not isinstance(payload, dict): return []
    cand = []
    for key in ("sources", "results"):
        if isinstance(payload.get(key), list):
            cand = payload[key]; break
    if not cand:
        for k in ("response", "web", "data"):
            sub = payload.get(k)
            if isinstance(sub, dict):
                for kk in ("sources", "results"):
                    if isinstance(sub.get(kk), list):
                        cand = sub[kk]; break
            if cand: break
    norm = []
    for it in cand:
        if not isinstance(it, dict): continue
        url = it.get("url") or it.get("link") or ""
        title = it.get("title") or it.get("site") or _domain_of(url) or "Fonte"
        score = it.get("score") or it.get("rank") or 0
        try: score = float(score)
        except: score = 0.0
        norm.append({"url": url, "title": title, "score": score})
    return norm

def _pick_main_source(sources: list[dict]) -> dict | None:
    if not sources: return None
    srt = sorted(sources, key=lambda s: float(s.get("score", 0.0)), reverse=True)
    return srt[0] if srt else None

def _render_inline_source_line(src: dict) -> str:
    if not src: return ""
    url = src.get("url") or ""
    title = src.get("title") or _domain_of(url) or "Fonte"
    dom = _domain_of(url)
    return f'Fonte: <a href="{hesc(url)}">{hesc(title)}</a> — <i>{hesc(dom)}</i>' if url else f"Fonte: <b>{hesc(title)}</b>"

def _compose_final_with_source(text_plain: str, payload: dict) -> tuple[str, bool]:
    """
    Rimuove eventuale blocco 'Fonti:' del modello e aggiunge 1 fonte principale inline.
    Ritorna (testo_pronto, use_html).
    """
    clean = FONTI_RE.sub("", text_plain or "").strip()
    if not INLINE_SOURCE:
        return clean, False
    sources = _harvest_sources(payload)
    main_src = _pick_main_source(sources)
    if not main_src:
        return clean, False
    src_line = _render_inline_source_line(main_src)
    return f"{hesc(clean)}\n\n{src_line}", True

def _is_ctx_overflow(text: str, payload: dict) -> bool:
    if text and CTX_ERR_RE.search(text): return True
    err = payload.get("error")
    if isinstance(err, str) and CTX_ERR_RE.search(err): return True
    return False

def extract_openai_like_text(data: dict) -> str:
    """Estrae testo stile OpenAI /chat completions o fallback chat API."""
    try:
        resp = data.get("response") or {}
        ch = resp.get("choices") or []
        if ch and "message" in ch[0]:
            return (ch[0]["message"].get("content") or "").strip()
    except Exception:
        pass
    if "reply" in data:
        return (data.get("reply") or "").strip()
    return ""

# === HTTP lifecycle ===
async def on_startup(app):
    app.bot_data["http"] = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180))
    app.bot_data["fb_map"] = {}
    log.info("🌐 HTTP session pronta; /generate=%s | /web/summarize=%s", QUANTUM_GENERATE_URL, QUANTUM_WEB_SUMMARY_URL)

async def on_shutdown(app):
    sess = app.bot_data.get("http")
    if sess and not sess.closed:
        await sess.close()
    log.info("👋 HTTP session chiusa")

# === Core calls ===
async def call_generate(text: str, http: aiohttp.ClientSession, chat_id: int, force_direct: bool = False) -> dict:
    """
    Chiede a Quantum API di decidere: DIRECT_LLM vs WEB_* e di rispondere.
    Se force_direct=True forza endpoint ?force=direct.
    """
    payload = {"prompt": text, "temperature": 0.3, "model": None, "source": "tg", "source_id": str(chat_id)}
    url = QUANTUM_GENERATE_URL + ("?force=direct" if force_direct else "")
    try:
        async with http.post(url, json=payload) as r:
            if r.status == 200:
                return await r.json()
            txt = await r.text()
            return {"ok": False, "error": f"/generate {r.status}: {txt[:300]}", "status": r.status}
    except asyncio.TimeoutError:
        return {"ok": False, "error": "Timeout: GPU/LLM lento"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

async def call_web_summary_query(query: str, http: aiohttp.ClientSession, chat_id: int) -> tuple[str, bool]:
    """
    Fallback/sintesi tramite /web/summarize in modalità QUERY (q=...).
    Se note=non_web_query o 0 risultati → ricade su /generate?force=direct.
    Ritorna (testo_finale, use_html).
    """
    payload = {"q": query, "k": 6, "summarize_top": 2, "source": "tg", "source_id": str(chat_id)}
    try:
        async with http.post(QUANTUM_WEB_SUMMARY_URL, json=payload) as r:
            if r.status != 200:
                _ = await r.text()
                # Forza direct LLM
                data2 = await call_generate(query, http, chat_id, force_direct=True)
                txt = extract_openai_like_text(data2) or "Non riesco a sintetizzare ora."
                return txt, False
            data = await r.json()
    except Exception:
        data2 = await call_generate(query, http, chat_id, force_direct=True)
        txt = extract_openai_like_text(data2) or "Non riesco a sintetizzare ora."
        return txt, False

    # Se il backend segnala che NON è query web → forza direct LLM
    if (data.get("note") == "non_web_query") or not (data.get("results") or []):
        data2 = await call_generate(query, http, chat_id, force_direct=True)
        txt = extract_openai_like_text(data2) or "Dimmi pure: posso rispondere direttamente."
        return txt, False

    summary = (data.get("summary") or "").strip()
    if not summary:
        # Se abbiamo solo risultati senza summary, mostra elenco compatto
        results = data.get("results") or []
        bullets = "\n".join(f"- {it.get('title','')} ({it.get('url','')})" for it in results[:4]) if results else ""
        summary = f"Sintesi rapida:\n{bullets}" if bullets else "Non ho abbastanza per una sintesi utile."

    final, use_html = _compose_final_with_source(summary, data)
    return final, use_html

async def call_web_read(url: str, http: aiohttp.ClientSession, chat_id: int) -> str:
    """
    Lettura URL con /web/summarize (modalità URL).
    """
    payload = {"source": "tg", "source_id": str(chat_id), "url": url, "return_sources": True}
    try:
        async with http.post(QUANTUM_WEB_SUMMARY_URL, json=payload) as r:
            if r.status == 200:
                data = await r.json()
            else:
                # fallback direct
                data2 = await call_generate(url, http, chat_id, force_direct=True)
                return extract_openai_like_text(data2) or f"❌ Errore lettura {r.status}"
    except Exception as e:
        data2 = await call_generate(url, http, chat_id, force_direct=True)
        return extract_openai_like_text(data2) or f"❌ Errore: {e}"

    summary = (data.get("summary") or data.get("answer") or "Contenuto letto.").strip()
    payload_for_src = data if ("sources" in data or "results" in data) else {"results":[{"url": url, "title": data.get("title", url)}]}
    final, _ = _compose_final_with_source(summary, payload_for_src)
    return final

# === Feedback (opzionale, NON addestra l'LLM) ===
async def send_feedback(http, query, used_intent, ok, elapsed_ms):
    if not FEEDBACK_ENABLED: return
    try:
        payload = {"query": query, "intent_used": used_intent, "satisfaction": 1.0 if ok else 0.0, "response_time_ms": int(elapsed_ms)}
        await http.post(f"{INTENT_ROUTER_URL}/feedback", json=payload)
    except Exception:
        pass

async def send_correction(http, query, correct_intent):
    if not FEEDBACK_ENABLED: return
    try:
        await http.post(f"{INTENT_ROUTER_URL}/correct", json={"query": query, "correct_intent": correct_intent})
    except Exception:
        pass

# === UI ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧠 *Quantum AI*\n"
        "• 🌐 Usa il web solo quando servono dati live\n"
        "• 🧠 Risponde diretto quando basta knowledge\n"
        "• 🧮 Calcoli locali\n",
        parse_mode="Markdown"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Comandi: /health, /web <q>, /read <url>, /persona, /persona_set, /persona_reset, /flushcache (admin)",
        parse_mode="Markdown"
    )

# === Handler principale ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return
    text = msg.text.strip()
    chat_id = update.effective_chat.id
    http = context.application.bot_data["http"]

    # Fast-path smalltalk → rispondi subito senza web (lasciamo decidere /generate ma forza direct se è proprio 1-2 parole)
    if is_smalltalk(text):
        data = await call_generate(text, http, chat_id, force_direct=True)
        reply_plain = extract_openai_like_text(data) or "Ciao! 👋"
        for part in split_text(reply_plain):
            await msg.reply_text(part, disable_web_page_preview=True)
        return

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
            await msg.reply_text(f"🧮 `{text}` = `{result}`", parse_mode="Markdown")
            await send_feedback(http, text, "CALCULATOR", True, 0)
            return

    # generate
    t0 = time.perf_counter()
    data = await call_generate(text, http, chat_id)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    reply_plain = extract_openai_like_text(data)

    # Se errore / overflow contesto → fallback web
    if (not reply_plain and not data.get("ok", True)) or _is_ctx_overflow(reply_plain, data):
        final, use_html = await call_web_summary_query(text, http, chat_id)
        for part in split_text(final):
            await msg.reply_text(part, parse_mode=ParseMode.HTML if use_html else None,
                                 disable_web_page_preview=not SOURCE_PREVIEW if use_html else True)
        await send_feedback(http, text, "WEB_SEARCH", True, elapsed_ms)
        return

    # testo ok → aggiungi eventuale fonte inline (se presente nel payload)
    final, use_html = _compose_final_with_source(reply_plain or "Ok.", data)
    for part in split_text(final):
        await msg.reply_text(part, parse_mode=ParseMode.HTML if use_html else None,
                             disable_web_page_preview=not SOURCE_PREVIEW if use_html else True)

    # meta + feedback (opzionali)
    used_intent = (data.get("intent") or "DIRECT_LLM").upper()
    conf = data.get("confidence")
    cached = data.get("cached")

    if SHOW_META:
        meta = []
        if used_intent: meta.append(f"intent={used_intent}")
        if conf is not None:
            try: meta.append(f"conf={float(conf):.2f}")
            except: meta.append(f"conf={conf}")
        if cached: meta.append("cached")
        await msg.reply_text(f"⏱ {elapsed_ms}ms | " + (" ".join(meta) if meta else "ok"))

    if FEEDBACK_ENABLED:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("👍", callback_data="fb_good"),
             InlineKeyboardButton("👎", callback_data="fb_bad")],
            [InlineKeyboardButton("🌐 Serve web", callback_data="force_web"),
             InlineKeyboardButton("🧠 Non serve web", callback_data="force_direct")]
        ])
        fb_msg = await msg.reply_text("Feedback?", reply_markup=kb)
        context.application.bot_data["fb_map"][fb_msg.message_id] = {"query": text, "intent": used_intent, "elapsed_ms": elapsed_ms}

    await send_feedback(http, text, used_intent, True, elapsed_ms)

# === Callback feedback (solo se abilitato) ===
async def feedback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not FEEDBACK_ENABLED:
        return
    q = update.callback_query
    await q.answer()
    http = context.application.bot_data["http"]
    meta = context.application.bot_data.get("fb_map", {}).get(q.message.message_id, {"query":"", "intent":"DIRECT_LLM", "elapsed_ms":0})
    if q.data == "fb_good":
        await send_feedback(http, meta["query"], meta["intent"], True, meta["elapsed_ms"])
        await q.edit_message_text("👍 Grazie!")
    elif q.data == "fb_bad":
        await send_feedback(http, meta["query"], meta["intent"], False, meta["elapsed_ms"])
        await q.edit_message_text("👎 Ricevuto.")
    elif q.data == "force_web":
        await send_correction(http, meta["query"], "WEB_SEARCH")
        await q.edit_message_text("🌐 Ok, userò il web la prossima volta")
    elif q.data == "force_direct":
        await send_correction(http, meta["query"], "DIRECT_LLM")
        await q.edit_message_text("🧠 Ok, risponderò direttamente")

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
    # Usa /web/summarize in modalità QUERY
    text = update.message.text
    query = text.split(maxsplit=1)[1] if len(text.split()) > 1 else ""
    if not query:
        await update.message.reply_text("Uso: /web <query>")
        return
    http = context.application.bot_data["http"]
    await update.message.reply_text(f"🌐 Cerco: {query}")
    final, use_html = await call_web_summary_query(query, http, update.effective_chat.id)
    for part in split_text(final):
        await update.message.reply_text(part, parse_mode=ParseMode.HTML if use_html else None,
                                        disable_web_page_preview=not SOURCE_PREVIEW if use_html else True)

async def read_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Usa /web/summarize in modalità URL
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
        use_html = bool(re.search(r'<a href="https?://', final))
        await update.message.reply_text(part, parse_mode=ParseMode.HTML if use_html else None,
                                        disable_web_page_preview=not SOURCE_PREVIEW if use_html else True)

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

    if FEEDBACK_ENABLED:
        app.add_handler(CallbackQueryHandler(feedback_callback))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    log.info("🤖 Avvio Telegram Bot (smart routing via /generate) | polling")
    app.run_polling(drop_pending_updates=True, poll_interval=1.0)
