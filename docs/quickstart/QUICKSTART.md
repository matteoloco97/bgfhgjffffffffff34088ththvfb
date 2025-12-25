# ⚡ QUICKSTART - QuantumDev Max Setup in 5 Minuti

Questa guida ti permette di attivare QuantumDev Max in meno di 5 minuti.

---

## 📋 Prerequisiti

- ✅ QuantumDev già installato e funzionante
- ✅ Redis in esecuzione
- ✅ Python 3.10+
- ✅ Accesso SSH al server

---

## 🚀 Step 1: Verifica Struttura

I nuovi moduli sono già presenti in `core/`:

```bash
ls -la core/
# Verifica che esistano:
# - conversational_memory.py
# - function_calling.py
# - reasoning_traces.py
# - artifacts.py
# - master_orchestrator.py
# - register_tools.py
```

---

## 🔧 Step 2: Configura .env

Aggiungi queste variabili al tuo `.env`:

```bash
# Apri il file .env
nano .env

# Aggiungi alla fine:
# === QUANTUMDEV MAX ===
ENABLE_CONVERSATIONAL_MEMORY=true
ENABLE_FUNCTION_CALLING=true
ENABLE_REASONING_TRACES=true
ENABLE_ARTIFACTS=true
MAX_CONTEXT_TOKENS=32000
SLIDING_WINDOW_SIZE=10
SUMMARIZATION_THRESHOLD=20
SESSION_TTL=604800
ARTIFACT_TTL=604800
MAX_ORCHESTRATION_TURNS=5
```

Salva con `Ctrl+X`, `Y`, `Enter`.

---

## 🔄 Step 3: Restart Service

```bash
sudo systemctl restart quantum-api
```

Verifica lo stato:

```bash
sudo systemctl status quantum-api
```

---

## ✅ Step 4: Test Rapido

### Test Health

```bash
curl http://127.0.0.1:8081/healthz | jq
```

Dovresti vedere le nuove features abilitate.

### Test Memory

```bash
# Prima richiesta
curl -X POST http://127.0.0.1:8081/chat \
  -H "Content-Type: application/json" \
  -d '{
    "source": "test",
    "source_id": "user1",
    "text": "Mi chiamo Matteo e lavoro con AI"
  }' | jq '.reply'

# Seconda richiesta (deve ricordare)
curl -X POST http://127.0.0.1:8081/chat \
  -H "Content-Type: application/json" \
  -d '{
    "source": "test",
    "source_id": "user1",
    "text": "Come mi chiamo?"
  }' | jq '.reply'
```

Se ricorda il tuo nome, la memoria funziona! ✅

### Test Function Calling

```bash
curl -X POST http://127.0.0.1:8081/chat \
  -H "Content-Type: application/json" \
  -d '{
    "source": "test",
    "source_id": "user1",
    "text": "Quanto fa 15 * 7 + 23?"
  }' | jq '.reply'
```

### Test Artifacts (Code)

```bash
curl -X POST http://127.0.0.1:8081/chat \
  -H "Content-Type: application/json" \
  -d '{
    "source": "test",
    "source_id": "user1",
    "text": "Scrivi una funzione Python per il fattoriale"
  }' | jq '.reply'
```

---

## 🧪 Step 5: Test Moduli Singoli

```bash
cd /root/quantumdev-open

# Test memoria
python -c "
import asyncio
from core.conversational_memory import get_conversational_memory
async def test():
    mem = get_conversational_memory()
    session = await mem.get_or_create_session('test', 'u1')
    print(f'Session ID: {session.session_id}')
    print('✅ Memory OK')
asyncio.run(test())
"

# Test function calling
python -c "
from core.function_calling import get_registry
registry = get_registry()
tools = registry.list_tools()
print(f'Tools registrati: {len(tools)}')
for t in tools:
    print(f'  - {t.name}')
print('✅ Function Calling OK')
"

# Test artifacts
python -c "
import asyncio
from core.artifacts import get_artifacts_manager
async def test():
    mgr = get_artifacts_manager()
    art = await mgr.create_code('Test', 'print(\"hello\")', 'python')
    print(f'Artifact: {art.id}')
    await mgr.delete(art.id)
    print('✅ Artifacts OK')
asyncio.run(test())
"
```

---

## 🎉 Fatto!

QuantumDev Max è ora attivo con:

- ✅ Memoria conversazionale 32K
- ✅ Tool orchestration autonoma
- ✅ Reasoning traces
- ✅ Sistema artifacts

---

## 🔥 Prossimi Passi

1. **Telegram Bot**: I nuovi comandi sono già disponibili
2. **Custom Tools**: Vedi [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md)
3. **Best Practices**: Vedi [EXAMPLES_AND_BEST_PRACTICES.md](EXAMPLES_AND_BEST_PRACTICES.md)

---

## ❓ Troubleshooting

### Il service non parte?

```bash
sudo journalctl -u quantum-api -f --lines=50
```

### Redis non connette?

```bash
redis-cli ping
# Deve rispondere: PONG
```

### Memoria non funziona?

```bash
redis-cli GET "session:test:user1"
# Deve mostrare i dati della sessione
```

### Tool non registrati?

```bash
python -c "from core.register_tools import ensure_tools_registered; ensure_tools_registered()"
```

---

## 📞 Supporto

Se qualcosa non funziona:
1. Controlla i log: `sudo journalctl -u quantum-api -f`
2. Verifica Redis: `redis-cli info`
3. Testa i moduli singolarmente
4. Contatta Matteo

---

**Tempo totale: ~5 minuti** ⏱️

**QuantumDev Max: Ready to go!** 🚀
