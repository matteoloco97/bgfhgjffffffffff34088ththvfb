# Environment Variables Reference

Questa documentazione elenca tutte le variabili d'ambiente configurabili per Jarvis/QuantumDev.

## LLM Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_ENDPOINT` | - | URL dell'endpoint LLM (es: `http://localhost:8080`) |
| `TUNNEL_ENDPOINT` | - | URL del tunnel Cloudflare (opzionale) |
| `LLM_MODEL` | `qwen2.5-32b-awq` | Nome del modello LLM |
| `LLM_TEMPERATURE` | `0.7` | Temperatura per la generazione |
| `LLM_MAX_TOKENS` | `512` | Max token per risposta |
| `LLM_MAX_CTX` | `8192` | Contesto massimo in token |
| `LLM_OUTPUT_BUDGET_TOK` | `512` | Budget token per output |
| `LLM_SAFETY_MARGIN_TOK` | `256` | Margine sicurezza token |

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

## Search Diversifier

| Variable | Default | Description |
|----------|---------|-------------|
| `DIVERSIFIER_ENABLED` | `true` | Abilita diversificazione risultati |

## Security

| Variable | Default | Description |
|----------|---------|-------------|
| `QUANTUM_SHARED_SECRET` | - | Secret per endpoint admin |

## Telegram Bot

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | - | Token bot Telegram |

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
# === LLM ===
LLM_ENDPOINT=http://localhost:8080
TUNNEL_ENDPOINT=https://your-tunnel.trycloudflare.com
LLM_MODEL=qwen2.5-32b-awq
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=512

# === Redis ===
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# === API Keys ===
ALPHA_VANTAGE_API_KEY=your_key_here
NEWSAPI_KEY=your_key_here
FOOTBALL_DATA_API_KEY=your_key_here

# === Cache TTL ===
LIVE_CACHE_TTL_WEATHER=1800
LIVE_CACHE_TTL_PRICE=60
LIVE_CACHE_TTL_SPORTS=300
LIVE_CACHE_TTL_NEWS=600

# === Features ===
WEB_SEARCH_DEEP_MODE=true
USE_RERANKER=true
DIVERSIFIER_ENABLED=true

# === Telegram ===
TELEGRAM_BOT_TOKEN=your_bot_token_here

# === Admin ===
QUANTUM_SHARED_SECRET=your_secret_here
```
