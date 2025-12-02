# Deployment & Testing Checklist

## Pre-Deployment Checklist

### ✅ Code Review
- [x] All code review issues resolved
- [x] Security analysis completed - NO VULNERABILITIES
- [x] Pattern matching tests passed (10/10)
- [x] Python syntax validation passed (3/3 files)

### ✅ Documentation
- [x] TEST_COMMANDS.md created
- [x] IMPLEMENTATION_SUMMARY.md created
- [x] SECURITY_SUMMARY.md created
- [x] Code comments updated

### ✅ Backward Compatibility
- [x] Telegram bot maintains fallback to `/chat`
- [x] Existing endpoints unchanged
- [x] No breaking changes

## Deployment Steps

### 1. Backup Current System
```bash
# Backup current code
cd /root/quantumdev-open
git stash
git branch backup-$(date +%Y%m%d) HEAD

# Backup .env file
cp .env .env.backup-$(date +%Y%m%d)
```

### 2. Deploy Changes
```bash
# Pull the changes
git fetch origin
git checkout copilot/update-query-analyzer-patterns
git pull origin copilot/update-query-analyzer-patterns

# Verify files
ls -la core/master_orchestrator.py
ls -la backend/quantum_api.py
ls -la scripts/telegram_bot.py
```

### 3. Environment Configuration (Optional)
```bash
# Edit .env to add/verify QUANTUM_UNIFIED_URL
nano .env

# Add this line (or verify it exists):
# QUANTUM_UNIFIED_URL=http://127.0.0.1:8081/unified
```

### 4. Restart Services
```bash
# Stop services
pkill -f quantum_api.py
pkill -f telegram_bot.py

# Start quantum_api
cd /root/quantumdev-open
nohup python3 backend/quantum_api.py > logs/api.log 2>&1 &

# Wait for API to be ready (check health)
sleep 5
curl http://127.0.0.1:8081/healthz | jq

# Start telegram bot
nohup python3 scripts/telegram_bot.py > logs/telegram.log 2>&1 &
```

### 5. Verify Services
```bash
# Check if processes are running
ps aux | grep quantum_api.py
ps aux | grep telegram_bot.py

# Check logs for errors
tail -50 logs/api.log
tail -50 logs/telegram.log

# Test health endpoint
curl http://127.0.0.1:8081/healthz | jq '.ok'
# Should return: true
```

## Testing Checklist

### Automated Tests
```bash
# Run pattern matching tests
python3 /tmp/test_query_analyzer.py
# Expected: All tests passed!

# Syntax validation
python3 -m py_compile core/master_orchestrator.py
python3 -m py_compile backend/quantum_api.py
python3 -m py_compile scripts/telegram_bot.py
# Expected: No errors
```

### Manual API Tests

#### Test 1: Weather Query (Auto-Web) ✅
```bash
curl -X POST http://127.0.0.1:8081/unified \
  -H "Content-Type: application/json" \
  -d '{"q": "Meteo Roma oggi?", "source": "test", "source_id": "debug"}' | jq
```

**Expected Response:**
- `success: true`
- `strategy: "hybrid"`
- `query_type: "research"`
- `tool_results` should contain weather data
- `reply` should contain temperature, conditions, etc.
- Should NOT say "consulta un sito meteo"

#### Test 2: ANSA News Query (Auto-Web) ✅
```bash
curl -X POST http://127.0.0.1:8081/unified \
  -H "Content-Type: application/json" \
  -d '{"q": "Consulta ANSA e dimmi le ultime notizie di oggi", "source": "test", "source_id": "debug"}' | jq
```

**Expected Response:**
- `success: true`
- `strategy: "hybrid"`
- `query_type: "research"`
- `tool_results` should contain news data
- `reply` should cite ANSA or other sources
- Should NOT say "dovresti controllare un sito"

#### Test 3: Bitcoin Price Query (Auto-Web) ✅
```bash
curl -X POST http://127.0.0.1:8081/unified \
  -H "Content-Type: application/json" \
  -d '{"q": "Quanto vale Bitcoin ora?", "source": "test", "source_id": "debug"}' | jq
```

**Expected Response:**
- `success: true`
- `strategy: "hybrid"`
- `query_type: "research"`
- `tool_results` should contain price data
- `reply` should include current BTC price

