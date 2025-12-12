# ⚡ QuantumDev GPU - Quick Reference

**Setup rapido Qwen 32B AWQ su Vast.ai in 15 minuti**

## 🚀 One-Liner Setup

```bash
cd "/root/quantumdev-open/ gpu 48VRAM" && chmod +x quick-start.sh test-system.sh && ./quick-start.sh <GPU_IP> <GPU_PORT>
```

**Esempio:**
```bash
cd "/root/quantumdev-open/ gpu 48VRAM" && chmod +x quick-start.sh test-system.sh && ./quick-start.sh 154.42.3.37 41234
```

## 📍 Come Ottenere IP/Porta da Vast.ai

1. **Login:** https://vast.ai/
2. **Instances → Your Instances**
3. **Cerca:** "Connect" button
4. **Copia:** SSH command mostrato
   ```
   ssh -p 41234 root@154.42.3.37 -L 8080:localhost:8080
         ^^^^^ IP   ^^^^^^^^^^^^^
         PORT       GPU_IP
   ```

## ⏱️ Timeline Setup

| Fase | Tempo |
|------|-------|
| 📤 Upload + config | 10-20s |
| 📦 Dependencies install | 5-8min |
| 📥 Model download | 3-5min |
| ⚡ Model loading | 2-3min |
| ✅ Ready | **~15min** |

## 🧪 Test Rapidi

```bash
# Test automatico completo
./test-system.sh

# Test endpoint
curl http://127.0.0.1:9011/v1/models

# Test inference
curl -X POST http://127.0.0.1:9011/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen-32b-instruct","messages":[{"role":"user","content":"Ciao"}],"max_tokens":50}'
```

## 📊 Monitoring Essenziale

```bash
# Tunnel status
systemctl status vast-tunnel

# Setup progress (sulla GPU)
ssh -p <PORT> root@<IP> 'tail -f /workspace/setup_qwen.log'

# vLLM logs (sulla GPU)
ssh -p <PORT> root@<IP> 'tail -f /workspace/vllm_qwen.log'

# Tunnel logs (VPS)
journalctl -u vast-tunnel -f
```

## ⚠️ Troubleshooting Rapido

### 1. SSH Connection Failed
```bash
# Test connessione
ssh -p <PORT> root@<IP>

# Verifica GPU running su Vast.ai
```

### 2. Setup Timeout
```bash
# Controlla log
ssh -p <PORT> root@<IP> 'tail -100 /workspace/setup_qwen.log'

# Verifica spazio disco
ssh -p <PORT> root@<IP> 'df -h'
```

### 3. Porta 9011 Non Risponde
```bash
# Verifica processo vLLM
ssh -p <PORT> root@<IP> 'ps aux | grep vllm'

# Check log errori
ssh -p <PORT> root@<IP> 'tail -50 /workspace/vllm_qwen.log | grep -i error'
```

### 4. Tunnel Non Attivo
```bash
# Restart tunnel
systemctl restart vast-tunnel

# Check status
journalctl -u vast-tunnel -n 20
```

## 🔧 Comandi Utili

### Restart Services

```bash
# Restart tunnel
systemctl restart vast-tunnel

# Restart quantum-api
systemctl restart quantum-api

# Restart telegram-bot
systemctl restart telegram-bot
```

### Check Logs

```bash
# Setup log completo
ssh -p <PORT> root@<IP> 'cat /workspace/setup_qwen.log'

# vLLM log completo
ssh -p <PORT> root@<IP> 'cat /workspace/vllm_qwen.log'

# Ultime 50 righe tunnel log
journalctl -u vast-tunnel -n 50

# Follow quantum-api logs
journalctl -u quantum-api -f
```

### GPU Info (sulla GPU)

```bash
# GPU usage
ssh -p <PORT> root@<IP> 'nvidia-smi'

# GPU usage real-time
ssh -p <PORT> root@<IP> 'watch -n 1 nvidia-smi'

# Spazio disco
ssh -p <PORT> root@<IP> 'df -h'
```

### Kill & Restart vLLM (sulla GPU)

```bash
# Kill vLLM
ssh -p <PORT> root@<IP> 'pkill -9 -f vllm'

# Restart setup
ssh -p <PORT> root@<IP> 'cd /workspace && python3 setup_gpu.py'
```

## 💰 Costi

| GPU | VRAM | Costo/ora | Costo/giorno |
|-----|------|-----------|--------------|
| A40 | 48GB | $0.314 | ~$7.54 |
| A6000 | 48GB | $0.45 | ~$10.80 |

*Usa spot instances per ~50% risparmio*

## 🔑 Credentials Quick Access

```bash
# File configurazione
cat "/root/quantumdev-open/ gpu 48VRAM/.env.gpu"

# Telegram Bot Token
8102361815:AAGmosNjWnJIBdQehdNrlNcKsoN6ifIbKzc

# Admin ID
5015947009

# Shared Secret
5e6ad9f7c2b14dceb2f4a1a9087c3da0d4a885c3e85f1b2d47a6f0e9c3b21d77
```

## 📱 Notifiche Telegram

Setup invia automaticamente 3 notifiche:
1. ✅ **Setup Started** - All'avvio
2. ✅ **Setup Complete** - A fine setup (con tempo totale)
3. ❌ **Setup Failed** - In caso di errore

## ✅ Quick Checklist

Dopo setup, verifica:
- [ ] `curl http://127.0.0.1:9011/v1/models` funziona
- [ ] `./test-system.sh` passa (>=70%)
- [ ] `systemctl status vast-tunnel` attivo
- [ ] Ricevuta notifica Telegram "Setup Complete"

## 📞 Help

**README completo:** `cat README.md`

**Issues:** GitHub repository

**Emergency stop GPU:** Vast.ai dashboard → Stop instance

---

**⚡ Quick reference - Tieni a portata di mano!**
