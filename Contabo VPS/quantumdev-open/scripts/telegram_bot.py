#!/usr/bin/env python3
# scripts/telegram_bot.py — Smart Intent + Autoweb + CHUNKING + STREAMING FIXED
# Version: 4.4 - Fix payload streaming endpoint
# - Chunking automatico per messaggi >4096 caratteri
# - Streaming progressivo con multi-message support
# - Smart Intent + Semantic Analysis + Fallback LLM
# - FIX: Payload corretto per /chat/stream endpoint

from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
import logging
import os
import sys
import fcntl
import re
import asyncio
import json
import time
from typing import List, Optional
from dotenv import load_dotenv
import aiohttp
from urllib.parse import urlparse

# Path progetto
sys.path.insert(0, "/root/quantumdev-open")

# Import chunking utility
from core.telegram_chunking import split_message

# Calculator (opzionale)
try:
    try:
        from core.calculator import safe_eval, is_calculator_query
    except Exception:
        from Core.calculator import safe_eval, is_calculator_query  # type: ignore
except Exception:
    safe_eval = None

    def is_calculator_query(_):
        return False

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

# Backend URLs
QUANTUM_CHAT_URL = os.getenv("QUANTUM_CHAT_URL", "http://127.0.0.1:8081/chat").strip()
QUANTUM_UNIFIED_URL = os.getenv("QUANTUM_UNIFIED_URL", "http://127.0.0.1:8081/unified").strip()
BACKEND_CHAT_URL = QUANTUM_UNIFIED_URL or QUANTUM_CHAT_URL

# Tools and system endpoints
QUANTUM_SYSTEM_STATUS_URL = os.getenv("QUANTUM_SYSTEM_STATUS_URL", "http://127.0.0.1:8081/system/status").strip()
QUANTUM_AUTOBUG_URL = os.getenv("QUANTUM_AUTOBUG_URL", "http://127.0.0.1:8081/autobug/run").strip()
QUANTUM_GPU_URL = os.getenv("QUANTUM_GPU_URL", "http://127.0.0.1:8081/system/gpu").strip()
QUANTUM_GPU_ALERTS_URL = os.getenv("QUANTUM_GPU_ALERTS_URL", "http://127.0.0.1:8081/system/gpu/alerts").strip()
QUANTUM_MATH_URL = os.getenv("QUANTUM_MATH_URL", "http://127.0.0.1:8081/tools/math").strip()
QUANTUM_PYTHON_URL = os.getenv("QUANTUM_PYTHON_URL", "http://127.0.0.1:8081/tools/python").strip()

# Web search endpoints
QUANTUM_WEB_SEARCH_URL = os.getenv("QUANTUM_WEB_SEARCH_URL", "http://127.0.0.1:8081/web/search").strip()
QUANTUM_WEB_SUMMARY_URL = os.getenv("QUANTUM_WEB_SUMMARY_URL", "http://127.0.0.1:8081/web/summarize").strip()
QUANTUM_WEB_RESEARCH_URL = os.getenv("QUANTUM_WEB_RESEARCH_URL", "http://127.0.0.1:8081/web/research").strip()
QUANTUM_HEALTH_URL = os.getenv("QUANTUM_HEALTH_URL", "http://127.0.0.1:8081/healthz").strip()

# Persona endpoints
QUANTUM_PERSONA_SET_URL = os.getenv("QUANTUM_PERSONA_SET_URL", "http://127.0.0.1:8081/persona/set").strip()
QUANTUM_PERSONA_GET_URL = os.getenv("QUANTUM_PERSONA_GET_URL", "http://127.0.0.1:8081/persona/get").strip()
QUANTUM_PERSONA_RESET_URL = os.getenv("QUANTUM_PERSONA_RESET_URL", "http://127.0.0.1:8081/persona/reset").strip()

# Streaming endpoint
QUANTUM_CHAT_STREAM_URL = os.getenv("QUANTUM_CHAT_STREAM_URL", "http://127.0.0.1:8081/chat/stream").strip()

# Streaming configuration
TELEGRAM_STREAMING_ENABLED = os.getenv("TELEGRAM_STREAMING_ENABLED", "0").strip() in ("1", "true", "True", "yes")

# UI flags
SOURCE_PREVIEW = os.getenv("TELEGRAM_SOURCE_PREVIEW", "0").strip() != "0"
SHOW_SOURCES = os.getenv("TELEGRAM_SHOW_SOURCES", "1").strip() != "0"
SHOW_CACHE_BADGE = os.getenv("TELEGRAM_SHOW_CACHE_BADGE", "1").strip() != "0"

# === LOGGING ===
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

# === SmartIntentClassifier per autoweb automatico ===
try:
    from core.smart_intent_classifier import SmartIntentClassifier
    _smart_intent = SmartIntentClassifier()
    log.info("✅ SmartIntentClassifier loaded for autoweb")
except Exception as e:
    _smart_intent = None
    log.warning(f"⚠️ SmartIntentClassifier not available: {e}")

# === Streaming handler (if enabled) ===
_streaming_handler = None
if TELEGRAM_STREAMING_ENABLED:
    try:
        from agents.telegram_streaming_handler import TelegramStreamingHandler
        log.info("✅ Streaming handler loaded (will initialize on startup)")
    except Exception as e:
        log.error(f"❌ Failed to load streaming handler: {e}")
        TELEGRAM_STREAMING_ENABLED = False

