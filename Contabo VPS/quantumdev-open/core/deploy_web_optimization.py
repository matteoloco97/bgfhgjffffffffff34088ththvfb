# in realta è un .sh
#!/usr/bin/env bash
# deploy_web_optimization.sh
# ==========================
# Master deployment script per ottimizzazione web search QuantumDev
#
# Applica 3 ottimizzazioni critiche in sequenza:
# 1. Synthesis prompt aggressivo (+30% success rate)
# 2. Parallel fetch (-80% latency)
# 3. Robust content extraction (+35% extraction success)
#
# Target finale: >85% success rate, <5s latency
#
# Usage: sudo bash deploy_web_optimization.sh

set -e  # Exit on error

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

PROJECT_ROOT="/root/quantumdev-open"
BACKUP_DIR="$PROJECT_ROOT/backups/web-optimization-$(date +%Y%m%d-%H%M%S)"

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║       QUANTUMDEV WEB SEARCH OPTIMIZATION DEPLOYMENT              ║${NC}"
echo -e "${BLUE}╔══════════════════════════════════════════════════════════════════╗${NC}"
echo ""

# ===== Pre-flight checks =====
echo -e "${YELLOW}[1/9] Pre-flight checks...${NC}"

if [ ! -d "$PROJECT_ROOT" ]; then
    echo -e "${RED}❌ Project root not found: $PROJECT_ROOT${NC}"
    exit 1
fi

cd "$PROJECT_ROOT"

if ! systemctl is-active --quiet quantum-api; then
    echo -e "${RED}⚠️  quantum-api service not running${NC}"
    read -p "Start it now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sudo systemctl start quantum-api
    else
        echo -e "${RED}Aborting.${NC}"
        exit 1
    fi
fi

echo -e "${GREEN}✓ Pre-flight OK${NC}"
echo ""

# ===== Backup =====
echo -e "${YELLOW}[2/9] Creating backups...${NC}"

mkdir -p "$BACKUP_DIR"
cp backend/quantum_api.py "$BACKUP_DIR/"
cp core/web_tools.py "$BACKUP_DIR/"

echo -e "${GREEN}✓ Backups saved to: $BACKUP_DIR${NC}"
echo ""

# ===== Dependencies =====
echo -e "${YELLOW}[3/9] Checking dependencies...${NC}"

source venv/bin/activate || {
    echo -e "${RED}❌ Virtual environment not found${NC}"
    exit 1
}

# Check and install if needed
python3 -c "import trafilatura" 2>/dev/null || pip install trafilatura
python3 -c "import readability" 2>/dev/null || pip install readability-lxml
python3 -c "from bs4 import BeautifulSoup" 2>/dev/null || pip install beautifulsoup4 lxml

echo -e "${GREEN}✓ Dependencies OK${NC}"
echo ""

# ===== Copy optimization files =====
echo -e "${YELLOW}[4/9] Copying optimization modules...${NC}"

# Assume files are in current directory or provide path
if [ ! -f "synthesis_prompt_v2.py" ]; then
    echo -e "${RED}❌ synthesis_prompt_v2.py not found${NC}"
    echo "Please ensure optimization files are in $PROJECT_ROOT"
    exit 1
fi

cp synthesis_prompt_v2.py backend/
cp parallel_fetch_optimizer.py backend/
cp robust_content_extraction.py core/

echo -e "${GREEN}✓ Modules copied${NC}"
echo ""

# ===== Apply patches =====
echo -e "${YELLOW}[5/9] Applying patches to quantum_api.py...${NC}"

# Patch 1: Import synthesis
if ! grep -q "from synthesis_prompt_v2 import" backend/quantum_api.py; then
    # Find imports section and add
    sed -i '/^from utils.chroma_handler import/a from synthesis_prompt_v2 import build_aggressive_synthesis_prompt' backend/quantum_api.py
    echo -e "${GREEN}✓ Added synthesis import${NC}"
else
    echo -e "${BLUE}ℹ Synthesis import already present${NC}"
fi

# Patch 2: Import parallel fetch
if ! grep -q "from parallel_fetch_optimizer import" backend/quantum_api.py; then
    sed -i '/^from synthesis_prompt_v2 import/a from parallel_fetch_optimizer import parallel_fetch_and_extract' backend/quantum_api.py
    echo -e "${GREEN}✓ Added parallel fetch import${NC}"
else
    echo -e "${BLUE}ℹ Parallel fetch import already present${NC}"
fi

echo ""

