# Environment Variables Reference

Questa documentazione elenca tutte le variabili d'ambiente configurabili per Jarvis/QuantumDev.

> **Version 4.0.0 - QuantumDev Max Uncensored** 🚀🧠

---

## QuantumDev Max Features (OTTIMIZZATO v4)

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_CONVERSATIONAL_MEMORY` | `true` | Abilita memoria conversazionale 64K |
| `ENABLE_FUNCTION_CALLING` | `true` | Abilita orchestrazione tool autonoma |
| `ENABLE_REASONING_TRACES` | `true` | Abilita tracciamento ragionamento |
| `ENABLE_ARTIFACTS` | `true` | Abilita sistema artifacts |
| `ENABLE_PROACTIVE_SUGGESTIONS` | `true` | Suggerimenti proattivi (abilitato) |
| `VERBOSE_REASONING` | `false` | Mostra log dettagliati reasoning |

## Context Management (OTTIMIZZATO v4)

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_CONTEXT_TOKENS` | `65536` | Finestra contesto massima (64K - aumentato) |
| `SLIDING_WINDOW_SIZE` | `20` | Ultimi N turni in sliding window (aumentato) |
| `SUMMARIZATION_THRESHOLD` | `30` | Turni prima di auto-summarization (aumentato) |
| `SUMMARIZATION_TOKEN_LIMIT` | `4000` | Max token per summarization (aumentato) |
| `SESSION_TTL` | `2592000` | TTL sessioni in secondi (30 giorni - aumentato) |
| `CONVERSATION_TTL_DAYS` | `30` | Durata conversazioni in giorni (aumentato) |
| `PERSIST_ARCHIVE_ENABLED` | `true` | Archiviazione sessioni (abilitato) |
| `ARTIFACT_TTL` | `604800` | TTL artifacts in secondi (7 giorni) |
| `MAX_ARTIFACTS_PER_USER` | `100` | Max artifacts salvati per utente |

## Personal Memory System (OTTIMIZZATO v4)

| Variable | Default | Description |
|----------|---------|-------------|
| `USER_PROFILE_ENABLED` | `true` | Abilita memoria profilo utente |
| `USER_PROFILE_MAX_AGE_DAYS` | `3650` | Ritenzione fatti utente (10 anni) |
| `EPISODIC_MEMORY_ENABLED` | `true` | Abilita memoria episodica |
| `EPISODIC_BUFFER_SIZE` | `20` | Messaggi prima di summarization (aumentato) |
| `EPISODIC_BUFFER_TOKEN_LIMIT` | `4000` | Token limit buffer (aumentato) |
| `EPISODIC_MAX_AGE_DAYS` | `365` | Ritenzione memoria episodica (1 anno) |
| `MEMORY_PROFILE_TOP_K` | `10` | Fatti profilo da recuperare (aumentato) |
| `MEMORY_EPISODIC_TOP_K` | `5` | Riassunti episodici da recuperare (aumentato) |
| `MEMORY_MAX_CONTEXT_TOKENS` | `2000` | Token massimi per contesto memoria (aumentato) |

## Tool Orchestration (NEW)

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_ORCHESTRATION_TURNS` | `5` | Max turni orchestrazione multi-tool |
| `TOOL_TIMEOUT_S` | `30` | Timeout singolo tool (secondi) |

---

## LLM Configuration (OTTIMIZZATO v4)

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_ENDPOINT` | - | URL dell'endpoint LLM (es: `http://localhost:8080`) |
| `TUNNEL_ENDPOINT` | - | URL del tunnel Cloudflare (opzionale) |
| `LLM_MODEL` | `qwen2.5-32b-awq` | Nome del modello LLM |
| `LLM_TEMPERATURE` | `0.75` | Temperatura per la generazione (aumentato) |
| `LLM_MAX_TOKENS` | `2048` | Max token per risposta (aumentato) |
| `LLM_MAX_CTX` | `32768` | Contesto massimo in token (aumentato a 32K) |
| `LLM_OUTPUT_BUDGET_TOK` | `2048` | Budget token per output (aumentato) |
| `LLM_SAFETY_MARGIN_TOK` | `512` | Margine sicurezza token (aumentato) |

