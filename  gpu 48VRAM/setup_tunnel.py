# Sulla GPU
cat > /workspace/setup_tunnel.sh << 'TUNNELSCRIPT'
#!/bin/bash
set -e

echo "🚇 QUANTUM TUNNEL SETUP"
echo "======================="

# Carica .env
if [ ! -f /workspace/.env ]; then
    echo "❌ File .env mancante!"
    exit 1
fi

source /workspace/.env

# Setup chiave SSH
mkdir -p /workspace/.ssh
chmod 700 /workspace/.ssh
echo "$GPU_SSH_PRIVATE_KEY" > /workspace/.ssh/gpu_tunnel_key
chmod 600 /workspace/.ssh/gpu_tunnel_key

echo "🔑 Chiave SSH salvata"
echo ""

# Test connessione
echo "🔍 Test connessione a ${CPU_SSH_USER}@${CPU_SSH_HOST}:${CPU_SSH_PORT}"

ssh -i /workspace/.ssh/gpu_tunnel_key \
    -o StrictHostKeyChecking=no \
    -o ConnectTimeout=10 \
    -p ${CPU_SSH_PORT} \
    ${CPU_SSH_USER}@${CPU_SSH_HOST} \
    "echo 'OK'" || {
    echo "❌ Connessione SSH fallita!"
    exit 1
}

echo "✅ Connessione SSH OK"
echo ""

# Kill vecchi tunnel
pkill -f "ssh.*${CPU_TUNNEL_PORT}" 2>/dev/null || true
sleep 2

# Crea reverse tunnel: GPU:8001 → CPU:9001
echo "🚇 Creazione reverse tunnel: GPU:8001 → CPU:${CPU_TUNNEL_PORT}"

ssh -N -f \
    -i /workspace/.ssh/gpu_tunnel_key \
    -o StrictHostKeyChecking=no \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -o ExitOnForwardFailure=yes \
    -R ${CPU_TUNNEL_PORT}:127.0.0.1:8001 \
    -p ${CPU_SSH_PORT} \
    ${CPU_SSH_USER}@${CPU_SSH_HOST}

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Reverse tunnel creato!"
    echo ""
    echo "📡 Endpoint sulla CPU:"
    echo "   http://127.0.0.1:${CPU_TUNNEL_PORT}/v1/chat/completions"
    echo ""
    echo "🔍 Processo tunnel:"
    ps aux | grep "ssh.*${CPU_TUNNEL_PORT}" | grep -v grep
    echo ""
    echo "💡 Per testare dalla CPU:"
    echo "   curl http://127.0.0.1:9001/v1/models"
else
    echo "❌ Tunnel fallito"
    exit 1
fi
TUNNELSCRIPT

chmod +x /workspace/setup_tunnel.sh
echo "✅ Script tunnel creato"
