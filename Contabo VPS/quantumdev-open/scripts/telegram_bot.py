#!/usr/bin/env python3
# scripts/telegram_bot.py — Smart Intent + Autoweb automatico intelligente (PATCH 2025-12-11)
# - Sistema ibrido intelligente a 3 livelli per autoweb universale:
#   • LIVELLO 1: SmartIntentClassifier pattern matching (meteo, prezzi, sport, news)
#   • LIVELLO 2: Analisi semantica (eventi temporali, tech, aziende, geopolitica)
#   • LIVELLO 3: Fallback intelligente a /chat con fallback autoweb
# - Intent WEB_SEARCH → /web/search automatico
# - Intent WEB_READ → /web/summarize automatico con URL
# - Intent DIRECT_LLM → /chat normale
# - Semantic autoweb per query complesse: "Cos'è successo oggi?", "Nuovo iPhone?", etc.
# - /web e /read continuano a funzionare come comandi manuali (backward compatible)
# - Calculator locale (se disponibile)
# - Attribution pulita: fonti reali quando si usa il web + badge cache opzionale
# - Log puliti, lock single-instance
# - Ritento automatico 1 volta su timeout/502/504
# - PATCH 18/11: supporto QUANTUM_WEB_SEARCH_URL + fonti lette anche da "results"
# - PATCH 21/11: testi /start e /help allineati a Jarvis (AI personale incensurata)
# - PATCH 10/12: SmartIntentClassifier per autoweb automatico
# - PATCH 11/12: Semantic autoweb analysis per copertura universale query

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

# Backend URLs - prefer QUANTUM_UNIFIED_URL for chat
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
SOURCE_PREVIEW = os.getenv("TELEGRAM_SOURCE_PREVIEW", "0").strip() != "0"  # anteprime Telegram
SHOW_SOURCES = os.getenv("TELEGRAM_SHOW_SOURCES", "1").strip() != "0"      # mostra elenco fonti
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
_user_streaming_prefs: dict[int, bool] = {}  # chat_id -> streaming_enabled

# === Constants ===
TG_MAX = 4096
MIN_AUTOWEB_SUMMARY_LENGTH = 50  # Minimum characters for a valid autoweb summary


def split_text(s: str, size: int = TG_MAX) -> list[str]:
    return [s[i:i + size] for i in range(0, len(s), size)] if s else []


def should_auto_search_semantic(text: str) -> tuple[bool, str]:
    """
    Analisi semantica per decidere se fare autoweb.
    
    Questa funzione analizza il testo della query per identificare pattern semantici
    che indicano la necessità di cercare informazioni aggiornate sul web.
    
    Returns:
        (should_search, reason) - True se è necessaria la ricerca web, motivo della decisione
    """
    text_lower = text.lower().strip()
    
    # Pattern semantici che indicano necessità di web search
    
    # 1. Eventi temporali (oggi, recente, ultimo, nuovo)
    temporal_indicators = [
        'oggi', 'ieri', 'recente', 'recentemente', 'ultimo', 'ultima',
        'nuovo', 'nuova', 'attuale', 'attuali', 'corrente',
        'questo mese', 'questa settimana', 'quest\'anno',
        'aggiornamento', 'aggiornamenti', 'novità'
    ]
    has_temporal = any(ind in text_lower for ind in temporal_indicators)
    
    # 2. Verbi di ricerca/scoperta
    search_verbs = [
        'cos\'è successo', 'cosa succede', 'cosa è cambiato',
        'scoperta', 'scoperte', 'annunciato', 'rivelato',
        'lanciato', 'rilasciato', 'pubblicato', 'ha annunciato'
    ]
    has_search_verb = any(verb in text_lower for verb in search_verbs)
    
    # 3. Prodotti/tech (spesso hanno aggiornamenti)
    tech_products = [
        'iphone', 'ipad', 'macbook', 'airpods',
        'samsung galaxy', 'pixel', 'android',
        'windows', 'macos', 'ios',
        'chatgpt', 'claude', 'gemini', 'copilot',
        'tesla', 'model', 'cybertruck'
    ]
    has_tech_product = any(prod in text_lower for prod in tech_products)
    
    # 4. Aziende tech/finance (info spesso cambiano)
    companies = [
        'openai', 'anthropic', 'google', 'microsoft', 'apple',
        'meta', 'facebook', 'amazon', 'nvidia', 'tesla',
        'spacex', 'twitter', 'x.com'
    ]
    has_company = any(comp in text_lower for comp in companies)
    
    # 5. Eventi geopolitici/finanziari
    events = [
        'guerra', 'conflitto', 'crisi', 'elezioni', 'voto',
        'mercato', 'borsa', 'inflazione', 'tassi',
        'fed', 'bce', 'governo', 'parlamento', 'situazione'
    ]
    has_event = any(ev in text_lower for ev in events)
    
    # 6. Query interrogative su fatti verificabili
    factual_patterns = [
        'quanto costa', 'quanto vale', 'quanti',
        'qual è il', 'quale è', 'chi è il', 'chi ha',
        'dove si trova', 'dove è', 'quando è',
        'come funziona il nuovo', 'cosa fa',
        'è vero che', 'è successo che'
    ]
    has_factual = any(pat in text_lower for pat in factual_patterns)
    
    # Decisione con priorità
    
    # Alta priorità: eventi temporali + verbi di ricerca/scoperta
    if has_temporal and (has_search_verb or has_factual):
        return True, "temporal_event_query"
    
    # Alta priorità: prodotti tech + indicatori temporali
    if has_tech_product and has_temporal:
        return True, "tech_product_update"
    
    # Media priorità: company + (temporal o factual o search verb)
    if has_company and (has_temporal or has_factual or has_search_verb):
        return True, "company_info_query"
    
    # Media priorità: eventi geopolitici/finanziari + temporal
    if has_event and has_temporal:
        return True, "geopolitical_or_financial_event"
    
    # Media priorità: eventi geopolitici/finanziari standalone (sempre search)
    if has_event and any(kw in text_lower for kw in ['guerra', 'conflitto', 'elezioni', 'mercato', 'borsa', 'inflazione']):
        return True, "geopolitical_or_financial_event"
    
    # Bassa priorità: query fattuali complesse
    if has_factual and len(text_lower.split()) >= 4:
        # Query factual lunga probabilmente richiede info aggiornate
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

