#!/usr/bin/env python3
"""
core/unified_web_handler.py
============================

Handler unificato per tutte le richieste web.
Garantisce che /web e auto-web usino la stessa pipeline.

Obiettivi:
1. Formato risposta standard: TL;DR + bullet + fonti
2. Routing consistente per intent
3. Cache unificata per live data
4. Fallback intelligenti

Questo modulo è il punto di ingresso unico per:
- /web <query>
- /webdeep <query> 
- Auto-web da chat/generate
"""

import asyncio
import logging
import hashlib
import time
import re
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

log = logging.getLogger(__name__)

# ===================== RESPONSE FORMAT =====================


def format_standard_response(
    tldr: str,
    bullets: List[str],
    sources: List[Dict[str, str]] = None,
    note: str = None,
    emoji: str = "📌",
) -> str:
    """
    Formatta una risposta nel formato standard Jarvis.
    
    Formato:
    📌 TL;DR: [sintesi 1-2 frasi]
    
    **✅ Punti chiave:**
    1. [punto 1]
    2. [punto 2]
    ...
    
    **📡 Fonti:**
    - [fonte 1]
    - [fonte 2]
    
    **⚠️ Nota:** [se presente]
    """
    lines = []
    
    # TL;DR
    if tldr:
        lines.append(f"{emoji} **TL;DR:** {tldr}\n")
    
    # Bullet points
    if bullets:
        lines.append("**✅ Punti chiave:**")
        for i, bullet in enumerate(bullets[:6], 1):  # Max 6 punti
            # Pulisci bullet
            bullet = bullet.strip()
            if bullet.startswith("•") or bullet.startswith("-"):
                bullet = bullet[1:].strip()
            lines.append(f"{i}. {bullet}")
        lines.append("")
    
    # Fonti
    if sources:
        lines.append("**📡 Fonti:**")
        for src in sources[:5]:  # Max 5 fonti
            title = src.get("title", src.get("url", "Fonte"))
            url = src.get("url", "")
            if url:
                lines.append(f"• [{title}]({url})")
            else:
                lines.append(f"• {title}")
        lines.append("")
    
    # Nota
    if note:
        lines.append(f"**⚠️ Nota:** {note}")
    
    return "\n".join(lines)


def format_live_data_response(
    title: str,
    data_points: List[Tuple[str, str]],  # [(label, value), ...]
    analysis: str = None,
    source: str = None,
    emoji: str = "📊",
) -> str:
    """
    Formatta risposta per dati live (meteo, prezzi, sport).
    
    Formato:
    📊 **[Titolo]**
    
    **✅ Dati verificati:**
    • Label1: Valore1
    • Label2: Valore2
    
    **⚠️ Analisi:** [se presente]
    
    📡 Fonte: [fonte] (aggiornato: timestamp)
    """
    lines = [f"{emoji} **{title}**\n"]
    
    if data_points:
        lines.append("**✅ Dati verificati:**")
        for label, value in data_points:
            lines.append(f"• {label}: **{value}**")
        lines.append("")
    
    if analysis:
        lines.append(f"**⚠️ Analisi:** {analysis}\n")
    
    if source:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines.append(f"📡 Fonte: {source} (aggiornato: {timestamp})")
    
    return "\n".join(lines)


# ===================== INTENT DETECTION =====================