# === Per-user streaming preferences ===
_user_streaming_prefs: dict[int, bool] = {}

# === Constants ===
TG_MAX = 4096
MIN_AUTOWEB_SUMMARY_LENGTH = 50


def split_text(s: str, size: int = TG_MAX) -> list[str]:
    """Legacy function - use split_message instead for intelligent chunking"""
    return [s[i:i + size] for i in range(0, len(s), size)] if s else []


# ============================================================
# STREAMING MESSAGE MANAGER CON CHUNKING AUTOMATICO
# ============================================================

class StreamingMessageManager:
    """Gestisce streaming con chunking automatico per messaggi lunghi"""
    
    def __init__(self, min_update_interval: float = 2.0):
        self.primary_message = None
        self.additional_messages: List = []
        self.current_text = ""
        self.last_update_time = 0
        self.min_update_interval = min_update_interval
    
    async def initialize(self, update, context, initial_text: str = "🤔 Sto pensando..."):
        """Inizializza messaggio primario"""
        self.primary_message = await update.message.reply_text(initial_text)
        self.current_text = ""
        return self.primary_message
    
    async def update(self, new_text: str, force: bool = False) -> bool:
        """Aggiorna con chunking automatico"""
        current_time = time.time()
        if not force and (current_time - self.last_update_time) < self.min_update_interval:
            return False
        
        if len(new_text) - len(self.current_text) < 50 and not force:
            return False
        
        self.current_text = new_text
        self.last_update_time = current_time
        
        # Dividi in chunk intelligenti
        chunks = split_message(new_text, add_markers=True)
        
        try:
            # Primo chunk
            await self.primary_message.edit_text(chunks[0])
            
            # Chunk aggiuntivi
            await self._manage_additional_chunks(chunks[1:])
            
            return True
        except Exception as e:
            log.warning(f"⚠️ Update error: {e}")
            return False
    
    async def _manage_additional_chunks(self, chunks: List[str]):
        """Gestisce chunk 2+"""
        needed = len(chunks)
        current = len(self.additional_messages)
        
        # Crea nuovi se necessario
        if needed > current:
            for i in range(current, needed):
                try:
                    msg = await self.primary_message.reply_text(chunks[i])
                    self.additional_messages.append(msg)
                except Exception as e:
                    log.warning(f"⚠️ Create chunk error: {e}")
        
        # Rimuovi extra
        elif needed < current:
            for msg in self.additional_messages[needed:]:
                try:
                    await msg.delete()
                except:
                    pass
            self.additional_messages = self.additional_messages[:needed]
        
        # Aggiorna esistenti
        for i, chunk in enumerate(chunks):
            if i < len(self.additional_messages):
                try:
                    await self.additional_messages[i].edit_text(chunk)
                except:
                    pass
    
    async def finalize(self, final_text: str):
        """Finalizza"""
        await self.update(final_text, force=True)
    
    def reset(self):
        """Reset"""
        self.primary_message = None
        self.additional_messages = []
        self.current_text = ""


def should_auto_search_semantic(text: str) -> tuple[bool, str]:
    """Analisi semantica per decidere se fare autoweb"""
    text_lower = text.lower().strip()
    
    temporal_indicators = [
        'oggi', 'ieri', 'recente', 'recentemente', 'ultimo', 'ultima',
        'nuovo', 'nuova', 'attuale', 'attuali', 'corrente',
        'questo mese', 'questa settimana', 'quest\'anno',
        'aggiornamento', 'aggiornamenti', 'novità'
    ]
    has_temporal = any(ind in text_lower for ind in temporal_indicators)
    
    search_verbs = [
        'cos\'è successo', 'cosa succede', 'cosa è cambiato',
        'scoperta', 'scoperte', 'annunciato', 'rivelato',
        'lanciato', 'rilasciato', 'pubblicato', 'ha annunciato'
    ]
    has_search_verb = any(verb in text_lower for verb in search_verbs)
    
    tech_products = [
        'iphone', 'ipad', 'macbook', 'airpods',
        'samsung galaxy', 'pixel', 'android',
        'windows', 'macos', 'ios',
        'chatgpt', 'claude', 'gemini', 'copilot',
        'tesla', 'model', 'cybertruck'
    ]
    has_tech_product = any(prod in text_lower for prod in tech_products)
    
    companies = [
        'openai', 'anthropic', 'google', 'microsoft', 'apple',
        'meta', 'facebook', 'amazon', 'nvidia', 'tesla',
        'spacex', 'twitter', 'x.com'
    ]
    has_company = any(comp in text_lower for comp in companies)
    
    events = [
        'guerra', 'conflitto', 'crisi', 'elezioni', 'voto',
        'mercato', 'borsa', 'inflazione', 'tassi',
        'fed', 'bce', 'governo', 'parlamento', 'situazione'
    ]
    has_event = any(ev in text_lower for ev in events)
    
    factual_patterns = [
        'quanto costa', 'quanto vale', 'quanti',
        'qual è il', 'quale è', 'chi è il', 'chi ha',
        'dove si trova', 'dove è', 'quando è',
        'come funziona il nuovo', 'cosa fa',
        'è vero che', 'è successo che'
    ]
    has_factual = any(pat in text_lower for pat in factual_patterns)
    
    if has_temporal and (has_search_verb or has_factual):
        return True, "temporal_event_query"
    if has_tech_product and has_temporal:
        return True, "tech_product_update"
    if has_company and (has_temporal or has_factual or has_search_verb):
        return True, "company_info_query"
    if has_event and has_temporal:
        return True, "geopolitical_or_financial_event"
    if has_event and any(kw in text_lower for kw in ['guerra', 'conflitto', 'elezioni', 'mercato', 'borsa', 'inflazione']):
        return True, "geopolitical_or_financial_event"
    if has_factual and len(text_lower.split()) >= 4:
        return True, "complex_factual_query"
    
    return False, "no_search_needed"