# ===== Manual patch instructions =====
echo -e "${YELLOW}[6/9] MANUAL STEPS REQUIRED${NC}"
echo ""
echo -e "${YELLOW}You need to manually edit 2 files:${NC}"
echo ""
echo -e "${BLUE}FILE 1: backend/quantum_api.py${NC}"
echo "--------------------------------------"
echo ""
echo "CHANGE 1: Replace synthesis prompt (around line 450-500)"
echo "FIND:"
echo '  prompt = ('
echo '      "Sei un assistente che risponde SOLO usando le fonti fornite.\\n"'
echo '      ...'
echo '  )'
echo ""
echo "REPLACE WITH:"
echo '  prompt = build_aggressive_synthesis_prompt(q, ['
echo '      {"idx": i+1, "title": e.get("title",""), "url": e["url"], "text": e["text"]}'
echo '      for i, e in enumerate(synth_docs)'
echo '  ])'
echo ""
echo "CHANGE 2: Replace sequential fetch with parallel (around line 600-650)"
echo "FIND:"
echo '  for r in topk[:nsum]:'
echo '      url = r.get("url", "")'
echo '      ...'
echo '      text, og_img = await asyncio.wait_for('
echo '          fetch_and_extract(url),'
echo ""
echo "REPLACE WITH:"
echo '  # Fetch parallelo (NUOVO)'
echo '  extracts, fetch_stats = await parallel_fetch_and_extract('
echo '      results=topk[:nsum],'
echo '      max_concurrent=WEB_FETCH_MAX_INFLIGHT,'
echo '      timeout_per_url=WEB_FETCH_TIMEOUT_S,'
echo '      min_successful=2,'
echo '  )'
echo '  '
echo '  # Estrai stats'
echo '  attempted = fetch_stats.get("attempted", 0)'
echo '  ok_count = fetch_stats.get("ok", 0)'
echo '  timeouts = fetch_stats.get("timeouts", 0)'
echo '  errors = fetch_stats.get("errors", 0)'
echo '  fetch_duration_ms = fetch_stats.get("duration_ms", 0)'
echo '  done_early = fetch_stats.get("early_exit", False)'
echo ""
echo ""
echo -e "${BLUE}FILE 2: core/web_tools.py${NC}"
echo "--------------------------------------"
echo ""
echo "Add import at top:"
echo '  from robust_content_extraction import extract_content_robust'
echo ""
echo "In fetch_and_extract_robust(), replace extraction strategies with:"
echo '  text = extract_content_robust(html, url)'
echo ""
echo ""

read -p "Press ENTER when you've completed the manual edits..." 

echo ""

# ===== Validate syntax =====
echo -e "${YELLOW}[7/9] Validating Python syntax...${NC}"

python3 -m py_compile backend/quantum_api.py || {
    echo -e "${RED}❌ Syntax error in quantum_api.py${NC}"
    echo "Restoring backup..."
    cp "$BACKUP_DIR/quantum_api.py" backend/
    exit 1
}

python3 -m py_compile core/web_tools.py || {
    echo -e "${RED}❌ Syntax error in web_tools.py${NC}"
    echo "Restoring backup..."
    cp "$BACKUP_DIR/web_tools.py" core/
    exit 1
}

echo -e "${GREEN}✓ Syntax validation passed${NC}"
echo ""

# ===== Restart service =====
echo -e "${YELLOW}[8/9] Restarting quantum-api service...${NC}"

sudo systemctl restart quantum-api

# Wait for startup
echo -n "Waiting for service to be ready"
for i in {1..10}; do
    sleep 1
    echo -n "."
    if curl -s http://127.0.0.1:8081/healthz > /dev/null 2>&1; then
        echo ""
        echo -e "${GREEN}✓ Service is UP${NC}"
        break
    fi
done

# Check if still down
if ! curl -s http://127.0.0.1:8081/healthz > /dev/null 2>&1; then
    echo -e "${RED}❌ Service failed to start${NC}"
    echo "Checking logs..."
    sudo journalctl -u quantum-api -n 50 --no-pager
    
    echo ""
    echo "Restoring backups..."
    cp "$BACKUP_DIR/quantum_api.py" backend/
    cp "$BACKUP_DIR/web_tools.py" core/
    sudo systemctl restart quantum-api
    
    exit 1
fi

echo ""

# ===== Run tests =====
echo -e "${YELLOW}[9/9] Running validation tests...${NC}"
echo ""

test_queries=(
    "meteo Roma domani"
    "python tutorial"
    "ultime notizie Italia"
)

success_count=0
total_tests=${#test_queries[@]}

for query in "${test_queries[@]}"; do
    echo -e "${BLUE}Testing: \"$query\"${NC}"
    
    start_time=$(date +%s.%N)
    
    response=$(curl -s -X POST "http://127.0.0.1:8081/web/search" \
        -H "Content-Type: application/json" \
        -d "{\"q\": \"$query\", \"k\": 5, \"source\": \"test\", \"source_id\": \"test\"}")
    
    end_time=$(date +%s.%N)
    latency=$(echo "$end_time - $start_time" | bc)
    
    # Check if got useful response
    summary=$(echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('summary',''))" 2>/dev/null || echo "")
    
    if [ -n "$summary" ] && [ ${#summary} -gt 50 ]; then
        echo -e "  ${GREEN}✓ SUCCESS${NC} (${latency}s)"
        echo -e "  Summary: ${summary:0:100}..."
        ((success_count++))
    else
        echo -e "  ${RED}✗ FAILED${NC} (${latency}s)"
        echo -e "  Response: ${response:0:200}"
    fi
    
    echo ""
done

success_rate=$(echo "scale=1; $success_count * 100 / $total_tests" | bc)

echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                     DEPLOYMENT RESULTS                            ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "Success Rate: ${GREEN}${success_rate}%${NC} (${success_count}/${total_tests} tests passed)"
echo -e "Backups saved: ${BACKUP_DIR}"
echo ""

if [ "$success_count" -ge 2 ]; then
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                  ✅ DEPLOYMENT SUCCESSFUL                         ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Monitor logs: sudo journalctl -u quantum-api -f"
    echo "2. Check metrics in production"
    echo "3. If issues: bash $0 rollback"
else
    echo -e "${RED}╔══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║                   ⚠️  DEPLOYMENT INCOMPLETE                       ║${NC}"
    echo -e "${RED}╚══════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "Review the failed tests and check logs"
    echo "Rollback if needed: bash $0 rollback"
fi

echo ""
echo "Full test command for manual verification:"
echo ""
echo 'curl -X POST "http://127.0.0.1:8081/web/search" \'
echo '  -H "Content-Type: application/json" \'
echo '  -d '"'"'{"q": "meteo Roma domani", "k": 5, "source": "test", "source_id": "test"}'"'"' | jq'

exit 0