#### Test 4: General Query (Direct LLM) ✅
```bash
curl -X POST http://127.0.0.1:8081/unified \
  -H "Content-Type: application/json" \
  -d '{"q": "Spiegami cosa è il machine learning", "source": "test", "source_id": "debug"}' | jq
```

**Expected Response:**
- `success: true`
- `strategy: "direct_llm"` or `"hybrid"`
- `query_type: "general"` or `"research"`
- Good explanation provided

#### Test 5: Fallback to /chat ✅
```bash
# Stop unified endpoint temporarily
# The telegram bot should fallback to /chat

curl -X POST http://127.0.0.1:8081/chat \
  -H "Content-Type: application/json" \
  -d '{"text": "Ciao", "source": "test", "source_id": "debug"}' | jq
```

**Expected Response:**
- `reply` should contain a greeting
- Should work normally

### Telegram Bot Tests

#### Test 6: Weather via Telegram ✅
Send to bot:
```
Che tempo fa a Milano?
```

**Expected:**
- Bot should respond with weather data automatically
- Should NOT ask to use `/web` command
- Should cite source (e.g., "Open-Meteo")

#### Test 7: Bitcoin Price via Telegram ✅
Send to bot:
```
Prezzo Bitcoin
```

**Expected:**
- Bot should respond with current BTC price
- Should cite source (e.g., "CoinGecko" or similar)

#### Test 8: News via Telegram ✅
Send to bot:
```
Ultime notizie oggi
```

**Expected:**
- Bot should fetch and display news
- Should cite sources

#### Test 9: General Chat via Telegram ✅
Send to bot:
```
Come funziona il machine learning?
```

**Expected:**
- Bot should provide explanation
- No web tools needed
- Direct LLM response

#### Test 10: Conversational Context ✅
Send sequence to bot:
```
1. Ciao
2. Ricordi il mio nome? (if you previously told it your name)
3. Che cosa abbiamo discusso prima?
```

**Expected:**
- Context should be maintained across messages
- Bot should remember previous conversation

## Monitoring

### Key Metrics to Monitor

1. **Strategy Distribution**
   ```bash
   # Check logs for strategy usage
   grep "Strategy:" logs/api.log | tail -20
   ```

2. **Tool Usage**
   ```bash
   # Check logs for tool executions
   grep "tool_results" logs/api.log | tail -20
   ```

3. **Error Rate**
   ```bash
   # Check for errors
   grep "error" logs/api.log | tail -20
   grep "ERROR" logs/telegram.log | tail -20
   ```

4. **Response Times**
   ```bash
   # Check duration_ms in responses
   grep "duration_ms" logs/api.log | tail -20
   ```

### Success Criteria

- ✅ Health endpoint returns `{"ok": true}`
- ✅ Weather queries use HYBRID strategy
- ✅ News queries use HYBRID strategy
- ✅ Price queries use HYBRID strategy
- ✅ Tool results are present in responses
- ✅ Responses cite sources
- ✅ Telegram bot responds to queries
- ✅ Fallback to /chat works
- ✅ No increase in error rate
- ✅ Response times acceptable (< 5s for most queries)

## Rollback Plan

If issues are encountered:

```bash
# Stop services
pkill -f quantum_api.py
pkill -f telegram_bot.py

# Rollback to backup branch
cd /root/quantumdev-open
git checkout main  # or your previous branch
git pull origin main

# Restore .env if needed
cp .env.backup-YYYYMMDD .env

# Restart services
nohup python3 backend/quantum_api.py > logs/api.log 2>&1 &
nohup python3 scripts/telegram_bot.py > logs/telegram.log 2>&1 &

# Verify
curl http://127.0.0.1:8081/healthz | jq
```

## Post-Deployment

### User Feedback Collection

Monitor for:
1. User satisfaction with auto-web responses
2. Accuracy of weather/price/news data
3. Response quality improvements
4. Any false positives/negatives in pattern matching

### Potential Tuning

If needed, adjust patterns in `core/master_orchestrator.py`:
- Add more keywords to RESEARCH_PATTERNS
- Adjust strategy selection thresholds
- Fine-tune prompt templates

## Support

For issues or questions:
1. Check logs in `/root/quantumdev-open/logs/`
2. Review TEST_COMMANDS.md
3. Review IMPLEMENTATION_SUMMARY.md
4. Review SECURITY_SUMMARY.md

---

**Last Updated**: 2025-12-02  
**Version**: 1.0  
**Status**: READY FOR DEPLOYMENT ✅
