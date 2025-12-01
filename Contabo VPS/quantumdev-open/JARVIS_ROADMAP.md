# 🚀 Jarvis Roadmap - Live Agents Implementation

Questo documento descrive le modifiche effettuate per implementare la "roadmap Jarvis" con i live agents.

## 📁 File Creati

### Nuovi Agenti (`agents/`)

1. **`agents/price_agent.py`** - Agente prezzi crypto/azioni/forex
   - API: CoinGecko (crypto), Alpha Vantage (stocks/forex)
   - Supporta: BTC, ETH, SOL, XRP, e molte altre crypto
   - Supporta: AAPL, MSFT, TSLA, NVDA e altri titoli
   - Supporta: EUR/USD, GBP/USD, XAU/USD (oro) e altri forex

2. **`agents/sports_agent.py`** - Agente risultati sportivi
   - API: TheSportsDB, football-data.org
   - Supporta: Risultati, classifiche, squadre Serie A/Premier/Champions
   - Squadre: Milan, Inter, Juve, Roma, Real Madrid, Barcelona, ecc.

3. **`agents/news_agent.py`** - Agente breaking news
   - API: NewsAPI.org, GNews
   - Supporta: Ultime notizie per topic, headlines Italia
   - Topic: crypto, tech, sport, geopolitica, finanza

4. **`agents/schedule_agent.py`** - Agente calendario eventi
   - API: TheSportsDB, Ergast (F1)
   - Supporta: Orari partite, calendario F1, eventi macro FED/BCE

5. **`agents/code_agent.py`** - 🆕 Agente codice dedicato
   - Generazione codice strutturata con piano + implementazione
   - Debug e fix di errori con spiegazione
   - Generazione test unitari
   - Code review e documentazione
   - Formato: Piano → Codice → Istruzioni → Note

### Nuovi Core Modules (`core/`)

6. **`core/unified_web_handler.py`** - 🆕 Handler web unificato
   - Garantisce consistenza tra /web e auto-web
   - Formato risposta standard: TL;DR + bullet + fonti
   - Routing unificato per tutti gli intent
   - Cache per live data con TTL configurabili

### File Modificati

7. **`core/smart_intent_classifier.py`** - Pattern estesi (SmartIntent 2.0)
   - Più crypto (SOL, XRP, DOGE, ecc.)
   - Più forex (GBP/USD, USD/JPY, ecc.)
   - Più azioni (AAPL, MSFT, TSLA, ecc.)
   - Più sport (squadre, competizioni)
   - Keywords betting e trading
   - Nuovi live_type: "price", "sports", "news", "schedule", "betting", "trading", "code"

8. **`backend/quantum_api.py`** - Integrazione agenti
   - Import di tutti i nuovi agenti (incluso code_agent)
   - Import di unified_web_handler
   - Nuovo endpoint `/web/deep` per ricerca approfondita
   - Nuovo endpoint `/code` per generazione codice
   - Nuovo endpoint `/unified-web` per routing consistente
   - Funzione `cached_live_call()` per cache Redis
   - Healthcheck con stato live agents esteso

9. **`backend/synthesis_prompt_v2.py`** - 🆕 Formato TL;DR
   - Prompt v4 con formato TL;DR + bullet + fonti
   - Risposte più secche e concrete
   - Meno "fuffa" e frasi evasive
   - Limite a 6 bullet points

10. **`agents/advanced_web_research.py`** - Multi-step Research v2
    - Multi-step: riformula e cerca se la prima ricerca non basta
    - Parallel fetch aggressivo con asyncio.Semaphore
    - Dedup per dominio (max 2 risultati per dominio)
    - Quality estimation per decidere se continuare
    - Prompt di sintesi con formato standardizzato

## 🔧 Variabili .env Necessarie

### Esistenti (già configurate)
```env
# LLM
LLM_ENDPOINT=...
LLM_MODEL=...
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=512

# Redis (per cache)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
```

### Nuove (opzionali ma raccomandate)

