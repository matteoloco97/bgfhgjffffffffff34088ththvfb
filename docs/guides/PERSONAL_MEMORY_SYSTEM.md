# Personal Memory System Documentation

## Overview

The Personal Memory System provides Jarvis with **real long-term memory** through two complementary layers:

1. **User Profile Memory** - Stable facts and preferences about the user
2. **Episodic Conversation Memory** - Summaries of past conversations per chat/session

## Architecture

### Components

```
core/
├── user_profile_memory.py   # User profile facts storage
├── episodic_memory.py        # Conversation summaries
└── memory_manager.py         # Central coordinator
```

### ChromaDB Collections

- `user_profile` - User facts (bio, goals, preferences, projects)
- `conversation_history` - Conversation summaries per chat_id/session_id

## User Profile Memory

### Features

- Automatic detection of "remember" statements (Italian + English)
- Auto-classification into categories: bio, goal, preference, project, misc
- Semantic search with user_id filtering
- Privacy filtering for sensitive data (API keys, passwords, etc.)

### "Remember" Statement Patterns

**Italian:**
- "ricorda che..."
- "da ora in poi ricordati che..."
- "memorizza che..."

**English:**
- "remember that..."
- "from now on, assume that..."
- "keep in mind that..."
- "please remember..."

### Example Usage

```bash
# Save a user fact via API
curl -X POST http://localhost:8081/memory/user_profile/save \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "matteo",
    "fact_text": "I prefer direct and concise answers",
    "category": "preference"
  }'

# Or let the user say it naturally in chat:
# "Ricorda che preferisco risposte dirette e concise"
```

### Query User Facts

```bash
# List all user facts
curl http://localhost:8081/memory/user_profile/list?user_id=matteo&limit=50

# Response:
{
  "ok": true,
  "user_id": "matteo",
  "count": 5,
  "facts": [
    {
      "id": "user:matteo:preference:1234567890",
      "text": "I prefer direct and concise answers",
      "metadata": {
        "user_id": "matteo",
        "category": "preference",
        "created_at": 1234567890,
        "updated_at": 1234567890
      }
    }
  ]
}
```

## Episodic Conversation Memory

### Features

- Rolling buffer per conversation (default: 10 turns)
- Automatic summarization when threshold reached
- Semantic retrieval of past conversation context
- LLM-based or rule-based summaries (fallback)
- Token-based thresholds (default: 2000 tokens)

### Conversation ID

- **Telegram:** `tg:{chat_id}`
- **GUI/API:** `gui:{session_id}` or `api:{session_id}`

### Example Usage

```bash
# Check buffer status
curl "http://localhost:8081/memory/episodic/buffer_status?conversation_id=tg:123456"

# Response:
{
  "ok": true,
  "conversation_id": "tg:123456",
  "status": {
    "exists": true,
    "size": 7,
    "max_size": 10,
    "estimated_tokens": 1200,
    "token_limit": 2000,
    "needs_summarization": false
  }
}
```

### List Conversation Summaries

```bash
# Get recent summaries for a conversation
curl "http://localhost:8081/memory/episodic/summaries?conversation_id=tg:123456&limit=20"

# Response:
{
  "ok": true,
  "conversation_id": "tg:123456",
  "count": 3,
  "summaries": [
    {
      "id": "conv:tg:123456:1234567890",
      "text": "Discussione su configurazione hardware Jarvis e GPU VRAM disponibile",
      "metadata": {
        "conversation_id": "tg:123456",
        "created_at": 1234567890,
        "turns_count": 10
      }
    }
  ]
}
```

## Chat Flow Integration

### Automatic Processing

When a user sends a message via `/chat`:

1. **Process "remember" statements** → Save to user profile
2. **Gather memory context** → Query user profile + episodic memory
3. **Inject into LLM prompt** → Add memory contexts to system prompt
4. **Generate response** → LLM uses memory-enhanced context
5. **Record turn** → Add to conversation buffer for future summarization

### Memory Context in Prompt

```
User Profile / Known Facts:
1. [preference] I prefer direct and concise answers
2. [goal] My main goal is to reduce debt
3. [bio] I live in Milan

Conversation Context (previous discussion):
• Discussione su AI e machine learning basics
• Setup di un progetto Python con ChromaDB
```

## Debug & Monitoring

### Check Memory State

```bash
# Get complete memory state
curl "http://localhost:8081/memory/debug_state?user_id=matteo&conversation_id=tg:123456"

# Response:
{
  "ok": true,
  "user_id": "matteo",
  "conversation_id": "tg:123456",
  "personal_memory": {
    "profile_memory": {
      "enabled": true,
      "facts_count": 12,
      "by_category": {
        "preference": 3,
        "goal": 2,
        "bio": 4,
        "project": 3
      }
    },
    "episodic_memory": {
      "enabled": true,
      "summaries_count": 5,
      "buffer_status": {
        "exists": true,
        "size": 7,
        "max_size": 10,
        "estimated_tokens": 1200,
        "token_limit": 2000,
        "needs_summarization": false
      }
    }
  },
  "legacy_chroma": {
    "persist_dir": "/memory/chroma",
    "embed_model": "sentence-transformers/all-MiniLM-L6-v2",
    "collections": [
      {"name": "user_profile", "count": 12},
      {"name": "conversation_history", "count": 23},
      {"name": "facts", "count": 145},
      {"name": "prefs", "count": 8},
      {"name": "betting_history", "count": 67}
    ]
  }
}
```