# === LIVE query detection (percorso veloce) ===

LIVE_WEATHER_KWS = [
    "meteo", "che tempo", "weather",
    "temperatura", "pioggia", "neve",
]

LIVE_PRICE_KWS = [
    "prezzo", "quotazione", "quanto vale",
    "valore", "tasso di cambio", "cambio",
    "btc", "bitcoin", "eth", "ethereum",
    "eurusd", "eur/usd", "usd/eur",
    "azioni", "borsa", "indice", "stock", "share", "price",
]

LIVE_RESULTS_KWS = [
    "risultato", "risultati", "score",
    "chi ha vinto", "chi ha segnato",
    "classifica", "standing", "table",
]

LIVE_SCHEDULE_KWS = [
    "orari", "a che ora", "quando gioca",
    "quando inizia", "what time",
]

LIVE_NEWS_KWS = [
    "ultime notizie", "breaking news",
    "oggi cosa è successo", "oggi cosa succede",
]


def _detect_live_type(q: str) -> str | None:
    """Riconosce query 'live' per usare il percorso veloce /web/summarize."""
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

# === HTTP lifecycle ===


async def on_startup(app):
    app.bot_data["http"] = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180))
    
    # Initialize streaming handler if enabled
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
        "  Streaming: %s (%s)\n"
        "  System status: %s\n"
        "  AutoBug: %s\n"
        "  Math: %s\n"
        "  Python exec: %s\n"
        "  Web search: %s\n"
        "  Web summarize: %s\n"
        "  Web research: %s",
        BACKEND_CHAT_URL,
        streaming_status,
        QUANTUM_CHAT_STREAM_URL if TELEGRAM_STREAMING_ENABLED else "N/A",
        QUANTUM_SYSTEM_STATUS_URL,
        QUANTUM_AUTOBUG_URL,
        QUANTUM_MATH_URL,
        QUANTUM_PYTHON_URL,
        QUANTUM_WEB_SEARCH_URL,
        QUANTUM_WEB_SUMMARY_URL,
        QUANTUM_WEB_RESEARCH_URL,
    )


async def on_shutdown(app):
    sess = app.bot_data.get("http")
    if sess and not sess.closed:
        await sess.close()
    log.info("👋 HTTP session chiusa")

# === Core calls ===


async def _post_json(
    http: aiohttp.ClientSession,
    url: str,
    payload: dict
) -> tuple[int, dict | None, str | None]:
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
        log.warning("⚠️ Retry %s per %s: %s", status, url, payload.get("q") or payload.get("url") or "")
        status, data, txt = await _post_json(http, url, payload)
    return status, data, txt


def is_streaming_enabled_for_user(chat_id: int) -> bool:
    """Check if streaming is enabled for a specific user."""
    # Global setting must be enabled
    if not TELEGRAM_STREAMING_ENABLED:
        return False
    
    # Check user preference (default to True if streaming is globally enabled)
    return _user_streaming_prefs.get(chat_id, True)


def set_user_streaming_preference(chat_id: int, enabled: bool):
    """Set streaming preference for a specific user."""
    _user_streaming_prefs[chat_id] = enabled
    log.info(f"User {chat_id} streaming preference: {enabled}")


async def call_chat_streaming(
    text: str,
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    initial_message = None
) -> tuple[str, bool]:
    """
    Call chat endpoint with streaming support.
    
    Returns:
        (response_text, success)
    """
    if not _streaming_handler:
        return "", False
    
    # Prepare payload (same as non-streaming)
    payload = {
        "text": text,
        "source": "tg",
        "source_id": str(chat_id)
    }
    
    # Use streaming handler
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
    # Try unified endpoint first (uses master orchestrator for smart routing)
    try:
        payload = {"q": text, "source": "tg", "source_id": str(chat_id)}
        status, data, txt = await _post_json_retry(http, QUANTUM_UNIFIED_URL, payload)
        if status == 200 and isinstance(data, dict):
            return data
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        log.warning(f"Unified endpoint failed, falling back to /chat: {e}")
    
    # Fallback to legacy /chat endpoint
    payload = {"source": "tg", "source_id": str(chat_id), "text": text}
    status, data, txt = await _post_json_retry(http, QUANTUM_CHAT_URL, payload)
    if status == 200 and isinstance(data, dict):
        return data
    return {"ok": False, "error": f"/chat {status}: {txt or ''}"}


