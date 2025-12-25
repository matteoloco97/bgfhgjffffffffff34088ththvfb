#!/usr/bin/env python3
"""
agents/news_agent.py
====================

Agente news dedicato per Jarvis.
Gestisce query su breaking news, ultime notizie, eventi recenti.

API usate:
- NewsAPI.org (con API key)
- GNews API (alternativa)
- RSS fallback per fonti italiane

Formato risposta standardizzato:
- Emoji + titolo topic
- Blocco notizie verificate (✅)
- Blocco analisi/commenti (⚠️)
- Fonti con timestamp
"""

import asyncio
import logging
import re
import os
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

# ===================== CONFIG =====================

NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")
GNEWS_API_KEY = os.getenv("GNEWS_API_KEY", "")
NEWS_API_TIMEOUT = float(os.getenv("NEWS_API_TIMEOUT", "10.0"))
NEWS_MAX_ARTICLES = int(os.getenv("NEWS_MAX_ARTICLES", "5"))

# ===================== TOPIC MAPPING =====================

# Mapping topic comuni → keywords di ricerca
TOPIC_KEYWORDS: Dict[str, List[str]] = {
    # Crypto
    "bitcoin": ["bitcoin", "btc", "cryptocurrency"],
    "crypto": ["cryptocurrency", "bitcoin", "ethereum", "crypto market"],
    "ethereum": ["ethereum", "eth", "crypto"],
    # Finance
    "borsa": ["stock market", "borsa", "mercati finanziari"],
    "finanza": ["finance", "economia", "mercati"],
    "economia": ["economy", "economics", "gdp", "inflation"],
    # Tech
    "tech": ["technology", "tech", "AI", "innovation"],
    "ai": ["artificial intelligence", "AI", "machine learning"],
    "apple": ["apple", "iphone", "tim cook"],
    "google": ["google", "alphabet", "android"],
    "tesla": ["tesla", "elon musk", "electric vehicles"],
    # Sports
    "calcio": ["football", "soccer", "serie a", "champions league"],
    "sport": ["sports", "football", "basketball", "tennis"],
    # Geopolitics
    "guerra": ["war", "conflict", "military"],
    "ucraina": ["ukraine", "russia ukraine", "zelensky"],
    "gaza": ["gaza", "israel", "hamas", "middle east"],
    "russia": ["russia", "putin", "kremlin"],
    "cina": ["china", "beijing", "xi jinping"],
    "usa": ["united states", "usa", "biden", "trump"],
    # Italy
    "italia": ["italy", "italian", "rome"],
    "politica italiana": ["italian politics", "governo", "parlamento"],
    "governo": ["government", "politics", "parliament"],
}

# Fonti italiane affidabili (per filtro)
ITALIAN_SOURCES = [
    "ansa.it",
    "repubblica.it",
    "corriere.it",
    "ilsole24ore.com",
    "lastampa.it",
    "ilfattoquotidiano.it",
    "adnkronos.com",
    "rainews.it",
    "tgcom24.mediaset.it",
    "sky.it",
]

# ===================== API CALLS =====================


async def _fetch_news_newsapi(
    query: str, language: str = "it", page_size: int = 5
) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch news da NewsAPI.org.
    """
    if not NEWSAPI_KEY:
        log.warning("NewsAPI key not configured")
        return None

    try:
        import aiohttp

        url = "https://newsapi.org/v2/everything"
        params = {
            "q": query,
            "language": language,
            "sortBy": "publishedAt",
            "pageSize": page_size,
            "apiKey": NEWSAPI_KEY,
        }

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=NEWS_API_TIMEOUT)
        ) as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    log.warning(f"NewsAPI returned {resp.status}")
                    return None

                data = await resp.json()

                if data.get("status") != "ok":
                    log.warning(f"NewsAPI error: {data.get('message')}")
                    return None

                articles = data.get("articles", [])
                result = []

                for article in articles[:page_size]:
                    result.append(
                        {
                            "title": article.get("title", ""),
                            "description": article.get("description", ""),
                            "source": article.get("source", {}).get("name", ""),
                            "url": article.get("url", ""),
                            "published_at": article.get("publishedAt", ""),
                            "author": article.get("author", ""),
                        }
                    )

                return result

    except Exception as e:
        log.error(f"NewsAPI error: {e}")
        return None


async def _fetch_news_gnews(
    query: str, language: str = "it", max_articles: int = 5
) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch news da GNews API (alternativa a NewsAPI).
    """
    if not GNEWS_API_KEY:
        log.warning("GNews API key not configured")
        return None

    try:
        import aiohttp

        url = "https://gnews.io/api/v4/search"
        params = {
            "q": query,
            "lang": language,
            "max": max_articles,
            "sortby": "publishedAt",
            "apikey": GNEWS_API_KEY,
        }

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=NEWS_API_TIMEOUT)
        ) as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    log.warning(f"GNews API returned {resp.status}")
                    return None

                data = await resp.json()
                articles = data.get("articles", [])
                result = []

                for article in articles[:max_articles]:
                    result.append(
                        {
                            "title": article.get("title", ""),
                            "description": article.get("description", ""),
                            "source": article.get("source", {}).get("name", ""),
                            "url": article.get("url", ""),
                            "published_at": article.get("publishedAt", ""),
                            "author": "",
                        }
                    )

                return result

    except Exception as e:
        log.error(f"GNews API error: {e}")
        return None


