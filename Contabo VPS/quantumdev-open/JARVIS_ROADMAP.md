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

1. ~~**BettingAgent** - Quote, probabilità, value bet~~ ✅ IMPLEMENTATO
2. ~~**TradingAgent** - Analisi tecnica, segnali~~ ✅ IMPLEMENTATO
3. **Memoria storica query** - Contesto conversazione
4. ~~**EdgeAgent** - Calcolo EV per betting~~ ✅ INTEGRATO IN BettingAgent

---

## 🆕 Update v2.3 - Betting/Trading Agents & Follow-up Queries

### BettingAgent (`agents/betting_agent.py`)

Nuovo agente dedicato per betting e scommesse con:

1. **Calcoli EV (Expected Value)**
   - `calcola ev quota 2.50 probabilità 45%`
   - Determina se una scommessa è "value" (EV positivo)
   - Mostra edge rispetto al bookmaker

2. **Kelly Criterion**
   - `kelly quota 1.85 prob 60%`
   - Calcola stake ottimale per massimizzare crescita bankroll
   - Supporta Quarter/Half Kelly per ridurre varianza

3. **Funzioni disponibili:**
   - `calculate_ev(odds, probability, stake)` - Calcola EV
   - `calculate_kelly(odds, probability, fraction)` - Calcola Kelly
   - `decimal_to_probability(odds)` - Converte quota → probabilità
   - `american_to_decimal(american_odds)` - Converte quote US

4. **Formato risposta:**
   ```
   🎰 **Calcolo Expected Value (EV)**

   **✅ Input:**
   • Quota: **2.50**
   • Probabilità stimata: **45.0%**
   • Stake: **€100**

   **📊 Risultati:**
   • Expected Value: **€12.50**
   • ROI atteso: **12.50%**
   • Edge: **+5.00%**

   **✅ Verdetto:** Value Bet! (EV positivo)
   ```

### TradingAgent (`agents/trading_agent.py`)

Nuovo agente dedicato per trading e risk management:

1. **Position Sizing**
   - `position size account 10000 risk 2% entry 100 sl 95`
   - Calcola quante unità comprare basandosi su rischio massimo

2. **Risk/Reward Calculation**
   - `risk reward entry 100 sl 95 tp 115`
   - Calcola R:R ratio e win rate necessario per break-even

3. **Leverage Impact**
   - `impatto leva 10x su 1000€ con movimento 5%`
   - Mostra P/L su margine e rischio liquidazione

4. **Funzioni disponibili:**
   - `calculate_position_size(account, risk_pct, entry, sl)` - Position sizing
   - `calculate_risk_reward(entry, sl, tp)` - Calcola R:R
   - `calculate_leverage_impact(position, leverage, change_pct)` - Impatto leva
   - `calculate_compound_growth(initial, return_pct, months)` - Crescita composta

### Follow-up Query Generation

Migliorata la ricerca multi-step in `advanced_web_research.py`:

1. **Generazione follow-up con LLM**
   - Analizza gli estratti raccolti
   - Identifica gaps informativi
   - Genera query mirate per colmare lacune

2. **Prompt intelligente:**
   ```
   QUERY ORIGINALE: [query]
   INFORMAZIONI RACCOLTE FINORA: [estratti]
   QUALITÀ CORRENTE: [score]/1.0

   Genera UNA SINGOLA query per colmare le lacune...
   ```

3. **Fallback robusto:**
   - Se LLM fallisce, usa variante semplice
   - Validazione: non troppo corta, non duplicata

### Intent Detection Unificato

Consolidati i classificatori in `UnifiedIntentDetector`:

1. **Nuovi intent:**
   - `BETTING` - Query su scommesse/quote
   - `TRADING` - Query su analisi/position sizing

2. **Retrocompatibilità:**
   - Metodo `to_smart_intent_format()` per conversione
   - Mantiene compatibilità con vecchio SmartIntentClassifier

3. **Travel detection:**
   - Evita che "volo roma" sia classificato come sports (Roma squadra)

### Fallback Migliorati

Aggiunto fallback robusto per tutti gli agenti:

