# 📖 INTEGRATION GUIDE - QuantumDev Max

Guida completa per l'integrazione e il deployment di QuantumDev Max.

---

## 📑 Indice

1. [Architettura Dettagliata](#-architettura-dettagliata)
2. [Setup Ambiente](#-setup-ambiente)
3. [Configurazione Moduli](#-configurazione-moduli)
4. [Integrazione API](#-integrazione-api)
5. [Custom Tools](#-custom-tools)
6. [Telegram Bot Extended](#-telegram-bot-extended)
7. [Monitoraggio](#-monitoraggio)
8. [Troubleshooting Avanzato](#-troubleshooting-avanzato)

---

## 🏗️ Architettura Dettagliata

### Flusso di una Richiesta

```
1. User Request → Telegram/API
         ↓
2. Master Orchestrator
         ↓
3. Load Memory Context ←─────────────────┐
         ↓                               │
4. Analyze Query (QueryAnalyzer)         │
         ↓                               │
5. Strategy Decision                     │
   ├─ DIRECT_LLM → LLM call             │
   ├─ TOOL_ASSISTED → Function Caller   │
   └─ MEMORY_RECALL → Memory Search     │
         ↓                               │
6. Execute Strategy                      │
         ↓                               │
7. Generate Response                     │
         ↓                               │
8. Extract Artifacts                     │
         ↓                               │
9. Save to Memory ───────────────────────┘
         ↓
10. Return Response
```

### Componenti

| Componente | File | Responsabilità |
|------------|------|----------------|
| Memory | `conversational_memory.py` | Gestione sessioni, sliding window, summarization |
| Tools | `function_calling.py` | Registry tool, orchestrazione, esecuzione |
| Traces | `reasoning_traces.py` | Tracciamento pensiero, performance |
| Artifacts | `artifacts.py` | Contenuti strutturati, persistenza |
| Orchestrator | `master_orchestrator.py` | Coordinamento centrale |
| Tool Registry | `register_tools.py` | Registrazione tool disponibili |

---

## 🔧 Setup Ambiente

### 1. Requisiti Sistema

```bash
# VPS (Contabo)
CPU: 6+ vCPU
RAM: 12GB+
Storage: 100GB SSD
OS: Ubuntu 22.04

# GPU Server
GPU: RTX 8000 (48GB VRAM)
RAM: 32GB
Storage: 200GB NVMe
```

### 2. Dipendenze Python

```bash
# Requirements già installati con QuantumDev base
# Nessuna nuova dipendenza richiesta per QuantumDev Max

# Verifica versioni
python --version  # 3.10+
pip show redis    # redis-py
pip show fastapi  # FastAPI
```

### 3. Redis Setup

```bash
# Verifica Redis
redis-cli ping
# → PONG

# Verifica memoria disponibile
redis-cli info memory | grep used_memory_human

# Configura maxmemory (opzionale)
redis-cli config set maxmemory 1gb
redis-cli config set maxmemory-policy allkeys-lru
```

---

## ⚙️ Configurazione Moduli

### Conversational Memory

```python
# ENV
ENABLE_CONVERSATIONAL_MEMORY=true
MAX_CONTEXT_TOKENS=32000        # 32K context window
SLIDING_WINDOW_SIZE=10          # Ultimi 10 turni
SUMMARIZATION_THRESHOLD=20      # Summarize dopo 20 turni
SESSION_TTL=604800              # 7 giorni

# Uso programmatico
from core.conversational_memory import get_conversational_memory

memory = get_conversational_memory(llm_func=your_llm_function)

# Get/Create session
session = await memory.get_or_create_session("tg", "user123")

# Add turn
await memory.add_turn(
    source="tg",
    source_id="user123",
    user_message="Ciao, parlami di Python",
    assistant_response="Python è un linguaggio..."
)

# Build context for LLM
context = memory.build_context(session, max_tokens=4000)

# Search history
results = await memory.search_history("tg", "user123", "Python")

# Get stats
stats = await memory.get_session_stats("tg", "user123")
```

### Function Calling

```python
# ENV
ENABLE_FUNCTION_CALLING=true
MAX_ORCHESTRATION_TURNS=5
TOOL_TIMEOUT_S=30

# Registra un nuovo tool
from core.function_calling import register_tool, ToolCategory, ToolParameter

@register_tool(
    name="my_tool",
    description="Descrizione del tool",
    category=ToolCategory.SPECIALIZED,
    parameters=[
        ToolParameter("param1", "string", "Descrizione param1"),
        ToolParameter("param2", "number", "Opzionale", required=False, default=10),
    ],
    examples=["esempio query 1", "esempio query 2"],
    timeout_s=15,
)
async def my_tool(param1: str, param2: int = 10):
    # Implementazione
    result = await do_something(param1, param2)
    return {"status": "ok", "result": result}

# Uso del caller
from core.function_calling import get_function_caller

caller = get_function_caller(llm_func=your_llm)

# Call singolo tool
result = await caller.call_tool("calculator", {"expression": "2+2"})

# Orchestrazione multi-tool
result = await caller.orchestrate("Cerca il prezzo BTC e calcola 10% di commissione")
```

### Reasoning Traces

```python
# ENV
ENABLE_REASONING_TRACES=true
VERBOSE_REASONING=false         # Set true per debug

# Uso programmatico
from core.reasoning_traces import get_reasoning_tracer, ThinkingType

tracer = get_reasoning_tracer()

# Start trace
trace = tracer.start_trace("Query dell'utente")

# Add steps
step = tracer.add_step(ThinkingType.ANALYSIS, "Analyzing query")
# ... do work ...
tracer.complete_step(step, "Analysis complete")

# Complete trace
result = tracer.complete_trace(final_answer="Risposta", success=True)

# Using context managers (più elegante)
from core.reasoning_traces import analyze, plan, execute, synthesize

with analyze("Understanding the problem"):
    # Analysis code
    pass

with plan("Creating approach"):
    # Planning code
    pass

with execute("Running tools"):
    # Execution code
    pass

with synthesize("Generating response"):
    # Synthesis code
    pass
```

### Artifacts

```python
# ENV
ENABLE_ARTIFACTS=true
ARTIFACT_TTL=604800             # 7 giorni

# Uso programmatico
from core.artifacts import get_artifacts_manager, ArtifactType

manager = get_artifacts_manager()

# Create code artifact
code_artifact = await manager.create_code(
    title="Hello World",
    code="print('Hello!')",
    language="python",
    source="tg",
    source_id="user123",
)

# Create table artifact
table_artifact = await manager.create_table(
    title="Comparison",
    headers=["Name", "Value"],
    rows=[["A", 1], ["B", 2]],
    source="tg",
    source_id="user123",
)

# Create JSON artifact
json_artifact = await manager.create_json(
    title="API Response",
    data={"status": "ok", "items": [1, 2, 3]},
    source="tg",
    source_id="user123",
)

# Get artifact
artifact = await manager.get(artifact_id)

# List user artifacts
user_artifacts = await manager.list_user_artifacts("tg", "user123", limit=10)

# Search
results = await manager.search_artifacts("python", source="tg", source_id="user123")
```

---

## 🔌 Integrazione API

### Master Orchestrator

```python
from core.master_orchestrator import get_master_orchestrator

orchestrator = get_master_orchestrator(llm_func=your_llm)

# Process query
result = await orchestrator.process(
    query="Scrivi una funzione Python per sorting",
    source="api",
    source_id="user123",
    show_reasoning=True,
    create_artifacts=True,
)

# Result structure
{
    "response": "Ecco la funzione...",
    "query": "...",
    "query_type": "code",
    "strategy": "direct_llm",
    "artifacts": [...],
    "tool_results": [...],
    "duration_ms": 1234,
    "success": True,
    "reasoning_trace": {...}  # if show_reasoning=True
}

# Get session info
info = await orchestrator.get_session_info("api", "user123")

# Clear session
await orchestrator.clear_session("api", "user123")
```

### Endpoint API (quantum_api.py)

Aggiungi questi endpoint al tuo `quantum_api.py`:

```python
# Endpoint per session info
@app.get("/session/info")
async def session_info(source: str, source_id: str):
    from core.master_orchestrator import get_master_orchestrator
    orchestrator = get_master_orchestrator()
    return await orchestrator.get_session_info(source, source_id)

# Endpoint per clear session
@app.post("/session/clear")
async def session_clear(source: str = Body(...), source_id: str = Body(...)):
    from core.master_orchestrator import get_master_orchestrator
    orchestrator = get_master_orchestrator()
    success = await orchestrator.clear_session(source, source_id)
    return {"ok": success}

# Endpoint per artifacts list
@app.get("/artifacts/list")
async def artifacts_list(source: str, source_id: str, limit: int = 20):
    from core.artifacts import get_artifacts_manager
    manager = get_artifacts_manager()
    artifacts = await manager.list_user_artifacts(source, source_id, limit)
    return {"artifacts": [a.to_dict() for a in artifacts]}

# Endpoint per artifact by id
@app.get("/artifact/{artifact_id}")
async def get_artifact(artifact_id: str):
    from core.artifacts import get_artifacts_manager
    manager = get_artifacts_manager()
    artifact = await manager.get(artifact_id)
    if not artifact:
        return {"error": "Not found"}
    return artifact.to_dict()
```

---

## 🔧 Custom Tools

### Template Completo

```python
# my_custom_tools.py
from core.function_calling import register_tool, ToolCategory, ToolParameter
import logging

log = logging.getLogger(__name__)

@register_tool(
    name="stock_analyzer",
    description="Analizza performance di un'azione con indicatori tecnici",
    category=ToolCategory.DATA,
    parameters=[
        ToolParameter("symbol", "string", "Simbolo azione (es: AAPL, TSLA)"),
        ToolParameter("period", "string", "Periodo: 1d, 1w, 1m, 3m, 1y", required=False, default="1m"),
        ToolParameter("indicators", "array", "Indicatori: RSI, MACD, SMA", required=False),
    ],
    examples=[
        "analizza AAPL ultimo mese",
        "performance TSLA con RSI e MACD",
    ],
    requires_confirmation=False,
    timeout_s=20,
)
async def stock_analyzer(
    symbol: str,
    period: str = "1m",
    indicators: list = None
) -> dict:
    """
    Analizza un'azione con indicatori tecnici.
    """
    try:
        # Fetch data
        data = await fetch_stock_data(symbol, period)
        
        # Calculate indicators
        result = {
            "symbol": symbol,
            "period": period,
            "current_price": data["price"],
            "change_percent": data["change"],
        }
        
        if indicators:
            if "RSI" in indicators:
                result["rsi"] = calculate_rsi(data)
            if "MACD" in indicators:
                result["macd"] = calculate_macd(data)
            if "SMA" in indicators:
                result["sma"] = calculate_sma(data)
        
        return result
        
    except Exception as e:
        log.error(f"Stock analyzer error: {e}")
        return {"error": str(e), "symbol": symbol}
```

### Registrazione Automatica

```python
# Nel tuo __init__.py o startup
from core.register_tools import ensure_tools_registered
import my_custom_tools  # importa per registrare

# Verifica
from core.function_calling import get_registry
registry = get_registry()
print(f"Tools: {[t.name for t in registry.list_tools()]}")
```

---

## 📱 Telegram Bot Extended

### Nuovi Comandi

Aggiungi questi handler al bot:

```python
# /context - mostra stats sessione
async def context_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from core.master_orchestrator import get_master_orchestrator
    orchestrator = get_master_orchestrator()
    
    info = await orchestrator.get_session_info("tg", str(update.effective_chat.id))
    
    lines = [
        "📊 **Session Info**",
        f"Turni: {info.get('session', {}).get('turn_count', 0)}",
        f"Messaggi: {info.get('session', {}).get('message_count', 0)}",
        f"Token usati: {info.get('session', {}).get('total_tokens', 0)}",
        f"Artifacts: {info.get('recent_artifacts', 0)}",
    ]
    
    await update.message.reply_text("\n".join(lines))

# /think <query> - mostra reasoning
async def think_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else ""
    if not query:
        return await update.message.reply_text("Uso: /think <query>")
    
    from core.master_orchestrator import get_master_orchestrator
    orchestrator = get_master_orchestrator(llm_func=your_llm)
    
    result = await orchestrator.process(
        query=query,
        source="tg",
        source_id=str(update.effective_chat.id),
        show_reasoning=True,
    )
    
    # Format reasoning
    trace = result.reasoning_trace or {}
    steps = trace.get("steps", [])
    
    lines = ["🧠 **Reasoning Trace**\n"]
    for step in steps:
        status = "✅" if step["status"] == "completed" else "❌"
        lines.append(f"{status} {step['title']} ({step['duration_ms']}ms)")
    
    lines.append(f"\n📝 **Response:**\n{result.response[:2000]}")
    
    await update.message.reply_text("\n".join(lines))

# /artifacts - lista artifacts
async def artifacts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from core.artifacts import get_artifacts_manager
    manager = get_artifacts_manager()
    
    artifacts = await manager.list_user_artifacts(
        "tg",
        str(update.effective_chat.id),
        limit=10
    )
    
    if not artifacts:
        return await update.message.reply_text("Nessun artifact salvato.")
    
    lines = ["📦 **Your Artifacts:**\n"]
    for art in artifacts:
        lines.append(f"• `{art.id}` - {art.title} ({art.type.value})")
    
    await update.message.reply_text("\n".join(lines))

# /artifact <id> - mostra artifact
async def artifact_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    artifact_id = context.args[0] if context.args else ""
    if not artifact_id:
        return await update.message.reply_text("Uso: /artifact <id>")
    
    from core.artifacts import get_artifacts_manager
    manager = get_artifacts_manager()
    
    artifact = await manager.get(artifact_id)
    if not artifact:
        return await update.message.reply_text("Artifact non trovato.")
    
    await update.message.reply_text(artifact.format_display(max_lines=30))

# /reset - clear session
async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from core.master_orchestrator import get_master_orchestrator
    orchestrator = get_master_orchestrator()
    
    success = await orchestrator.clear_session("tg", str(update.effective_chat.id))
    
    if success:
        await update.message.reply_text("🔄 Sessione resettata. La memoria è stata cancellata.")
    else:
        await update.message.reply_text("⚠️ Errore nel reset della sessione.")

# Registra handlers
app.add_handler(CommandHandler("context", context_cmd))
app.add_handler(CommandHandler("think", think_cmd))
app.add_handler(CommandHandler("artifacts", artifacts_cmd))
app.add_handler(CommandHandler("artifact", artifact_cmd))
app.add_handler(CommandHandler("reset", reset_cmd))
```

---

## 📊 Monitoraggio

### Log Importanti

```bash
# Tutti i log
sudo journalctl -u quantum-api -f

# Filtra per modulo
sudo journalctl -u quantum-api -f | grep "ConversationalMemory"
sudo journalctl -u quantum-api -f | grep "FunctionCaller"
sudo journalctl -u quantum-api -f | grep "Orchestrator"
```

### Metriche Redis

```bash
# Sessioni attive
redis-cli keys "session:*" | wc -l

# Artifacts
redis-cli keys "artifact:*" | wc -l

# Memoria usata
redis-cli info memory | grep used_memory_human

# TTL di una sessione
redis-cli ttl "session:tg:123456"
```

### Health Check Esteso

```python
@app.get("/healthz/extended")
async def healthz_extended():
    from core.master_orchestrator import get_master_orchestrator
    from core.function_calling import get_registry
    
    orchestrator = get_master_orchestrator()
    registry = get_registry()
    
    return {
        "features": {
            "memory": ENABLE_CONVERSATIONAL_MEMORY,
            "tools": ENABLE_FUNCTION_CALLING,
            "traces": ENABLE_REASONING_TRACES,
            "artifacts": ENABLE_ARTIFACTS,
        },
        "tools_count": len(registry.list_tools()),
        "tools": [t.name for t in registry.list_tools()],
        "config": {
            "max_context_tokens": MAX_CONTEXT_TOKENS,
            "sliding_window": SLIDING_WINDOW_SIZE,
            "summarize_threshold": SUMMARIZATION_THRESHOLD,
        },
    }
```

---

## 🔧 Troubleshooting Avanzato

### Memoria non Salva

```python
# Test diretto Redis
import redis
r = redis.Redis(host='localhost', port=6379, db=0)
r.set("test_key", "test_value")
print(r.get("test_key"))  # b'test_value'

# Test sessione
from core.conversational_memory import get_conversational_memory
import asyncio

async def test():
    mem = get_conversational_memory()
    session = await mem.get_or_create_session("test", "debug")
    await mem.add_turn("test", "debug", "Hello", "Hi there!")
    
    # Verifica in Redis
    import redis
    r = redis.Redis(decode_responses=True)
    data = r.get("session:test:debug")
    print(data)

asyncio.run(test())
```

### Tool Non Eseguito

```python
# Debug tool execution
from core.function_calling import get_function_caller, get_registry

registry = get_registry()
tool = registry.get("calculator")
print(f"Tool found: {tool is not None}")
print(f"Tool enabled: {tool.enabled if tool else 'N/A'}")

# Test diretto
import asyncio
from core.function_calling import calculator_tool

result = asyncio.run(calculator_tool("2+2"))
print(result)
```

### Reasoning Trace Vuoto

```python
# Verifica abilitazione
import os
print(f"ENABLE_REASONING_TRACES: {os.getenv('ENABLE_REASONING_TRACES')}")

# Test manuale
from core.reasoning_traces import get_reasoning_tracer

tracer = get_reasoning_tracer(enabled=True)
trace = tracer.start_trace("Test query")
tracer.analysis("Test step", "Content")
result = tracer.complete_trace("Final answer")
print(result.to_dict())
```

### Performance Lenta

```python
# Profiling
import time

async def profile_orchestration():
    from core.master_orchestrator import get_master_orchestrator
    
    orchestrator = get_master_orchestrator(llm_func=mock_llm)
    
    start = time.perf_counter()
    result = await orchestrator.process("Test query", "test", "user1")
    duration = time.perf_counter() - start
    
    print(f"Total: {duration*1000:.0f}ms")
    print(f"Reported: {result.duration_ms}ms")
    print(f"Steps: {len(result.reasoning_trace.get('steps', []))}")
```

---

## 📞 Supporto

1. **Log**: `sudo journalctl -u quantum-api -f`
2. **Redis**: `redis-cli monitor`
3. **Test moduli**: `python -m core.<module_name>`
4. **Contatta Matteo**

---

**QuantumDev Max - Integration Complete** 🚀
