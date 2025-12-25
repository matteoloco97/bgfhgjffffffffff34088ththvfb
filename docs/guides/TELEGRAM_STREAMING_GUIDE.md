# Telegram Bot Streaming Guide

Complete guide for enabling and using streaming responses in the QuantumDev Telegram bot.

## 🚀 What is Streaming?

Streaming enables progressive message updates in Telegram, showing responses appearing word-by-word in real-time instead of waiting for the complete response.

**Benefits:**
- ✅ Better user experience - see responses appearing instantly
- ✅ Feels faster - first tokens arrive in ~1-2 seconds
- ✅ More engaging - watch the AI "think" and write
- ✅ Works with all bot features - autoweb, commands, etc.

## 📋 Requirements

1. **Backend**: Running FastAPI server with `/chat/stream` endpoint
2. **Python packages**: `httpx>=0.25.0`, `python-telegram-bot>=20.0`
3. **Environment**: Set `TELEGRAM_STREAMING_ENABLED=1` in `.env`

## 🔧 Installation

### 1. Install Dependencies

Dependencies should already be in `requirements.txt`:
```bash
pip install httpx>=0.25.0 python-telegram-bot>=20.0
```

### 2. Configure Environment

Add to your `.env` file:
```env
# Enable streaming
TELEGRAM_STREAMING_ENABLED=1

# Streaming endpoint (default)
QUANTUM_CHAT_STREAM_URL=http://127.0.0.1:8081/chat/stream

# Your bot token
TELEGRAM_BOT_TOKEN=your_token_here
```

See `ENV_STREAMING_EXAMPLE.env` for complete configuration.

### 3. Start the Bot

```bash
python scripts/telegram_bot.py
```

Look for log messages:
```
✅ Streaming handler initialized
🌐 HTTP session ready
  Streaming: ENABLED (http://127.0.0.1:8081/chat/stream)
```

## 👤 User Commands

Users can control streaming per-chat with the `/streaming` command:

### Check Status
```
/streaming
```
Response:
```
✅ Streaming: ATTIVO

Usa:
• /streaming on - per attivare le risposte progressive
• /streaming off - per disattivare
```

### Enable Streaming
```
/streaming on
```
Response:
```
✅ Streaming ATTIVATO

Da ora vedrai le risposte apparire progressivamente,
parola per parola, mentre vengono generate.
```

### Disable Streaming
```
/streaming off
```
Response:
```
❌ Streaming DISATTIVATO

Da ora riceverai le risposte complete in un singolo messaggio.
```

## 🎯 How It Works

### Message Flow

1. **User sends message**: "Cos'è successo oggi in Italia?"
2. **Bot responds immediately**: "🤔 Thinking..."
3. **Typing indicator**: Shows bot is "typing"
4. **Progressive updates**: Message updates every 500ms or 50 tokens
   ```
   Le principali notizie di oggi...
   → Le principali notizie di oggi riguardano...
   → Le principali notizie di oggi riguardano la politica...
   → [continues updating]
   ```
5. **Final message**: Complete response with all tokens

### Smart Batching

The streaming handler uses intelligent batching to avoid rate limits:

- **Time-based**: Updates every 500ms minimum
- **Token-based**: Updates every 50 tokens
- **Whichever comes first**: Balances responsiveness and efficiency

This protects against Telegram's rate limits while maintaining smooth UX.

### Error Handling

If streaming fails for any reason:
1. Error is logged
2. System falls back to non-streaming `/chat` endpoint
3. User receives complete response (may be slightly delayed)
4. No loss of functionality

Common fallback scenarios:
- Backend `/chat/stream` endpoint unavailable
- Network timeout or connection error
- Invalid SSE format from backend
- HTTP error codes (500, 502, etc.)

## 🏗️ Architecture

### Components

1. **TelegramStreamingHandler** (`agents/telegram_streaming_handler.py`)
   - Manages SSE stream parsing
   - Handles progressive message updates
   - Implements smart batching
   - Provides error handling and fallback

2. **Bot Integration** (`scripts/telegram_bot.py`)
   - Detects if streaming is enabled
   - Routes messages to streaming or non-streaming handler
   - Manages per-user preferences
   - Implements `/streaming` command

3. **Backend Endpoint** (`/chat/stream`)
   - Server-Sent Events (SSE) format
   - Streams tokens progressively
   - Sends thinking/token/done/error messages

### Message Types

The backend sends SSE messages in this format:

```
data: {"type": "thinking", "content": "Processing..."}

data: {"type": "token", "text": "Hello", "index": 0}

data: {"type": "token", "text": " world", "index": 1}

data: {"type": "done", "total_tokens": 2}
```

## 🔒 Rate Limits

### Telegram API Limits

- **Message edits**: ~30 per second per chat
- **Our safety margin**: 2 edits per second (500ms minimum)
- **Token batching**: Reduces unnecessary edits

### Recommendations

- ✅ Use 500ms minimum interval (default)
- ✅ Batch 50 tokens (default)
- ⚠️ Don't go below 200ms interval
- ⚠️ Don't reduce batch size below 20 tokens

## 🧪 Testing

### Manual Testing