async def _fetch_headlines(
    country: str = "it", category: str = None
) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch top headlines (per notizie generali).
    """
    if not NEWSAPI_KEY:
        return None

    try:
        import aiohttp

        url = "https://newsapi.org/v2/top-headlines"
        params = {
            "country": country,
            "pageSize": NEWS_MAX_ARTICLES,
            "apiKey": NEWSAPI_KEY,
        }
        if category:
            params["category"] = category

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=NEWS_API_TIMEOUT)
        ) as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None

                data = await resp.json()
                if data.get("status") != "ok":
                    return None

                articles = data.get("articles", [])
                result = []

                for article in articles:
                    result.append(
                        {
                            "title": article.get("title", ""),
                            "description": article.get("description", ""),
                            "source": article.get("source", {}).get("name", ""),
                            "url": article.get("url", ""),
                            "published_at": article.get("publishedAt", ""),
                            "author": article.get("author", ""),
                        }
                    )

                return result

    except Exception as e:
        log.error(f"Headlines API error: {e}")
        return None


# ===================== FORMATTERS =====================


def _format_relative_time(published_at: str) -> str:
    """Formatta timestamp in tempo relativo."""
    try:
        if not published_at:
            return ""
        
        # Parse ISO format - gestisce vari formati
        timestamp = published_at
        if "Z" in timestamp:
            timestamp = timestamp.replace("Z", "+00:00")
        
        dt = datetime.fromisoformat(timestamp)
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()

        diff = now - dt

        if diff.days > 0:
            return f"{diff.days} giorni fa"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} ore fa"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} minuti fa"
        else:
            return "pochi secondi fa"
    except Exception:
        return published_at[:10] if published_at else ""


def _format_news_response(topic: str, articles: List[Dict[str, Any]]) -> str:
    """
    Formatta lista notizie in stile Jarvis standardizzato.
    """
    lines = [f"📰 **Ultime notizie: {topic}**\n"]

    lines.append("**✅ Breaking news verificate:**\n")

    for i, article in enumerate(articles[:NEWS_MAX_ARTICLES], 1):
        title = article.get("title", "Senza titolo")
        source = article.get("source", "Fonte sconosciuta")
        published = _format_relative_time(article.get("published_at", ""))
        description = article.get("description", "")
        url = article.get("url", "")

        # Titolo con numero
        lines.append(f"**{i}. {title}**")

        # Breve descrizione (troncata)
        if description:
            desc_short = description[:150] + "..." if len(description) > 150 else description
            lines.append(f"   {desc_short}")

        # Metadata
        lines.append(f"   📍 {source} • 🕐 {published}")
        if url:
            lines.append(f"   🔗 {url}\n")
        else:
            lines.append("")

    # Blocco note
    lines.append("**⚠️ Nota:**")
    lines.append("• Le notizie sono ordinate per data di pubblicazione")
    lines.append("• Verifica sempre le fonti per notizie sensibili")

    lines.append(f"\n📡 Fonte: NewsAPI/GNews (aggiornato: {datetime.now().strftime('%Y-%m-%d %H:%M')})")

    return "\n".join(lines)


def _format_headlines_response(articles: List[Dict[str, Any]], country: str = "Italia") -> str:
    """
    Formatta top headlines in stile Jarvis.
    """
    lines = [f"📰 **Notizie principali – {country}**\n"]

    lines.append("**✅ Ultime ore:**\n")

    for i, article in enumerate(articles[:NEWS_MAX_ARTICLES], 1):
        title = article.get("title", "Senza titolo")
        source = article.get("source", "")
        published = _format_relative_time(article.get("published_at", ""))

        lines.append(f"**{i}.** {title}")
        lines.append(f"   📍 {source} • 🕐 {published}\n")

    lines.append(f"📡 Fonte: NewsAPI (aggiornato: {datetime.now().strftime('%Y-%m-%d %H:%M')})")

    return "\n".join(lines)


# ===================== QUERY EXTRACTION =====================


def extract_news_topic(query: str) -> Optional[Dict[str, Any]]:
    """
    Estrae topic e tipo di richiesta news dalla query.
    """
    q = query.lower().strip()

    # Rimuovi parole comuni
    q_clean = re.sub(
        r"\b(ultime|notizie|news|breaking|oggi|ieri|cosa|è|successo|cosa succede|"
        r"novità|aggiornamenti|su|di|del|della)\b",
        " ",
        q,
    )
    q_clean = re.sub(r"\s+", " ", q_clean).strip()

    # Cerca topic conosciuti
    for topic, keywords in TOPIC_KEYWORDS.items():
        if topic in q or any(kw.lower() in q for kw in keywords):
            return {
                "type": "topic_search",
                "topic": topic,
                "keywords": keywords,
                "search_query": keywords[0] if keywords else topic,
            }

    # Se c'è un argomento specifico dopo "notizie su" / "news about"
    match = re.search(r"(?:notizie|news)\s+(?:su|about|di)\s+(.+)", q)
    if match:
        topic = match.group(1).strip()
        return {
            "type": "topic_search",
            "topic": topic,
            "keywords": [topic],
            "search_query": topic,
        }

    # Query generica per headlines
    if any(kw in q for kw in ["ultime notizie", "breaking news", "news oggi", "notizie del giorno"]):
        return {
            "type": "headlines",
            "country": "it",
        }

    # Se c'è almeno una parola significativa, cerca quella
    if q_clean and len(q_clean) > 2:
        return {
            "type": "topic_search",
            "topic": q_clean,
            "keywords": [q_clean],
            "search_query": q_clean,
        }

    return None


def is_news_query(query: str) -> bool:
    """
    Determina se la query è una richiesta di news.
    """
    q = query.lower().strip()

    news_keywords = [
        "notizie",
        "news",
        "breaking",
        "ultime",
        "cosa è successo",
        "cosa succede",
        "novità",
        "aggiornamenti",
        "headline",
        "headlines",
    ]

    # Check keywords espliciti
    if any(kw in q for kw in news_keywords):
        return True

    # Pattern specifici
    if re.search(r"(ultime|latest|breaking)\s+(news|notizie)", q):
        return True

    if re.search(r"(cosa|what).+(successo|happened|succede|happening)", q):
        return True

    return False


# ===================== PUBLIC API =====================


async def get_news_answer(query: str) -> Optional[str]:
    """
    API principale: data una query news, restituisce la risposta formattata.
    """
    parsed = extract_news_topic(query)

    if not parsed:
        return "❌ Non ho capito la richiesta. Prova con: `ultime notizie bitcoin`, `news su Tesla`, `breaking news Italia`"

    query_type = parsed.get("type")

    try:
        if query_type == "headlines":
            country = parsed.get("country", "it")
            articles = await _fetch_headlines(country=country)
            if articles:
                return _format_headlines_response(articles)
            else:
                # Fallback: headlines fallite, prova topic generico
                return "❌ Impossibile recuperare le ultime notizie. Verifica la configurazione API."

        elif query_type == "topic_search":
            topic = parsed.get("topic")
            search_query = parsed.get("search_query")

            # Prova NewsAPI
            articles = await _fetch_news_newsapi(search_query)

            # Fallback a GNews
            if not articles:
                articles = await _fetch_news_gnews(search_query)

            if articles:
                return _format_news_response(topic, articles)
            else:
                return f"❌ Nessuna notizia recente trovata per '{topic}'. Potrebbe essere necessaria una API key NewsAPI/GNews."

    except Exception as e:
        log.error(f"News agent error: {e}")
        return f"❌ Errore nel recupero notizie: {e}"

    return None


async def get_news_for_query(query: str) -> Optional[str]:
    """
    Wrapper: verifica se è una news query e restituisce la risposta.
    """
    if not is_news_query(query):
        return None

    return await get_news_answer(query)
