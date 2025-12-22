# Test Commands for Jarvis AI Auto-Web Feature

This document contains test commands to verify the automatic web tool usage functionality.

## Prerequisites

Make sure the QuantumDev API server is running on `http://127.0.0.1:8081`

## Test 1: Weather Query (Auto-Web)

This test verifies that the orchestrator automatically uses web/weather tools when asked about weather.

```bash
curl -X POST http://127.0.0.1:8081/unified \
  -H "Content-Type: application/json" \
  -d '{"q": "Meteo Roma oggi?", "source": "test", "source_id": "debug"}'
```

**Expected Results:**
- `strategy` should be `"hybrid"` or `"tool_assisted"` (NOT `"direct_llm"`)
- `tool_results` should contain weather data or web search results
- `reply` should contain actual weather information (temperature, conditions, etc.)
- Response should NOT say "ti consiglio di consultare un sito di meteo"

## Test 2: ANSA News Query (Auto-Web)

This test verifies that the orchestrator automatically uses web/news tools when asked about news.

```bash
curl -X POST http://127.0.0.1:8081/unified \
  -H "Content-Type: application/json" \
  -d '{"q": "Consulta ANSA e dimmi le ultime notizie di oggi", "source": "test", "source_id": "debug"}'
```

**Expected Results:**
- `strategy` should be `"hybrid"` or `"tool_assisted"` (NOT `"direct_llm"`)
- `tool_results` should contain web search or news agent results
- `reply` should contain actual news headlines and summaries
- Response should cite sources (e.g., "Ho appena controllato ANSA...")
- Response should NOT say "dovresti controllare un sito di notizie"

## Test 3: Bitcoin Price Query (Auto-Web)

This test verifies automatic price lookup for crypto.

```bash
curl -X POST http://127.0.0.1:8081/unified \
  -H "Content-Type: application/json" \
  -d '{"q": "Quanto vale Bitcoin ora?", "source": "test", "source_id": "debug"}'
```

**Expected Results:**
- `strategy` should be `"hybrid"` or `"tool_assisted"`
- `tool_results` should contain price data
- `reply` should include current BTC price with source citation

## Test 4: General Query (Direct LLM)

This test verifies that general queries that don't need web still work correctly.

```bash
curl -X POST http://127.0.0.1:8081/unified \
  -H "Content-Type: application/json" \
  -d '{"q": "Spiegami cosa è il machine learning", "source": "test", "source_id": "debug"}'
```

**Expected Results:**
- `strategy` might be `"direct_llm"` or `"hybrid"` depending on classifier
- Response should provide a good explanation
- No web tools needed for this general knowledge question

## Debugging Tips

### Check Response Structure

All responses should have this structure:
```json
{
  "reply": "...",
  "query_type": "research|general|...",
  "strategy": "hybrid|tool_assisted|direct_llm",
  "tool_results": [...],
  "duration_ms": 123,
  "success": true
}
```

### Common Issues

1. **Strategy is always "direct_llm"**: Check that the QueryAnalyzer patterns are matching correctly
2. **No tool_results**: Verify that function calling is enabled and tools are registered
3. **Generic responses**: Check that tool results are being properly integrated into the final LLM prompt

### Check Orchestrator Health

```bash
curl http://127.0.0.1:8081/healthz | jq
```

Look for:
- `"smart_intent": true`
- `"live_agents"` section showing available agents

### Telegram Bot Testing

Once the server is verified working, test via Telegram:

1. Send: "Che tempo fa a Milano?"
   - Bot should automatically fetch weather without `/web` command

2. Send: "Ultime notizie ANSA"
   - Bot should automatically fetch news without `/web` command

3. Send: "Quanto vale ETH?"
   - Bot should automatically fetch Ethereum price
