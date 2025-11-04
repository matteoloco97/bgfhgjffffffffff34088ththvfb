# Sulla GPU
cat > /workspace/setup_tunnel.sh << 'TUNNELSCRIPT'
#!/bin/bash
set -euo pipefail

echo "🚇 QUANTUM TUNNEL SETUP"
echo "======================="

ENV_FILE="/workspace/.env"
KEY_DIR="/workspace/.ssh"
DEFAULT_PORT="9011"        # <-- porta tunnel di default (patch)
LOCAL_VLLM_PORT="8001"     # porta vLLM lato GPU
LOG="/workspace/create_tunnel.log"

# --- Carica .env (se presente) ---
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
else
  echo "⚠️  File .env non trovato in $ENV_FILE. Userò solo le variabili d'ambiente correnti."
fi

# --- Variabili richieste / default ---
CPU_SSH_HOST="${CPU_SSH_HOST:-}"
CPU_SSH_USER="${CPU_SSH_USER:-gpu-tunnel}"
CPU_SSH_PORT="${CPU_SSH_PORT:-22}"
CPU_TUNNEL_PORT="${CPU_TUNNEL_PORT:-$DEFAULT_PORT}"

GPU_PRIVATE_KEY_PATH="${GPU_PRIVATE_KEY_PATH:-}"
GPU_SSH_PRIVATE_KEY="${GPU_SSH_PRIVATE_KEY:-}"

# --- Prepara directory chiavi ---
mkdir -p "$KEY_DIR"
chmod 700 "$KEY_DIR"

# --- Sorgente chiave: preferisci file, altrimenti crea da contenuto ---
KEY_PATH=""
if [[ -n "$GPU_PRIVATE_KEY_PATH" && -f "$GPU_PRIVATE_KEY_PATH" ]]; then
  KEY_PATH="$GPU_PRIVATE_KEY_PATH"
else
  if [[ -z "$GPU_SSH_PRIVATE_KEY" ]]; then
    echo "❌ Nessuna chiave SSH fornita. Imposta GPU_PRIVATE_KEY_PATH o GPU_SSH_PRIVATE_KEY."
    exit 1
  fi
  KEY_PATH="$KEY_DIR/gpu_tunnel_key"
  printf "%s" "$GPU_SSH_PRIVATE_KEY" > "$KEY_PATH"
fi
chmod 600 "$KEY_PATH"
echo "🔑 Chiave SSH pronta: $KEY_PATH"
echo

# --- Validazioni minime ---
if [[ -z "$CPU_SSH_HOST" ]]; then
  echo "❌ Variabile CPU_SSH_HOST mancante."
  exit 1
fi

# --- Test connessione/handshake ---
echo "🔍 Test connessione a ${CPU_SSH_USER}@${CPU_SSH_HOST}:${CPU_SSH_PORT}"
if ssh -i "$KEY_PATH" \
      -o StrictHostKeyChecking=no \
      -o ConnectTimeout=10 \
      -p "$CPU_SSH_PORT" \
      "${CPU_SSH_USER}@${CPU_SSH_HOST}" "echo OK" ; then
  echo "✅ Connessione SSH OK"
else
  echo "❌ Connessione SSH fallita (handshake)."
  exit 1
fi
echo

# --- Kill eventuali tunnel già attivi sulla stessa porta ---
echo "🧹 Chiudo eventuali tunnel precedenti sulla porta ${CPU_TUNNEL_PORT}..."
pkill -f "ssh.*-R ${CPU_TUNNEL_PORT}:" 2>/dev/null || true
sleep 1

SSH_COMMON_OPTS="-i $KEY_PATH -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -p $CPU_SSH_PORT"

# --- Preferisci autossh se presente, altrimenti fallback con loop ---
start_autossh() {
  echo "🚇 Avvio AUTOSSH: GPU:${LOCAL_VLLM_PORT} → CPU:${CPU_TUNNEL_PORT}"
  nohup autossh -M 0 -N \
      $SSH_COMMON_OPTS \
      -R ${CPU_TUNNEL_PORT}:127.0.0.1:${LOCAL_VLLM_PORT} \
      "${CPU_SSH_USER}@${CPU_SSH_HOST}" \
      >> "$LOG" 2>&1 &
}

start_loop() {
  echo "🚇 Avvio LOOP robusto: GPU:${LOCAL_VLLM_PORT} → CPU:${CPU_TUNNEL_PORT}"
  nohup bash -c '
    set -e
    while true; do
      echo "[`date +%FT%T`] starting tunnel..." >> '"$LOG"'
      ssh -N '"$SSH_COMMON_OPTS"' -R '"${CPU_TUNNEL_PORT}"':127.0.0.1:'"${LOCAL_VLLM_PORT}"' '"${CPU_SSH_USER}@${CPU_SSH_HOST}"' >> '"$LOG"' 2>&1 || true
      echo "[`date +%FT%T`] ssh exited, retry in 3s" >> '"$LOG"'
      sleep 3
    done
  ' >/dev/null 2>&1 &
}

echo "📝 Log: $LOG"
echo

if command -v autossh >/dev/null 2>&1 ; then
  start_autossh
else
  echo "ℹ️  autossh non trovato: uso loop di riconnessione."
  start_loop
fi

sleep 2

# --- Verifica processi ---
echo "🔍 Processi tunnel attivi:"
ps aux | grep "[s]sh.*-R ${CPU_TUNNEL_PORT}:" || true
echo

# --- Output finale ---
echo "✅ Reverse tunnel attivo (o in avvio)."
echo
echo "📡 Endpoint sulla CPU (lato server):"
echo "   http://127.0.0.1:${CPU_TUNNEL_PORT}/v1/chat/completions"
echo
echo "💡 Test (DA CPU):"
echo "   curl -s http://127.0.0.1:${CPU_TUNNEL_PORT}/v1/models | jq ."
echo
echo "📜 Log in streaming (DA GPU):"
echo "   tail -n 50 -f $LOG"
TUNNELSCRIPT

chmod +x /workspace/setup_tunnel.sh
echo "✅ Script tunnel creato (porta default 9011)"
