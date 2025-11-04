#!/bin/bash
# scripts/gpu-tunnel/setup_cpu_tunnel.sh
# Setup CPU per accettare reverse SSH tunnel dalle GPU

set -e

echo "🔧 QuantumDev - Setup CPU Tunnel Receiver"
echo "=========================================="
echo ""

# === Config ===
TUNNEL_USER="gpu-tunnel"
TUNNEL_HOME="/home/$TUNNEL_USER"
SSH_DIR="$TUNNEL_HOME/.ssh"
KEY_NAME="gpu_key"
CPU_TUNNEL_PORT=9001

# === 1. Crea utente dedicato ===
echo "👤 Creazione utente $TUNNEL_USER..."
if id "$TUNNEL_USER" &>/dev/null; then
    echo "   ℹ️  Utente già esistente, skip"
else
    useradd -m -s /bin/bash "$TUNNEL_USER"
    echo "   ✅ Utente creato"
fi

# === 2. Setup SSH directory ===
echo ""
echo "📁 Setup directory SSH..."
mkdir -p "$SSH_DIR"
chmod 700 "$SSH_DIR"
chown -R "$TUNNEL_USER:$TUNNEL_USER" "$TUNNEL_HOME"
echo "   ✅ Directory pronta"

# === 3. Genera chiave SSH ===
echo ""
echo "🔑 Generazione chiave SSH per GPU..."
KEY_PATH="$SSH_DIR/$KEY_NAME"

if [ -f "$KEY_PATH" ]; then
    echo "   ⚠️  Chiave già esistente. Vuoi rigenerarla? [y/N]"
    read -r REPLY
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "   ℹ️  Riutilizzo chiave esistente"
    else
        rm -f "$KEY_PATH" "$KEY_PATH.pub"
        ssh-keygen -t ed25519 -f "$KEY_PATH" -N "" -C "gpu-tunnel@vast"
        echo "   ✅ Nuova chiave generata"
    fi
else
    ssh-keygen -t ed25519 -f "$KEY_PATH" -N "" -C "gpu-tunnel@vast"
    echo "   ✅ Chiave generata"
fi

# === 4. Configura authorized_keys ===
echo ""
echo "🔐 Setup authorized_keys..."
cat "$KEY_PATH.pub" > "$SSH_DIR/authorized_keys"
chmod 600 "$SSH_DIR/authorized_keys"
chown -R "$TUNNEL_USER:$TUNNEL_USER" "$SSH_DIR"
echo "   ✅ authorized_keys configurato"

# === 5. Configura SSHD ===
echo ""
echo "⚙️  Configurazione SSHD..."

SSHD_CONFIG="/etc/ssh/sshd_config"
BACKUP_CONFIG="/etc/ssh/sshd_config.backup.$(date +%Y%m%d_%H%M%S)"

# Backup
cp "$SSHD_CONFIG" "$BACKUP_CONFIG"
echo "   📦 Backup: $BACKUP_CONFIG"

# Verifica/aggiungi configurazioni necessarie
if ! grep -q "^GatewayPorts" "$SSHD_CONFIG"; then
    echo "GatewayPorts no" >> "$SSHD_CONFIG"
fi

if ! grep -q "^AllowTcpForwarding" "$SSHD_CONFIG"; then
    echo "AllowTcpForwarding yes" >> "$SSHD_CONFIG"
fi

if ! grep -q "^PermitTunnel" "$SSHD_CONFIG"; then
    echo "PermitTunnel yes" >> "$SSHD_CONFIG"
fi

echo "   ✅ SSHD configurato"

# === 6. Riavvia SSHD ===
echo ""
echo "🔄 Riavvio SSHD..."
systemctl restart sshd
systemctl status sshd --no-pager -l | head -n 5
echo "   ✅ SSHD riavviato"

# === 7. Mostra chiave privata per la GPU ===
echo ""
echo "=========================================="
echo "📋 CHIAVE PRIVATA PER LA GPU"
echo "=========================================="
echo ""
echo "⚠️  IMPORTANTE: Copia questa chiave e salvala in /workspace/.env sulla GPU"
echo ""
echo "--- INIZIO CHIAVE ---"
cat "$KEY_PATH"
echo "--- FINE CHIAVE ---"
echo ""

# === 8. Salva chiave in file per copia facile ===
OUTPUT_DIR="/root/quantumdev-open/config/gpu-tunnel"
mkdir -p "$OUTPUT_DIR"
cp "$KEY_PATH" "$OUTPUT_DIR/gpu_private_key"
cp "$KEY_PATH.pub" "$OUTPUT_DIR/gpu_public_key.pub"
chmod 600 "$OUTPUT_DIR/gpu_private_key"

echo "📁 Chiavi salvate anche in: $OUTPUT_DIR/"
echo "   - gpu_private_key (da copiare sulla GPU)"
echo "   - gpu_public_key.pub (per riferimento)"
echo ""

# === 9. Info finale ===
echo "=========================================="
echo "✅ SETUP COMPLETATO"
echo "=========================================="
echo ""
echo "📝 Prossimi passi:"
echo "   1. Copia la chiave privata sopra"
echo "   2. Sulla GPU, crea /workspace/.env con:"
echo "      GPU_SSH_PRIVATE_KEY=\"contenuto della chiave\""
echo "      CPU_SSH_HOST=\"$(hostname -I | awk '{print $1}')\""
echo "      CPU_TUNNEL_PORT=$CPU_TUNNEL_PORT"
echo ""
echo "   3. Modifica setup_gpu.py (ti guiderò al prossimo step)"
echo ""
echo "🔌 Il tunnel sarà accessibile su: 127.0.0.1:$CPU_TUNNEL_PORT"
echo ""