class UnifiedIntentDetector:
    """
    Classificatore unificato per intent web.
    Mappa query → agente appropriato.
    
    NOTA: Questo è il classificatore UNICO per tutto il sistema.
    SmartIntentClassifier e altri classificatori devono delegare qui.
    """
    
    # Intent types
    WEATHER = "weather"
    PRICE = "price"
    SPORTS = "sports"
    NEWS = "news"
    SCHEDULE = "schedule"
    CODE = "code"
    BETTING = "betting"
    TRADING = "trading"
    DEEP_RESEARCH = "deep_research"
    GENERAL_WEB = "general_web"
    DIRECT_LLM = "direct_llm"
    
    def __init__(self):
        # Weather patterns
        self.weather_patterns = [
            r"meteo\s+\w+",
            r"che\s+tempo\s+fa",
            r"previsioni\s+\w+",
            r"weather\s+\w+",
            r"temperatura\s+\w+",
        ]
        self.weather_keywords = [
            "meteo", "che tempo", "weather", "temperatura",
            "pioggia", "neve", "previsioni", "nuvoloso", "sereno",
        ]
        
        # Price patterns  
        self.price_keywords = [
            "prezzo", "quotazione", "quanto vale", "valore",
            "price", "quote", "market cap", "tasso", "cambio",
        ]
        self.asset_keywords = [
            # Crypto principali
            "btc", "bitcoin", "eth", "ethereum", "sol", "solana",
            "xrp", "ripple", "ada", "cardano", "doge", "dogecoin",
            "bnb", "binance coin", "usdt", "usdc", "matic", "polygon",
            "link", "chainlink", "uni", "uniswap", "ltc", "litecoin",
            "avax", "avalanche", "dot", "polkadot", "shib", "shiba",
            "atom", "cosmos", "near", "apt", "aptos", "arb", "arbitrum",
            "sui", "pepe", "trx", "tron",
            # Forex
            "euro", "dollaro", "eurusd", "eur/usd", "gbpusd", "gbp/usd",
            "usdjpy", "usd/jpy", "forex", "fx",
            # Commodities
            "oro", "gold", "xauusd", "argento", "silver", "petrolio", "oil",
            # Stocks/Indices
            "azioni", "stock", "stocks", "shares",
            "apple", "aapl", "microsoft", "msft", "google", "googl",
            "amazon", "amzn", "tesla", "tsla", "nvidia", "nvda", "meta",
            "nasdaq", "s&p", "dow jones", "dow", "ftse", "dax",
        ]
        
        # Sports patterns
        self.sports_keywords = [
            "risultato", "risultati", "score", "partita", "partite",
            "chi ha vinto", "classifica", "standings",
            "serie a", "premier league", "champions", "calcio",
            "gol", "marcatori", "formazione",
        ]
        self.team_keywords = [
            "milan", "inter", "juventus", "juve", "napoli", "roma",
            "lazio", "atalanta", "fiorentina", "torino", "bologna",
            "real madrid", "barcellona", "barcelona", "psg",
            "manchester", "liverpool", "chelsea", "arsenal", "bayern",
        ]
        
        # News patterns
        self.news_keywords = [
            "notizie", "news", "breaking", "ultime",
            "cosa è successo", "cosa succede", "novità", "aggiornamenti",
            "headlines", "latest news",
        ]
        
        # Schedule patterns
        self.schedule_keywords = [
            "quando gioca", "a che ora", "orario", "calendario",
            "prossima partita", "prossimo gp", "f1", "formula 1",
            "prossima gara", "quando è", "quando sarà",
            "fed", "fomc", "bce", "ecb",
        ]
        
        # Code patterns
        self.code_keywords = [
            "scrivi codice", "genera codice", "crea script",
            "implementa", "programma che", "funzione che",
            "debug", "fixa", "fix", "correggi",
            "scrivi uno script", "genera uno script",
            "codice python", "codice javascript",
        ]
        
        # Betting patterns (NEW)
        self.betting_keywords = [
            "scommessa", "scommesse", "bet", "betting",
            "quote", "odds", "pronostico", "pronostici",
            "value bet", "over", "under", "handicap",
            "1x2", "combo", "multipla", "singola",
            "expected value", "ev", "kelly", "kelly criterion",
            "bookmaker", "bookie", "quota",
        ]
        
        # Trading patterns (NEW)
        self.trading_keywords = [
            "trading", "trader", "trade",
            "long", "short", "buy signal", "sell signal",
            "stop loss", "take profit", "tp", "sl",
            "leva", "leverage", "margin",
            "analisi tecnica", "technical analysis",
            "supporto", "resistenza", "support", "resistance",
            "candlestick", "pattern", "trend",
            "portafoglio", "portfolio", "allocazione",
            "risk management", "position size",
        ]
        
        # Deep research triggers
        self.deep_research_triggers = [
            "ricerca completa", "ricerca approfondita", "analisi completa",
            "deep research", "fammi una ricerca", "indaga su",
            "tutto quello che sai su", "approfondisci",
        ]
        
        # Travel patterns (to avoid confusion with sports teams like Roma)
        self.travel_keywords = [
            "volo", "voli", "flight", "flights",
            "hotel", "albergo", "booking",
            "viaggio", "viaggi", "travel", "trip",
            "vacanza", "vacanze",
        ]
    
    def classify(self, query: str) -> Dict[str, Any]:
        """
        Classifica una query e ritorna intent + confidence.
        
        Returns:
            Dict con keys: intent, confidence, reason, live_type (opzionale)
        """
        q = query.lower().strip()
        
        # Empty query
        if not q:
            return {
                "intent": self.DIRECT_LLM,
                "confidence": 0.0,
                "reason": "empty_query",
                "live_type": None,
            }
        
        # Check deep research first (esplicito)
        if any(t in q for t in self.deep_research_triggers):
            return {
                "intent": self.DEEP_RESEARCH,
                "confidence": 0.95,
                "reason": "explicit_deep_research",
                "live_type": None,
            }
        
        # Check code
        if any(kw in q for kw in self.code_keywords):
            return {
                "intent": self.CODE,
                "confidence": 0.95,
                "reason": "code_request",
                "live_type": "code",
            }
        
        # Check weather (alta priorità)
        has_weather_keyword = any(kw in q for kw in self.weather_keywords)
        has_weather_pattern = any(re.search(p, q) for p in self.weather_patterns)
        if has_weather_keyword or has_weather_pattern:
            return {
                "intent": self.WEATHER,
                "confidence": 0.95,
                "reason": "weather_query",
                "live_type": "weather",
            }
        
        # Check travel BEFORE sports (to avoid "roma" matching as team)
        if any(kw in q for kw in self.travel_keywords):
            return {
                "intent": self.GENERAL_WEB,
                "confidence": 0.85,
                "reason": "travel_query",
                "live_type": "travel",
            }
        
        # Check betting (NEW)
        if any(kw in q for kw in self.betting_keywords):
            return {
                "intent": self.BETTING,
                "confidence": 0.90,
                "reason": "betting_query",
                "live_type": "betting",
            }
        
        # Check trading (NEW)
        if any(kw in q for kw in self.trading_keywords):
            # Educational questions → LLM
            if any(p in q for p in ["cos'è", "che cos'è", "cosa significa", "spiega"]):
                return {
                    "intent": self.DIRECT_LLM,
                    "confidence": 0.85,
                    "reason": "trading_educational",
                    "live_type": "trading",
                }
            return {
                "intent": self.TRADING,
                "confidence": 0.88,
                "reason": "trading_query",
                "live_type": "trading",
            }
        
        # Check price
        has_price_keyword = any(kw in q for kw in self.price_keywords)
        has_asset = any(kw in q for kw in self.asset_keywords)
        if has_price_keyword and has_asset:
            return {
                "intent": self.PRICE,
                "confidence": 0.92,
                "reason": "price_query",
                "live_type": "price",
            }
        if has_asset and len(q.split()) <= 4:
            # Query breve con asset = probabilmente prezzo
            return {
                "intent": self.PRICE,
                "confidence": 0.85,
                "reason": "implicit_price_query",
                "live_type": "price",
            }
        
        # Check sports
        has_sports = any(kw in q for kw in self.sports_keywords)
        has_team = any(kw in q for kw in self.team_keywords)
        if has_sports or has_team:
            return {
                "intent": self.SPORTS,
                "confidence": 0.90,
                "reason": "sports_query",
                "live_type": "sports",
            }
        
        # Check schedule
        if any(kw in q for kw in self.schedule_keywords):
            return {
                "intent": self.SCHEDULE,
                "confidence": 0.88,
                "reason": "schedule_query",
                "live_type": "schedule",
            }
        
        # Check news
        if any(kw in q for kw in self.news_keywords):
            return {
                "intent": self.NEWS,
                "confidence": 0.85,
                "reason": "news_query",
                "live_type": "news",
            }
        
        # Check if needs live/fresh data
        live_indicators = [
            "oggi", "adesso", "ora", "attuale", "live",
            "ultime", "recente", "aggiornato",
        ]
        if any(ind in q for ind in live_indicators):
            return {
                "intent": self.GENERAL_WEB,
                "confidence": 0.75,
                "reason": "needs_fresh_data",
                "live_type": None,
            }
        
        # Default: direct LLM for general knowledge
        return {
            "intent": self.DIRECT_LLM,
            "confidence": 0.6,
            "reason": "general_knowledge",
            "live_type": None,
        }
    
    def to_smart_intent_format(self, classification: Dict[str, Any]) -> Dict[str, Any]:
        """
        Converte il formato di classificazione a quello usato da SmartIntentClassifier.
        Utile per retrocompatibilità.
        """
        intent = classification.get("intent", self.DIRECT_LLM)
        
        # Map to SmartIntentClassifier format
        if intent in (self.WEATHER, self.PRICE, self.SPORTS, self.NEWS, 
                      self.SCHEDULE, self.BETTING, self.TRADING, self.GENERAL_WEB):
            return {
                "intent": "WEB_SEARCH",
                "confidence": classification.get("confidence", 0.8),
                "reason": classification.get("reason", ""),
                "live_type": classification.get("live_type"),
                "url": None,
            }
        elif intent == self.CODE:
            return {
                "intent": "DIRECT_LLM",
                "confidence": classification.get("confidence", 0.95),
                "reason": "code_generation_request",
                "live_type": "code",
            }
        else:
            return {
                "intent": "DIRECT_LLM",
                "confidence": classification.get("confidence", 0.6),
                "reason": classification.get("reason", ""),
                "live_type": classification.get("live_type"),
            }


