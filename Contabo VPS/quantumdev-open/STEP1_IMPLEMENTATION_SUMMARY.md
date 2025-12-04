# Step 1 - Pipeline Miglioramenti Comprensione Domande

## Summary

This implementation enhances the QuantumDev question understanding pipeline with three major improvements:

1. **Intent LLM + Fallback** - Smarter intent detection with LLM fallback for uncertain patterns
2. **Text Pre-processing** - Centralized query normalization with language detection and multi-question handling
3. **Memory Integration** - Aggressive user profile and episodic memory injection into LLM context

## Changes Made

### New Files Created

#### 1. `core/text_preprocessing.py`
Centralized text preprocessing module that:
- Normalizes whitespace and removes control characters
- Detects language (Italian/English) using stopwords
- Identifies multi-question queries
- Preserves accents and special characters

**Functions:**
- `preprocess_user_query(raw_text: str) -> Dict` - Main preprocessing function

**Returns:**
- `clean_text`: Normalized text
- `lower_text`: Lowercase version
- `has_multiple_questions`: Boolean flag
- `language_hint`: "it", "en", or None

#### 2. `core/memory_context_builder.py`
Memory context builder that integrates user profile and episodic memory:
- Detects self-referential questions ("chi sono?", "le mie preferenze", etc.)
- Retrieves relevant user profile facts
- Retrieves recent conversation summaries
- Respects token budgets
- Saves new memory (episodic buffer + "remember" statements)
- Auto-summarizes conversation buffer when needed

**Functions:**
- `build_memory_context()` - Build context from profile + episodic memory
- `save_to_memory()` - Save new turn to memory
- `maybe_summarize_buffer()` - Conditionally summarize episodic buffer
- `is_self_question()` - Detect self-referential questions

### Modified Files

#### 3. `core/smart_intent_classifier.py`
Enhanced with LLM fallback logic:
- Added environment variable configuration (INTENT_LLM_MIN_CONFIDENCE, INTENT_LLM_MAX_FALLBACKS)
- New helper method `_try_llm_classification()` for LLM-based intent detection
- New helper method `_normalize_result()` to standardize intent results
- Enhanced `classify()` to use LLM as fallback when pattern confidence is low
- All results now include:
  - `source`: "pattern" or "llm"
  - `low_confidence`: Boolean (true if confidence < 0.65)

#### 4. `core/master_orchestrator.py`
Integrated preprocessing and memory:
- **Step 1 (NEW)**: Text preprocessing at query entry
  - Uses `preprocess_user_query()` to normalize input
  - Extracts clean_text, lower_text, language_hint, multi-question flag
- **Step 3B (NEW)**: Personal memory context loading
  - Calls `build_memory_context()` to retrieve profile + episodic facts
  - Constructs formatted memory context text
- **Modified Direct LLM generation**: 
  - Injects personal memory context into system prompt
  - Adds multi-question handling hint when detected
  - Uses clean_text instead of raw query
- **Step 6 (ENHANCED)**: Memory saving
  - Saves to episodic buffer via `save_to_memory()`
  - Auto-detects "remember" statements and saves to user profile
  - Conditionally summarizes buffer when threshold reached

#### 5. `backend/quantum_api.py`
Added new environment variables:
- `USER_PROFILE_ENABLED` (default: True)
- `EPISODIC_MEMORY_ENABLED` (default: True)
- `MEMORY_PROFILE_TOP_K` (default: 5)
- `MEMORY_EPISODIC_TOP_K` (default: 3)
- `MEMORY_MAX_CONTEXT_TOKENS` (default: 800)

## Environment Variables

### Intent Classification (in `core/smart_intent_classifier.py`)
```bash
# Enable LLM-based intent classification fallback
LLM_INTENT_ENABLED=0  # 0=disabled, 1=enabled (default: 0)

# Minimum confidence score to accept LLM classification
INTENT_LLM_MIN_CONFIDENCE=0.45  # default: 0.45

# Maximum number of LLM fallback attempts (for future use)
INTENT_LLM_MAX_FALLBACKS=1  # default: 1
```

### Personal Memory (in `backend/quantum_api.py`)
```bash
# Enable user profile memory (stable facts about user)
USER_PROFILE_ENABLED=1  # default: 1 (True)

# Enable episodic memory (recent conversation summaries)
EPISODIC_MEMORY_ENABLED=1  # default: 1 (True)

# Number of user profile facts to retrieve
MEMORY_PROFILE_TOP_K=5  # default: 5

# Number of episodic memory summaries to retrieve
MEMORY_EPISODIC_TOP_K=3  # default: 3

# Maximum tokens for memory context (combined profile + episodic)
MEMORY_MAX_CONTEXT_TOKENS=800  # default: 800
```

