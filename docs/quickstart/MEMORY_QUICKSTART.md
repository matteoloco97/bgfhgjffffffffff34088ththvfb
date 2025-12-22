# Personal Memory System - Quick Start Guide

## What is it?

Jarvis now has **real personal memory**! It remembers facts about you and your conversations across sessions.

## Two Types of Memory

### 1. **User Profile Memory** (Stable Facts)
Long-term facts and preferences about you that persist across all conversations.

**Examples:**
- Personal details (age, location, language)
- Goals and objectives
- Preferences and style choices
- Projects you're working on

### 2. **Episodic Memory** (Conversation Context)
Short-term memory of what was discussed in each conversation/chat.

**Examples:**
- What you talked about earlier in THIS chat
- Summaries of longer conversations
- Context to avoid repeating information

## How to Use It

### Saving Facts to Your Profile

Just tell Jarvis to remember something using natural language:

**Italian:**
```
Ricorda che il mio colore preferito è blu
Ricorda che abito a Milano
Da ora in poi ricordati che preferisco risposte concise
Memorizza che sto lavorando su un progetto AI
```

**English:**
```
Remember that I prefer concise answers
Remember that I'm 30 years old
From now on, assume that I like direct communication
Keep in mind that I work in the AI sector
```

**What happens:**
1. Jarvis detects the "remember" statement
2. Extracts the fact
3. Auto-classifies it (bio/goal/preference/project)
4. Saves it to your profile
5. Responds normally

### Using Saved Facts

Just ask normally - Jarvis will automatically retrieve relevant facts:

**You:** "Qual è il mio colore preferito?"
**Jarvis:** *(retrieves saved fact)* "Il tuo colore preferito è blu."

**You:** "Di cosa mi sto occupando?"
**Jarvis:** *(retrieves project facts)* "Stai lavorando su un progetto AI."

### Conversation Memory

This happens automatically - no special commands needed.

**Example:**
```
You: Parliamo di machine learning
Jarvis: Certo! Di cosa vuoi parlare?
You: Come funziona il gradient descent?
Jarvis: [explains]
... (more messages)
You: Cosa stavamo dicendo prima?
Jarvis: [retrieves episodic summary] Stavamo parlando di machine learning, 
        in particolare del gradient descent...
```

## Privacy & Security

### What Gets Blocked

Jarvis **will NOT save** sensitive information:
- ❌ API keys (sk_..., pk_...)
- ❌ Passwords
- ❌ Tokens
- ❌ Credit card numbers
- ❌ Long secret strings

**Example:**
```
You: Remember my password is SuperSecret123
Jarvis: [detects sensitive data] [BLOCKS saving] [responds normally]
```

### What's Safe to Save

- ✅ Personal preferences
- ✅ Goals and objectives
- ✅ Work/project information
- ✅ Favorite things
- ✅ Communication style preferences

## Configuration

If you're running Jarvis yourself, you can configure memory via environment variables:

```bash
# Enable/Disable
USER_PROFILE_ENABLED=1
EPISODIC_MEMORY_ENABLED=1

# How many facts to retrieve
MEMORY_PROFILE_TOP_K=5
MEMORY_EPISODIC_TOP_K=3

# Buffer size before auto-summarization
EPISODIC_BUFFER_SIZE=10
EPISODIC_BUFFER_TOKEN_LIMIT=2000

# Data retention
USER_PROFILE_MAX_AGE_DAYS=365
EPISODIC_MAX_AGE_DAYS=90
```

## Examples

### Example 1: Setting Up Your Profile

```
You: Ricorda che ho 30 anni
Jarvis: [saves to profile]

You: Ricorda che abito a Roma
Jarvis: [saves to profile]

You: Ricorda che preferisco il tono diretto
Jarvis: [saves to profile]

You: Ricorda che sto lavorando su Jarvis AI
Jarvis: [saves to profile]
```

Now Jarvis knows these facts permanently!

### Example 2: Using Profile Facts

```
You: Quanti anni ho?
Jarvis: Hai 30 anni.

You: Dove abito?
Jarvis: Abiti a Roma.

You: Come preferisco che mi rispondi?
Jarvis: Preferisci un tono diretto.
```

### Example 3: Long Conversation

```
You: Spiegami come funziona il machine learning
Jarvis: [explains ML basics]

You: E il deep learning?
Jarvis: [explains DL]

... (10+ exchanges about AI)

You: Cosa stavamo discutendo?
Jarvis: Stavamo discutendo di machine learning e deep learning, 
        in particolare di come funzionano e le loro differenze.
```

### Example 4: Multi-Chat Isolation

Conversation in Telegram:
```
You: Parliamo di calcio
Jarvis: [discusses soccer]
```

Later, in Web UI:
```
You: Ciao
Jarvis: Ciao! [doesn't mention soccer - different conversation]
```

But in Telegram again:
```
You: Cosa stavamo dicendo?
Jarvis: Stavamo parlando di calcio [remembers this conversation]
```

## Tips for Best Results

### DO:
- ✅ Use clear, simple statements
- ✅ One fact at a time works best
- ✅ Use "remember that..." or "ricorda che..." explicitly
- ✅ Save important preferences you want Jarvis to always know

### DON'T:
- ❌ Don't save secrets or passwords
- ❌ Don't expect Jarvis to remember everything forever (retention limits apply)
- ❌ Don't save very long texts (keep facts concise)

## Troubleshooting

### "Why didn't Jarvis remember what I told it?"

**Possible reasons:**
1. You didn't use a "remember" trigger phrase
2. The fact contained sensitive data (blocked for security)
3. ChromaDB is not available (check system status)
4. Memory is disabled in configuration

**Solution:**
Use explicit "remember" phrases: "Ricorda che..." or "Remember that..."

### "Jarvis is using old information"

**Possible reasons:**
1. Old facts still in database
2. Newer facts not ranked higher

**Solution:**
Tell Jarvis the updated information using "remember" again. You can also ask administrators to clean up old data.

### "How do I delete a saved fact?"

Currently, facts age out automatically based on retention settings. Manual deletion requires database access. Future versions may include a user-facing delete feature.

## Advanced: API Usage

If you're integrating with the API directly:

### Chat with Memory
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Ricorda che preferisco risposte concise"}
    ],
    "source": "api",
    "source_id": "my_session_123"
  }'
```

### Manual Fact Addition
```bash
curl -X POST http://localhost:8000/memory/fact \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "user.preference.tone",
    "value": "Preferisco risposte concise e dirette",
    "source": "user"
  }'
```

## Questions?

The memory system is designed to be invisible and natural. You don't need to think about it - just talk to Jarvis normally, and use "remember that..." when you want something saved permanently.

For technical details, see `MEMORY_SYSTEM_SUMMARY.md`.
