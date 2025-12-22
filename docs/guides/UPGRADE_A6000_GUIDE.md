# 🚀 QuantumDev v5 - Guida Upgrade per GPU A6000 48GB

## 📋 Panoramica Modifiche

Questa guida documenta tutte le ottimizzazioni applicate per massimizzare le prestazioni dell'AI con una GPU NVIDIA A6000 da 48GB VRAM.

---

## 🔧 Modifiche Applicate

### 1. Configurazione LLM (`core/chat_engine.py`)

| Parametro | Prima | Dopo | Beneficio |
|-----------|-------|------|-----------|
| `LLM_MAX_CTX` | 32K | 64K | Più contesto per conversazioni lunghe |
| `LLM_MAX_TOKENS` | 2048 | 4096 | Risposte più complete e articolate |
| `LLM_SAFETY_MARGIN_TOK` | 512 | 1024 | Margine maggiore per stabilità |
| `LLM_HTTP_TIMEOUT_S` | 60s | 180s | Tempo per risposte lunghe (32B model) |
| `RETRY_ATTEMPTS` | 2 | 3 | Maggiore resilienza |

### 2. Preset LLM (`core/llm_config.py`)

**Nuovi preset ottimizzati:**

| Preset | max_tokens | Temperatura | Uso |
|--------|-----------|-------------|-----|
| `chat` | 4096 | 0.7 | Conversazione standard |
| `chat_extended` | 8192 | 0.7 | Topic complessi |
| `code_generation` | 8192 | 0.3 | Codice production-ready |
| `code_debug` | 4096 | 0.2 | Debug e analisi |
| `reasoning` | 6000 | 0.2 | Chain-of-thought |
| `research` | 6000 | 0.4 | Sintesi ricerca |

### 3. Code Agent (`agents/code_agent.py`)

**Miglioramenti:**
- Prompt ottimizzati per codice production-ready
- Best practices per linguaggio specifico (Python, JS, TS, Go, Rust)
- Debug con root cause analysis
- Test generation con coverage matrix
- Timeout aumentato a 60s
- Max tokens per codice: 8192

### 4. Memoria Conversazionale (`core/conversational_memory.py`)

| Parametro | Prima | Dopo |
|-----------|-------|------|
| Sliding Window | 20 turni | 30 turni |
| Summarization | dopo 30 turni | dopo 40 turni |
| Session TTL | 30 giorni | 90 giorni |
| Token Limit | 4000 | 8000 |

### 5. Web Research (`agents/web_research_agent.py`)

| Parametro | Prima | Dopo |
|-----------|-------|------|
| Budget Token | 2000 | 4000 |
| Max Documenti | 5 | 8 |
| Max Steps | 3 | 4 |
| Concurrent Fetch | 4 | 6 |
| Timeout | 5s | 8s |

---

## ⚙️ Configurazione `.env`

### File da Usare

Copia `ENV_A6000_48GB_OPTIMIZED.env` nel tuo `.env`:

```bash
cp "Contabo VPS/quantumdev-open/ENV_A6000_48GB_OPTIMIZED.env" .env
```

### Variabili Critiche

```env
# Endpoint - OBBLIGATORIO
LLM_ENDPOINT=http://127.0.0.1:5000/v1

# Modello
LLM_MODEL=DeepSeek-R1-Distill-Qwen-32B-abliterated-Q6_K

# Context Window (A6000 può gestire 64K)
LLM_MAX_CTX=65536
LLM_MAX_TOKENS=4096

# Timeout (modello 32B richiede più tempo)
LLM_HTTP_TIMEOUT_S=180.0

# Features
ENABLE_CONVERSATIONAL_MEMORY=true
ENABLE_FUNCTION_CALLING=true
ENABLE_REASONING_TRACES=true
```

---

## 🖥️ Configurazione GPU Vast.ai

### Avvio Ottimizzato del Server