async def call_backend_json(
    http: aiohttp.ClientSession,
    url: str,
    payload: dict | None = None,
    method: str = "POST",
    timeout: float = 30.0
) -> dict:
    """
    Generic helper for calling backend JSON endpoints.
    
    Args:
        http: HTTP session
        url: Backend endpoint URL
        payload: JSON payload (for POST requests)
        method: HTTP method (GET or POST)
        timeout: Request timeout in seconds
        
    Returns:
        Response dict or error dict with {"ok": False, "error": "..."}
    """
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
        else:  # POST
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


# === Formatting WEB results (attribution + cache badge) ===


def _format_sources_block(data: dict, max_sources: int = 3) -> str:
    """
    Mostra le fonti provenienti da:
    - used_sources / sources (es. /web/research)
    - results (es. /web/search, /web/summarize)
    """
    if not SHOW_SOURCES:
        return ""

    sources = (
        data.get("used_sources")
        or data.get("sources")
        or data.get("results")
        or []
    )
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

# === /web/summarize (RESTO come fallback e fast-path) ===


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
            bullets = "\n".join(
                f"- {it.get('title', '').strip() or it.get('url', '')}" for it in results[:4]
            )
            return (
                f"Sintesi rapida:\n{bullets}"
                + _format_sources_block(data)
                + _cache_badge(data)
            )
        return "Nessun risultato utile."

    # Summary + (fonti + cache badge opzionali)
    return summary + _format_sources_block(data) + _cache_badge(data)

# === /web/research — motore principale per query non-live =======================

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
        "\n"
        "• 💬 Chatta normalmente per usare Jarvis su qualsiasi tema (business, crypto, coding, vita reale…)\n"
        "• 🌐 Autoweb intelligente con 3 livelli:\n"
        "  → Pattern Match: meteo, prezzi, sport, news\n"
        "  → Semantic Analysis: eventi attuali, tech, aziende, geopolitica\n"
        "  → Fallback intelligente: sempre una risposta informata\n"
        "• 🔗 Invia un URL per ottenere automaticamente un riassunto della pagina\n"
        "• 🧮 Se scrivi un'espressione tipo 2+2*10 provo a calcolarla in locale\n"
        "• 🛠️ Comandi manuali: /web <query> per forzare ricerca web, /read <url> per leggere pagine\n"
        "\n"
        "Esempi autoweb intelligente:\n"
        "• 'Meteo Roma?' → Ricerca web automatica (pattern)\n"
        "• 'Cos'è successo oggi in Ucraina?' → Web search (semantic)\n"
        "• 'Nuovo iPhone 16?' → Info aggiornate (semantic)\n"
        "• 'Cosa ha annunciato OpenAI?' → Notizie recenti (semantic)\n"
        "• 'https://example.com' → Riassunto automatico\n"
        "• 'Ciao come stai?' → Chat normale con LLM"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    streaming_line = ""
    if TELEGRAM_STREAMING_ENABLED:
        streaming_line = "• /streaming [on|off] – attiva/disattiva risposte progressive\n"
    
    await update.message.reply_text(
        "Comandi disponibili:\n"
        "• /start – riepilogo funzioni di Jarvis (AI personale)\n"
        "• /help – questo messaggio\n"
        "• /health – stato del backend QuantumDev\n"
        "• /status – stato del sistema (CPU, RAM, disk, GPU, uptime)\n"
        "• /autobug – diagnostica completa di tutti i subsistemi\n"
        "• /gpu – stato GPU (VRAM, utilizzo, temperatura)\n"
        "• /gpu_history – cronologia metriche GPU (60 minuti)\n"
        "• /gpu_alerts – alert GPU recenti (24 ore)\n"
        "• /math <expr> – calcolatrice (es: /math 2*(3+5.5))\n"
        "• /py <code> – esegui codice Python (solo admin)\n"
        "• /web <query> – ricerca web (live + ricerca avanzata)\n"
        "• /read <url> – leggi e riassumi una singola pagina\n"
        "• /persona – mostra la persona attuale del bot per questa chat\n"
        "• /persona_set <testo> – imposta una persona custom per questa chat\n"
        "• /persona_reset – resetta la persona per questa chat\n"
        f"{streaming_line}"
        "• /flushcache – svuota Redis (solo admin)"
    )