1. Enable streaming: `TELEGRAM_STREAMING_ENABLED=1`
2. Start bot: `python scripts/telegram_bot.py`
3. Send message in Telegram: "Tell me a short story"
4. Observe progressive updates
5. Toggle with `/streaming off` and compare

### Automated Tests

Run test suite:
```bash
python tests/test_telegram_streaming.py
```

Tests cover:
- SSE message parsing
- Batching logic
- Error handling
- User preferences
- Message truncation

### Performance Testing

Key metrics to monitor:
- **First token latency**: Should be <2 seconds
- **Update frequency**: Should match batching config (500ms)
- **Telegram errors**: Should be minimal (log warnings)
- **Memory usage**: Should be stable over time

## 🐛 Troubleshooting

### Streaming Not Working

**Symptom**: Messages appear complete, not progressive

**Checklist**:
1. ✅ Check `TELEGRAM_STREAMING_ENABLED=1` in `.env`
2. ✅ Verify backend `/chat/stream` endpoint is running
3. ✅ Check user preference with `/streaming`
4. ✅ Look for errors in bot logs
5. ✅ Test backend endpoint with curl:
   ```bash
   curl -X POST http://localhost:8081/chat/stream \
     -H "Content-Type: application/json" \
     -d '{"text": "Hello", "source": "test", "source_id": "test"}'
   ```

### "Message is not modified" Errors

**Symptom**: Warnings in logs about message not modified

**Explanation**: This is normal! Happens when:
- Batch contains no new tokens
- Text is identical to previous update
- Timing race conditions

**Solution**: Already handled gracefully, no action needed.

### Slow Updates

**Symptom**: Updates appear slower than expected

**Possible causes**:
1. Backend LLM is slow (check backend logs)
2. Network latency between bot and backend
3. Batching interval is too high

**Solutions**:
- Optimize backend LLM inference
- Reduce `MIN_EDIT_INTERVAL_MS` (not below 200ms)
- Check network connectivity

### High Memory Usage

**Symptom**: Bot memory grows over time

**Possible causes**:
1. httpx connections not being closed
2. Message objects accumulating

**Solutions**:
- Restart bot periodically
- Check for memory leaks in error paths
- Monitor with `htop` or similar

## 🎛️ Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_STREAMING_ENABLED` | `0` | Enable streaming (1) or disable (0) |
| `QUANTUM_CHAT_STREAM_URL` | `http://127.0.0.1:8081/chat/stream` | Backend streaming endpoint |
| `TELEGRAM_BOT_TOKEN` | - | Bot token from @BotFather |

### Handler Constants

Located in `agents/telegram_streaming_handler.py`:

```python
MIN_EDIT_INTERVAL_MS = 500    # Minimum time between edits
TOKEN_BATCH_SIZE = 50         # Tokens to accumulate before update
MAX_MESSAGE_LENGTH = 4096     # Telegram message limit
STREAM_TIMEOUT_S = 120        # Total timeout for stream
CONNECT_TIMEOUT_S = 10        # Connection timeout
```

Adjust these carefully - they balance UX and rate limits.

## 📚 API Reference

### TelegramStreamingHandler

```python
class TelegramStreamingHandler:
    def __init__(self, bot: Bot)
    
    async def stream_response(
        self,
        chat_id: int,
        url: str,
        payload: dict,
        initial_message: Optional[Message] = None,
        on_error: Optional[Callable[[str], Any]] = None
    ) -> tuple[str, bool]:
        """
        Stream response from backend to Telegram.
        
        Returns:
            (final_text, success)
        """
```

### Helper Functions

```python
def is_streaming_enabled_for_user(chat_id: int) -> bool:
    """Check if streaming is enabled for user."""

def set_user_streaming_preference(chat_id: int, enabled: bool):
    """Set user's streaming preference."""

async def call_chat_streaming(
    text: str,
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    initial_message = None
) -> tuple[str, bool]:
    """Call chat endpoint with streaming support."""
```

## 🔮 Future Enhancements

Potential improvements for future versions:

1. **Adaptive Batching**: Adjust batch size based on message length
2. **Quality Indicators**: Show confidence/quality during streaming
3. **Cancellation**: Allow users to stop long responses
4. **Multiple Streams**: Support parallel streaming for web search
5. **Voice Messages**: Stream-to-speech conversion
6. **Analytics**: Track streaming performance metrics

## 📝 Best Practices

### For Developers

- ✅ Always test with real Telegram bot before deploying
- ✅ Monitor logs for rate limit warnings
- ✅ Keep batching intervals conservative (500ms+)
- ✅ Test fallback scenarios regularly
- ✅ Document any configuration changes

### For Users

- ✅ Try both modes (streaming on/off) to see preference
- ✅ Use streaming for longer responses
- ✅ Disable for quick factual queries if preferred
- ✅ Report any issues to admin

## 📞 Support

For issues or questions:
1. Check logs: `tail -f logs/telegram_bot.log`
2. Review this guide
3. Test with manual curl commands
4. Contact repository maintainer

## 📄 License

Same as parent project (QuantumDev).

---

**Version**: 1.0  
**Last Updated**: 2025-12-17  
**Author**: QuantumDev Team