## Web Search Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `WEB_SUMMARY_BUDGET_TOK` | `1200` | Budget token per sommari web |
| `WEB_EXTRACT_PER_DOC_TOK` | `700` | Token per documento estratto |
| `WEB_SUMMARIZE_TOP_DEFAULT` | `2` | Numero default di documenti da riassumere |
| `WEB_SEARCH_DEEP_MODE` | `false` | Abilita ricerca deep (multi-step) |
| `WEB_DEEP_MAX_SOURCES` | `15` | Max sorgenti in deep mode |
| `WEB_FETCH_TIMEOUT_S` | `3.0` | Timeout fetch pagine (secondi) |
| `WEB_FETCH_MAX_INFLIGHT` | `4` | Max richieste parallele |
| `WEB_READ_TIMEOUT_S` | `6.0` | Timeout lettura pagine |

## Multi-Engine Search Configuration (NEW - SPRINT 1)

| Variable | Default | Description |
|----------|---------|-------------|
| `BRAVE_SEARCH_API_KEY` | - | API key per Brave Search (richiesta per Brave) |
| `BRAVE_SEARCH_ENABLED` | `1` | Abilita Brave Search (`1` = enabled, `0` = disabled) |
| `BRAVE_SEARCH_COUNT` | `10` | Numero risultati da Brave Search per query |
| `SEARCH_ENGINES_ENABLED` | `duckduckgo,brave,bing` | Lista motori (comma-separated) |
| `MULTI_ENGINE_DEDUP_THRESHOLD` | `0.85` | Threshold fuzzy dedup URL (0.0-1.0) |

## Live Agents Cache TTL (in secondi)

| Variable | Default | Description |
|----------|---------|-------------|
| `LIVE_CACHE_TTL_WEATHER` | `1800` | TTL cache meteo (30 min) |
| `LIVE_CACHE_TTL_PRICE` | `60` | TTL cache prezzi (1 min) |
| `LIVE_CACHE_TTL_SPORTS` | `300` | TTL cache sport (5 min) |
| `LIVE_CACHE_TTL_NEWS` | `600` | TTL cache news (10 min) |
| `LIVE_CACHE_TTL_SCHEDULE` | `3600` | TTL cache calendario (1 ora) |
| `LIVE_AGENT_TIMEOUT_S` | `10.0` | Timeout chiamate live agents |

## Advanced Cache TTL (in secondi)

| Variable | Default | Description |
|----------|---------|-------------|
| `CACHE_TTL_WEATHER` | `1800` | TTL cache weather domain |
| `CACHE_TTL_PRICE` | `60` | TTL cache price domain |
| `CACHE_TTL_SPORTS` | `300` | TTL cache sports domain |
| `CACHE_TTL_NEWS` | `600` | TTL cache news domain |
| `CACHE_TTL_SCHEDULE` | `3600` | TTL cache schedule domain |
| `CACHE_TTL_GENERIC` | `21600` | TTL cache generico (6 ore) |

## API Keys (External Services)

| Variable | Default | Description |
|----------|---------|-------------|
| `ALPHA_VANTAGE_API_KEY` | `demo` | API key Alpha Vantage (azioni/forex) |
| `COINGECKO_API_KEY` | - | API key CoinGecko Pro (opzionale) |
| `FOOTBALL_DATA_API_KEY` | - | API key football-data.org |
| `NEWSAPI_KEY` | - | API key NewsAPI.org |
| `GNEWS_API_KEY` | - | API key GNews (alternativa) |
| `ODDS_API_KEY` | - | API key per quote betting (opzionale) |

## Betting/Trading Agent Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `BETTING_API_TIMEOUT` | `10.0` | Timeout chiamate betting API |
| `TRADING_API_TIMEOUT` | `10.0` | Timeout chiamate trading API |
| `LIVE_CACHE_TTL_BETTING` | `300` | TTL cache betting (5 min) |
| `LIVE_CACHE_TTL_TRADING` | `120` | TTL cache trading (2 min) |

## Redis Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | `localhost` | Host Redis |
| `REDIS_PORT` | `6379` | Porta Redis |
| `REDIS_DB` | `0` | Database Redis |

## Reranker Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_RERANKER` | `true` | Abilita/disabilita reranker |
| `RERANKER_MODEL` | `BAAI/bge-reranker-base` | Modello reranker |
| `RERANKER_DEVICE` | `cpu` | Device per reranker (cpu/cuda) |