# === Handler principale (Smart Intent + Autoweb automatico) ===


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle incoming messages with intelligent autoweb routing.
    
    Flow:
    1. Check calculator
    2. SmartIntentClassifier (pattern matching) - LEVEL 1
    3. Semantic analysis (NEW) - LEVEL 2
    4. Execute autoweb if needed
    5. Fallback to /chat - LEVEL 3
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
    
    # ========== LIVELLO 1: Pattern Matching (SmartIntent) ==========
    # Use cached instance of SmartIntentClassifier for efficiency
    if _smart_intent:
        try:
            classification = _smart_intent.classify(text)
            
            intent = classification.get("intent")
            confidence = classification.get("confidence", 0)
            live_type = classification.get("live_type")
            url = classification.get("url")
            
            # Log intent (metadata only, no user content)
            log.info(
                f"Intent: {intent} (confidence={confidence:.2f}, "
                f"live_type={live_type}, query_len={len(text)})"
            )
            
            # ===== AUTOWEB per WEB_SEARCH (pattern match) =====
            if intent == "WEB_SEARCH" and confidence >= 0.75:
                log.info("Autoweb: Triggering web search (pattern match)...")
                try:
                    web_result = await call_backend_json(
                        http,
                        QUANTUM_WEB_SEARCH_URL,
                        payload={
                            "q": text,
                            "source": "tg",
                            "source_id": str(chat_id),
                            "k": 6,
                            "summarize_top": 3
                        },
                        timeout=30.0
                    )
                    
                    if web_result and not web_result.get("ok") is False:
                        summary = web_result.get("summary", "").strip()
                        if summary:
                            # Success!
                            sources_block = _format_sources_block(web_result)
                            full_reply = summary
                            if sources_block:
                                full_reply += f"\n\n{sources_block}"
                            
                            for chunk in split_text(full_reply, 3500):
                                await msg.reply_text(chunk, disable_web_page_preview=True)
                            return
                except Exception as e:
                    log.warning(f"Autoweb search failed: {e}")
                    # Fallback to chat below
            
            # ===== AUTOWEB per WEB_READ (URL) =====
            elif intent == "WEB_READ" and url:
                log.info(f"Autoweb: Reading URL {url[:50]}...")
                try:
                    read_result = await call_backend_json(
                        http,
                        QUANTUM_WEB_SUMMARY_URL,
                        payload={
                            "url": url,
                            "source": "tg",
                            "source_id": str(chat_id)
                        },
                        timeout=20.0
                    )
                    
                    if read_result and not read_result.get("ok") is False:
                        summary = read_result.get("summary", "").strip()
                        if summary:
                            for chunk in split_text(summary, 3500):
                                await msg.reply_text(chunk, disable_web_page_preview=True)
                            return
                except Exception as e:
                    log.warning(f"Autoweb URL read failed: {e}")
                    # Fallback to chat below
        
        except Exception as e:
            log.error(f"Intent classification error: {e}")
    
    # ========== LIVELLO 2: Semantic Analysis (NEW) ==========
    should_search, reason = should_auto_search_semantic(text)
    
    if should_search:
        log.info(f"Autoweb: Semantic trigger ({reason})...")
        try:
            web_result = await call_backend_json(
                http,
                QUANTUM_WEB_SEARCH_URL,
                payload={
                    "q": text,
                    "source": "tg",
                    "source_id": str(chat_id),
                    "k": 6,
                    "summarize_top": 3
                },
                timeout=30.0
            )
            
            if web_result and not web_result.get("ok") is False:
                summary = web_result.get("summary", "").strip()
                if summary and len(summary) > MIN_AUTOWEB_SUMMARY_LENGTH:  # Check it's substantial
                    sources_block = _format_sources_block(web_result)
                    full_reply = summary
                    if sources_block:
                        full_reply += f"\n\n{sources_block}"
                    
                    for chunk in split_text(full_reply, 3500):
                        await msg.reply_text(chunk, disable_web_page_preview=True)
                    return
        except Exception as e:
            log.warning(f"Semantic autoweb failed: {e}")
            # Fallback to chat below
    
    # ========== LIVELLO 3: Fallback a /chat ==========
    # Check if streaming is enabled for this user
    use_streaming = is_streaming_enabled_for_user(chat_id)
    
    if use_streaming:
        # Try streaming first
        try:
            reply, success = await call_chat_streaming(text, chat_id, context)
            if success and reply:
                # Streaming succeeded - message already updated progressively
                return
            else:
                # Streaming failed, fall back to non-streaming
                log.warning("Streaming failed, falling back to non-streaming")
        except Exception as e:
            log.error(f"Streaming error: {e}, falling back to non-streaming")
    
    # Non-streaming fallback (or if streaming is disabled)
    data = await call_chat(text, http, chat_id)
    reply = (data.get("reply") or "").strip()
    
    if not reply:
        await msg.reply_text(
            "Non riesco a rispondere ora. "
            "Prova con /web <query> per cercare informazioni online."
        )
        return
    
    for chunk in split_text(reply, 3500):
        await msg.reply_text(chunk, disable_web_page_preview=True)

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
    text = update.message.text or ""
    query = text.split(maxsplit=1)[1] if len(text.split()) > 1 else ""
    if not query:
        await update.message.reply_text("Uso: /web <query>")
        return
    http = context.application.bot_data["http"]
    chat_id = update.effective_chat.id

    # Mostra solo indicatore typing, niente messaggi "Cerco..."
    await typing(context, chat_id)

    live_type = _detect_live_type(query)
    if live_type:
        # Percorso veloce per meteo/prezzi/risultati/news
        final = await call_web_summary_query(query, http, chat_id)
    else:
        # Ricerca avanzata per query complesse
        final = await call_web_research(query, http, chat_id)

    for part in split_text(final):
        await update.message.reply_text(part, disable_web_page_preview=not SOURCE_PREVIEW)


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
    for part in split_text(final):
        await update.message.reply_text(part, disable_web_page_preview=not SOURCE_PREVIEW)


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
    """
    /streaming command - Toggle streaming mode on/off for this user.
    
    Usage:
        /streaming - Show current status
        /streaming on - Enable streaming
        /streaming off - Disable streaming
    """
    if not TELEGRAM_STREAMING_ENABLED:
        await update.message.reply_text(
            "⚠️ Il supporto streaming non è abilitato su questo bot.\n"
            "L'amministratore deve impostare TELEGRAM_STREAMING_ENABLED=1 nel .env"
        )
        return
    
    chat_id = update.effective_chat.id
    text = update.message.text or ""
    args = text.split()[1:] if len(text.split()) > 1 else []
    
    if not args:
        # Show current status
        current = is_streaming_enabled_for_user(chat_id)
        status_emoji = "✅" if current else "❌"
        status_text = "ATTIVO" if current else "DISATTIVO"
        await update.message.reply_text(
            f"{status_emoji} Streaming: {status_text}\n\n"
            "Usa:\n"
            "• /streaming on - per attivare le risposte progressive\n"
            "• /streaming off - per disattivare\n\n"
            "Con lo streaming attivo, vedrai le risposte apparire parola per parola "
            "invece di aspettare la risposta completa."
        )
        return
    
    action = args[0].lower()
    
    if action in ("on", "enable", "1", "true", "yes", "attiva"):
        set_user_streaming_preference(chat_id, True)
        await update.message.reply_text(
            "✅ Streaming ATTIVATO\n\n"
            "Da ora vedrai le risposte apparire progressivamente, "
            "parola per parola, mentre vengono generate."
        )
    elif action in ("off", "disable", "0", "false", "no", "disattiva"):
        set_user_streaming_preference(chat_id, False)
        await update.message.reply_text(
            "❌ Streaming DISATTIVATO\n\n"
            "Da ora riceverai le risposte complete in un singolo messaggio."
        )
    else:
        await update.message.reply_text(
            "⚠️ Comando non valido.\n\n"
            "Usa:\n"
            "• /streaming on - per attivare\n"
            "• /streaming off - per disattivare\n"
            "• /streaming - per vedere lo stato attuale"
        )


