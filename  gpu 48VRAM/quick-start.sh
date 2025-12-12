#!/bin/bash
set -e

# ========= COLORI ANSI =========
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# ========= BANNER ASCII =========
print_banner() {
    echo -e "${CYAN}"
    cat << "EOF"
   ____  _    _   _    _   _ _______ _    _ __  __ 
  / __ \| |  | | | |  | | /\| |__   __| |  | |  \/  |
 | |  | | |  | | | |  | |/  \| |  | |  | |  | | \  / |
 | |  | | |  | | | |  | / /\ \ |  | |  | |  | | |\/| |
 | |__| | |__| | | |__| / ____ \| | |  | |__| | |  | |
  \___\_\\____/   \____/_/    \_\_|   \____/|_|  |_|
                                                      
         QuantumDev GPU Setup - Qwen 32B AWQ
         =====================================
EOF
    echo -e "${NC}"
}

# ========= FUNZIONI HELPER =========
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "\n${MAGENTA}==>${NC} ${CYAN}$1${NC}\n"
}

# ========= VALIDAZIONE PARAMETRI =========
if [ "$#" -ne 2 ]; then
    echo -e "${RED}Uso:${NC} $0 <gpu-ip> <gpu-port>"
    echo -e "${YELLOW}Esempio:${NC} $0 154.42.3.37 41234"
    exit 1
fi

GPU_IP="$1"
GPU_PORT="$2"

print_banner

log_info "GPU IP: ${GPU_IP}"
log_info "GPU Port: ${GPU_PORT}"
log_info "Timestamp: $(date '+%Y-%m-%d %H:%M:%S')"

# ========= STEP 1: AUTO-DETECT VPS IP =========
log_step "STEP 1: Rilevamento IP pubblico VPS"

VPS_IP=$(curl -s --max-time 10 ifconfig.me || echo "")
if [ -z "$VPS_IP" ]; then
    log_error "Impossibile rilevare IP pubblico VPS"
    exit 1
fi

log_success "VPS IP rilevato: ${VPS_IP}"

# ========= STEP 2: CONFIGURAZIONE .env.gpu =========
log_step "STEP 2: Configurazione file .env.gpu"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env.gpu"
SETUP_FILE="${SCRIPT_DIR}/setup_gpu.py"

if [ ! -f "$ENV_FILE" ]; then
    log_error "File .env.gpu non trovato: ${ENV_FILE}"
    exit 1
fi

if [ ! -f "$SETUP_FILE" ]; then
    log_error "File setup_gpu.py non trovato: ${SETUP_FILE}"
    exit 1
fi

# Sostituisci AUTO_DETECT con IP reale
sed -i "s/CPU_HOST=AUTO_DETECT/CPU_HOST=${VPS_IP}/" "$ENV_FILE"
sed -i "s/AUTO_DETECT_IP/${VPS_IP}/" "$ENV_FILE"

log_success "Configurazione aggiornata con IP: ${VPS_IP}"

# ========= STEP 3: TEST CONNESSIONE SSH =========
log_step "STEP 3: Test connessione SSH alla GPU"

log_info "Testing SSH: root@${GPU_IP}:${GPU_PORT}"
if ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no -p "${GPU_PORT}" "root@${GPU_IP}" "echo 'SSH OK'" &>/dev/null; then
    log_success "Connessione SSH funzionante"
else
    log_error "Connessione SSH fallita. Verifica IP, porta e chiave SSH."
    exit 1
fi

# ========= STEP 4: UPLOAD FILES =========
log_step "STEP 4: Upload setup_gpu.py e .env.gpu sulla GPU"

log_info "Upload setup_gpu.py..."
scp -P "${GPU_PORT}" -o StrictHostKeyChecking=no "$SETUP_FILE" "root@${GPU_IP}:/workspace/" || {
    log_error "Upload setup_gpu.py fallito"
    exit 1
}

log_info "Upload .env.gpu..."
scp -P "${GPU_PORT}" -o StrictHostKeyChecking=no "$ENV_FILE" "root@${GPU_IP}:/workspace/.env" || {
    log_error "Upload .env.gpu fallito"
    exit 1
}

log_success "Files uploaded successfully"

# ========= STEP 5: ESECUZIONE SETUP GPU =========
log_step "STEP 5: Avvio setup GPU in background"

log_info "Executing setup_gpu.py sulla GPU..."
ssh -p "${GPU_PORT}" "root@${GPU_IP}" "cd /workspace && nohup python3 setup_gpu.py > setup.out 2>&1 &" || {
    log_error "Esecuzione setup_gpu.py fallita"
    exit 1
}

log_success "Setup GPU avviato in background"