1. **Price Agent:**
   - Se API fallisce, fornisce link a CoinGecko/Yahoo/TradingView
   - Messaggi informativi invece di errori generici

2. **Betting/Trading:**
   - Fallback a risposte educative
   - Spiega concetti senza dati live

### Unit Tests

Aggiunti test in `tests/`:

1. **`test_intent_detection.py`**
   - Test per tutti gli intent (weather, price, sports, news, schedule, code, betting, trading)
   - Test edge cases (query vuota, travel vs sports)
   - Test retrocompatibilità

2. **`test_betting_trading_agents.py`**
   - Test calcoli EV e Kelly
   - Test position size e risk/reward
   - Test leverage impact
   - Test parsing query

---

## 🔧 Nuove Variabili .env

```env
# === BETTING AGENT ===
ODDS_API_KEY=                    # Opzionale: per quote live
BETTING_API_TIMEOUT=10.0

# === TRADING AGENT ===
TRADING_API_TIMEOUT=10.0

# === CACHE TTL NUOVI AGENTI ===
LIVE_CACHE_TTL_BETTING=300       # 5 minuti (quote cambiano)
LIVE_CACHE_TTL_TRADING=120       # 2 minuti (dati volatili)
```

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


---

## 🆕 Update v3.0 - QuantumDev Max AI Enhancements ✨

**Release Date:** December 2024

### New Features Implemented

#### 1. Vector Memory & RAG (`core/vector_memory.py`) ✅ COMPLETED

Sistema di memoria vettoriale avanzato con ChromaDB:

- **Semantic Search:** Ricerca semantica su conversazioni passate
- **Embedding Model:** sentence-transformers (all-MiniLM-L6-v2)
- **Persistent Storage:** Database vettoriale su disco
- **Session-based:** Documenti organizzati per sessione
- **Metadata Support:** Metadata ricchi per ogni documento

**Funzionalità:**
- `add_document(session_id, text, metadata)` - Aggiunge documento al database vettoriale
- `query_documents(session_id, query, top_k)` - Ricerca semantica con risultati ordinati per rilevanza
- `delete_session_documents(session_id)` - Rimozione documenti di una sessione
- `get_collection_stats()` - Statistiche sulla collezione

**Integrazione:**
- Automaticamente integrato in `conversational_memory.py`
- Tool `memory_search` registrato per ricerca semantica
- Salvataggio automatico di messaggi e riassunti

**Configurazione:**
```env
CHROMA_PERSIST_DIR=./data/chroma_db
CHROMA_COLLECTION=quantumdev_memory
EMBEDDING_MODEL=all-MiniLM-L6-v2
```

---

#### 2. Enhanced Web Search (`core/enhanced_web.py`) ✅ COMPLETED

Ricerca web migliorata con estrazione contenuti:

- **SerpAPI Integration:** Supporto per SerpAPI (opzionale, migliori risultati)
- **DuckDuckGo Fallback:** Fallback automatico se SerpAPI non disponibile
- **Content Extraction:** Estrazione testo da pagine web con BeautifulSoup
- **Smart Snippets:** Snippet generati da contenuto reale (max 500 caratteri)
- **Async Support:** Completamente asincrono

**Funzionalità:**
- `enhanced_search(query, k)` - Ricerca con estrazione contenuti
- Rimozione automatica di script, style, e tag non necessari
- Snippet intelligenti con boundary detection

**Tool Registrato:**
- `enhanced_web_search` - Preferito rispetto a `web_search` base
- `web_search` - Mantenuto per compatibilità ma con descrizione aggiornata

**Configurazione:**
```env
SERPAPI_KEY=  # Opzionale, migliora risultati
ENHANCED_SEARCH_TIMEOUT=10
MAX_SNIPPET_LENGTH=500
```

---

#### 3. Code Execution (`agents/code_execution.py`) ✅ COMPLETED

Esecuzione sicura di codice Python in ambiente isolato:

- **Subprocess Isolation:** Codice eseguito in subprocess separato
- **Timeout Enforcement:** Limite di 10 secondi (configurabile)
- **Security Checks:** Blocco automatico di import/operazioni pericolose
- **Error Handling:** Cattura e reporting di stdout, stderr, exit_code

