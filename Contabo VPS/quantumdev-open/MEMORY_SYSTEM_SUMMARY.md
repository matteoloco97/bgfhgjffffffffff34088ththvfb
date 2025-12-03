# Personal Memory System - Implementation Summary

## Overview

This document provides a complete summary of the Personal Memory System implementation for Jarvis AI. The system provides two levels of memory: **User Profile Memory** (global per user) and **Episodic Conversation Memory** (per chat/session).

## System Architecture

### Components

1. **User Profile Memory** (`core/user_profile_memory.py`)
   - Stable facts and preferences about users
   - Auto-detection of "remember" statements
   - Category-based organization (bio, goal, preference, project, misc)
   - ChromaDB collection: `user_profile`

2. **Episodic Memory** (`core/episodic_memory.py`)
   - Conversation history summaries per chat/session
   - Rolling buffer with automatic summarization
   - ChromaDB collection: `conversation_history`

3. **Memory Manager** (`core/memory_manager.py`)
   - Central integration point
   - Coordinates profile + episodic memory
   - Sensitive data filtering
   - Single interface for chat flow

4. **Integration** (`backend/quantum_api.py`)
   - Integrated into `/chat` endpoint
   - Processes remember statements
   - Gathers and injects memory context into LLM prompts
   - Records conversation turns

## Features Implemented

### ✅ User Profile Memory

**Auto-Detection of "Remember" Statements:**
- Italian patterns: "ricorda che...", "da ora in poi ricordati...", "memorizza..."
- English patterns: "remember that...", "from now on, assume that...", "keep in mind..."

**Category Auto-Classification:**
- `bio`: Age, location, language, personal facts
- `goal`: Objectives, targets, things to achieve
- `preference`: Preferences, likes, tone/style choices
- `project`: Work, projects being built
- `misc`: Everything else

**Storage & Retrieval:**
- Each fact stored with: user_id, category, created_at, updated_at
- Semantic search with top-k retrieval
- Optional category filtering
- Metadata includes source and classification

### ✅ Episodic Conversation Memory

**Rolling Buffer System:**
- Configurable size (default: 10 messages)
- Token-based threshold for auto-summarization
- Per-conversation isolation using conversation_id

**Summarization:**
- LLM-based summarization (when available)
- Rule-based fallback (extracts key topics)
- Summaries stored in ChromaDB for retrieval

**Retrieval:**
- Semantic search of past conversation summaries
- Chronological access to recent summaries
- Conversation context injection into prompts

### ✅ Security & Privacy

**Sensitive Data Filtering:**
- API keys (sk_, pk_ prefixes)
- Passwords and tokens
- Credit card numbers
- JWT tokens
- Long alphanumeric secrets

**Pattern Matching:**
```python
SENSITIVE_PATTERNS = [
    r'\b[A-Za-z0-9]{25,}\b',              # Very long strings
    r'\b(?:password|pwd|passwd|token|secret|api[_-]?key)\s*[:=]\s*\S+',
    r'\b\d{13,19}\b',                      # Card numbers
    r'\bsk_[a-zA-Z0-9_]{10,}',            # Stripe keys
    r'\bpk_[a-zA-Z0-9_]{10,}',
    r'\beyJ[A-Za-z0-9_-]{10,}',           # JWT tokens
]
```

### ✅ Integration into Chat Flow

**Location:** `backend/quantum_api.py` - `/chat` endpoint

1. **Input Processing** (lines 2317-2323):
   ```python
   from core.memory_manager import process_user_message
   memory_process = await process_user_message(user_id, conversation_id, text)
   ```
   - Detects "remember" statements
   - Saves to user profile (if not sensitive)
   - Logs saved fact ID

2. **Memory Context Gathering** (lines 2446-2456):
   ```python
   from core.memory_manager import gather_memory_context
   memory_context_dict = await gather_memory_context(user_id, conversation_id, text)
   ```
   - Retrieves top-k profile facts (default: 5)
   - Retrieves top-k episodic summaries (default: 3)
   - Returns formatted context strings

3. **Prompt Assembly** (lines 2561-2569):
   ```python
   # Add NEW personal memory contexts
   if memory_context_dict.get("profile_context"):
       full_sys += "\n\n" + memory_context_dict["profile_context"]
   
   if memory_context_dict.get("episodic_context"):
       full_sys += "\n\n" + memory_context_dict["episodic_context"]
   ```
   - Injects profile context
   - Injects episodic context
   - Maintains token budget

4. **Conversation Recording** (lines 2576-2589):
   ```python
   from core.memory_manager import record_conversation_turn
   record_result = await record_conversation_turn(
       conversation_id=conversation_id,
       user_message=text,
       assistant_message=reply_text,
       user_id=user_id,
       llm_func=reply_with_llm
   )
   ```
   - Adds turn to buffer
   - Auto-summarizes when threshold reached
   - Clears buffer after summarization

## Configuration

### Environment Variables