def first_url(s: str | None) -> str | None:
    if not s:
        return None
    m = re.search(r"(https?://\S+)", s)
    return m.group(1) if m else None


def _domain(u: str) -> str:
    try:
        return urlparse(u).netloc or u
    except Exception:
        return u


async def typing(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    try:
        await context.bot.send_chat_action(chat_id, "typing")
    except Exception:
        pass


LIVE_WEATHER_KWS = ["meteo", "che tempo", "weather", "temperatura", "pioggia", "neve"]
LIVE_PRICE_KWS = ["prezzo", "quotazione", "quanto vale", "valore", "tasso di cambio", "cambio", "btc", "bitcoin", "eth", "ethereum", "eurusd", "azioni", "borsa", "indice", "stock"]
LIVE_RESULTS_KWS = ["risultato", "risultati", "score", "chi ha vinto", "chi ha segnato", "classifica", "standing", "table"]
LIVE_SCHEDULE_KWS = ["orari", "a che ora", "quando gioca", "quando inizia", "what time"]
LIVE_NEWS_KWS = ["ultime notizie", "breaking news", "oggi cosa è successo", "oggi cosa succede"]


def _detect_live_type(q: str) -> str | None:
    s = (q or "").lower().strip()
    if not s:
        return None

    def any_in(kws: list[str]) -> bool:
        return any(k in s for k in kws)

    if any_in(LIVE_WEATHER_KWS):
        return "weather"
    if any_in(LIVE_PRICE_KWS):
        return "price"
    if any_in(LIVE_RESULTS_KWS):
        return "results"
    if any_in(LIVE_SCHEDULE_KWS):
        return "schedule"
    if any_in(LIVE_NEWS_KWS):
        return "news"
    return None


async def on_startup(app):
    app.bot_data["http"] = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180))
    
    global _streaming_handler
    if TELEGRAM_STREAMING_ENABLED:
        try:
            from agents.telegram_streaming_handler import TelegramStreamingHandler
            _streaming_handler = TelegramStreamingHandler(app.bot)
            log.info("✅ Streaming handler initialized")
        except Exception as e:
            log.error(f"❌ Failed to initialize streaming handler: {e}")
    
    streaming_status = "ENABLED" if TELEGRAM_STREAMING_ENABLED else "DISABLED"
    log.info(
        "🌐 HTTP session ready\n"
        "  Chat endpoint: %s\n"
        "  Streaming: %s\n"
        "  Chunking: ENABLED (intelligent message splitting)",
        BACKEND_CHAT_URL,
        streaming_status
    )


async def on_shutdown(app):
    sess = app.bot_data.get("http")
    if sess and not sess.closed:
        await sess.close()
    log.info("👋 HTTP session chiusa")


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


async def _post_json_retry(http: aiohttp.ClientSession, url: str, payload: dict) -> tuple[int, dict | None, str | None]:
    status, data, txt = await _post_json(http, url, payload)
    if status in (502, 504, 598, 599):
        log.warning("⚠️ Retry %s per %s", status, url)
        status, data, txt = await _post_json(http, url, payload)
    return status, data, txt


def is_streaming_enabled_for_user(chat_id: int) -> bool:
    if not TELEGRAM_STREAMING_ENABLED:
        return False
    return _user_streaming_prefs.get(chat_id, True)


def set_user_streaming_preference(chat_id: int, enabled: bool):
    _user_streaming_prefs[chat_id] = enabled
    log.info(f"User {chat_id} streaming preference: {enabled}")


async def call_chat_streaming(text: str, chat_id: int, context: ContextTypes.DEFAULT_TYPE, initial_message = None) -> tuple[str, bool]:
    if not _streaming_handler:
        return "", False
    
    payload = {"text": text, "source": "tg", "source_id": str(chat_id)}
    
    try:
        response_text, success = await _streaming_handler.stream_response(
            chat_id=chat_id,
            url=QUANTUM_CHAT_STREAM_URL,
            payload=payload,
            initial_message=initial_message,
            on_error=lambda err: log.error(f"Streaming error: {err}")
        )
        return response_text, success
    except Exception as e:
        log.error(f"Streaming failed: {e}")
        return "", False


async def call_chat(text: str, http: aiohttp.ClientSession, chat_id: int) -> dict:
    try:
        payload = {"q": text, "source": "tg", "source_id": str(chat_id)}
        status, data, txt = await _post_json_retry(http, QUANTUM_UNIFIED_URL, payload)
        if status == 200 and isinstance(data, dict):
            return data
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        log.warning(f"Unified endpoint failed, falling back to /chat: {e}")
    
    payload = {"source": "tg", "source_id": str(chat_id), "text": text}
    status, data, txt = await _post_json_retry(http, QUANTUM_CHAT_URL, payload)
    if status == 200 and isinstance(data, dict):
        return data
    return {"ok": False, "error": f"/chat {status}: {txt or ''}"}


