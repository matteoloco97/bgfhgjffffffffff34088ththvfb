!/bin/bash
# ============================================================
# QUANTUMDEV SYSTEM VERIFICATION SCRIPT
# ============================================================
# Comprehensive health check for QuantumDev deployment
# Tests all critical components and provides actionable feedback
#
# Usage: 
#   ./verify_system.sh              # Full check
#   ./verify_system.sh --quick      # Skip slow tests
#   ./verify_system.sh --fix        # Auto-fix common issues
#   ./verify_system.sh --json       # JSON output for monitoring
#
# Deploy to: /root/quantumdev-open/scripts/verify_system.sh
# Make executable: chmod +x /root/quantumdev-open/scripts/verify_system.sh

set -e

# ============================================================
# CONFIGURATION
# ============================================================
PROJECT_ROOT="/root/quantumdev-open"
QUICK_MODE=0
FIX_MODE=0
JSON_MODE=0
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0
WARNINGS=0

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ============================================================
# UTILITY FUNCTIONS
# ============================================================

print_header() {
    if [ $JSON_MODE -eq 0 ]; then
        echo ""
        echo -e "${BLUE}╔══════════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${BLUE}║       QUANTUMDEV SYSTEM VERIFICATION                             ║${NC}"
        echo -e "${BLUE}╔══════════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${CYAN}Date: $(date '+%Y-%m-%d %H:%M:%S')${NC}"
        echo -e "${CYAN}Hostname: $(hostname)${NC}"
        echo ""
    fi
}

print_section() {
    if [ $JSON_MODE -eq 0 ]; then
        echo ""
        echo -e "${BLUE}═══ $1 ═══${NC}"
    fi
}

check_ok() {
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    PASSED_CHECKS=$((PASSED_CHECKS + 1))
    if [ $JSON_MODE -eq 0 ]; then
        echo -e "  ${GREEN}✓${NC} $1"
    fi
}

check_fail() {
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
    if [ $JSON_MODE -eq 0 ]; then
        echo -e "  ${RED}✗${NC} $1"
        if [ -n "$2" ]; then
            echo -e "    ${RED}→${NC} $2"
        fi
    fi
}

check_warn() {
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    WARNINGS=$((WARNINGS + 1))
    if [ $JSON_MODE -eq 0 ]; then
        echo -e "  ${YELLOW}⚠${NC} $1"
        if [ -n "$2" ]; then
            echo -e "    ${YELLOW}→${NC} $2"
        fi
    fi
}

info() {
    if [ $JSON_MODE -eq 0 ]; then
        echo -e "  ${CYAN}ℹ${NC} $1"
    fi
}

# ============================================================
# CHECK FUNCTIONS
# ============================================================

check_services() {
    print_section "Services Status"
    
    # quantum-api
    if systemctl is-active --quiet quantum-api; then
        check_ok "quantum-api: RUNNING"
    else
        check_fail "quantum-api: NOT RUNNING" "systemctl start quantum-api"
    fi
    
    # telegram-bot
    if systemctl is-active --quiet telegram-bot; then
        check_ok "telegram-bot: RUNNING"
    else
        check_warn "telegram-bot: NOT RUNNING" "systemctl start telegram-bot"
    fi
    
    # redis-server
    if systemctl is-active --quiet redis-server; then
        check_ok "redis-server: RUNNING"
    else
        check_fail "redis-server: NOT RUNNING" "systemctl start redis-server"
    fi
    
    # Redis connectivity
    if redis-cli ping >/dev/null 2>&1; then
        check_ok "Redis: RESPONDING"
    else
        check_fail "Redis: NOT RESPONDING"
    fi
}

check_critical_files() {
    print_section "Critical Files"
    
    # Core modules
    local files=(
        "core/llm_config.py"
        "core/web_response_formatter.py"
        "core/smart_intent_classifier.py"
        "core/chat_engine.py"
        "backend/quantum_api.py"
        "scripts/telegram_bot.py"
    )
    
    for file in "${files[@]}"; do
        if [ -f "$PROJECT_ROOT/$file" ]; then
            check_ok "$file"
        else
            check_fail "$file: MISSING"
        fi
    done
    
    # Configuration files
    if [ -f "$PROJECT_ROOT/.env" ]; then
        check_ok ".env configuration"
    else
        check_fail ".env: MISSING" "Copy from .env.example"
    fi
    
    if [ -f "$PROJECT_ROOT/config/source_policy.yaml" ]; then
        check_ok "source_policy.yaml"
    else
        check_warn "source_policy.yaml: MISSING" "Optional but recommended"
    fi
}