# === NEW TELEGRAM COMMANDS ===

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /status command - Display system status information.
    Shows CPU, RAM, disk, GPU usage and uptime.
    """
    http = context.application.bot_data["http"]
    
    # Show typing indicator
    await typing(context, update.effective_chat.id)
    
    try:
        # Call /system/status endpoint
        data = await call_backend_json(http, QUANTUM_SYSTEM_STATUS_URL, method="GET", timeout=10.0)
        
        if not data.get("ok", False):
            error_msg = data.get("error", "unknown_error")
            await update.message.reply_text(f"❌ Errore nel recupero dello stato del sistema: {error_msg}")
            return
        
        # Build human-readable status message
        lines = ["📊 System Status:\n"]
        
        # CPU
        cpu = data.get("cpu", {})
        cpu_percent = cpu.get("percent", 0.0)
        cores = cpu.get("cores_logical", 0)
        lines.append(f"• CPU: {cpu_percent:.1f}% ({cores} cores)")
        
        # Memory
        mem = data.get("memory", {})
        mem_used_gb = mem.get("used", 0) / (1024**3)
        mem_total_gb = mem.get("total", 0) / (1024**3)
        mem_percent = mem.get("percent", 0.0)
        lines.append(f"• RAM: {mem_used_gb:.1f} / {mem_total_gb:.1f} GB ({mem_percent:.1f}%)")
        
        # Disk
        disk = data.get("disk", {})
        disk_percent = disk.get("percent", 0.0)
        disk_used_gb = disk.get("used", 0) / (1024**3)
        disk_total_gb = disk.get("total", 0) / (1024**3)
        lines.append(f"• Disk: {disk_used_gb:.1f} / {disk_total_gb:.1f} GB ({disk_percent:.1f}%)")
        
        # GPU (if available)
        gpu = data.get("gpu", {})
        gpus = gpu.get("gpus", [])
        if gpus:
            for i, gpu_info in enumerate(gpus):
                gpu_name = gpu_info.get("name", "Unknown")
                gpu_mem_used = gpu_info.get("memory_used_mb", 0) / 1024
                gpu_mem_total = gpu_info.get("memory_total_mb", 0) / 1024
                gpu_util = gpu_info.get("utilization_percent", 0)
                lines.append(f"• GPU {i}: {gpu_name} ({gpu_util}%, {gpu_mem_used:.1f} / {gpu_mem_total:.1f} GB)")
        
        # Uptime
        uptime_data = data.get("uptime", {})
        uptime_seconds = uptime_data.get("seconds", 0)
        hours = uptime_seconds // 3600
        minutes = (uptime_seconds % 3600) // 60
        lines.append(f"• Uptime: {hours}h {minutes}m")
        
        message = "\n".join(lines)
        await update.message.reply_text(message)
        
    except Exception as e:
        log.error(f"/status command error: {e}")
        await update.message.reply_text(f"❌ Errore: {e}")


async def autobug_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /autobug command - Run health checks on all subsystems.
    Shows status of LLM, web search, Redis, ChromaDB, system, OCR.
    """
    http = context.application.bot_data["http"]
    
    # Show typing indicator
    await typing(context, update.effective_chat.id)
    
    # Send initial message
    await update.message.reply_text("🩺 Running AutoBug diagnostics...")
    
    try:
        # Call /autobug/run endpoint
        data = await call_backend_json(http, QUANTUM_AUTOBUG_URL, payload={}, method="POST", timeout=60.0)
        
        if not data:
            await update.message.reply_text("❌ Errore: nessuna risposta dal backend")
            return
        
        # Build human-readable report
        checks = data.get("checks", [])
        overall_ok = data.get("ok", False)
        summary = data.get("summary", {})
        duration_ms = data.get("duration_ms", 0)
        
        # Header
        status_emoji = "✅" if overall_ok else "⚠️"
        lines = [
            f"{status_emoji} AutoBug Report:",
            f"Duration: {duration_ms:.0f}ms",
            f"Passed: {summary.get('passed', 0)}/{summary.get('total', 0)}\n"
        ]
        
        # Individual checks
        for check in checks:
            name = check.get("name", "unknown")
            enabled = check.get("enabled", False)
            ok = check.get("ok", False)
            latency = check.get("latency_ms")
            error = check.get("error")
            
            if not enabled:
                lines.append(f"• {name}: DISABLED")
            elif ok:
                lat_str = f" ({latency:.0f}ms)" if latency else ""
                lines.append(f"• {name}: OK{lat_str}")
            else:
                err_str = f" ({error})" if error else ""
                lines.append(f"• {name}: FAIL{err_str}")
        
        message = "\n".join(lines)
        
        # Send report (split if too long)
        for chunk in split_text(message, 3000):
            await update.message.reply_text(chunk)
        
    except Exception as e:
        log.error(f"/autobug command error: {e}")
        await update.message.reply_text(f"❌ Errore: {e}")