## Environment Variables

### User Profile Memory

```bash
# Enable/disable user profile memory
USER_PROFILE_ENABLED=1

# ChromaDB collection name
USER_PROFILE_COLLECTION=user_profile

# Maximum age for facts (days)
USER_PROFILE_MAX_AGE_DAYS=365

# Default user ID (for single-user setup)
DEFAULT_USER_ID=matteo

# Top-K facts to retrieve
MEMORY_PROFILE_TOP_K=5
```

### Episodic Memory

```bash
# Enable/disable episodic memory
EPISODIC_MEMORY_ENABLED=1

# ChromaDB collection name
EPISODIC_MEMORY_COLLECTION=conversation_history

# Buffer size (number of turns before summarization)
EPISODIC_BUFFER_SIZE=10

# Token threshold for summarization
EPISODIC_BUFFER_TOKEN_LIMIT=2000

# Enable/disable automatic summarization
EPISODIC_SUMMARIZE_ENABLED=1

# Maximum age for episodes (days)
EPISODIC_MAX_AGE_DAYS=90

# Top-K summaries to retrieve
MEMORY_EPISODIC_TOP_K=3
```

### Memory Context

```bash
# Maximum tokens for all memory context
MEMORY_MAX_CONTEXT_TOKENS=800
```

## Privacy & Security

### Automatic Filtering

The system automatically blocks saving:

- API keys and tokens (pattern: long alphanumeric strings)
- Passwords (pattern: `password=...`, `pwd=...`, etc.)
- Credit card numbers (pattern: 13-19 digit sequences)
- Stripe-like keys (pattern: `sk_...`, `pk_...`)

### Example

```python
# User says:
"Remember that my API key is sk_test_abc123xyz789"

# System response:
{
  "remember_detected": true,
  "fact_saved": false,
  "blocked_sensitive": true
}
```

## Cleanup Utilities

### Manual Cleanup

```python
from core.user_profile_memory import cleanup_old_user_facts
from core.episodic_memory import cleanup_old_episodes

# Clean up old user facts (older than 365 days)
deleted_count = cleanup_old_user_facts(user_id="matteo", days=365)

# Clean up old episodes (older than 90 days)
deleted_count = cleanup_old_episodes(conversation_id=None, days=90)
```

## Testing

### Run Tests

```bash
# User profile memory tests
python tests/test_user_profile_memory.py

# Episodic memory tests
python tests/test_episodic_memory.py

# Integration tests
python tests/test_memory_integration.py
```

### Test Coverage

- ✅ "Remember" statement detection (IT/EN)
- ✅ Category auto-classification
- ✅ User fact save/query/delete
- ✅ Conversation buffer management
- ✅ Summarization (LLM + fallback)
- ✅ Memory context gathering
- ✅ Privacy filtering
- ✅ Multi-user isolation
- ✅ Multi-conversation isolation

## Example Conversations

### Setting Preferences

```
User: Ricorda che preferisco risposte brevi e dirette
Jarvis: Ok, ho memorizzato che preferisci risposte brevi e dirette.

[Saved to user_profile: preference]
```

### Using Profile Memory

```
User: Come dovrei risponderti?
Jarvis: Secondo quello che ho in memoria, preferisci risposte brevi e dirette.

[Retrieved from user_profile]
```

### Episodic Recall

```
User: Di cosa abbiamo parlato ieri?
Jarvis: Ieri abbiamo discusso della configurazione hardware di Jarvis,
        in particolare della GPU e della VRAM disponibile.

[Retrieved from conversation_history for this chat_id]
```

## Migration from Legacy

The new system coexists with the legacy ChromaDB collections:

- **Legacy:** `facts`, `prefs`, `betting_history` (still active)
- **New:** `user_profile`, `conversation_history` (enhanced)

Both systems are queried during chat, ensuring backward compatibility.

## Future Enhancements

- [ ] Multi-user support with user authentication
- [ ] Fact editing and updates (not just append)
- [ ] Importance scoring for facts
- [ ] Automatic fact extraction from conversations
- [ ] Cross-conversation profile building
- [ ] Export/import user profiles
- [ ] Advanced privacy controls per user

## Support

For issues or questions, check the logs:

```bash
tail -f /root/quantumdev-open/logs/quantum_api.log | grep "\[memory\]"
```

Look for:
- `[memory] Saved user profile fact: ...`
- `[memory] Retrieved ... chars of profile context`
- `[memory] Created conversation summary for ...`