check_dependencies() {
    print_section "Python Dependencies"
    
    cd "$PROJECT_ROOT"
    source venv/bin/activate 2>/dev/null || {
        check_fail "Virtual environment not found"
        return
    }
    
    # Critical dependencies
    local deps=(
        "fastapi"
        "redis"
        "chromadb"
        "sentence_transformers"
        "trafilatura"
        "readability"
    )
    
    for dep in "${deps[@]}"; do
        if python3 -c "import ${dep//-/_}" 2>/dev/null; then
            check_ok "$dep"
        else
            check_fail "$dep: NOT INSTALLED" "pip install $dep --break-system-packages"
        fi
    done
    
    # Optional dependencies
    if python3 -c "import PIL" 2>/dev/null; then
        check_ok "Pillow (OCR support)"
    else
        check_warn "Pillow: NOT INSTALLED" "Optional: pip install Pillow"
    fi
    
    if python3 -c "import pytesseract" 2>/dev/null; then
        check_ok "pytesseract (OCR support)"
    else
        check_warn "pytesseract: NOT INSTALLED" "Optional: pip install pytesseract"
    fi
}

check_api_endpoints() {
    print_section "API Endpoints"
    
    # Health check
    if curl -sf http://127.0.0.1:8081/healthz >/dev/null 2>&1; then
        check_ok "Health endpoint: RESPONDING"
    else
        check_fail "Health endpoint: NOT RESPONDING"
        return
    fi
    
    # Check response time
    if [ $QUICK_MODE -eq 0 ]; then
        local start=$(date +%s%N)
        curl -sf http://127.0.0.1:8081/healthz >/dev/null 2>&1
        local end=$(date +%s%N)
        local latency=$(( (end - start) / 1000000 ))
        
        if [ $latency -lt 100 ]; then
            check_ok "API latency: ${latency}ms (excellent)"
        elif [ $latency -lt 500 ]; then
            check_ok "API latency: ${latency}ms (good)"
        else
            check_warn "API latency: ${latency}ms (slow)"
        fi
    fi
}

check_web_search() {
    print_section "Web Search Performance"
    
    if [ $QUICK_MODE -eq 1 ]; then
        info "Skipped (quick mode)"
        return
    fi
    
    # Test simple web search
    local start=$(date +%s%N)
    local response=$(curl -sf -X POST http://127.0.0.1:8081/web/search \
        -H "Content-Type: application/json" \
        -d '{"q":"test","source":"verify","source_id":"1"}' 2>/dev/null)
    local end=$(date +%s%N)
    local latency=$(( (end - start) / 1000000 ))
    
    if [ -n "$response" ]; then
        if [ $latency -lt 5000 ]; then
            check_ok "Web search: ${latency}ms (target: <5000ms)"
        else
            check_warn "Web search: ${latency}ms (SLOW, target: <5000ms)"
        fi
    else
        check_fail "Web search: NO RESPONSE"
    fi
}

check_memory_systems() {
    print_section "Memory Systems"
    
    # ChromaDB directory
    if [ -d "/memory/chroma" ]; then
        local size=$(du -sh /memory/chroma | cut -f1)
        check_ok "ChromaDB directory exists: $size"
    else
        check_fail "ChromaDB directory missing" "mkdir -p /memory/chroma"
    fi
    
    # Check ChromaDB collections
    if python3 -c "import chromadb; chromadb.PersistentClient(path='/memory/chroma')" 2>/dev/null; then
        check_ok "ChromaDB accessible"
    else
        check_warn "ChromaDB initialization issue"
    fi
    
    # Redis memory usage
    local redis_mem=$(redis-cli info memory | grep used_memory_human | cut -d: -f2 | tr -d '\r')
    if [ -n "$redis_mem" ]; then
        info "Redis memory usage: $redis_mem"
    fi
}

check_disk_space() {
    print_section "Disk Space"
    
    # Root partition
    local usage=$(df -h / | tail -1 | awk '{print $5}' | sed 's/%//')
    if [ "$usage" -lt 80 ]; then
        check_ok "Root partition: ${usage}% used"
    elif [ "$usage" -lt 90 ]; then
        check_warn "Root partition: ${usage}% used (getting full)"
    else
        check_fail "Root partition: ${usage}% used (CRITICAL)"
    fi
    
    # /memory partition (if separate)
    if mountpoint -q /memory; then
        local mem_usage=$(df -h /memory | tail -1 | awk '{print $5}' | sed 's/%//')
        if [ "$mem_usage" -lt 80 ]; then
            check_ok "/memory partition: ${mem_usage}% used"
        else
            check_warn "/memory partition: ${mem_usage}% used"
        fi
    fi
}

check_browserless() {
    print_section "Browserless Integration"
    
    if curl -sf http://127.0.0.1:3000/health >/dev/null 2>&1; then
        check_ok "Browserless: RUNNING"
    else
        check_warn "Browserless: NOT RUNNING" "Optional but recommended for better extraction"
    fi
}

