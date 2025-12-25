#!/bin/bash

# === QuantumDev Health Check ===
# ⏰ Log: /root/quantumdev-open/scripts/health.log

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
LOG_FILE="/root/quantumdev-open/scripts/health.log"

# === Funzione log ===
log() {
    echo "[$TIMESTAMP] $1" >> "$LOG_FILE"
}

# === Check Redis ===
redis-cli ping | grep -q PONG
if [ $? -ne 0 ]; then
    log "❌ ERRORE: Redis non raggiungibile."
    curl -s -X POST https://api.telegram.org/bot<INSERISCI_BOT_TOKEN>/sendMessage \
         -d chat_id=<INSERISCI_CHAT_ID> \
         -d text="⚠️ QuantumDev ALERT: Redis non risponde!"
    exit 1
fi

# === Recupera endpoint e modello attivi ===
ENDPOINT=$(redis-cli get gpu_active_endpoint | tr -d '"')
MODEL=$(redis-cli get gpu_active_model | tr -d '"')

if [[ -z "$ENDPOINT" || -z "$MODEL" ]]; then
    log "❌ ERRORE: Endpoint o modello assenti in Redis."
    curl -s -X POST https://api.telegram.org/bot<INSERISCI_BOT_TOKEN>/sendMessage \
         -d chat_id=<INSERISCI_CHAT_ID> \
         -d text="⚠️ QuantumDev ALERT: Endpoint o modello non impostati in Redis!"
    exit 1
fi

# === Esegui test sul modello ===
RESPONSE=$(curl -s -X POST "$ENDPOINT" \
    -H "Content-Type: application/json" \
    -d '{
        "model": "'"$MODEL"'",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 8
    }')

# === Controllo risposta ===
echo "$RESPONSE" | grep -q "content"
if [ $? -eq 0 ]; then
    log "✅ OK: GPU attiva e modello $MODEL risponde."
else
    log "❌ ERRORE: Nessuna risposta valida dal modello."
    curl -s -X POST https://api.telegram.org/bot<INSERISCI_BOT_TOKEN>/sendMessage \
         -d chat_id=<INSERISCI_CHAT_ID> \
         -d text="⚠️ QuantumDev ALERT: GPU attiva ma nessuna risposta valida da $MODEL!"
    exit 1
fi