# ===================== UNIFIED HANDLER =====================


class UnifiedWebHandler:
    """
    Handler unificato per richieste web.
    Garantisce consistenza tra /web e auto-web.
    """
    
    def __init__(self):
        self.intent_detector = UnifiedIntentDetector()
        self._cache: Dict[str, Tuple[str, float]] = {}
        self._cache_ttl = {
            UnifiedIntentDetector.WEATHER: 1800,  # 30 min
            UnifiedIntentDetector.PRICE: 60,       # 1 min
            UnifiedIntentDetector.SPORTS: 300,     # 5 min
            UnifiedIntentDetector.NEWS: 600,       # 10 min
            UnifiedIntentDetector.SCHEDULE: 3600,  # 1 ora
            UnifiedIntentDetector.BETTING: 300,    # 5 min (quote cambiano spesso)
            UnifiedIntentDetector.TRADING: 120,    # 2 min (dati trading volatili)
            UnifiedIntentDetector.GENERAL_WEB: 3600,
        }
    
    def _cache_key(self, query: str, intent: str) -> str:
        """Genera chiave cache."""
        q_hash = hashlib.sha256(query.lower().encode()).hexdigest()[:12]
        return f"web:{intent}:{q_hash}"
    
    def _get_cached(self, key: str, ttl: int) -> Optional[str]:
        """Recupera da cache se non scaduto."""
        if key in self._cache:
            result, timestamp = self._cache[key]
            if time.time() - timestamp < ttl:
                return result
        return None
    
    def _set_cached(self, key: str, result: str):
        """Salva in cache."""
        self._cache[key] = (result, time.time())
    
    async def handle(
        self,
        query: str,
        source: str = "web",
        deep: bool = False,
    ) -> Dict[str, Any]:
        """
        Gestisce una richiesta web in modo unificato.
        
        Args:
            query: Query utente
            source: Sorgente della richiesta (web, tg, api)
            deep: Se True, usa ricerca approfondita
        
        Returns:
            Dict con risposta, intent, sources, etc.
        """
        t_start = time.perf_counter()
        
        # Classifica intent
        classification = self.intent_detector.classify(query)
        intent = classification["intent"]
        confidence = classification["confidence"]
        reason = classification["reason"]
        
        # Override per deep mode
        if deep:
            intent = UnifiedIntentDetector.DEEP_RESEARCH
        
        log.info(f"WebHandler: query='{query[:50]}...', intent={intent}, conf={confidence:.2f}")
        
        # Check cache
        cache_key = self._cache_key(query, intent)
        ttl = self._cache_ttl.get(intent, 3600)
        cached = self._get_cached(cache_key, ttl)
        
        if cached:
            return {
                "response": cached,
                "intent": intent,
                "confidence": confidence,
                "reason": reason,
                "cached": True,
                "latency_ms": int((time.perf_counter() - t_start) * 1000),
            }
        
        # Route to appropriate handler
        response = await self._route_to_handler(query, intent)
        
        # Cache result
        if response:
            self._set_cached(cache_key, response)
        
        return {
            "response": response,
            "intent": intent,
            "confidence": confidence,
            "reason": reason,
            "cached": False,
            "latency_ms": int((time.perf_counter() - t_start) * 1000),
        }
    
    async def _route_to_handler(self, query: str, intent: str) -> str:
        """
        Routing a handler specifico per intent.
        """
        try:
            if intent == UnifiedIntentDetector.WEATHER:
                return await self._handle_weather(query)
            
            elif intent == UnifiedIntentDetector.PRICE:
                return await self._handle_price(query)
            
            elif intent == UnifiedIntentDetector.SPORTS:
                return await self._handle_sports(query)
            
            elif intent == UnifiedIntentDetector.NEWS:
                return await self._handle_news(query)
            
            elif intent == UnifiedIntentDetector.SCHEDULE:
                return await self._handle_schedule(query)
            
            elif intent == UnifiedIntentDetector.CODE:
                return await self._handle_code(query)
            
            elif intent == UnifiedIntentDetector.BETTING:
                return await self._handle_betting(query)
            
            elif intent == UnifiedIntentDetector.TRADING:
                return await self._handle_trading(query)
            
            elif intent == UnifiedIntentDetector.DEEP_RESEARCH:
                return await self._handle_deep_research(query)
            
            elif intent == UnifiedIntentDetector.GENERAL_WEB:
                return await self._handle_general_web(query)
            
            else:
                return await self._handle_direct_llm(query)
                
        except Exception as e:
            log.error(f"Handler error for intent={intent}: {e}")
            return f"❌ Errore nel processare la richiesta: {e}"
    
    async def _handle_weather(self, query: str) -> str:
        """Handler per meteo."""
        try:
            from agents.weather_open_meteo import get_weather_for_query
            result = await get_weather_for_query(query)
            return result or "❌ Impossibile recuperare i dati meteo."
        except ImportError:
            return "❌ Agente meteo non disponibile."
        except Exception as e:
            return f"❌ Errore meteo: {e}"
    
    async def _handle_price(self, query: str) -> str:
        """Handler per prezzi."""
        try:
            from agents.price_agent import get_price_for_query
            result = await get_price_for_query(query)
            return result or "❌ Impossibile recuperare il prezzo."
        except ImportError:
            return "❌ Agente prezzi non disponibile."
        except Exception as e:
            return f"❌ Errore prezzi: {e}"
    
    async def _handle_sports(self, query: str) -> str:
        """Handler per sport."""
        try:
            from agents.sports_agent import get_sports_for_query
            result = await get_sports_for_query(query)
            return result or "❌ Impossibile recuperare i dati sportivi."
        except ImportError:
            return "❌ Agente sport non disponibile."
        except Exception as e:
            return f"❌ Errore sport: {e}"
    
    async def _handle_news(self, query: str) -> str:
        """Handler per news."""
        try:
            from agents.news_agent import get_news_for_query
            result = await get_news_for_query(query)
            return result or "❌ Impossibile recuperare le notizie."
        except ImportError:
            return "❌ Agente news non disponibile."
        except Exception as e:
            return f"❌ Errore news: {e}"
    
    async def _handle_schedule(self, query: str) -> str:
        """Handler per calendario."""
        try:
            from agents.schedule_agent import get_schedule_for_query
            result = await get_schedule_for_query(query)
            return result or "❌ Impossibile recuperare il calendario."
        except ImportError:
            return "❌ Agente calendario non disponibile."
        except Exception as e:
            return f"❌ Errore calendario: {e}"
    
    async def _handle_code(self, query: str) -> str:
        """Handler per codice."""
        try:
            from agents.code_agent import get_code_for_query
            from core.chat_engine import reply_with_llm
            result = await get_code_for_query(query, llm_func=reply_with_llm)
            return result or "❌ Impossibile generare il codice."
        except ImportError as e:
            log.warning(f"Code agent import error: {e}")
            return "❌ Agente codice non disponibile."
        except Exception as e:
            return f"❌ Errore generazione codice: {e}"
    
    async def _handle_betting(self, query: str) -> str:
        """Handler per betting/scommesse."""
        try:
            from agents.betting_agent import get_betting_for_query
            result = await get_betting_for_query(query)
            return result or "❌ Impossibile elaborare la richiesta di betting."
        except ImportError:
            log.info("Betting agent not available, using fallback")
            return await self._betting_fallback(query)
        except Exception as e:
            log.error(f"Betting handler error: {e}")
            return await self._betting_fallback(query)
    
    async def _betting_fallback(self, query: str) -> str:
        """Fallback per betting quando l'agente non è disponibile."""
        try:
            from core.chat_engine import reply_with_llm
            prompt = (
                "L'utente chiede informazioni su betting/scommesse. "
                "Fornisci una risposta educativa su:\n"
                "- Expected Value (EV)\n"
                "- Kelly Criterion\n"
                "- Value betting\n"
                "- Gestione del bankroll\n\n"
                f"Query: {query}\n\n"
                "NOTA: Non fornire consigli specifici su scommesse. "
                "Spiega solo i concetti matematici e le strategie generali."
            )
            return await reply_with_llm(prompt, "")
        except Exception as e:
            return f"⚠️ Modulo betting in sviluppo. Per calcoli EV e Kelly, consulta risorse specializzate. Errore: {e}"
    
    async def _handle_trading(self, query: str) -> str:
        """Handler per trading."""
        try:
            from agents.trading_agent import get_trading_for_query
            result = await get_trading_for_query(query)
            return result or "❌ Impossibile elaborare la richiesta di trading."
        except ImportError:
            log.info("Trading agent not available, using fallback")
            return await self._trading_fallback(query)
        except Exception as e:
            log.error(f"Trading handler error: {e}")
            return await self._trading_fallback(query)
    
    async def _trading_fallback(self, query: str) -> str:
        """Fallback per trading quando l'agente non è disponibile."""
        try:
            from core.chat_engine import reply_with_llm
            prompt = (
                "L'utente chiede informazioni su trading. "
                "Fornisci una risposta educativa su:\n"
                "- Analisi tecnica (supporti, resistenze, pattern)\n"
                "- Risk management (stop loss, position sizing)\n"
                "- Concetti di portafoglio\n\n"
                f"Query: {query}\n\n"
                "NOTA: Non fornire consigli finanziari specifici. "
                "Spiega solo i concetti e le strategie generali."
            )
            return await reply_with_llm(prompt, "")
        except Exception as e:
            return f"⚠️ Modulo trading in sviluppo. Per analisi tecniche, consulta risorse specializzate. Errore: {e}"
    
    async def _handle_deep_research(self, query: str) -> str:
        """Handler per ricerca approfondita."""
        try:
            from agents.advanced_web_research import AdvancedWebResearch
            researcher = AdvancedWebResearch(
                max_steps=3,
                min_sources=8,
                quality_threshold=0.70
            )
            result = await researcher.research_deep(query)
            
            if result.get("answer"):
                # Formatta in modo standard, troncando a confine parola
                answer = result["answer"]
                tldr = self._truncate_at_word_boundary(answer, 200)
                sources = result.get("sources", [])
                return format_standard_response(
                    tldr=tldr,
                    bullets=[],  # La risposta è già completa
                    sources=sources[:5],
                    emoji="🔬",
                )
            return "❌ Ricerca non ha prodotto risultati."
        except ImportError:
            return "❌ Modulo ricerca avanzata non disponibile."
        except Exception as e:
            return f"❌ Errore ricerca: {e}"
    
    def _truncate_at_word_boundary(self, text: str, max_len: int) -> str:
        """Tronca testo a confine parola per evitare tagli a metà."""
        if len(text) <= max_len:
            return text
        # Trova ultimo spazio prima del limite
        truncated = text[:max_len]
        last_space = truncated.rfind(" ")
        if last_space > max_len * 0.7:  # Se lo spazio è ragionevolmente vicino
            return truncated[:last_space] + "..."
        return truncated + "..."
    
    async def _handle_general_web(self, query: str) -> str:
        """Handler per ricerca web generica."""
        # Usa la pipeline web standard da quantum_api
        try:
            # Import lazy per evitare dipendenze circolari
            from backend.quantum_api import _web_search_pipeline
            
            ws = await _web_search_pipeline(
                q=query,
                src="unified",
                sid="default",
                k=6,
                nsum=2,
            )
            
            summary = ws.get("summary", "")
            results = ws.get("results", [])
            
            if summary:
                return summary
            elif results:
                # Fallback: lista risultati
                lines = ["🔍 Risultati trovati:\n"]
                for i, r in enumerate(results[:5], 1):
                    title = r.get("title", "")[:60]
                    url = r.get("url", "")
                    lines.append(f"{i}. {title}\n   {url}")
                return "\n".join(lines)
            else:
                return "❌ Nessun risultato trovato per questa ricerca."
                
        except ImportError:
            log.warning("quantum_api not available for general web search")
            return f"🔍 Ricerca web per: {query}\n\n(Pipeline web in caricamento...)"
        except Exception as e:
            log.error(f"General web search error: {e}")
            return f"❌ Errore nella ricerca web: {e}"
    
    async def _handle_direct_llm(self, query: str) -> str:
        """Handler per risposta diretta LLM."""
        try:
            from core.chat_engine import reply_with_llm
            return await reply_with_llm(query, "")
        except ImportError:
            return "❌ Motore LLM non disponibile."
        except Exception as e:
            return f"❌ Errore LLM: {e}"


# ===================== SINGLETON =====================

_HANDLER_INSTANCE: Optional[UnifiedWebHandler] = None


def get_unified_web_handler() -> UnifiedWebHandler:
    """Get singleton instance."""
    global _HANDLER_INSTANCE
    if _HANDLER_INSTANCE is None:
        _HANDLER_INSTANCE = UnifiedWebHandler()
    return _HANDLER_INSTANCE


# ===================== CONVENIENCE FUNCTIONS =====================


async def handle_web_query(
    query: str,
    source: str = "web",
    deep: bool = False,
) -> Dict[str, Any]:
    """
    Funzione di convenienza per gestire query web.
    """
    handler = get_unified_web_handler()
    return await handler.handle(query, source, deep)


async def handle_web_command(
    query: str,
    command: str = "web",
) -> str:
    """
    Gestisce comandi /web e /webdeep da Telegram/CLI.
    
    Args:
        query: Testo dopo il comando
        command: Tipo di comando (web, webdeep)
    
    Returns:
        Risposta formattata
    """
    deep = command in ("webdeep", "deep")
    result = await handle_web_query(query, source="command", deep=deep)
    return result.get("response", "❌ Nessuna risposta disponibile.")