async def call_backend_json(http: aiohttp.ClientSession, url: str, payload: dict | None = None, method: str = "POST", timeout: float = 30.0) -> dict:
    try:
        if method.upper() == "GET":
            async with http.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                status = r.status
                if status == 200:
                    data = await r.json()
                    return data if isinstance(data, dict) else {"ok": False, "error": "invalid_response"}
                else:
                    txt = await r.text()
                    return {"ok": False, "error": f"http_{status}", "detail": txt}
        else:
            async with http.post(url, json=payload or {}, timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                status = r.status
                if status == 200:
                    data = await r.json()
                    return data if isinstance(data, dict) else {"ok": False, "error": "invalid_response"}
                else:
                    txt = await r.text()
                    return {"ok": False, "error": f"http_{status}", "detail": txt}
    except asyncio.TimeoutError:
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _format_sources_block(data: dict, max_sources: int = 3) -> str:
    if not SHOW_SOURCES:
        return ""

    sources = data.get("used_sources") or data.get("sources") or data.get("results") or []
    if not isinstance(sources, list) or not sources:
        return ""

    lines: list[str] = []
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


async def call_web_summary_query(query: str, http: aiohttp.ClientSession, chat_id: int) -> str:
    payload = {"q": query, "k": 6, "summarize_top": 2, "source": "tg", "source_id": str(chat_id)}
    status, data, _ = await _post_json_retry(http, QUANTUM_WEB_SUMMARY_URL, payload)
    if status != 200 or not isinstance(data, dict):
        return "Non riesco a sintetizzare ora."
    note = (data.get("note") or "").lower()

    if note == "non_web_query":
        return "Richiesta breve/smalltalk: non serve il web. Scrivimi direttamente senza /web 🙂"
    if note in {"no_results", "empty_serp"}:
        tips = "Suggerimenti: prova ad aggiungere `site:dominio` o dettagli temporali (es. anno/oggi)."
        return f"Nessun risultato affidabile trovato.\n{tips}"

    summary = (data.get("summary") or "").strip()
    if not summary:
        results = data.get("results") or []
        if results:
            bullets = "\n".join(f"- {it.get('title', '').strip() or it.get('url', '')}" for it in results[:4])
            return f"Sintesi rapida:\n{bullets}" + _format_sources_block(data) + _cache_badge(data)
        return "Nessun risultato utile."

    return summary + _format_sources_block(data) + _cache_badge(data)


_BAD_PATTERNS = ["le fonti fornite non contengono", "consulta le fonti specifiche", "aprire una fonte attendibile"]


def _looks_bad_summary(text: str) -> bool:
    s = text.lower()
    if len(s) < 40:
        return True
    return any(p in s for p in _BAD_PATTERNS)


async def call_web_research(query: str, http: aiohttp.ClientSession, chat_id: int) -> str:
    payload = {"q": query, "source": "tg", "source_id": str(chat_id)}
    status, data, _ = await _post_json_retry(http, QUANTUM_WEB_RESEARCH_URL, payload)

    if status == 200 and isinstance(data, dict):
        answer = (data.get("answer") or "").strip()
        if answer and not _looks_bad_summary(answer):
            return answer + _format_sources_block(data)

    return await call_web_summary_query(query, http, chat_id)


async def call_web_read(url: str, http: aiohttp.ClientSession, chat_id: int) -> str:
    payload = {"source": "tg", "source_id": str(chat_id), "url": url, "return_sources": True}
    status, data, _ = await _post_json_retry(http, QUANTUM_WEB_SUMMARY_URL, payload)
    if status != 200 or not isinstance(data, dict):
        return f"❌ Errore lettura ({status})"
    summary = (data.get("summary") or data.get("answer") or "Nessun contenuto estratto").strip()
    return summary + _format_sources_block(data) + _cache_badge(data)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    autoweb_status = "🤖 Autoweb INTELLIGENTE ATTIVO (3 livelli)" if _smart_intent else "⚠️ Autoweb NON DISPONIBILE"
    
    streaming_info = ""
    if TELEGRAM_STREAMING_ENABLED:
        chat_id = update.effective_chat.id
        user_streaming = is_streaming_enabled_for_user(chat_id)
        streaming_emoji = "⚡" if user_streaming else "📝"
        streaming_status = "ATTIVO" if user_streaming else "DISATTIVO"
        streaming_info = f"\n• {streaming_emoji} Streaming: {streaming_status} (usa /streaming per cambiare)"
    
    await update.message.reply_text(
        "🧠 Jarvis – AI personale di Matteo (QuantumDev)\n"
        "\n"
        f"{autoweb_status}\n"
        f"{streaming_info}\n"
        "• 📝 Chunking intelligente: messaggi lunghi divisi automaticamente\n"
        "\n"
        "• 💬 Chatta normalmente per usare Jarvis su qualsiasi tema\n"
        "• 🌐 Autoweb intelligente con 3 livelli:\n"
        "  → Pattern Match: meteo, prezzi, sport, news\n"
        "  → Semantic Analysis: eventi attuali, tech, aziende, geopolitica\n"
        "  → Fallback intelligente: sempre una risposta informata\n"
        "• 🔗 Invia un URL per ottenere automaticamente un riassunto\n"
        "• 🧮 Calcolatrice locale per espressioni matematiche\n"
        "\n"
        "Esempi autoweb:\n"
        "• 'Meteo Roma?' → Ricerca web automatica\n"
        "• 'Cos'è successo oggi?' → Info aggiornate\n"
        "• 'Nuovo iPhone?' → Notizie recenti\n"
        "• 'https://example.com' → Riassunto automatico"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    streaming_line = ""
    if TELEGRAM_STREAMING_ENABLED:
        streaming_line = "• /streaming [on|off] – attiva/disattiva risposte progressive\n"
    
    await update.message.reply_text(
        "Comandi disponibili:\n"
        "• /start – riepilogo funzioni\n"
        "• /help – questo messaggio\n"
        "• /health – stato backend\n"
        "• /status – stato sistema (CPU, RAM, disk, GPU)\n"
        "• /autobug – diagnostica completa\n"
        "• /gpu – stato GPU (VRAM, utilizzo, temperatura)\n"
        "• /gpu_history – cronologia metriche GPU (60 min)\n"
        "• /gpu_alerts – alert GPU recenti (24 ore)\n"
        "• /math <expr> – calcolatrice\n"
        "• /py <code> – esegui Python (solo admin)\n"
        "• /web <query> – ricerca web\n"
        "• /read <url> – leggi e riassumi pagina\n"
        "• /persona – mostra persona attuale\n"
        "• /persona_set <testo> – imposta persona custom\n"
        "• /persona_reset – resetta persona\n"
        f"{streaming_line}"
        "• /flushcache – svuota Redis (solo admin)"
    )


# === Handler principale con Chunking + STREAMING FIXED ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler principale con smart autoweb + chunking + streaming.
    
    Flow:
    1. Calculator check
    2. SmartIntent (pattern matching) - LEVEL 1
    3. Semantic analysis - LEVEL 2
    4. Execute autoweb if needed (con chunking)
    5. Fallback to /chat - LEVEL 3 (con chunking e streaming)
    """
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
    
    # ========== LIVELLO 1: Pattern Matching ==========
    if _smart_intent:
        try:
            classification = _smart_intent.classify(text)
            intent = classification.get("intent")
            confidence = classification.get("confidence", 0)
            url = classification.get("url")
            
            log.info(f"Intent: {intent} (conf={confidence:.2f}, len={len(text)})")
            
            if intent == "WEB_SEARCH" and confidence >= 0.75:
                log.info("Autoweb: web search (pattern match)...")
                try:
                    web_result = await call_backend_json(
                        http, QUANTUM_WEB_SEARCH_URL,
                        payload={"q": text, "source": "tg", "source_id": str(chat_id), "k": 6, "summarize_top": 3},
                        timeout=30.0
                    )
                    
                    if web_result and not web_result.get("ok") is False:
                        summary = web_result.get("summary", "").strip()
                        if summary:
                            sources_block = _format_sources_block(web_result)
                            full_reply = summary + (f"\n\n{sources_block}" if sources_block else "")
                            
                            chunks = split_message(full_reply, add_markers=True)
                            for chunk in chunks:
                                await msg.reply_text(chunk, disable_web_page_preview=True)
                            return
                except Exception as e:
                    log.warning(f"Autoweb search failed: {e}")
            
            elif intent == "WEB_READ" and url:
                log.info(f"Autoweb: reading URL {url[:50]}...")
                try:
                    read_result = await call_backend_json(
                        http, QUANTUM_WEB_SUMMARY_URL,
                        payload={"url": url, "source": "tg", "source_id": str(chat_id)},
                        timeout=20.0
                    )
                    
                    if read_result and not read_result.get("ok") is False:
                        summary = read_result.get("summary", "").strip()
                        if summary:
                            chunks = split_message(summary, add_markers=True)
                            for chunk in chunks:
                                await msg.reply_text(chunk, disable_web_page_preview=True)
                            return
                except Exception as e:
                    log.warning(f"Autoweb URL read failed: {e}")
        
        except Exception as e:
            log.error(f"Intent classification error: {e}")
    
    # ========== LIVELLO 2: Semantic Analysis ==========
    should_search, reason = should_auto_search_semantic(text)
    
    if should_search:
        log.info(f"Autoweb: semantic trigger ({reason})...")
        try:
            web_result = await call_backend_json(
                http, QUANTUM_WEB_SEARCH_URL,
                payload={"q": text, "source": "tg", "source_id": str(chat_id), "k": 6, "summarize_top": 3},
                timeout=30.0
            )
            
            if web_result and not web_result.get("ok") is False:
                summary = web_result.get("summary", "").strip()
                if summary and len(summary) > MIN_AUTOWEB_SUMMARY_LENGTH:
                    sources_block = _format_sources_block(web_result)
                    full_reply = summary + (f"\n\n{sources_block}" if sources_block else "")
                    
                    chunks = split_message(full_reply, add_markers=True)
                    for chunk in chunks:
                        await msg.reply_text(chunk, disable_web_page_preview=True)
                    return
        except Exception as e:
            log.warning(f"Semantic autoweb failed: {e}")
    
    # ========== LIVELLO 3: Fallback a /chat CON STREAMING + CHUNKING ==========
    use_streaming = is_streaming_enabled_for_user(chat_id)
    
    if use_streaming:
        # Streaming con StreamingMessageManager (gestisce chunking automaticamente)
        manager = StreamingMessageManager(min_update_interval=2.0)
        await manager.initialize(update, context)
        
        accumulated_text = ""
        token_count = 0
        
        try:
            import httpx
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    'POST',
                    QUANTUM_CHAT_STREAM_URL,
                    # FIX: Payload corretto per /chat/stream endpoint
                    json={'text': text, 'source': 'tg', 'source_id': str(chat_id)}
                ) as response:
                    
                    async for line in response.aiter_lines():
                        if not line.strip() or not line.startswith('data: '):
                            continue
                        
                        data_str = line[6:]
                        if data_str == '[DONE]':
                            break
                        
                        try:
                            data = json.loads(data_str)
                            
                            if data.get('type') == 'token':
                                accumulated_text += data.get('text', '')
                                token_count += 1
                                
                                # Update ogni 100 token
                                if token_count % 100 == 0:
                                    await manager.update(accumulated_text)
                            
                            elif data.get('type') == 'done':
                                await manager.finalize(data.get('text', accumulated_text))
                                return
                        
                        except json.JSONDecodeError:
                            continue
            
            if accumulated_text:
                await manager.finalize(accumulated_text)
            return
            
        except Exception as e:
            log.error(f"Streaming error: {e}, fallback to non-streaming")
    
    # Non-streaming fallback CON CHUNKING
    data = await call_chat(text, http, chat_id)
    reply = (data.get("reply") or "").strip()
    
    if not reply:
        await msg.reply_text("Non riesco a rispondere ora. Prova con /web <query>.")
        return
    
    chunks = split_message(reply, add_markers=True)
    for chunk in chunks:
        await msg.reply_text(chunk, disable_web_page_preview=True)


# === Comandi (invariati, tutti con chunking) ===

async def health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    http = context.application.bot_data["http"]
    try:
        async with http.get(QUANTUM_HEALTH_URL) as r:
            txt = await r.text()
        chunks = split_message(txt, add_markers=False)
        for chunk in chunks:
            await update.message.reply_text(chunk)
    except Exception as e:
        await update.message.reply_text(f"❌ Health fallita: {e}")


async def web_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    query = text.split(maxsplit=1)[1] if len(text.split()) > 1 else ""
    if not query:
        await update.message.reply_text("Uso: /web <query>")
        return
    http = context.application.bot_data["http"]
    chat_id = update.effective_chat.id
    await typing(context, chat_id)

    live_type = _detect_live_type(query)
    if live_type:
        final = await call_web_summary_query(query, http, chat_id)
    else:
        final = await call_web_research(query, http, chat_id)

    chunks = split_message(final, add_markers=True)
    for chunk in chunks:
        await update.message.reply_text(chunk, disable_web_page_preview=not SOURCE_PREVIEW)


async def read_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    args = text.split(maxsplit=1)[1] if len(text.split()) > 1 else ""
    url = first_url(args)
    if not url:
        await update.message.reply_text("Uso: /read <url>")
        return
    http = context.application.bot_data["http"]
    await update.message.reply_text(f"📄 Leggo {url}...")
    final = await call_web_read(url, http, update.effective_chat.id)
    
    chunks = split_message(final, add_markers=True)
    for chunk in chunks:
        await update.message.reply_text(chunk, disable_web_page_preview=not SOURCE_PREVIEW)


async def flush_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not ADMIN_CHAT_ID or chat_id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ Non sei autorizzato.")
        return
    try:
        import redis as _r
        r = _r.Redis(host="localhost", port=6379, db=0)
        r.flushall()
        await update.message.reply_text("✅ Cache Redis svuotata.")
    except Exception as e:
        await update.message.reply_text(f"❌ Errore: {e}")


async def persona_get(update: Update, context: ContextTypes.DEFAULT_TYPE):
    http = context.application.bot_data["http"]
    payload = {"source": "tg", "source_id": str(update.effective_chat.id)}
    try:
        async with http.post(QUANTUM_PERSONA_GET_URL, json=payload) as r:
            if r.status != 200:
                return await update.message.reply_text(f"❌ persona/get {r.status}")
            data = await r.json()
        persona = data.get("persona") or "(vuota)"
        chunks = split_message(f"🧠 Persona attuale:\n{persona}", add_markers=False)
        for chunk in chunks:
            await update.message.reply_text(chunk)
    except Exception as e:
        await update.message.reply_text(f"❌ Errore persona/get: {e}")


async def persona_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    http = context.application.bot_data["http"]
    text = update.message.text or ""
    args = text.split(maxsplit=1)[1] if len(text.split()) > 1 else ""
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


async def streaming_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not TELEGRAM_STREAMING_ENABLED:
        await update.message.reply_text("⚠️ Il supporto streaming non è abilitato.")
        return
    
    chat_id = update.effective_chat.id
    text = update.message.text or ""
    args = text.split()[1:] if len(text.split()) > 1 else []
    
    if not args:
        current = is_streaming_enabled_for_user(chat_id)
        status_emoji = "✅" if current else "❌"
        status_text = "ATTIVO" if current else "DISATTIVO"
        await update.message.reply_text(
            f"{status_emoji} Streaming: {status_text}\n\n"
            "Usa:\n"
            "• /streaming on - attiva\n"
            "• /streaming off - disattiva\n\n"
            "Con streaming attivo, i messaggi lunghi si dividono automaticamente."
        )
        return
    
    action = args[0].lower()
    
    if action in ("on", "enable", "1", "true", "yes", "attiva"):
        set_user_streaming_preference(chat_id, True)
        await update.message.reply_text("✅ Streaming ATTIVATO con chunking automatico.")
    elif action in ("off", "disable", "0", "false", "no", "disattiva"):
        set_user_streaming_preference(chat_id, False)
        await update.message.reply_text("❌ Streaming DISATTIVATO (chunking comunque attivo).")
    else:
        await update.message.reply_text("⚠️ Usa: /streaming on|off")


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    http = context.application.bot_data["http"]
    await typing(context, update.effective_chat.id)
    
    try:
        data = await call_backend_json(http, QUANTUM_SYSTEM_STATUS_URL, method="GET", timeout=10.0)
        
        if not data.get("ok", False):
            await update.message.reply_text(f"❌ Errore: {data.get('error', 'unknown')}")
            return
        
        lines = ["📊 System Status:\n"]
        
        cpu = data.get("cpu", {})
        lines.append(f"• CPU: {cpu.get('percent', 0):.1f}% ({cpu.get('cores_logical', 0)} cores)")
        
        mem = data.get("memory", {})
        mem_gb = mem.get("used", 0) / (1024**3)
        mem_tot = mem.get("total", 0) / (1024**3)
        lines.append(f"• RAM: {mem_gb:.1f} / {mem_tot:.1f} GB ({mem.get('percent', 0):.1f}%)")
        
        disk = data.get("disk", {})
        disk_gb = disk.get("used", 0) / (1024**3)
        disk_tot = disk.get("total", 0) / (1024**3)
        lines.append(f"• Disk: {disk_gb:.1f} / {disk_tot:.1f} GB ({disk.get('percent', 0):.1f}%)")
        
        uptime = data.get("uptime", {}).get("seconds", 0)
        hours = uptime // 3600
        minutes = (uptime % 3600) // 60
        lines.append(f"• Uptime: {hours}h {minutes}m")
        
        await update.message.reply_text("\n".join(lines))
        
    except Exception as e:
        await update.message.reply_text(f"❌ Errore: {e}")


async def autobug_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    http = context.application.bot_data["http"]
    await typing(context, update.effective_chat.id)
    await update.message.reply_text("🩺 Running AutoBug...")
    
    try:
        data = await call_backend_json(http, QUANTUM_AUTOBUG_URL, payload={}, method="POST", timeout=60.0)
        
        if not data:
            await update.message.reply_text("❌ Nessuna risposta")
            return
        
        checks = data.get("checks", [])
        overall_ok = data.get("ok", False)
        summary = data.get("summary", {})
        
        status_emoji = "✅" if overall_ok else "⚠️"
        lines = [
            f"{status_emoji} AutoBug Report:",
            f"Passed: {summary.get('passed', 0)}/{summary.get('total', 0)}\n"
        ]
        
        for check in checks:
            name = check.get("name", "unknown")
            enabled = check.get("enabled", False)
            ok = check.get("ok", False)
            latency = check.get("latency_ms")
            
            if not enabled:
                lines.append(f"• {name}: DISABLED")
            elif ok:
                lat = f" ({latency:.0f}ms)" if latency else ""
                lines.append(f"• {name}: OK{lat}")
            else:
                err = check.get("error", "")
                lines.append(f"• {name}: FAIL {err}")
        
        message = "\n".join(lines)
        chunks = split_message(message, add_markers=False)
        for chunk in chunks:
            await update.message.reply_text(chunk)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Errore: {e}")


async def math_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    http = context.application.bot_data["http"]
    text = update.message.text or ""
    args = text.split(maxsplit=1)
    
    if len(args) < 2:
        await update.message.reply_text("Uso: /math <expr>")
        return
    
    expr = args[1].strip()
    await typing(context, update.effective_chat.id)
    
    try:
        data = await call_backend_json(http, QUANTUM_MATH_URL, payload={"expr": expr}, method="POST", timeout=5.0)
        
        if data.get("ok", False):
            result = data.get("result")
            await update.message.reply_text(f"🧮 Risultato: {result}")
        else:
            await update.message.reply_text(f"⚠️ Errore: {data.get('error', 'calc_failed')}")
    except Exception as e:
        await update.message.reply_text(f"❌ Errore: {e}")


async def py_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    http = context.application.bot_data["http"]
    chat_id = update.effective_chat.id
    
    if not ADMIN_CHAT_ID or chat_id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ Solo admin.")
        return
    
    text = update.message.text or ""
    args = text.split(maxsplit=1)
    
    if len(args) < 2:
        await update.message.reply_text("Uso: /py <code>")
        return
    
    code = args[1].strip()
    await typing(context, chat_id)
    await update.message.reply_text("🐍 Executing...")
    
    try:
        data = await call_backend_json(http, QUANTUM_PYTHON_URL, payload={"code": code, "timeout_s": 5.0}, method="POST", timeout=10.0)
        
        lines = []
        ok = data.get("ok", False)
        timeout = data.get("timeout", False)
        
        if timeout:
            lines.append("⏱️ Timeout")
        elif ok:
            lines.append("✅ Success")
        else:
            lines.append("❌ Failed")
        
        stdout = data.get("stdout", "")
        if stdout:
            lines.append(f"\n📤 Output:\n{stdout[:800]}")
        
        stderr = data.get("stderr", "")
        if stderr and not ok:
            lines.append(f"\n⚠️ Error:\n{stderr[:400]}")
        
        message = "\n".join(lines) if lines else "No output"
        chunks = split_message(message, add_markers=False)
        for chunk in chunks:
            await update.message.reply_text(chunk)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Errore: {e}")


async def gpu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    http = context.application.bot_data["http"]
    await typing(context, update.effective_chat.id)
    
    try:
        data = await call_backend_json(http, QUANTUM_GPU_URL, method="GET", timeout=10.0)
        
        current = data.get("current", {})
        gpus = current.get("gpus", [])
        
        lines = ["🖥️ GPU Status:\n"]
        
        if not gpus:
            lines.append("❌ No GPU detected")
        else:
            for gpu in gpus:
                idx = gpu.get("index", 0)
                name = gpu.get("name", "Unknown")
                vram_gb = gpu.get("memory_used", 0) / (1024**3)
                vram_tot = gpu.get("memory_total", 0) / (1024**3)
                vram_pct = gpu.get("memory_percent", 0)
                util = gpu.get("utilization_percent", 0)
                temp = gpu.get("temperature", 0)
                
                lines.append(f"\n🎮 GPU {idx}: {name}")
                lines.append(f"💾 VRAM: {vram_gb:.1f} / {vram_tot:.1f} GB ({vram_pct:.1f}%)")
                lines.append(f"⚡ Usage: {util:.1f}%")
                lines.append(f"🌡️ Temp: {temp:.1f}°C")
        
        await update.message.reply_text("\n".join(lines))
        
    except Exception as e:
        await update.message.reply_text(f"❌ Errore: {e}")


async def gpu_history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    http = context.application.bot_data["http"]
    await typing(context, update.effective_chat.id)
    
    try:
        data = await call_backend_json(http, f"{QUANTUM_GPU_URL}?history_minutes=60", method="GET", timeout=10.0)
        
        history = data.get("history", [])
        
        if not history:
            await update.message.reply_text("📊 No history available")
            return
        
        lines = [f"📊 GPU History ({len(history)} points):\n"]
        
        vram_vals = []
        temp_vals = []
        for entry in history:
            gpus = entry.get("metrics", {}).get("gpus", [])
            if gpus:
                vram_vals.append(gpus[0].get("memory_percent", 0))
                temp_vals.append(gpus[0].get("temperature", 0))
        
        if vram_vals:
            lines.append(f"💾 VRAM: {vram_vals[-1]:.1f}% (avg: {sum(vram_vals)/len(vram_vals):.1f}%, max: {max(vram_vals):.1f}%)")
        if temp_vals:
            lines.append(f"🌡️ Temp: {temp_vals[-1]:.1f}°C (avg: {sum(temp_vals)/len(temp_vals):.1f}°C, max: {max(temp_vals):.1f}°C)")
        
        await update.message.reply_text("\n".join(lines))
        
    except Exception as e:
        await update.message.reply_text(f"❌ Errore: {e}")


async def gpu_alerts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    http = context.application.bot_data["http"]
    await typing(context, update.effective_chat.id)
    
    try:
        data = await call_backend_json(http, f"{QUANTUM_GPU_ALERTS_URL}?hours=24", method="GET", timeout=10.0)
        
        active = data.get("active_alerts", [])
        history = data.get("history", [])
        
        lines = ["🚨 GPU Alerts (24h):\n"]
        
        if active:
            lines.append("\n⚠️ Active:")
            for alert in active[:5]:
                lines.append(f"• {alert.get('message', 'Unknown')}")
        
        if history:
            lines.append(f"\n📜 History ({len(history)}):")
            for alert in history[:5]:
                resolved = "✅" if alert.get("resolved") else "🔴"
                lines.append(f"{resolved} {alert.get('message', 'Unknown')[:60]}")
        
        if not active and not history:
            lines.append("✅ No alerts")
        
        await update.message.reply_text("\n".join(lines))
        
    except Exception as e:
        await update.message.reply_text(f"❌ Errore: {e}")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.exception("❌ Errore bot:", exc_info=context.error)


if __name__ == "__main__":
    if not BOT_TOKEN:
        raise SystemExit("❌ TELEGRAM_BOT_TOKEN non impostato")

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
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("autobug", autobug_cmd))
    app.add_handler(CommandHandler("gpu", gpu_cmd))
    app.add_handler(CommandHandler("gpu_history", gpu_history_cmd))
    app.add_handler(CommandHandler("gpu_alerts", gpu_alerts_cmd))
    app.add_handler(CommandHandler("math", math_cmd))
    app.add_handler(CommandHandler("py", py_cmd))
    app.add_handler(CommandHandler("flushcache", flush_cache))
    app.add_handler(CommandHandler("web", web_cmd))
    app.add_handler(CommandHandler("read", read_cmd))
    app.add_handler(CommandHandler("persona", persona_get))
    app.add_handler(CommandHandler("persona_set", persona_set))
    app.add_handler(CommandHandler("persona_reset", persona_reset))
    
    if TELEGRAM_STREAMING_ENABLED:
        app.add_handler(CommandHandler("streaming", streaming_cmd))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    log.info("🤖 Telegram Bot (Jarvis + Chunking + Streaming FIXED)")
    app.run_polling(drop_pending_updates=True, poll_interval=1.0)
