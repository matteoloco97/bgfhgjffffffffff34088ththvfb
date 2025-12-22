# Quick Reference: Web Synthesis Optimization

This guide provides quick snippets for using the new optimization features.

---

## 🚀 Using LLM Presets

### Get a Preset
```python
from core.llm_config import get_preset

# Get web synthesis preset (optimized for speed)
preset = get_preset("web_synthesis")
# Returns: LLMPreset(temperature=0.2, max_tokens=120, ...)
```

### Available Presets
- `web_synthesis` - Ultra-fast, concise responses (50 words max)
- `chat` - Standard conversational
- `code_generation` - Low temp for code
- `creative_writing` - High temp for creativity
- `factual_qa` - Very low temp for facts

### Use with LLM
```python
from core.chat_engine import reply_with_llm

# With preset
preset = get_preset("web_synthesis")
response = await reply_with_llm(
    user_text=prompt,
    persona=persona,
    temperature=preset.temperature,
    max_tokens=preset.max_tokens,
    stop_sequences=preset.stop_sequences,
)
```

---

## 🔧 Smart Extract Trimming

### Basic Usage
```python
from core.web_response_formatter import smart_trim_extracts

extracts = [
    {"url": "...", "title": "...", "text": "long text..."},
    # ... more extracts
]

# Trim to optimize for LLM
trimmed = smart_trim_extracts(
    extracts,
    query="user query",
    max_sources=3,           # Max 3 sources
    max_chars_per_source=200, # 200 chars each
    max_total_tokens=400      # Total token budget
)

# Result includes relevance scores
for ext in trimmed:
    print(f"Score: {ext['relevance_score']}, Tokens: {ext['tokens']}")
```

### How It Works
1. Extracts keywords from query
2. Scores each extract by keyword relevance
3. Sorts by relevance score
4. Trims to fit token budget
5. Preserves sentence boundaries

---

## 🧹 HTML Cleaning

### Clean Extract Text
```python
from core.web_response_formatter import _clean_extract

dirty = "<p>Some <b>HTML</b> text with &nbsp; entities</p>"
clean = _clean_extract(dirty)
# Returns: "Some HTML text with entities"
```

### What Gets Removed
- HTML tags (`<p>`, `<div>`, etc.)
- HTML entities (`&nbsp;`, `&#8364;`, etc.)
- Duplicate whitespace
- Repeated sentences

---

## 📊 Performance Logging

### Read Performance Logs
Look for logs with `[PERF]` prefix:

```
[PERF] Web synthesis breakdown: 
fetch=1234ms, preprocess=56ms, llm=789ms, postprocess=12ms, total=2091ms
```

### Add Your Own Timing
```python
import time

t_start = time.perf_counter()
# ... your code ...
elapsed_ms = int((time.perf_counter() - t_start) * 1000)
log.info(f"[PERF] Operation took {elapsed_ms}ms")
```

---

## 🎯 Token Utilities

### Estimate Tokens
```python
from core.web_response_formatter import _approx_tokens

text = "Some text to estimate..."
tokens = _approx_tokens(text)
# Uses 1 token ≈ 4 characters
```

### Extract Keywords
```python
from core.web_response_formatter import _extract_keywords

query = "What is the price of Bitcoin?"
keywords = _extract_keywords(query, top_n=5)
# Returns: ['price', 'bitcoin'] (no stopwords)
```

### Score Relevance
```python
from core.web_response_formatter import _score_extract_relevance

text = "Bitcoin price is $45000"
keywords = ["bitcoin", "price"]
score = _score_extract_relevance(text, keywords)
# Returns: 1.0 (both keywords found)
```

---

## ⚡ Quick Tips

### 1. Always Trim Before LLM
```python
# ❌ DON'T
response = await llm_func(build_prompt(raw_extracts))

# ✅ DO
trimmed = smart_trim_extracts(raw_extracts, query)
response = await llm_func(build_prompt(trimmed))
```

### 2. Use Presets for Consistency
```python
# ❌ DON'T hardcode
response = await reply_with_llm(prompt, persona, temperature=0.2, max_tokens=120)

# ✅ DO use preset
preset = get_preset("web_synthesis")
response = await reply_with_llm(
    prompt, persona,
    temperature=preset.temperature,
    max_tokens=preset.max_tokens
)
```

### 3. Pre-compile Regex for Repeated Use
```python
# ❌ DON'T compile repeatedly
for text in texts:
    cleaned = re.sub(r'<[^>]+>', '', text)

# ✅ DO compile once
import re
TAG_PATTERN = re.compile(r'<[^>]+>')
for text in texts:
    cleaned = TAG_PATTERN.sub('', text)
```

### 4. Log Performance Breakdowns
```python
# ✅ DO log detailed timings
log.info(
    f"[PERF] Pipeline: "
    f"step1={t1}ms, step2={t2}ms, total={total}ms"
)
```

---

## 🔍 Debugging

### Check Preset Configuration
```python
from core.llm_config import get_preset_info

info = get_preset_info("web_synthesis")
print(info)
# Shows all preset parameters
```

### Verify Trimming Results
```python
trimmed = smart_trim_extracts(extracts, query)
total_tokens = sum(e.get("tokens", 0) for e in trimmed)
print(f"Total tokens: {total_tokens}")
print(f"Sources: {len(trimmed)}")
for e in trimmed:
    print(f"  - {e['title']}: {e['tokens']} tokens, score={e['relevance_score']}")
```

### Test Keyword Extraction
```python
query = "Your test query here"
keywords = _extract_keywords(query)
print(f"Keywords: {keywords}")
```

---

## 📚 Further Reading

- Full documentation: `WEB_SYNTHESIS_OPTIMIZATION_SUMMARY.md`
- Test examples: `tests/test_web_synthesis_optimization.py`
- LLM config: `core/llm_config.py`
- Formatter: `core/web_response_formatter.py`

---

**Last Updated**: 2025-12-04
