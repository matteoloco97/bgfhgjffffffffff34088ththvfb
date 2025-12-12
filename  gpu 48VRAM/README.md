# 🚀 QuantumDev GPU Setup - Qwen 32B AWQ

Setup completo e automatizzato per **Qwen 2.5 32B Instruct AWQ** su GPU Vast.ai con integrazione backend QuantumDev.

## ⚡ Quick Start (3 comandi)

```bash
# 1. Ottieni IP e porta dalla GPU Vast.ai
# (Vedi sezione "Come ottenere credenziali Vast.ai" sotto)

# 2. Esegui quick-start script
cd "/root/quantumdev-open/ gpu 48VRAM"
chmod +x quick-start.sh test-system.sh
./quick-start.sh <GPU_IP> <GPU_PORT>

# 3. Testa il sistema
./test-system.sh
```

**Esempio:**
```bash
./quick-start.sh 154.42.3.37 41234
```

## 📋 Prerequisiti

### GPU Vast.ai
- **GPU richiesta:** NVIDIA A40 48GB (o superiore)
- **Template:** PyTorch 2.x + CUDA 12.1
- **Storage:** Almeno 50GB liberi
- **Rete:** Porta SSH accessibile

### VPS/Server Locale
- **OS:** Ubuntu 20.04+ o Debian 11+
- **Python:** 3.8+
- **Accesso:** Root o sudo
- **Connettività:** SSH client installato

### Credenziali
- Token Telegram Bot: `8102361815:AAGmosNjWnJIBdQehdNrlNcKsoN6ifIbKzc`
- Admin ID: `5015947009`
- Shared Secret: `5e6ad9f7c2b14dceb2f4a1a9087c3da0d4a885c3e85f1b2d47a6f0e9c3b21d77`

## 📖 Guida Step-by-Step

### Step 1: Preparazione Repository

```bash
cd /root/quantumdev-open
ls " gpu 48VRAM"
```

Dovresti vedere:
- `setup_gpu.py` - Script Python per setup GPU
- `.env.gpu` - File configurazione
- `quick-start.sh` - Script deploy automatico
- `test-system.sh` - Script test sistema
- `README.md` - Questa guida
- `QUICK_REFERENCE.md` - Reference rapida

### Step 2: Rent GPU su Vast.ai

1. **Vai su:** https://vast.ai/
2. **Filtra GPU:** 
   - VRAM: >= 48GB
   - GPU Type: A40, A6000, o superiore
   - Disk Space: >= 50GB
3. **Rent instance**
4. **Annota:**
   - IP pubblico (es: `154.42.3.37`)
   - Porta SSH (es: `41234`)

### Step 3: Ottenere SSH Access

Una volta rentata l'istanza:
```bash
# Vast.ai fornisce comando SSH come:
ssh -p 41234 root@154.42.3.37 -L 8080:localhost:8080

# Annota IP e PORT
GPU_IP="154.42.3.37"
GPU_PORT="41234"
```

### Step 4: Eseguire Quick Start

```bash
cd "/root/quantumdev-open/ gpu 48VRAM"
chmod +x quick-start.sh test-system.sh

# Esegui con i tuoi parametri
./quick-start.sh 154.42.3.37 41234
```

**Cosa fa lo script:**
1. ✅ Rileva IP pubblico VPS automaticamente
2. ✅ Configura `.env.gpu` con IP corretto
3. ✅ Testa connessione SSH alla GPU
4. ✅ Upload `setup_gpu.py` e `.env.gpu` su GPU
5. ✅ Esegue setup in background sulla GPU
6. ✅ Monitora progress ogni 30 secondi
7. ✅ Crea systemd service per tunnel persistente
8. ✅ Restart quantum-api e telegram-bot

### Step 5: Monitoring Setup

Il setup richiede **~15 minuti**. Lo script monitora automaticamente, ma puoi controllare manualmente:

```bash
# Log setup sulla GPU
ssh -p 41234 root@154.42.3.37 'tail -f /workspace/setup_qwen.log'

# Log vLLM sulla GPU
ssh -p 41234 root@154.42.3.37 'tail -f /workspace/vllm_qwen.log'

# Status tunnel sul VPS
journalctl -u vast-tunnel -f
```

