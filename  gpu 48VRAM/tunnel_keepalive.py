#!/bin/bash
# tunnel_keepalive.sh - mantiene vivo il tunnel GPU -> CPU

CPU_IP="84.247.166.247"
CPU_USER="root"
CPU_PORT=22
REMOTE_PORT=9011
LOCAL_VLLM_PORT=8001
SSH_KEY="/root/.ssh/id_ed25519"

while true; do
  echo "🔌 Avvio tunnel SSH verso ${CPU_USER}@${CPU_IP}:${REMOTE_PORT} -> localhost:${LOCAL_VLLM_PORT}"

  ssh -N \
    -R ${REMOTE_PORT}:127.0.0.1:${LOCAL_VLLM_PORT} \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -o TCPKeepAlive=yes \
    -i "${SSH_KEY}" \
    -p ${CPU_PORT} \
    ${CPU_USER}@${CPU_IP}

  echo "⚠️ Tunnel SSH terminato, retry tra 5s..."
  sleep 5
done
