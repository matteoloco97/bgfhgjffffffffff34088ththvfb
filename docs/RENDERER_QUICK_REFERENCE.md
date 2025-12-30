# JS Renderer Pipeline - Quick Reference

## TL;DR

The JS Renderer automatically activates when web scraping encounters JavaScript-heavy pages (React, Vue, Angular, etc.) that don't render properly with static HTML parsing.

## How It Works

```
User Query
    ↓
Web Research Agent
    ↓
fetch_and_extract_async(url)
    ↓
├─→ Fetch HTML
├─→ Extract text
└─→ Check if JS-heavy?
    ├─→ NO  → Return extracted text ✅
    └─→ YES → Call Renderer Service
                ↓
              Playwright/Chromium renders page
                ↓
              Re-extract from rendered HTML
                ↓
              Return improved text ✅
```

## Quick Start

### 1. Enable Renderer (in .env)
```bash
RENDERER_ENABLED=1
```

### 2. Start Renderer Service
```bash
# Option A: Systemd (recommended for production)
sudo systemctl start quantum-web-renderer

# Option B: Manual
cd services/web_renderer
./start.sh
```

### 3. Verify
```bash
curl http://127.0.0.1:8890/health
# Should return: {"status": "healthy", "browser_ready": true}
```

## Usage Examples

### Automatic (Recommended)
```python
from core.web_tools import fetch_and_extract_async

# Renderer activates automatically for JS-heavy pages
text, og_image = await fetch_and_extract_async("https://react.dev")
```

### Manual (with full logging)
```python
from core.web_tools import fetch_and_extract_with_renderer

extracted, fetch_log = await fetch_and_extract_with_renderer("https://vuejs.org")

print(f"Used renderer: {fetch_log.used_renderer}")
print(f"Renderer OK: {fetch_log.renderer_ok}")
print(f"Extracted: {fetch_log.extract_chars} chars")
```

## Configuration

### Key Environment Variables

| Variable | Default | What It Does |
|----------|---------|--------------|
| `RENDERER_ENABLED` | `1` | Turn renderer on/off |
| `RENDERER_URL` | `http://127.0.0.1:8890/render` | Renderer endpoint |
| `EXTRACT_MIN_CHARS` | `800` | Min chars before triggering renderer |
| `RENDERER_TIMEOUT_S` | `15` | How long to wait for render |

### When Does Renderer Activate?

The renderer triggers when:
1. Extracted text < 800 chars (configurable via `EXTRACT_MIN_CHARS`)
2. Page has React/Vue/Angular markers (`__NEXT_DATA__`, `react-root`, etc.)
3. High JavaScript density in HTML
4. Very low text-to-HTML ratio

## Monitoring

### Check Logs
```bash
# Renderer service
sudo journalctl -u quantum-web-renderer -f

# Main app (look for [FETCH_LOG])
grep FETCH_LOG /var/log/quantum-api.log
```

### Log Fields
```json
{
  "url": "https://react.dev",
  "fetch_ok": true,
  "status_code": 200,
  "extract_chars": 2341,
  "used_renderer": true,
  "renderer_ok": true,
  "timings_ms": {
    "fetch": 234,
    "extract": 12,
    "render": 3421,
    "reextract": 15,
    "total": 3682
  }
}
```

## Troubleshooting

### Problem: Renderer not being used

**Check**:
```bash
# 1. Is it enabled?
env | grep RENDERER_ENABLED

# 2. Is service running?
curl http://127.0.0.1:8890/health

# 3. Is threshold too high?
env | grep EXTRACT_MIN_CHARS
```

**Fix**: Lower threshold in `.env`:
```bash
EXTRACT_MIN_CHARS=500
```

### Problem: Renderer times out

**Fix**: Increase timeout:
```bash
RENDERER_TIMEOUT_S=30
```

### Problem: High memory usage

**Fix**: Reduce concurrency:
```bash
RENDERER_MAX_CONCURRENT=1
```

## Testing

```bash
# Unit tests
python tests/test_renderer_integration.py

# End-to-end test
python scripts/test_renderer_pipeline.py
```

## Performance

| Scenario | Static HTML | With Renderer |
|----------|-------------|---------------|
| Simple blog | 200ms | 200ms (not triggered) |
| React SPA | 150ms (poor) | 3-5s (good content) |
| Vue app | 180ms (poor) | 4-6s (good content) |

**Note**: Renderer adds 3-5s latency but extracts 10-50x more content from JS-heavy sites.

## Files Modified

- `core/web_tools.py` - Wired renderer into `fetch_and_extract_async`
- `deployment/etc/systemd/system/quantum-web-renderer.service` - Systemd service
- `scripts/test_renderer_pipeline.py` - End-to-end test
- `tests/test_renderer_integration.py` - Unit tests
- `docs/WEB_RENDERER_SETUP.md` - Full documentation

## Security Notes

- ✅ Renderer binds to `127.0.0.1` (localhost only)
- ✅ Rate limited via semaphore (`RENDERER_MAX_CONCURRENT`)
- ✅ Optional URL allowlist (`RENDERER_ALLOWLIST`)
- ⚠️ Don't expose renderer port externally
- ⚠️ Consider running as non-root user in production

## Learn More

- Full setup guide: `docs/WEB_RENDERER_SETUP.md`
- Implementation: `core/web_tools.py` (line 632+)
- Renderer service: `services/web_renderer/app.py`
- Test examples: `scripts/test_renderer_pipeline.py`

---

**Questions?** See troubleshooting in `docs/WEB_RENDERER_SETUP.md`