```env
# === PRICE AGENT ===
# Alpha Vantage (stocks/forex) - free tier disponibile
ALPHA_VANTAGE_API_KEY=demo
# CoinGecko Pro (opzionale, migliora rate limits)
COINGECKO_API_KEY=

# === NEWS AGENT ===
# NewsAPI.org - free tier: 100 req/day
NEWSAPI_KEY=your_newsapi_key_here
# GNews (alternativa) - free tier: 100 req/day
GNEWS_API_KEY=your_gnews_key_here

# === SPORTS AGENT ===
# football-data.org - free tier: 10 req/min
FOOTBALL_DATA_API_KEY=your_football_data_key_here

# === CODE AGENT ===
CODE_AGENT_TIMEOUT=30.0
CODE_MAX_TOKENS=2048

# === LIVE CACHE TTL (in secondi) ===
LIVE_CACHE_TTL_WEATHER=1800    # 30 minuti
LIVE_CACHE_TTL_PRICE=60        # 1 minuto (prezzi cambiano spesso)
LIVE_CACHE_TTL_SPORTS=300      # 5 minuti
LIVE_CACHE_TTL_NEWS=600        # 10 minuti
LIVE_CACHE_TTL_SCHEDULE=3600   # 1 ora

# === LIVE AGENT TIMEOUT ===
LIVE_AGENT_TIMEOUT_S=10.0

# === API TIMEOUTS ===
PRICE_API_TIMEOUT=8.0
SPORTS_API_TIMEOUT=10.0
NEWS_API_TIMEOUT=10.0
SCHEDULE_API_TIMEOUT=10.0

# === WEB RESEARCH AGENT v2 ===
WEB_RESEARCH_BUDGET_TOK=2000      # Token budget per contesto
WEB_RESEARCH_MAX_DOCS=5           # Max documenti da leggere
WEB_RESEARCH_MAX_STEPS=3          # Max step di ricerca
WEB_RESEARCH_QUALITY_THRESHOLD=0.6  # Soglia qualità per stop
WEB_RESEARCH_MAX_CONCURRENT=4     # Max fetch paralleli
```

## 📦 Dipendenze Python

Le seguenti librerie sono già incluse nel progetto o sono standard:

```
aiohttp>=3.8.0      # Per chiamate API async (già presente)
redis>=4.0.0        # Per caching (già presente)
requests>=2.28.0    # Per chiamate HTTP sync (già presente)
```

**Nessuna nuova dipendenza richiesta!** Tutti gli agenti usano `aiohttp` già presente.

## 🔄 Come Funziona il Routing

1. L'utente invia una query (es: "prezzo bitcoin")
2. `SmartIntentClassifier` o `UnifiedIntentDetector` classifica la query con `live_type`
3. Se `live_type == "price"` → `PriceAgent`
4. Se `live_type == "sports"` → `SportsAgent`
5. Se `live_type == "news"` → `NewsAgent`
6. Se `live_type == "schedule"` → `ScheduleAgent`
7. Se `live_type == "weather"` → `WeatherAgent` (già esistente)
8. Se `live_type == "code"` → `CodeAgent` 🆕
9. Fallback → `WebResearchAgent` per ricerche generiche

### Priorità Live Agents

```
1. Weather Agent (meteo)
2. Price Agent (prezzi/quotazioni)
3. Sports Agent (risultati/classifiche)
4. News Agent (breaking news)
5. Schedule Agent (orari/calendario)
6. Code Agent (generazione/debug codice) 🆕
7. Web Research Agent (fallback generico)
```

## 📊 Formato Risposte Standardizzato v4 (TL;DR)

Tutte le risposte web seguono ora questo formato compatto:

```
📌 **TL;DR:** [Sintesi 1-2 frasi]

**✅ Punti chiave:**
1. [Fatto concreto con numero/data]
2. [Fatto concreto]
3. [Fatto concreto]

**📡 Fonti:** [1] Nome1, [2] Nome2

**⚠️ Nota:** [Solo se necessario, max 1 riga]
```

### Formato Code Agent

```
📌 **[Titolo componente]**

**📋 Piano:**
1. [Passo 1]
2. [Passo 2]
3. [Passo 3]

**💻 Codice:**
```python
[codice completo]
```

**🚀 Come usarlo:**
1. [Istruzione 1]
2. [Istruzione 2]

**⚠️ Note:**
• [Dipendenze]
• [Limitazioni]
```

## 🆕 Nuovi Endpoints API

### `/web/deep` (POST)
Ricerca approfondita multi-step.

```json
{
  "q": "quali sono i rischi degli ETF obbligazionari nel 2025?",
  "source": "tg",
  "source_id": "123"
}
```