## ChromaDB Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CHROMA_PERSIST_DIR` | `/memory/chroma` | Directory persistenza ChromaDB |
| `EMBEDDING_MODEL_NAME` | `sentence-transformers/all-MiniLM-L6-v2` | Modello embedding |
| `MEM_HALF_LIFE_D` | `7.0` | Half-life memoria (giorni) |

## Semantic Cache

| Variable | Default | Description |
|----------|---------|-------------|
| `SEMCACHE_INIT_ON_STARTUP` | `false` | Inizializza cache al boot |

## Intent Classification

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_INTENT_ENABLED` | `false` | Abilita LLM-based intent classification |
| `INTENT_FEEDBACK_ENABLED` | `false` | Abilita telemetria intent |
| `INTENT_LLM_MIN_CONFIDENCE` | `0.40` | Confidenza minima per LLM intent classification |

## Intelligent Autoweb Configuration (NEW)

| Variable | Default | Description |
|----------|---------|-------------|
| `SEMANTIC_AUTOWEB_ENABLED` | `1` | Abilita analisi semantica per autoweb intelligente |
| `SEMANTIC_MIN_QUERY_LENGTH` | `4` | Lunghezza minima query per analisi semantica (parole) |
| `WEB_SEARCH_DEFAULT_K` | `6` | Numero default di risultati web search |
| `WEB_SEARCH_DEFAULT_SUMMARIZE_TOP` | `3` | Numero default di documenti da riassumere |
| `WEB_SEARCH_TIMEOUT` | `30` | Timeout web search in secondi |

## Search Diversifier

| Variable | Default | Description |
|----------|---------|-------------|
| `DIVERSIFIER_ENABLED` | `true` | Abilita diversificazione risultati |

## Advanced Tools (BLOCK 4)

| Variable | Default | Description |
|----------|---------|-------------|
| `TOOLS_MATH_ENABLED` | `true` | Abilita tool calcolatrice/math |
| `TOOLS_PYTHON_EXEC_ENABLED` | `false` | Abilita esecuzione codice Python (sandbox) |
| `TOOLS_DOCS_ENABLED` | `true` | Abilita upload e RAG su documenti |
| `MAX_UPLOAD_SIZE_MB` | `10` | Dimensione massima file upload (MB) |
| `DOCS_MAX_CHUNKS_PER_FILE` | `500` | Max chunks per documento indicizzato |
| `DOCS_CHUNK_SIZE` | `1000` | Dimensione chunk testo (caratteri) |
| `DOCS_CHUNK_OVERLAP` | `200` | Overlap tra chunks (caratteri) |
| `CHROMA_COLLECTION_USER_DOCS` | `user_docs` | Nome collezione ChromaDB per documenti |

## OCR Tools (BLOCK 5)

| Variable | Default | Description |
|----------|---------|-------------|
| `TOOLS_OCR_ENABLED` | `false` | Abilita OCR su immagini |
| `OCR_MAX_IMAGE_SIZE_MB` | `10` | Dimensione massima immagine OCR (MB) |
| `OCR_DEFAULT_LANG` | `eng+ita` | Lingue default per OCR (es: 'eng', 'ita', 'eng+ita') |

## Security

| Variable | Default | Description |
|----------|---------|-------------|
| `QUANTUM_SHARED_SECRET` | - | Secret per endpoint admin |

## Telegram Bot

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | - | Token bot Telegram |
| `TELEGRAM_STREAMING_ENABLED` | `0` | Abilita risposte progressive (streaming SSE, 1=on, 0=off) |
| `TELEGRAM_SOURCE_PREVIEW` | `0` | Abilita anteprime URL in Telegram |
| `TELEGRAM_SHOW_SOURCES` | `1` | Mostra elenco fonti nei risultati |
| `TELEGRAM_SHOW_CACHE_BADGE` | `1` | Mostra badge "(da cache)" |

---

## Esempio .env minimo

```env
# LLM
LLM_ENDPOINT=http://localhost:8080
LLM_MODEL=qwen2.5-32b-awq

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Telegram (opzionale)
TELEGRAM_BOT_TOKEN=your_bot_token_here

