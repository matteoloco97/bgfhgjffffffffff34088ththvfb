#!/bin/bash

# ========= COLORI =========
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ========= CONTATORI =========
PASSED=0
FAILED=0

# ========= FUNZIONI HELPER =========
test_start() {
    echo -e "\n${CYAN}[TEST]${NC} $1"
}

test_pass() {
    echo -e "${GREEN}  ✅ PASSED:${NC} $1"
    PASSED=$((PASSED + 1))
}

test_fail() {
    echo -e "${RED}  ❌ FAILED:${NC} $1"
    FAILED=$((FAILED + 1))
}

# ========= BANNER =========
echo -e "${CYAN}"
cat << "EOF"
 _____ _____ ____ _____   ______   _______ _____ _____ __  __ 
|_   _| ____/ ___|_   _| / ___\ \ / / ___ |_   _| ____|  \/  |
  | | |  _| \___ \ | |   \___ \\ V /\___ \ | | |  _| | |\/| |
  | | | |___ ___) || |    ___) || |  ___) || | | |___| |  | |
  |_| |_____|____/ |_|   |____/ |_| |____/ |_| |_____|_|  |_|
                                                              
EOF
echo -e "${NC}"
echo -e "${BLUE}Test completo sistema QuantumDev GPU${NC}\n"

# ========= TEST 1: LLM ENDPOINT =========
test_start "LLM Endpoint /v1/models"
RESPONSE=$(curl -s -m 5 http://127.0.0.1:9011/v1/models)
if echo "$RESPONSE" | grep -q "qwen-32b-instruct"; then
    test_pass "Endpoint risponde con modello corretto"
else
    test_fail "Endpoint non risponde o modello non trovato"
fi

# ========= TEST 2: LLM INFERENCE =========
test_start "LLM Inference /v1/chat/completions"
INFERENCE=$(curl -s -m 30 -X POST http://127.0.0.1:9011/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{
        "model": "qwen-32b-instruct",
        "messages": [{"role": "user", "content": "Rispondi solo con un numero: 2+2=?"}],
        "max_tokens": 5,
        "temperature": 0.1
    }')

if echo "$INFERENCE" | grep -q "choices"; then
    ANSWER=$(echo "$INFERENCE" | grep -o '"content":"[^"]*"' | head -1 | sed 's/"content":"\(.*\)"/\1/')
    test_pass "Inference funzionante. Risposta: ${ANSWER}"
else
    test_fail "Inference non funzionante"
fi

# ========= TEST 3: QUANTUM-API SERVICE =========
test_start "quantum-api service status"
if systemctl is-active --quiet quantum-api.service; then
    test_pass "quantum-api service attivo"
else
    test_fail "quantum-api service non attivo"
fi

# ========= TEST 4: TELEGRAM-BOT SERVICE =========
test_start "telegram-bot service status"
if systemctl is-active --quiet telegram-bot.service; then
    test_pass "telegram-bot service attivo"
else
    test_fail "telegram-bot service non attivo"
fi

# ========= TEST 5: REDIS =========
test_start "Redis connectivity"
if redis-cli ping &>/dev/null; then
    test_pass "Redis risponde"
else
    test_fail "Redis non risponde"
fi

# ========= TEST 6: VAST-TUNNEL SERVICE =========
test_start "vast-tunnel service status"
if systemctl is-active --quiet vast-tunnel.service; then
    test_pass "vast-tunnel service attivo"
else
    test_fail "vast-tunnel service non attivo"
fi

# ========= TEST 7: CHROMADB DIRECTORY =========
test_start "ChromaDB directory"
if [ -d "/root/quantumdev-open/chroma_db" ]; then
    DB_SIZE=$(du -sh /root/quantumdev-open/chroma_db 2>/dev/null | cut -f1)
    test_pass "ChromaDB directory presente (${DB_SIZE})"
else
    test_fail "ChromaDB directory non trovata"
fi

# ========= TEST 8: WEB SEARCH CAPABILITY =========
test_start "Web search capability"
if command -v jina &>/dev/null || curl -s "https://api.jina.ai" &>/dev/null; then
    test_pass "Web search tools disponibili"
else
    test_fail "Web search tools non configurati"
fi

# ========= TEST 9: NETWORK TUNNEL =========
test_start "Network tunnel (porta 9011)"
if netstat -tlnp 2>/dev/null | grep -q ":9011"; then
    test_pass "Porta 9011 in ascolto"
else
    test_fail "Porta 9011 non in ascolto"
fi

# ========= TEST 10: GPU VLLM LOG =========
test_start "vLLM log file"
if [ -f "/workspace/vllm_qwen.log" ]; then
    LOG_SIZE=$(du -sh /workspace/vllm_qwen.log 2>/dev/null | cut -f1)
    test_pass "vLLM log presente (${LOG_SIZE})"
else
    test_fail "vLLM log non trovato"
fi

# ========= SUMMARY FINALE =========
echo -e "\n${CYAN}========================================${NC}"
echo -e "${CYAN}           TEST SUMMARY${NC}"
echo -e "${CYAN}========================================${NC}"
echo -e "${GREEN}✅ PASSED: ${PASSED}${NC}"
echo -e "${RED}❌ FAILED: ${FAILED}${NC}"
echo -e "${CYAN}========================================${NC}\n"

TOTAL=$((PASSED + FAILED))
PERCENTAGE=$((PASSED * 100 / TOTAL))

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}🎉 Tutti i test superati! Sistema completamente operativo.${NC}\n"
    exit 0
elif [ $PERCENTAGE -ge 70 ]; then
    echo -e "${YELLOW}⚠️  Sistema parzialmente operativo (${PERCENTAGE}% test passati).${NC}"
    echo -e "${YELLOW}   Alcuni componenti potrebbero richiedere attenzione.${NC}\n"
    exit 1
else
    echo -e "${RED}❌ Sistema NON operativo (${PERCENTAGE}% test passati).${NC}"
    echo -e "${RED}   Richiesta troubleshooting urgente.${NC}\n"
    exit 2
fi