Risposta:
```json
{
  "answer": "...",
  "sources": [...],
  "steps": [...],
  "quality": 0.85,
  "total_sources": 12
}
```

### `/code` (POST)
Generazione codice strutturata.

```json
{
  "q": "scrivi una funzione Python che calcola il fattoriale",
  "language": "python",
  "source": "tg"
}
```

Risposta:
```json
{
  "ok": true,
  "code": "📌 **Calcolo Fattoriale**\n\n**📋 Piano:**...",
  "language": "python"
}
```

### `/unified-web` (POST)
Endpoint unificato per qualsiasi richiesta web.

```json
{
  "q": "meteo roma",
  "deep": false,
  "source": "api"
}
```

Risposta:
```json
{
  "response": "...",
  "intent": "weather",
  "confidence": 0.95,
  "cached": true,
  "latency_ms": 45
}
```

## 🔍 WebResearchAgent v2 - Multi-Step

Il nuovo WebResearchAgent implementa:

1. **Multi-step search**: Se la prima ricerca ha qualità bassa (< 0.6), riformula la query e cerca di nuovo
2. **Parallel fetch**: Scarica fino a 4 pagine in parallelo per velocità
3. **Dedup per dominio**: Max 2 risultati per dominio per garantire diversità
4. **Quality estimation**: Stima qualità basata su:
   - Numero di estratti
   - Diversità domini
   - Match keywords query
5. **Prompt strutturato**: Output con formato TL;DR + bullet + fonti

## 🚀 Prossimi Passi (da implementare)

1. **BettingAgent** - Quote, probabilità, value bet
2. **TradingAgent** - Analisi tecnica, segnali
3. **Memoria storica query** - Contesto conversazione
4. **EdgeAgent** - Calcolo EV per betting

---

## 🆕 Update v2.2 - Unified Handler & Code Agent

### Code Agent (`agents/code_agent.py`)

Agente dedicato per generazione codice con:

1. **Generazione strutturata**
   - Piano in passi chiari
   - Codice completo e funzionante
   - Istruzioni di esecuzione (3-5 passi)
   - Note su dipendenze e limitazioni

2. **Debug intelligente**
   - Analisi dell'errore
   - Codice corretto con spiegazione
   - Suggerimenti aggiuntivi

3. **Linguaggi supportati**
   - Python, JavaScript, TypeScript
   - Java, C/C++, C#
   - Go, Rust, Bash/Shell
   - SQL, HTML/CSS, Ruby, PHP

4. **Tipi di richieste**
   - `generate`: Generazione nuovo codice
   - `debug`: Fix di errori
   - `explain`: Spiegazione codice
   - `test`: Generazione unit test
   - `optimize`: Refactoring/ottimizzazione

### Unified Web Handler (`core/unified_web_handler.py`)

Handler unificato che:

1. **Garantisce consistenza**
   - Stesso routing per /web e auto-web
   - Stesso formato risposta
   - Stessa cache

2. **Intent detection unificata**
   - Weather, Price, Sports, News, Schedule, Code
   - Deep Research, General Web, Direct LLM

3. **Cache intelligente**
   - TTL configurabili per tipo
   - Cache key basata su intent + query hash

4. **Formato risposta standard**
   - `format_standard_response()`: TL;DR + bullet + fonti
   - `format_live_data_response()`: Per dati live strutturati

---

## 📝 Note

- Gli agenti usano cache Redis per evitare chiamate ripetute
- Se un agente fallisce, c'è sempre fallback su WebResearch
- Le API gratuite hanno rate limits, la cache aiuta a rispettarli
- Per produzione, consigliato ottenere API key a pagamento per:
  - Alpha Vantage (azioni/forex real-time)
  - NewsAPI (più richieste)
  - football-data.org (più richieste)

## 🔒 Healthcheck

L'endpoint `/healthz` ora include lo stato di tutti i live agents:

```json
{
  "live_agents": {
    "weather": true,
    "price": true,
    "sports": true,
    "news": true,
    "schedule": true,
    "code": true,
    "unified_web": true
  },
  "live_cache_ttl": {
    "weather": 1800,
    "price": 60,
    "sports": 300,
    "news": 600,
    "schedule": 3600
  }
}
```