### Existing Memory Variables (referenced)
```bash
# User profile collection name
USER_PROFILE_COLLECTION=user_profile  # default: user_profile

# Episodic memory collection name
EPISODIC_MEMORY_COLLECTION=conversation_history  # default: conversation_history

# Episodic buffer size (messages before summarization)
EPISODIC_BUFFER_SIZE=10  # default: 10

# Episodic buffer token limit
EPISODIC_BUFFER_TOKEN_LIMIT=2000  # default: 2000

# Enable automatic summarization
EPISODIC_SUMMARIZE_ENABLED=1  # default: 1 (True)
```

## How It Works

### Query Flow (via /unified endpoint)

1. **Pre-processing**
   - Query passes through `preprocess_user_query()`
   - Gets normalized, language detected, multi-question flag set
   - Clean text used for all downstream processing

2. **Intent Classification**
   - Pattern-based classification runs first
   - If confidence < 0.7 and LLM_INTENT_ENABLED=1:
     - Attempts LLM-based classification via `get_llm_intent_classifier()`
     - If LLM confidence >= INTENT_LLM_MIN_CONFIDENCE, uses LLM result
     - Otherwise falls back to pattern result
   - Result includes source ("pattern"/"llm") and low_confidence flag

3. **Memory Context Building**
   - Checks if query is self-referential (e.g., "chi sono?", "le mie preferenze")
   - Retrieves up to MEMORY_PROFILE_TOP_K relevant user profile facts
   - Retrieves up to MEMORY_EPISODIC_TOP_K recent conversation summaries
   - Trims combined context to MEMORY_MAX_CONTEXT_TOKENS
   - Formats as bullet-pointed sections

4. **LLM Generation**
   - System prompt constructed with:
     - Conversational memory (existing)
     - **NEW**: Personal memory context (profile + episodic)
     - **NEW**: Multi-question hint (if detected)
   - Query sent to LLM with enriched context

5. **Memory Saving**
   - Turn saved to episodic buffer
   - Detects "ricorda che..." / "remember that..." patterns
   - Saves user profile facts when detected
   - Auto-summarizes buffer if size/token threshold reached

## Testing

All components tested independently:
- ✅ Text preprocessing (language detection, multi-question, normalization)
- ✅ Intent classifier (pattern + LLM fallback structure, new fields)
- ✅ Memory context builder (self-question detection, context formatting)
- ✅ All Python files have valid syntax
- ✅ Graceful degradation when optional dependencies missing

## Backward Compatibility

- ✅ No breaking changes to existing APIs
- ✅ All new fields are additive (source, low_confidence)
- ✅ Environment variables have sensible defaults
- ✅ Features can be disabled via env vars
- ✅ Graceful fallback when LLM intent classifier not available
- ✅ No new dependencies added to requirements.txt

## Dependencies

**None added** - All new code uses only existing dependencies:
- Uses existing user_profile_memory.py and episodic_memory.py modules
- Uses existing token_budget utilities
- Uses existing llm_intent_classifier (optional)
- Gracefully degrades if dotenv or other deps missing

## Usage Example

### Enable All Features
```bash
# .env or environment
LLM_INTENT_ENABLED=1
INTENT_LLM_MIN_CONFIDENCE=0.45

USER_PROFILE_ENABLED=1
EPISODIC_MEMORY_ENABLED=1
MEMORY_PROFILE_TOP_K=5
MEMORY_EPISODIC_TOP_K=3
MEMORY_MAX_CONTEXT_TOKENS=800
```

### API Call
```python
POST /unified
{
  "q": "Ciao! Cosa sai di me? E qual è il meteo oggi?",
  "source": "tg",
  "source_id": "matteo"
}
```

### Processing
1. Pre-processing detects:
   - Language: Italian
   - Multi-question: Yes (2 questions)
2. Intent: DIRECT_LLM (conversational)
3. Memory retrieval:
   - Detects self-question ("cosa sai di me?")
   - Retrieves user profile facts
   - Retrieves recent conversation history
4. LLM receives enriched prompt with:
   - Memory context: "📌 Informazioni utente: ..."
   - Multi-question hint
5. After response:
   - Saved to episodic buffer
   - Checked for "ricorda che..." patterns
   - Buffer auto-summarized if needed

## Security & Privacy

- ✅ No secrets stored in code
- ✅ User data isolated by user_id
- ✅ Memory respects token budgets (no token overflow)
- ✅ Graceful error handling (no crashes on missing memory)
- ✅ Logging at appropriate levels (DEBUG/INFO/WARNING)

## Future Enhancements

Suggested for STEP 2:
- Add memory relevance scoring
- Implement memory decay/forgetting
- Add memory conflict resolution
- Support multi-user conversations
- Add memory export/import
- Implement memory privacy controls