# ========= STEP 6: MONITORING PROGRESS =========
log_step "STEP 6: Monitoring setup progress (porta 9011)"

log_info "Controllo ogni 30 secondi se porta 9011 risponde..."
log_info "Setup può richiedere 10-15 minuti (download modello + caricamento)"

MAX_ATTEMPTS=40  # 40 tentativi * 30 sec = 20 minuti
ATTEMPT=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    ATTEMPT=$((ATTEMPT + 1))
    ELAPSED=$((ATTEMPT * 30))
    
    log_info "Tentativo ${ATTEMPT}/${MAX_ATTEMPTS} (${ELAPSED}s elapsed)..."
    
    # Controlla se porta 9011 risponde
    if ssh -p "${GPU_PORT}" "root@${GPU_IP}" "curl -s -m 5 http://127.0.0.1:9011/v1/models" &>/dev/null; then
        log_success "✅ GPU server is UP and responding!"
        break
    fi
    
    if [ $ATTEMPT -lt $MAX_ATTEMPTS ]; then
        sleep 30
    fi
done

if [ $ATTEMPT -ge $MAX_ATTEMPTS ]; then
    log_error "Timeout: GPU server non risponde dopo 20 minuti"
    log_warn "Controlla i log sulla GPU: ssh -p ${GPU_PORT} root@${GPU_IP} 'tail -f /workspace/setup_qwen.log'"
    exit 1
fi

# ========= STEP 7: SYSTEMD SERVICE PER TUNNEL =========
log_step "STEP 7: Creazione systemd service per tunnel persistente"

SERVICE_FILE="/etc/systemd/system/vast-tunnel.service"

log_info "Creazione ${SERVICE_FILE}..."

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Vast.ai GPU Reverse Tunnel (Port 9011)
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/ssh -N -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -R 9011:127.0.0.1:9011 -p ${GPU_PORT} root@${GPU_IP}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

log_info "Reload systemd daemon..."
systemctl daemon-reload

log_info "Enable vast-tunnel service..."
systemctl enable vast-tunnel.service

log_info "Start vast-tunnel service..."
systemctl start vast-tunnel.service

sleep 2

if systemctl is-active --quiet vast-tunnel.service; then
    log_success "Tunnel service attivo"
else
    log_warn "Tunnel service non attivo (potrebbe richiedere configurazione SSH key)"
fi

# ========= STEP 8: RESTART SERVICES =========
log_step "STEP 8: Restart quantum-api e telegram-bot"

if systemctl is-active --quiet quantum-api.service; then
    log_info "Restart quantum-api..."
    systemctl restart quantum-api.service
    log_success "quantum-api restarted"
else
    log_warn "quantum-api.service non trovato o non attivo"
fi

if systemctl is-active --quiet telegram-bot.service; then
    log_info "Restart telegram-bot..."
    systemctl restart telegram-bot.service
    log_success "telegram-bot restarted"
else
    log_warn "telegram-bot.service non trovato o non attivo"
fi

# ========= SUMMARY FINALE =========
log_step "✅ SETUP COMPLETO!"

echo -e "${GREEN}"
cat << "EOF"
  ____  _    _  ____ ____ ______  _____ _____ 
 / ___|| |  | |/ ___/ ___| ____/ / ___// ___| 
 \___ \| |  | | |  | |   |  _| \ \__ \ \___ \ 
  ___) | |__| | |__| |___| |___ ) ___) | ___) |
 |____/ \____/ \___\\____|_____/ |____/ |____/ 
                                                
EOF
echo -e "${NC}"

echo -e "${CYAN}========================================${NC}"
echo -e "${GREEN}✅ GPU Setup Completato con Successo!${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""
echo -e "${BLUE}📊 INFORMAZIONI:${NC}"
echo -e "  • GPU IP:        ${GPU_IP}:${GPU_PORT}"
echo -e "  • VPS IP:        ${VPS_IP}"
echo -e "  • Local Port:    http://127.0.0.1:9011"
echo -e "  • Model:         Qwen2.5-32B-Instruct-AWQ"
echo -e "  • Context:       32K tokens"
echo ""
echo -e "${YELLOW}🔍 TEST RAPIDI:${NC}"
echo -e "  curl http://127.0.0.1:9011/v1/models"
echo -e "  ./test-system.sh"
echo ""
echo -e "${CYAN}📝 MONITORING:${NC}"
echo -e "  journalctl -u vast-tunnel -f"
echo -e "  ssh -p ${GPU_PORT} root@${GPU_IP} 'tail -f /workspace/vllm_qwen.log'"
echo ""
echo -e "${GREEN}🎉 Sistema operativo!${NC}"
echo ""