async def math_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /math command - Evaluate mathematical expressions.
    Usage: /math 2*(3+5.5)
    """
    http = context.application.bot_data["http"]
    
    # Extract expression from command
    text = update.message.text or ""
    args = text.split(maxsplit=1)
    
    if len(args) < 2:
        await update.message.reply_text("Usage: /math <expression>\nExample: /math 2*(3+5.5)")
        return
    
    expr = args[1].strip()
    
    if not expr:
        await update.message.reply_text("⚠️ Provide a mathematical expression.\nExample: /math 2+2*10")
        return
    
    # Show typing indicator
    await typing(context, update.effective_chat.id)
    
    try:
        # Call /tools/math endpoint
        data = await call_backend_json(
            http,
            QUANTUM_MATH_URL,
            payload={"expr": expr},
            method="POST",
            timeout=5.0
        )
        
        if data.get("ok", False):
            result = data.get("result")
            result_type = data.get("type", "")
            type_label = f" ({result_type})" if result_type else ""
            await update.message.reply_text(f"🧮 Risultato{type_label}: {result}")
        else:
            error = data.get("error", "calculation_failed")
            await update.message.reply_text(f"⚠️ Errore calcolo: {error}")
        
    except Exception as e:
        log.error(f"/math command error: {e}")
        await update.message.reply_text(f"❌ Errore: {e}")


async def py_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /py command - Execute Python code (admin only).
    Usage: /py print("Hello, World!")
    
    This command is restricted to the admin user for security.
    """
    http = context.application.bot_data["http"]
    chat_id = update.effective_chat.id
    
    # Check if user is admin
    if not ADMIN_CHAT_ID or chat_id != ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ This command is restricted to the admin user.")
        return
    
    # Extract code from command
    text = update.message.text or ""
    args = text.split(maxsplit=1)
    
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: /py <code>\n"
            "Example: /py print('Hello!')\n"
            "Example: /py x = 2 + 2\\nprint(f'Result: {x}')"
        )
        return
    
    code = args[1].strip()
    
    if not code:
        await update.message.reply_text("⚠️ Provide Python code to execute.")
        return
    
    # Show typing indicator
    await typing(context, chat_id)
    
    # Send initial message
    await update.message.reply_text("🐍 Executing Python code...")
    
    try:
        # Call /tools/python endpoint
        data = await call_backend_json(
            http,
            QUANTUM_PYTHON_URL,
            payload={"code": code, "timeout_s": 5.0},
            method="POST",
            timeout=10.0
        )
        
        if not data:
            await update.message.reply_text("❌ No response from backend")
            return
        
        ok = data.get("ok", False)
        stdout = data.get("stdout", "")
        stderr = data.get("stderr", "")
        error = data.get("error", "")
        timeout = data.get("timeout", False)
        
        # Build response message
        lines = []
        
        if timeout:
            lines.append("⏱️ Execution timed out")
        elif ok:
            lines.append("✅ Execution successful")
        else:
            lines.append("❌ Execution failed")
        
        # Add stdout (truncated to 800 chars)
        if stdout:
            stdout_truncated = stdout[:800]
            if len(stdout) > 800:
                stdout_truncated += "\n... (output truncated)"
            lines.append(f"\n📤 Output:\n{stdout_truncated}")
        
        # Add stderr if present
        if stderr and not ok:
            stderr_truncated = stderr[:400]
            if len(stderr) > 400:
                stderr_truncated += "\n... (error truncated)"
            lines.append(f"\n⚠️ Error:\n{stderr_truncated}")
        
        # Add error message if present
        if error and not timeout:
            lines.append(f"\n❌ Error: {error}")
        
        message = "\n".join(lines) if lines else "No output"
        
        # Send response (split if too long)
        for chunk in split_text(message, 3000):
            await update.message.reply_text(chunk, disable_web_page_preview=True)
        
    except Exception as e:
        log.error(f"/py command error: {e}")
        await update.message.reply_text(f"❌ Errore: {e}")