### Step 6: Verifica Funzionamento

```bash
# Test automatico completo
./test-system.sh

# Test manuale endpoint
curl http://127.0.0.1:9011/v1/models

# Test inference
curl -X POST http://127.0.0.1:9011/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-32b-instruct",
    "messages": [{"role": "user", "content": "Ciao! Come stai?"}],
    "max_tokens": 100
  }'
```

## ⏱️ Timeline Setup

| Fase | Durata | Descrizione |
|------|--------|-------------|
| 🔍 Auto-detect & config | 5-10s | Rileva VPS IP e configura .env |
| 📤 Upload files | 5-10s | Upload setup_gpu.py via SCP |
| 🐍 Python setup | 1-2min | Crea venv e installa pip |
| 📦 Dependencies | 5-8min | PyTorch 2.5.1 + vLLM 0.6.3.post1 |
| 📥 Model download | 3-5min | Download Qwen 32B AWQ (~20GB) |
| ⚡ Model loading | 2-3min | Caricamento in VRAM |
| ✅ Registration | 5-10s | Backend + Telegram notify |
| **TOTALE** | **~15min** | Setup completo end-to-end |

*Nota: I tempi variano in base a velocità rete e GPU*

## 📱 Notifiche Telegram

Riceverai notifiche automatiche su Telegram per:

### ✅ Setup Started
```
🚀 QuantumDev GPU Setup Started

📋 Correlation ID: a3f8c2d1
🤖 Model: Qwen2.5-32B-Instruct-AWQ
🔧 Config: 32K context, 85% VRAM
⏰ Started: 2024-01-15 10:30:00
```

### ✅ Setup Complete
```
✅ GPU Setup Complete!

📋 Correlation ID: a3f8c2d1
⏱️ Time: 14m 32s
🌐 Endpoint: http://0.0.0.0:9011
🎉 Sistema operativo!
```

### ❌ Setup Failed
```
❌ GPU Setup Failed

📋 Correlation ID: a3f8c2d1
🔴 Error: vLLM failed to start
⏰ Time: 2024-01-15 10:45:00
```

## 🧪 Testing

### Test Automatico

```bash
./test-system.sh
```

Output:
```
✅ PASSED: 8
❌ FAILED: 0
🎉 Tutti i test superati! Sistema completamente operativo.
```

### Test Manuali

```bash
# 1. Test endpoint models
curl http://127.0.0.1:9011/v1/models

# 2. Test chat completion
curl -X POST http://127.0.0.1:9011/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-32b-instruct",
    "messages": [
      {"role": "system", "content": "Sei un assistente utile."},
      {"role": "user", "content": "Spiegami cosa è un modello LLM."}
    ],
    "max_tokens": 200,
    "temperature": 0.7
  }'

# 3. Test streaming
curl -X POST http://127.0.0.1:9011/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-32b-instruct",
    "messages": [{"role": "user", "content": "Conta da 1 a 10"}],
    "stream": true
  }'
```

## 📊 Monitoring

### Logs vLLM

```bash
# Sulla GPU (via SSH)
ssh -p 41234 root@154.42.3.37 'tail -f /workspace/vllm_qwen.log'
```

### Tunnel Status

```bash
# Sul VPS
journalctl -u vast-tunnel -f

# Controlla se tunnel è attivo
systemctl status vast-tunnel
```

### Services Status

```bash
# quantum-api
systemctl status quantum-api
journalctl -u quantum-api -f

# telegram-bot
systemctl status telegram-bot
journalctl -u telegram-bot -f
```

### GPU Metrics (sulla GPU)

```bash
ssh -p 41234 root@154.42.3.37

# GPU usage
nvidia-smi

# GPU usage real-time
watch -n 1 nvidia-smi

# vLLM process
ps aux | grep vllm
```

## 🔧 Troubleshooting

### Problema: SSH Connection Failed

