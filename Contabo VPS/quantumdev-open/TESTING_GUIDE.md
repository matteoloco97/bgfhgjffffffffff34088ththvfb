# Testing Persona Cleanup and Smart Routing

## Quick Test Commands

### Test 1: Check Persona via API

```bash
curl -X POST http://127.0.0.1:8081/persona/get \
  -H 'Content-Type: application/json' \
  -d '{
  "source": "global",
  "source_id": "default"
}'
```

Expected: Should return persona with accurate descriptions of web and memory capabilities.

### Test 2: Meta Query (Should use DIRECT_LLM, not web)

```bash
curl -X POST http://127.0.0.1:8081/generate \
  -H 'Content-Type: application/json' \
  -d '{
  "prompt": "Chi sei e cosa puoi fare?"
}'
```

Expected response should:
- State it's Jarvis/Quantum AI
- Mention ability to access web when needed
- Mention memory capabilities (ChromaDB, Redis)
- NOT say "non posso accedere a internet" or "non ho memoria"

### Test 3: Live Query (Should use web automatically)

```bash
curl -X POST http://127.0.0.1:8081/generate \
  -H 'Content-Type: application/json' \
  -d '{
  "prompt": "Meteo Roma oggi"
}'
```

Expected: Should detect as live query and use weather agent or web search automatically.

### Test 4: Manual /web Command

```bash
curl -X POST http://127.0.0.1:8081/web/search \
  -H 'Content-Type: application/json' \
  -d '{
  "q": "prezzo Bitcoin oggi",
  "source": "test",
  "source_id": "manual"
}'
```

Expected: Should return web search results with summary and sources.

### Test 5: Explain Query (Should NOT use web)

```bash
curl -X POST http://127.0.0.1:8081/generate \
  -H 'Content-Type: application/json' \
  -d '{
  "prompt": "Spiegami il Kelly Criterion"
}'
```

Expected: Should use DIRECT_LLM, not web (conceptual/theoretical query).

### Test 6: Chat with Memory Context

```bash
curl -X POST http://127.0.0.1:8081/chat \
  -H 'Content-Type: application/json' \
  -d '{
  "source": "test",
  "source_id": "test123",
  "text": "Che hardware ha Jarvis?"
}'
```

Expected: Should query ChromaDB for hardware facts and use them in response.

## Automated Tests

Run the persona and routing tests:

```bash
cd /path/to/quantumdev-open
python3 tests/test_persona_and_routing.py
```

Or run individual test functions:

```bash
python3 << 'EOF'
import sys
sys.path.insert(0, '.')
from tests.test_persona_and_routing import TestPersonaDefinitions
test = TestPersonaDefinitions()
test.test_capabilities_brief_no_false_limitations()
test.test_default_persona_system_messages()
print("✓ All tests passed")
EOF
```

## Routing Decision Test

Test that routing decisions work correctly:

```bash
python3 << 'EOF'
import sys
sys.path.insert(0, '.')

from backend.quantum_api import (
    _is_meta_capability_query,
    _is_explain_query,
    _is_smalltalk_query,
    _is_quick_live_query
)

# Test meta queries
assert _is_meta_capability_query("chi sei?") == True
assert _is_meta_capability_query("puoi accedere a internet?") == True
print("✓ Meta query detection works")

# Test explain queries
assert _is_explain_query("spiegami il teorema di Bayes") == True
assert _is_explain_query("what is machine learning") == True
print("✓ Explain query detection works")

# Test smalltalk
assert _is_smalltalk_query("ciao") == True
assert _is_smalltalk_query("meteo Roma") == False
print("✓ Smalltalk detection works")

# Test live queries
assert _is_quick_live_query("meteo Roma") == True
assert _is_quick_live_query("prezzo Bitcoin") == True
assert _is_quick_live_query("risultati Serie A") == True
print("✓ Live query detection works")

print("\n✓✓✓ All routing tests passed ✓✓✓")
EOF
```

## Expected Behavior Summary

### 1. Persona Cleanup ✓
- **Web Access**: AI correctly states it CAN access web via /web command or automatically
- **Memory**: AI correctly states it HAS long-term memory via ChromaDB and Redis cache
- **Context**: AI explains it maintains conversation context but doesn't remember every past chat word-for-word
- **No False Limitations**: Removed phrases like "non posso accedere a internet", "non ho memoria"

### 2. Smart Routing ✓
- **Manual /web**: Always executes web search when explicitly requested
- **Auto-web**: Triggers for live queries (meteo, prezzi, notizie, risultati sportivi)
- **DIRECT_LLM**: Used for conceptual/theoretical queries (explain, define, calculate)
- **Memory Integration**: /chat endpoint queries ChromaDB before responding
- **Meta Queries**: Questions about AI capabilities use DIRECT_LLM with capability brief

### 3. Backward Compatibility ✓
- All existing endpoints maintained
- API schemas unchanged
- Telegram bot integration works as before
- Environment variables respected