async def gpu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /gpu command - Display current GPU status.
    Shows GPU name, VRAM usage, utilization, and temperature.
    """
    http = context.application.bot_data["http"]
    
    # Show typing indicator
    await typing(context, update.effective_chat.id)
    
    try:
        # Call /system/gpu endpoint
        gpu_url = os.getenv("QUANTUM_GPU_URL", "http://127.0.0.1:8081/system/gpu").strip()
        data = await call_backend_json(http, gpu_url, method="GET", timeout=10.0)
        
        current = data.get("current", {})
        health = data.get("health", {})
        status = current.get("status", "unknown")
        gpus = current.get("gpus", [])
        
        # Build message
        lines = ["🖥️ GPU Status:\n"]
        
        # Status
        status_emoji = "✅" if status in ("ok", "cached") else "❌"
        lines.append(f"{status_emoji} Status: {status.upper()}")
        
        if current.get("monitoring_mode"):
            lines.append(f"📡 Mode: {current['monitoring_mode'].upper()}")
        
        if not gpus:
            lines.append("\n❌ No GPU detected or monitoring unavailable")
            if current.get("error"):
                lines.append(f"Error: {current['error']}")
        else:
            # Show each GPU
            for gpu in gpus:
                gpu_name = gpu.get("name", "Unknown")
                gpu_idx = gpu.get("index", 0)
                
                lines.append(f"\n🎮 GPU {gpu_idx}: {gpu_name}")
                
                # VRAM
                vram_used_gb = gpu.get("memory_used", 0) / (1024**3)
                vram_total_gb = gpu.get("memory_total", 0) / (1024**3)
                vram_percent = gpu.get("memory_percent", 0.0)
                vram_emoji = "🟢" if vram_percent < 80 else "🟡" if vram_percent < 90 else "🔴"
                lines.append(f"{vram_emoji} VRAM: {vram_used_gb:.1f} / {vram_total_gb:.1f} GB ({vram_percent:.1f}%)")
                
                # Utilization
                util = gpu.get("utilization_percent", 0.0)
                util_emoji = "⚡" if util > 50 else "💤"
                lines.append(f"{util_emoji} Utilization: {util:.1f}%")
                
                # Temperature
                temp = gpu.get("temperature", 0.0)
                temp_emoji = "🟢" if temp < 70 else "🟡" if temp < 80 else "🔴"
                lines.append(f"{temp_emoji} Temperature: {temp:.1f}°C")
                
                # Power (if available)
                power = gpu.get("power_draw")
                if power is not None:
                    lines.append(f"⚡ Power: {power:.1f}W")
        
        # Health status
        is_healthy = health.get("is_healthy", False)
        health_emoji = "✅" if is_healthy else "⚠️"
        lines.append(f"\n{health_emoji} Health: {'HEALTHY' if is_healthy else 'ATTENTION NEEDED'}")
        
        # Active alerts
        alerts = health.get("alerts", [])
        if alerts:
            lines.append("\n🚨 Active Alerts:")
            for alert in alerts[:3]:  # Show up to 3 alerts
                lines.append(f"  • {alert}")
        
        # Cache info
        cache_age = current.get("cache_age_seconds")
        if cache_age is not None:
            lines.append(f"\n⏱️ Cache age: {cache_age:.1f}s")
        
        message = "\n".join(lines)
        await update.message.reply_text(message)
        
    except Exception as e:
        log.error(f"/gpu command error: {e}")
        await update.message.reply_text(f"❌ Errore nel recupero dello stato GPU: {e}")


async def gpu_history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /gpu_history command - Show GPU metrics history (last 60 minutes).
    Displays VRAM and temperature trends.
    """
    http = context.application.bot_data["http"]
    
    # Show typing indicator
    await typing(context, update.effective_chat.id)
    
    try:
        # Call /system/gpu endpoint with history
        gpu_url = os.getenv("QUANTUM_GPU_URL", "http://127.0.0.1:8081/system/gpu").strip()
        data = await call_backend_json(http, f"{gpu_url}?history_minutes=60", method="GET", timeout=10.0)
        
        history = data.get("history", [])
        
        if not history:
            await update.message.reply_text("📊 No GPU history available yet")
            return
        
        # Build message with history summary
        lines = ["📊 GPU History (Last 60 minutes):\n"]
        lines.append(f"📈 Data points: {len(history)}\n")
        
        # Calculate stats from history
        if history:
            # Get first GPU stats from each entry
            vram_values = []
            temp_values = []
            util_values = []
            
            for entry in history:
                metrics = entry.get("metrics", {})
                gpus = metrics.get("gpus", [])
                if gpus:
                    gpu = gpus[0]
                    vram_values.append(gpu.get("memory_percent", 0))
                    temp_values.append(gpu.get("temperature", 0))
                    util_values.append(gpu.get("utilization_percent", 0))
            
            if vram_values:
                lines.append("💾 VRAM Usage:")
                lines.append(f"  • Current: {vram_values[-1]:.1f}%")
                lines.append(f"  • Average: {sum(vram_values)/len(vram_values):.1f}%")
                lines.append(f"  • Max: {max(vram_values):.1f}%")
                lines.append(f"  • Min: {min(vram_values):.1f}%")
            
            if temp_values:
                lines.append("\n🌡️ Temperature:")
                lines.append(f"  • Current: {temp_values[-1]:.1f}°C")
                lines.append(f"  • Average: {sum(temp_values)/len(temp_values):.1f}°C")
                lines.append(f"  • Max: {max(temp_values):.1f}°C")
                lines.append(f"  • Min: {min(temp_values):.1f}°C")
            
            if util_values:
                lines.append("\n⚡ Utilization:")
                lines.append(f"  • Current: {util_values[-1]:.1f}%")
                lines.append(f"  • Average: {sum(util_values)/len(util_values):.1f}%")
                lines.append(f"  • Max: {max(util_values):.1f}%")
        
        message = "\n".join(lines)
        await update.message.reply_text(message)
        
    except Exception as e:
        log.error(f"/gpu_history command error: {e}")
        await update.message.reply_text(f"❌ Errore nel recupero della cronologia GPU: {e}")