**Operazioni Bloccate (sicurezza):**
- Import di `os`, `subprocess`, `sys`
- Uso di `eval()`, `exec()`, `compile()`
- Operazioni su file (`open()`, `file()`)
- Input utente (`input()`, `raw_input()`)

**Tool Registrato:**
- `code_executor(language, code)` - Esegue codice Python

**Configurazione:**
```env
CODE_EXEC_ENABLED=1
CODE_EXEC_TIMEOUT=10
```

**Esempio:**
```python
code = """
result = sum([1, 2, 3, 4, 5])
print(f"Sum: {result}")
"""
result = await run_code("python", code)
# Output: {"success": True, "stdout": "Sum: 15\n", ...}
```

---

#### 4. Proactive Suggestions (`core/proactive.py`) ✅ COMPLETED

Suggerimenti proattivi basati su LLM:

- **Context-Aware:** Analizza query utente e contesto conversazione
- **LLM-Driven:** Usa il modello LLM per generare suggerimenti pertinenti
- **Actionable:** Suggerimenti pratici e specifici (non generici)
- **Configurabile:** Numero massimo di suggerimenti configurabile

**Funzionalità:**
- `generate_suggestions(session, query, llm_func)` - Genera 3 suggerimenti
- Parsing intelligente della risposta LLM
- Integrato in `master_orchestrator.py`

**Configurazione:**
```env
ENABLE_PROACTIVE_SUGGESTIONS=false  # Disabilitato di default
MAX_PROACTIVE_SUGGESTIONS=3
```

**Quando attivo:**
- Suggerimenti aggiunti a `metadata["proactive_suggestions"]` nella risposta
- Visibili nel campo metadata della OrchestratorResponse

---

#### 5. LLM-based Query Classification ✅ COMPLETED

Classificazione query migliorata con LLM:

- **LLM Classification:** Classificazione primaria tramite LLM
- **Regex Fallback:** Fallback a regex se LLM non disponibile
- **Query Types:** GENERAL, CODE, RESEARCH, CALCULATION, MEMORY, CREATIVE
- **Strategy Selection:** Scelta automatica della strategia ottimale

**Funzionalità:**
- `classify_query_via_llm(query, llm_func)` - Classificazione via LLM
- Integrato in `master_orchestrator.analyze_query()`
- Strategy mapping: RESEARCH → TOOL_ASSISTED, MEMORY → MEMORY_RECALL

**Logica:**
1. Tenta classificazione via LLM
2. Se fallisce, usa regex patterns esistenti
3. Seleziona strategy basata su query_type

---

#### 6. Extended Persistence ✅ COMPLETED

Sistema di persistenza esteso per conversazioni:

- **TTL Configurabile:** TTL in giorni invece che secondi fissi
- **JSON Archive:** Salvataggio automatico in file JSON
- **Archive Loading:** Caricamento da archive se Redis scaduto
- **Automatic Archiving:** Archiviazione opzionale ad ogni update

**Funzionalità:**
- `_save_session()` - Salva su Redis + archive (opzionale)
- `_archive_session()` - Salva sessione in JSON
- `_load_from_archive()` - Carica da archive
- Creazione automatica directory `./data/archive/`

**Configurazione:**
```env
CONVERSATION_TTL_DAYS=7           # TTL in giorni
PERSIST_ARCHIVE_ENABLED=false     # Abilita archiving JSON
ARCHIVE_DIR=./data/archive        # Directory archivi
```

**Struttura Archive:**
```
./data/archive/
  ├── sess_abc123.json
  ├── sess_def456.json
  └── ...
```

---

### Updated Components

#### `core/conversational_memory.py` - Updated

**Modifiche:**
- Integrazione vector_memory per semantic search
- Metodo `search_memory(query, top_k)` per ricerca semantica
- Salvataggio automatico in vector DB dopo ogni turn
- Archiviazione JSON opzionale
- TTL configurabile in giorni

#### `core/master_orchestrator.py` - Updated

**Modifiche:**
- Classificazione query via LLM con fallback regex
- Generazione proactive suggestions (opzionale)
- Env var `ENABLE_PROACTIVE_SUGGESTIONS`
- Strategy selection migliorata per RESEARCH queries