```bash
# User Profile Memory
USER_PROFILE_COLLECTION=user_profile
USER_PROFILE_ENABLED=1
USER_PROFILE_MAX_AGE_DAYS=365
DEFAULT_USER_ID=matteo

# Episodic Memory
EPISODIC_MEMORY_COLLECTION=conversation_history
EPISODIC_MEMORY_ENABLED=1
EPISODIC_BUFFER_SIZE=10
EPISODIC_BUFFER_TOKEN_LIMIT=2000
EPISODIC_SUMMARIZE_ENABLED=1
EPISODIC_MAX_AGE_DAYS=90

# Memory Context
MEMORY_PROFILE_TOP_K=5
MEMORY_EPISODIC_TOP_K=3
MEMORY_MAX_CONTEXT_TOKENS=800

# ChromaDB
CHROMA_PERSIST_DIR=/memory/chroma
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
```

## Usage Examples

### 1. User Saves a Fact

**User:** "Ricorda che il mio colore preferito è blu"

**System:**
1. Detects "remember" statement
2. Extracts fact: "il mio colore preferito è blu"
3. Classifies as "preference"
4. Saves to user_profile collection
5. Returns normal response

### 2. User Asks Related Question

**User:** "Qual è il mio colore preferito?"

**System:**
1. Gathers profile context
2. Retrieves fact about blue color
3. Injects into LLM prompt:
   ```
   User Profile / Known Facts:
   1. [preference] il mio colore preferito è blu
   ```
4. LLM responds with accurate information

### 3. Long Conversation

**Conversation flow:**
- User asks about AI → Assistant responds
- User asks about Python → Assistant responds
- ... (10+ exchanges)
- Buffer threshold reached → System auto-summarizes
- Summary saved: "Conversazione su: AI | Python | machine learning"

**Later in same conversation:**
- User: "Cosa stavamo dicendo prima?"
- System retrieves episodic summary
- LLM has context of previous discussion

### 4. Sensitive Data Blocked

**User:** "Remember my API key is sk_test_abc123..."

**System:**
1. Detects "remember" statement
2. Checks for sensitive data → MATCH
3. Blocks saving
4. Logs warning
5. Returns normal response (doesn't save)

## Testing

### Test Suite

1. **Unit Tests:**
   - `tests/test_user_profile_memory.py` - 12 tests
   - `tests/test_episodic_memory.py` - 10 tests
   - `tests/test_memory_integration.py` - 10 tests

2. **Validation Script:**
   - `scripts/test_memory_system.py`
   - Runs without ChromaDB/network
   - Tests all core functions

### Running Tests

```bash
# Quick validation (no external dependencies)
python3 scripts/test_memory_system.py

# Unit tests (requires ChromaDB)
python3 -m unittest tests.test_user_profile_memory
python3 -m unittest tests.test_episodic_memory
python3 -m unittest tests.test_memory_integration
```

## API Endpoints

### Memory-Related Endpoints (Existing)

```
POST /memory/fact          - Add a fact manually
POST /memory/pref          - Add a preference manually
POST /memory/search        - Search memory
POST /memory/cleanup       - Cleanup old data
```

### Chat Endpoint (Main Integration)

```
POST /chat                 - Main chat with memory integration
```

**Example Request:**
```json
{
  "messages": [
    {"role": "user", "content": "Ricorda che preferisco risposte concise"}
  ],
  "source": "gui",
  "source_id": "session_123"
}
```

**Response includes memory-aware answer:**
```json
{
  "reply": "Ok, ho memorizzato che preferisci risposte concise. D'ora in poi sarò più diretto."
}
```

## Performance Considerations

### Token Budget Management

The system maintains token budget by:
1. Limiting profile context to ~400 tokens (50% of memory budget)
2. Limiting episodic context to ~400 tokens (50% of memory budget)
3. Total memory context capped at 800 tokens (configurable)
4. Trimming if needed to fit within LLM context window

### Memory Efficiency

- In-memory buffers per conversation (session-based)
- ChromaDB for persistent storage
- Automatic cleanup of old data
- Configurable retention periods

## Graceful Degradation

If ChromaDB is unavailable:
- System continues to work
- Memory features disabled
- Chat still functions normally
- Logs warnings but doesn't crash

## Future Enhancements (Not in Scope)

Potential future improvements:
- Multi-user support (already structured for it)
- Memory importance scoring
- Conflict resolution for contradictory facts
- Memory editing/deletion endpoints
- Analytics on memory usage

## Conclusion

The Personal Memory System is **fully implemented and integrated** into Jarvis. All requirements from Block 2 have been met:

✅ User profile memory with auto-capture
✅ Episodic conversation memory with summarization
✅ Safe extraction of "remember" statements (IT/EN)
✅ Sensitive data filtering
✅ Integration into main chat flow
✅ Comprehensive test coverage
✅ Quality code with proper error handling
✅ Backward compatibility maintained

The system is production-ready and can be enabled by setting the appropriate environment variables.