async def gpu_alerts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /gpu_alerts command - Show recent GPU alerts (last 24 hours).
    """
    http = context.application.bot_data["http"]
    
    # Show typing indicator
    await typing(context, update.effective_chat.id)
    
    try:
        # Call /system/gpu/alerts endpoint
        alerts_url = os.getenv("QUANTUM_GPU_ALERTS_URL", "http://127.0.0.1:8081/system/gpu/alerts").strip()
        data = await call_backend_json(http, f"{alerts_url}?hours=24", method="GET", timeout=10.0)
        
        alert_status = data.get("status", {})
        active_alerts = data.get("active_alerts", [])
        history = data.get("history", [])
        
        # Build message
        lines = ["🚨 GPU Alerts (Last 24 Hours):\n"]
        
        # Status
        enabled = alert_status.get("enabled", False)
        running = alert_status.get("running", False)
        
        status_emoji = "✅" if enabled and running else "❌"
        lines.append(f"{status_emoji} Alerting: {'ENABLED' if enabled else 'DISABLED'}")
        
        if enabled:
            active_count = alert_status.get("active_alerts", 0)
            lines.append(f"📊 Active alerts: {active_count}")
        
        # Active alerts
        if active_alerts:
            lines.append("\n⚠️ Currently Active:")
            for alert in active_alerts[:5]:  # Show up to 5
                level = alert.get("level", "info")
                level_emoji = "🔴" if level == "critical" else "🟡" if level == "warning" else "ℹ️"
                message_text = alert.get("message", "Unknown")
                lines.append(f"{level_emoji} {message_text}")
        
        # Recent history
        if history:
            lines.append(f"\n📜 Recent History ({len(history)} alerts):")
            for alert in history[:5]:  # Show up to 5
                level = alert.get("level", "info")
                resolved = alert.get("resolved", False)
                level_emoji = "🔴" if level == "critical" else "🟡" if level == "warning" else "ℹ️"
                resolved_emoji = "✅" if resolved else "🔴"
                message_text = alert.get("message", "Unknown")
                
                # Truncate long messages
                if len(message_text) > 60:
                    message_text = message_text[:57] + "..."
                
                lines.append(f"{resolved_emoji} {level_emoji} {message_text}")
        
        if not active_alerts and not history:
            lines.append("\n✅ No alerts in the last 24 hours")
        
        message = "\n".join(lines)
        await update.message.reply_text(message)
        
    except Exception as e:
        log.error(f"/gpu_alerts command error: {e}")
        await update.message.reply_text(f"❌ Errore nel recupero degli alert GPU: {e}")


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
    
    # Streaming command (if enabled)
    if TELEGRAM_STREAMING_ENABLED:
        app.add_handler(CommandHandler("streaming", streaming_cmd))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    log.info("🤖 Avvio Telegram Bot (Jarvis personale | LLM-only chat | web manuale avanzato + fast live + tools) | polling")
    app.run_polling(drop_pending_updates=True, poll_interval=1.0)