check_llm_endpoint() {
    print_section "LLM Endpoint"
    
    # Check if vLLM/Qwen endpoint responds
    if curl -sf http://127.0.0.1:9011/v1/models >/dev/null 2>&1; then
        check_ok "LLM endpoint: RESPONDING"
        
        # Get model info
        local model=$(curl -sf http://127.0.0.1:9011/v1/models | python3 -c "import sys,json; print(json.load(sys.stdin)['data'][0]['id'])" 2>/dev/null || echo "unknown")
        info "Model: $model"
    else
        check_warn "LLM endpoint: NOT RESPONDING" "Check vLLM server on GPU"
    fi
}

check_logs() {
    print_section "Recent Logs"
    
    # Check for recent errors in quantum-api logs
    if [ -f "$PROJECT_ROOT/logs/api.log" ]; then
        local errors=$(tail -100 "$PROJECT_ROOT/logs/api.log" | grep -i "error" | wc -l)
        if [ "$errors" -eq 0 ]; then
            check_ok "No recent errors in api.log"
        elif [ "$errors" -lt 5 ]; then
            check_warn "Found $errors recent error(s) in api.log"
        else
            check_fail "Found $errors recent error(s) in api.log" "Check logs/api.log"
        fi
    else
        check_warn "api.log not found"
    fi
}

check_gpu_connection() {
    print_section "GPU Connection"
    
    # Check if tunnel endpoint is accessible
    local tunnel=$(redis-cli get gpu_tunnel_endpoint 2>/dev/null || echo "")
    local direct=$(redis-cli get gpu_active_endpoint 2>/dev/null || echo "")
    
    if [ -n "$tunnel" ] || [ -n "$direct" ]; then
        check_ok "GPU endpoints configured in Redis"
        [ -n "$tunnel" ] && info "Tunnel: $tunnel"
        [ -n "$direct" ] && info "Direct: $direct"
    else
        check_warn "No GPU endpoints in Redis" "Run GPU setup script"
    fi
}

# ============================================================
# AUTO-FIX FUNCTIONS
# ============================================================

auto_fix() {
    print_section "Auto-Fix Attempts"
    
    info "Attempting to fix common issues..."
    
    # Create missing directories
    mkdir -p /memory/chroma /root/quantumdev-open/logs /root/quantumdev-open/status
    info "Created missing directories"
    
    # Restart failed services
    if ! systemctl is-active --quiet quantum-api; then
        info "Starting quantum-api..."
        systemctl start quantum-api 2>/dev/null && check_ok "Started quantum-api" || check_fail "Failed to start quantum-api"
    fi
    
    if ! systemctl is-active --quiet redis-server; then
        info "Starting redis-server..."
        systemctl start redis-server 2>/dev/null && check_ok "Started redis-server" || check_fail "Failed to start redis-server"
    fi
    
    info "Auto-fix completed. Re-run verification to check results."
}

# ============================================================
# REPORTING
# ============================================================

print_summary() {
    if [ $JSON_MODE -eq 0 ]; then
        echo ""
        echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
        echo -e "${BLUE}                        SUMMARY                                ${NC}"
        echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
        echo -e "Total checks:   $TOTAL_CHECKS"
        echo -e "${GREEN}Passed:         $PASSED_CHECKS${NC}"
        echo -e "${YELLOW}Warnings:       $WARNINGS${NC}"
        echo -e "${RED}Failed:         $FAILED_CHECKS${NC}"
        echo ""
        
        if [ $FAILED_CHECKS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
            echo -e "${GREEN}✓ System is healthy!${NC}"
        elif [ $FAILED_CHECKS -eq 0 ]; then
            echo -e "${YELLOW}⚠ System is operational with warnings${NC}"
        else
            echo -e "${RED}✗ System has critical issues${NC}"
        fi
        echo ""
    else
        # JSON output
        cat <<EOF
{
  "timestamp": "$(date -Iseconds)",
  "hostname": "$(hostname)",
  "summary": {
    "total": $TOTAL_CHECKS,
    "passed": $PASSED_CHECKS,
    "warnings": $WARNINGS,
    "failed": $FAILED_CHECKS
  },
  "status": "$([ $FAILED_CHECKS -eq 0 ] && echo "healthy" || echo "unhealthy")"
}
EOF
    fi
}

# ============================================================
# MAIN
# ============================================================

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --quick)
            QUICK_MODE=1
            shift
            ;;
        --fix)
            FIX_MODE=1
            shift
            ;;
        --json)
            JSON_MODE=1
            shift
            ;;
        --help)
            echo "Usage: $0 [--quick] [--fix] [--json] [--help]"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Run checks
print_header
check_services
check_critical_files
check_dependencies
check_api_endpoints
check_web_search
check_memory_systems
check_disk_space
check_browserless
check_llm_endpoint
check_gpu_connection
check_logs

# Auto-fix if requested
if [ $FIX_MODE -eq 1 ]; then
    auto_fix
fi

# Print summary
print_summary

# Exit code based on failures
exit $FAILED_CHECKS