**Sintomo:**
```
[ERROR] Connessione SSH fallita
```

**Soluzione:**
1. Verifica IP e porta: `ssh -p <PORT> root@<IP>`
2. Controlla che GPU Vast.ai sia running
3. Verifica firewall non blocchi porta SSH

### Problema: Timeout durante Setup

**Sintomo:**
```
[ERROR] Timeout: GPU server non risponde dopo 20 minuti
```

**Soluzione:**
1. Controlla log setup sulla GPU:
   ```bash
   ssh -p <PORT> root@<IP> 'cat /workspace/setup_qwen.log'
   ```
2. Verifica spazio disco:
   ```bash
   ssh -p <PORT> root@<IP> 'df -h'
   ```
3. Controlla se download modello è bloccato

### Problema: vLLM Non Risponde

**Sintomo:**
```
curl: (7) Failed to connect to 127.0.0.1 port 9011
```

**Soluzione:**
1. Verifica processo vLLM sulla GPU:
   ```bash
   ssh -p <PORT> root@<IP> 'ps aux | grep vllm'
   ```
2. Controlla log vLLM:
   ```bash
   ssh -p <PORT> root@<IP> 'tail -100 /workspace/vllm_qwen.log'
   ```
3. Restart vLLM manualmente se necessario

### Problema: Tunnel Non Funzionante

**Sintomo:**
```
systemctl status vast-tunnel
● vast-tunnel.service - Vast.ai GPU Reverse Tunnel
   Active: failed
```

**Soluzione:**
1. Verifica chiave SSH configurata in `.env.gpu`
2. Test connessione SSH manuale
3. Restart tunnel:
   ```bash
   systemctl restart vast-tunnel
   journalctl -u vast-tunnel -n 50
   ```

### Problema: Out of Memory (OOM)

**Sintomo:**
```
CUDA out of memory
```

**Soluzione:**
1. Riduci `gpu-memory-utilization` da 0.85 a 0.75
2. Riduci `max-num-seqs` da 4 a 2
3. Riduci `max-model-len` da 32768 a 16384

Modifica in `setup_gpu.py`:
```python
GPU_MEMORY_UTIL = 0.75
MAX_NUM_SEQS = 2
MAX_MODEL_LEN = 16384
```

## 💰 Costi Vast.ai

### A40 48GB
- **Costo:** ~$0.314/hour
- **Giornaliero:** ~$7.54
- **Mensile:** ~$226

### A6000 48GB
- **Costo:** ~$0.45/hour
- **Giornaliero:** ~$10.80
- **Mensile:** ~$324

**Consiglio:** Usa spot instances per risparmiare ~50%

## ✅ Success Checklist

Dopo il setup, verifica:

- [ ] `curl http://127.0.0.1:9011/v1/models` restituisce modello Qwen
- [ ] `./test-system.sh` passa tutti i test
- [ ] `systemctl status vast-tunnel` è active
- [ ] `systemctl status quantum-api` è active
- [ ] `systemctl status telegram-bot` è active
- [ ] Ricevuto notifica Telegram "GPU Setup Complete"
- [ ] Inference test funzionante con risposta corretta
- [ ] Log vLLM non mostra errori critici

## 📞 Support

**Issues:** Apri issue su GitHub repository

**Telegram:** Notifiche automatiche su chat admin

**Logs utili da includere:**
```bash
# Setup log
ssh -p <PORT> root@<IP> 'cat /workspace/setup_qwen.log'

# vLLM log (ultime 100 righe)
ssh -p <PORT> root@<IP> 'tail -100 /workspace/vllm_qwen.log'

# Tunnel log
journalctl -u vast-tunnel -n 50
```

## 📚 Risorse Aggiuntive

- **Qwen Model:** https://huggingface.co/Qwen/Qwen2.5-32B-Instruct-AWQ
- **vLLM Docs:** https://docs.vllm.ai/
- **Vast.ai:** https://vast.ai/
- **QUICK_REFERENCE.md:** Guide rapida comandi essenziali

---

**🎉 Buon lavoro con QuantumDev GPU!**