# Admin
QUANTUM_SHARED_SECRET=your_secret_here
```

## Esempio .env completo (con tutti gli agenti)

```env
# === LLM (OTTIMIZZATO v4) ===
LLM_ENDPOINT=http://localhost:8080
TUNNEL_ENDPOINT=https://your-tunnel.trycloudflare.com
LLM_MODEL=qwen2.5-32b-awq
LLM_TEMPERATURE=0.75
LLM_MAX_TOKENS=2048
LLM_MAX_CTX=32768
LLM_OUTPUT_BUDGET_TOK=2048
LLM_SAFETY_MARGIN_TOK=512

# === Redis ===
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# === QuantumDev Max Features (OTTIMIZZATO v4) ===
ENABLE_CONVERSATIONAL_MEMORY=true
ENABLE_FUNCTION_CALLING=true
ENABLE_REASONING_TRACES=true
ENABLE_ARTIFACTS=true
ENABLE_PROACTIVE_SUGGESTIONS=true

# === Context Management (OTTIMIZZATO v4) ===
MAX_CONTEXT_TOKENS=65536
SLIDING_WINDOW_SIZE=20
SUMMARIZATION_THRESHOLD=30
SUMMARIZATION_TOKEN_LIMIT=4000
SESSION_TTL=2592000
CONVERSATION_TTL_DAYS=30
PERSIST_ARCHIVE_ENABLED=true
ARTIFACT_TTL=604800

# === Personal Memory (OTTIMIZZATO v4) ===
USER_PROFILE_ENABLED=1
USER_PROFILE_MAX_AGE_DAYS=3650
EPISODIC_MEMORY_ENABLED=1
EPISODIC_BUFFER_SIZE=20
EPISODIC_BUFFER_TOKEN_LIMIT=4000
EPISODIC_MAX_AGE_DAYS=365
MEMORY_PROFILE_TOP_K=10
MEMORY_EPISODIC_TOP_K=5
MEMORY_MAX_CONTEXT_TOKENS=2000

# === Tool Orchestration ===
MAX_ORCHESTRATION_TURNS=5
TOOL_TIMEOUT_S=30

# === API Keys ===
ALPHA_VANTAGE_API_KEY=your_key_here
NEWSAPI_KEY=your_key_here
FOOTBALL_DATA_API_KEY=your_key_here
ODDS_API_KEY=your_key_here

# === Cache TTL ===
LIVE_CACHE_TTL_WEATHER=1800
LIVE_CACHE_TTL_PRICE=30
LIVE_CACHE_TTL_SPORTS=180
LIVE_CACHE_TTL_NEWS=300
LIVE_CACHE_TTL_BETTING=300
LIVE_CACHE_TTL_TRADING=60

# === Features ===
WEB_SEARCH_DEEP_MODE=true
USE_RERANKER=true
DIVERSIFIER_ENABLED=true
LLM_INTENT_ENABLED=1
INTENT_FEEDBACK_ENABLED=true

# === Tools (BLOCK 4 & 5) ===
TOOLS_MATH_ENABLED=true
TOOLS_PYTHON_EXEC_ENABLED=false
TOOLS_DOCS_ENABLED=true
TOOLS_OCR_ENABLED=true
OCR_MAX_IMAGE_SIZE_MB=20
OCR_DEFAULT_LANG=eng+ita

# === Telegram ===
TELEGRAM_BOT_TOKEN=your_bot_token_here

# === Admin ===
QUANTUM_SHARED_SECRET=your_secret_here
```

---

## Note sulla Configurazione v4

### Cambiamenti Principali

1. **Context Window Esteso**: Da 32K a 64K token per conversazioni più lunghe
2. **Memoria Persistente Estesa**: Fino a 10 anni per fatti personali, 1 anno per conversazioni
3. **Risposte Più Complete**: Max token aumentati da 512 a 2048
4. **Sliding Window Più Ampio**: Da 10 a 20 turni visibili
5. **Suggerimenti Proattivi**: Abilitati di default
6. **Archiviazione Sessioni**: Backup automatico delle conversazioni

### Requisiti Hardware

Con queste impostazioni ottimizzate, assicurati di avere:
- **GPU VRAM**: Almeno 24GB per context window esteso
- **RAM**: Almeno 32GB per ChromaDB e cache
- **Storage**: SSD con almeno 50GB liberi per persistenza

### Personalizzazione

Vedi il file `ENV_OPTIMIZED_V4.env` per una configurazione completa pronta all'uso.