#### `core/register_tools.py` - Updated

**Nuovi Tool Registrati:**
- `enhanced_web_search` - Ricerca web avanzata
- `code_executor` - Esecuzione codice sicura
- `memory_search` - Ricerca semantica memoria

**Tool Aggiornati:**
- `web_search` - Descrizione aggiornata (indica preferenza per enhanced version)

---

### Testing

Aggiunti test completi in `tests/`:

1. **`test_vector_memory.py`**
   - Test add/query/delete documents
   - Test semantic search
   - Test collection stats
   - Test edge cases (empty docs, session)

2. **`test_enhanced_web.py`**
   - Test HTML text extraction
   - Test snippet generation
   - Test enhanced search
   - Test fallback mechanisms

3. **`test_code_execution.py`**
   - Test esecuzione codice semplice
   - Test calcoli
   - Test security blocks (os, subprocess, eval)
   - Test timeout enforcement
   - Test error handling (syntax, runtime)

---

### Dependencies Added

Aggiunte a `requirements.txt`:

```txt
chromadb>=0.4.18
sentence-transformers>=2.2.2
beautifulsoup4>=4.12.0
lxml>=4.9.0
```

**Opzionale:**
```txt
google-search-results>=2.4.2  # SerpAPI client
```

---

### Migration Guide

Per aggiornare da versioni precedenti:

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Update .env:**
   ```bash
   # Vector Memory
   CHROMA_PERSIST_DIR=./data/chroma_db
   CHROMA_COLLECTION=quantumdev_memory
   
   # Enhanced Web
   SERPAPI_KEY=  # Optional
   
   # Code Execution
   CODE_EXEC_ENABLED=1
   
   # Proactive (optional)
   ENABLE_PROACTIVE_SUGGESTIONS=false
   
   # Persistence
   CONVERSATION_TTL_DAYS=7
   PERSIST_ARCHIVE_ENABLED=false
   ```

3. **Create data directories:**
   ```bash
   mkdir -p ./data/chroma_db
   mkdir -p ./data/archive
   ```

4. **Restart service:**
   ```bash
   sudo systemctl restart quantum-api
   ```

---

### Performance Impact

**Memory:**
- ChromaDB: ~100-500MB (dipende da numero documenti)
- Sentence Transformers model: ~80MB

**Disk:**
- ChromaDB persistent storage: ~10-100MB
- JSON archives: ~1KB per sessione

**CPU:**
- Embedding generation: moderato (cache interno ChromaDB)
- Code execution: subprocess isolation (minimal overhead)

---

### Security Considerations

**Code Execution:**
- ✅ Subprocess isolation
- ✅ Timeout enforcement
- ✅ Dangerous imports blocked
- ✅ No file/network access
- ⚠️ Solo Python supportato (per design)

**Web Search:**
- ✅ Request timeout
- ✅ Content sanitization (BeautifulSoup)
- ⚠️ SerpAPI key in .env (non commitare!)

**Vector Memory:**
- ✅ Session-based isolation
- ✅ Persistent storage locale
- ⚠️ Nessuna encryption dati (TODO future)

---

### Known Limitations

1. **Code Execution:**
   - Solo Python supportato
   - Nessun supporto per librerie esterne
   - Timeout fisso (non dinamico)

2. **Vector Memory:**
   - Nessuna compressione vettori
   - Nessun cleanup automatico sessioni vecchie
   - Embedding model fisso (non configurabile runtime)

3. **Enhanced Web:**
   - SerpAPI richiede API key (fallback a DDG)
   - Timeout fisso per fetch
   - Nessun retry automatico

---

### Future Improvements (TODO)

- [ ] Supporto multi-lingua per embedding
- [ ] Code execution per JavaScript/TypeScript
- [ ] Cleanup automatico vector DB (sessioni > 30 giorni)
- [ ] Encryption at rest per archives
- [ ] Retry logic per enhanced web search
- [ ] Dynamic timeout per code execution
- [ ] Proactive suggestions caching

---

**Status:** ✅ PRODUCTION READY

**Version:** 3.0.0

**Contributors:** Matteo (QuantumDev)