Sul terminale Vast.ai, usa questi parametri nel comando di avvio:

```bash
cd /workspace/text-generation-webui/

# Avvio con parametri ottimizzati per A6000 48GB
./start_linux.sh --listen --api --api-port 5000 \
    --model DeepSeek-R1-Distill-Qwen-32B-abliterated-Q6_K.gguf \
    --loader llama.cpp \
    --n-gpu-layers 100 \
    --n_ctx 65536 \
    --threads 8 \
    --threads_batch 8 \
    --flash-attn \
    --mlock
```

### Parametri Spiegati

| Parametro | Valore | Spiegazione |
|-----------|--------|-------------|
| `--n_ctx` | 65536 | Context window 64K |
| `--n-gpu-layers` | 100 | Tutti i layer su GPU |
| `--flash-attn` | - | Attention velocizzata |
| `--mlock` | - | Blocca modello in RAM |
| `--threads` | 8 | Thread CPU per operazioni |

---

## 🔌 Dipendenze Aggiuntive

Non sono necessarie nuove dipendenze. Tutte le ottimizzazioni utilizzano le librerie già presenti.

### Verifica Dipendenze (opzionale)

```bash
pip install -r requirements.txt
```

---

## ✅ Checklist Upgrade

1. **GPU Vast.ai:**
   - [ ] Aggiorna comando di avvio con nuovi parametri
   - [ ] Verifica che `--n_ctx 65536` funzioni
   - [ ] Riavvia server in tmux

2. **VPS Contabo:**
   - [ ] Copia nuovo `.env` da `ENV_A6000_48GB_OPTIMIZED.env`
   - [ ] Riavvia backend: `python -m backend.quantum_api`
   - [ ] Verifica tunnel SSH attivo

3. **Test:**
   - [ ] Testa chat con domanda lunga
   - [ ] Testa generazione codice
   - [ ] Testa ricerca web
   - [ ] Verifica tempi di risposta

---

## 📊 Risultati Attesi

Con queste ottimizzazioni dovresti vedere:

| Metrica | Miglioramento |
|---------|---------------|
| Context Window | 2x (32K → 64K) |
| Lunghezza Risposte | 2x più lunghe |
| Qualità Codice | Prompt ottimizzati per production |
| Memoria | 3x più turni ricordati |
| Ricerca Web | 2x più fonti analizzate |

---

## 🐛 Troubleshooting

### Timeout su risposte lunghe

Se ricevi timeout, verifica:
```env
LLM_HTTP_TIMEOUT_S=180.0  # o più alto se necessario
```

### Out of Memory sulla GPU

Se la GPU esaurisce memoria:
```bash
# Riduci context window
--n_ctx 49152  # 48K invece di 64K
```

### Tunnel SSH disconnesso

Script auto-reconnect per Contabo:
```bash
while true; do
    ssh -o ServerAliveInterval=60 -N -L 5000:localhost:5000 root@IP_HOST -p PORT_SSH
    echo "Tunnel disconnesso, riconnessione in 5s..."
    sleep 5
done
```

---

## 📚 File Modificati

1. `core/chat_engine.py` - Parametri LLM
2. `core/llm_config.py` - Preset
3. `core/conversational_memory.py` - Memoria
4. `core/master_orchestrator.py` - Context tokens
5. `agents/code_agent.py` - Code generation
6. `agents/web_research_agent.py` - Web research
7. `ENV_A6000_48GB_OPTIMIZED.env` - Configurazione completa (NUOVO)

---

## 🎯 Prossimi Passi Consigliati

1. **Streaming Response**: Implementare streaming per feedback immediato
2. **Batch Inference**: Aggregare query simili per efficienza
3. **GPU Monitoring**: Aggiungere metriche VRAM/utilizzo
4. **Fine-tuning**: Considerare LoRA per task specifici

---

*Documento generato per QuantumDev v5 - Ottimizzato per A6000 48GB*
