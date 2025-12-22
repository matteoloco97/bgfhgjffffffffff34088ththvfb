# Telegram Streaming - Quick Start Guide

Get streaming responses in your Telegram bot in 3 minutes! ⚡

## 🚀 Quick Setup (3 Steps)

### Step 1: Install Dependencies (if needed)
```bash
pip install httpx>=0.25.0 python-telegram-bot>=20.0
```

### Step 2: Configure Environment
Add to your `.env` file:
```env
TELEGRAM_STREAMING_ENABLED=1
```

That's it! The default streaming endpoint is already configured.

### Step 3: Start the Bot
```bash
python scripts/telegram_bot.py
```

Look for this in logs:
```
✅ Streaming handler initialized
🌐 HTTP session ready
  Streaming: ENABLED (http://127.0.0.1:8081/chat/stream)
```

## 💬 User Commands

### Check Streaming Status
```
/streaming
```

### Enable Streaming (Progressive Updates)
```
/streaming on
```
Responses appear word-by-word in real-time!

### Disable Streaming (Complete Messages)
```
/streaming off
```
Get full response in one message (traditional mode).

## 🎯 What to Expect

**With Streaming ON:**
```
You: Tell me about quantum computing
Bot: 🤔 Thinking...
     → Quantum computing is...
     → Quantum computing is a revolutionary...
     → Quantum computing is a revolutionary approach to...
     → [continues updating until complete]
```

**With Streaming OFF:**
```
You: Tell me about quantum computing
Bot: [waits]
     Quantum computing is a revolutionary approach to... [full message]
```

## ⚙️ Advanced Configuration

### Custom Endpoint (Optional)
If your backend uses a different port:
```env
QUANTUM_CHAT_STREAM_URL=http://localhost:8080/chat/stream
```

### All Telegram Settings
```env
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_STREAMING_ENABLED=1
TELEGRAM_SOURCE_PREVIEW=0
TELEGRAM_SHOW_SOURCES=1
TELEGRAM_SHOW_CACHE_BADGE=1
```

## 🐛 Troubleshooting

### Streaming Not Working?

**Check 1: Is it enabled globally?**
```bash
grep TELEGRAM_STREAMING_ENABLED .env
# Should show: TELEGRAM_STREAMING_ENABLED=1
```

**Check 2: Is it enabled for your chat?**
Send: `/streaming` in Telegram
Should show: "✅ Streaming: ATTIVO"

**Check 3: Is backend running?**
```bash
curl -X POST http://localhost:8081/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"text": "test", "source": "test", "source_id": "test"}'
```
Should see SSE stream output.

**Check 4: Bot logs**
```bash
tail -f logs/telegram_bot.log | grep -i stream
```
Look for error messages.

### Still Having Issues?

1. Restart the bot
2. Check backend is running
3. Try `/streaming off` then `/streaming on`
4. See full guide: `TELEGRAM_STREAMING_GUIDE.md`

## 📊 Performance

**First Response Time:**
- Streaming: 1-2 seconds (feels instant!)
- Non-streaming: 5-10 seconds (waits for full response)

**Update Frequency:**
- Every 500ms or 50 tokens (whichever comes first)
- Smooth, responsive UX

**Rate Limits:**
- Telegram allows ~30 edits/second
- We use max 2 edits/second (very safe)

## 🎓 Learn More

**Full Documentation:**
- `TELEGRAM_STREAMING_GUIDE.md` - Complete user guide
- `ENV_STREAMING_EXAMPLE.env` - All configuration options
- `STREAMING_IMPLEMENTATION_COMPLETE.md` - Technical details

**Example Config:**
- See `ENV_STREAMING_EXAMPLE.env` for annotated examples

**Need Help?**
- Check logs: `tail -f logs/telegram_bot.log`
- Test backend: `curl http://localhost:8081/healthz`
- Review documentation files above

## ✨ Tips

**Best Use Cases for Streaming:**
- ✅ Long answers (stories, explanations)
- ✅ Research queries (web search)
- ✅ Complex questions
- ✅ Casual conversation

**When to Disable:**
- Quick facts ("What's 2+2?")
- Commands (/status, /health)
- URL summaries (already fast)

**Pro Tip:**
Toggle streaming per conversation based on your needs!

---

**That's it!** You're ready to use streaming. Enjoy real-time AI responses! 🎉
