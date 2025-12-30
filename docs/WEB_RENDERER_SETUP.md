# Web Renderer Service - Setup Guide

## Overview

The Web Renderer is a Playwright-based microservice that renders JavaScript-heavy pages for content extraction. It automatically activates when the main web scraper detects insufficient content from static HTML.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Web Research Flow                                   │
├─────────────────────────────────────────────────────┤
│                                                       │
│  1. fetch_and_extract_async(url)                    │
│     └─> fetch_and_extract_with_renderer(url)        │
│         ├─> Fetch HTML (aiohttp)                    │
│         ├─> Extract text (trafilatura/bs4)          │
│         ├─> Check if JS-heavy                       │
│         │   ├─> Heuristics:                         │
│         │   │   - Text too short (< 800 chars)      │
│         │   │   - High script density               │
│         │   │   - Framework markers (React, Vue)    │
│         │   └─> If JS-heavy:                        │
│         │       └─> Call Renderer Service           │
│         │           └─> GET /render?url=...         │
│         │               └─> Playwright/Chromium     │
│         │                   └─> Rendered HTML       │
│         └─> Re-extract from rendered HTML           │
│                                                       │
└─────────────────────────────────────────────────────┘
```

## Installation

### 1. Install Dependencies

The renderer requires Playwright and Chromium:

```bash
cd /root/quantumdev-open/services/web_renderer
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure Environment

Add these variables to `/root/quantumdev-open/.env`:

```bash
# Enable renderer fallback
RENDERER_ENABLED=1

# Renderer service URL (should match systemd service port)
RENDERER_URL=http://127.0.0.1:8890/render

# Renderer timeout (seconds)
RENDERER_TIMEOUT_S=15

# Max concurrent renderer requests
RENDERER_MAX_CONCURRENT=2

# Minimum chars for extraction to be considered successful
EXTRACT_MIN_CHARS=800

# JS-heavy detection threshold (0.0-1.0)
EXTRACT_JS_HEAVY_THRESHOLD=0.30
```

### 3. Install systemd Service

```bash
# Copy service file
sudo cp deployment/etc/systemd/system/quantum-web-renderer.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable service (start on boot)
sudo systemctl enable quantum-web-renderer

# Start service now
sudo systemctl start quantum-web-renderer

# Check status
sudo systemctl status quantum-web-renderer
```

### 4. Verify Installation

```bash
# Check if service is running
curl http://127.0.0.1:8890/health

# Expected output:
# {
#   "status": "healthy",
#   "browser_ready": true,
#   "max_concurrent": 2
# }
```

## Testing

Run the test script to verify the pipeline:

```bash
cd /root/quantumdev-open
python scripts/test_renderer_pipeline.py
```

Expected output:
- ✅ Static URL test passes
- ✅ JS-heavy URL test passes (with renderer usage)
- ✅ Graceful degradation when renderer is offline
- ✅ Integration with fetch_and_extract_async

## Monitoring

### Check Logs

View renderer service logs:

```bash
# Real-time logs
sudo journalctl -u quantum-web-renderer -f

# Last 100 lines
sudo journalctl -u quantum-web-renderer -n 100

# Logs from today
sudo journalctl -u quantum-web-renderer --since today
```

### Look for Renderer Activity

In the main application logs, look for:

```
[FETCH_LOG] {"url": "...", "fetch_ok": true, "extract_chars": 1234, "used_renderer": true, "renderer_ok": true, ...}
```

Key fields:
- `fetch_ok`: Basic HTTP fetch succeeded
- `extract_chars`: Number of characters extracted
- `used_renderer`: Renderer was invoked
- `renderer_ok`: Renderer succeeded

### Performance Metrics

The logs include timing breakdowns:

```json
{
  "timings_ms": {
    "fetch": 245.3,
    "extract": 12.8,
    "render": 3421.5,
    "reextract": 15.2,
    "total": 3695.1
  }
}
```

## Troubleshooting

### Renderer Not Starting

**Symptom**: Service fails to start

**Solutions**:

1. Check if Chromium is installed:
   ```bash
   playwright install chromium
   ```

2. Verify Playwright is installed:
   ```bash
   pip install playwright
   ```

3. Check service logs:
   ```bash
   sudo journalctl -u quantum-web-renderer -n 50
   ```

### Renderer Times Out

**Symptom**: `render_ok=false`, error: "timeout"

**Solutions**:

1. Increase timeout in `.env`:
   ```bash
   RENDERER_TIMEOUT_S=30
   ```

2. Restart renderer service:
   ```bash
   sudo systemctl restart quantum-web-renderer
   ```

### High Memory Usage

**Symptom**: Renderer consuming too much RAM

**Solutions**:

1. Reduce concurrent renders:
   ```bash
   RENDERER_MAX_CONCURRENT=1
   ```

2. Add memory limits to systemd service (edit `/etc/systemd/system/quantum-web-renderer.service`):
   ```ini
   [Service]
   MemoryMax=1G
   MemoryHigh=800M
   ```

3. Restart service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart quantum-web-renderer
   ```

### Renderer Not Being Used

**Symptom**: `used_renderer=false` for JS-heavy sites

**Solutions**:

1. Lower the threshold in `.env`:
   ```bash
   EXTRACT_MIN_CHARS=500
   EXTRACT_JS_HEAVY_THRESHOLD=0.20
   ```

2. Check if renderer is enabled:
   ```bash
   # In .env, ensure:
   RENDERER_ENABLED=1
   ```

3. Verify renderer service is running:
   ```bash
   curl http://127.0.0.1:8890/health
   ```

### Graceful Degradation Not Working

**Symptom**: Application crashes when renderer is offline

**Check**:
- Renderer errors should be caught and logged
- Static extraction should continue
- No exceptions should propagate to caller

**Debug**:
```bash
# Test with renderer offline
sudo systemctl stop quantum-web-renderer
python scripts/test_renderer_pipeline.py
# Should see renderer_ok=false but no crashes
```

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RENDERER_ENABLED` | `1` | Enable (1) or disable (0) renderer |
| `RENDERER_URL` | `http://127.0.0.1:8890/render` | Renderer service endpoint |
| `RENDERER_TIMEOUT_S` | `15` | Request timeout in seconds |
| `RENDERER_MAX_CONCURRENT` | `2` | Max parallel renders |
| `EXTRACT_MIN_CHARS` | `800` | Min chars for good extraction |
| `EXTRACT_JS_HEAVY_THRESHOLD` | `0.30` | JS detection threshold |

### Renderer Service Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RENDERER_PORT` | `8890` | Port to listen on |
| `RENDERER_HOST` | `0.0.0.0` | Host to bind to |
| `RENDERER_TIMEOUT_MS` | `15000` | Page load timeout (ms) |
| `RENDERER_EXTRA_WAIT_MS` | `500` | Extra wait for SPAs (ms) |
| `RENDERER_BLOCK_RESOURCES` | `1` | Block images/fonts (1/0) |
| `RENDERER_MAX_HTML_BYTES` | `2000000` | Max HTML size (2MB) |
| `RENDERER_ALLOWLIST` | `""` | Allowed domains (empty=all) |

## Maintenance

### Restart Service

```bash
sudo systemctl restart quantum-web-renderer
```

### Stop Service

```bash
sudo systemctl stop quantum-web-renderer
```

### Disable Service (prevent auto-start)

```bash
sudo systemctl disable quantum-web-renderer
```

### Update Service Configuration

1. Edit service file:
   ```bash
   sudo nano /etc/systemd/system/quantum-web-renderer.service
   ```

2. Reload and restart:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart quantum-web-renderer
   ```

## Performance Tips

1. **Use allowlist for security**:
   ```bash
   RENDERER_ALLOWLIST=example.com,trusted-site.com
   ```

2. **Block heavy resources**:
   ```bash
   RENDERER_BLOCK_RESOURCES=1
   ```

3. **Tune concurrency**:
   - For low-memory systems: `RENDERER_MAX_CONCURRENT=1`
   - For high-performance: `RENDERER_MAX_CONCURRENT=4`

4. **Adjust timeouts**:
   - For slow sites: `RENDERER_TIMEOUT_S=30`
   - For fast sites: `RENDERER_TIMEOUT_S=10`

## Security Considerations

1. **Bind to localhost only** (already configured):
   - Service binds to `127.0.0.1`, not accessible externally

2. **Use allowlist in production**:
   - Prevents arbitrary URL rendering
   - Add trusted domains to `RENDERER_ALLOWLIST`

3. **Resource limits**:
   - Prevents DoS via excessive renders
   - Configure `RENDERER_MAX_CONCURRENT`

4. **Sandboxing**:
   - Chromium runs with `--no-sandbox` (required for root)
   - Consider running as dedicated user in production

## Integration Examples

### Web Research Agent

Automatically uses renderer when needed:

```python
from core.web_tools import fetch_and_extract_async

# Automatically uses renderer for JS-heavy pages
text, og_image = await fetch_and_extract_async(
    "https://react.dev",
    timeout=10.0
)
```

### Advanced Web Research

Multi-step research with renderer support:

```python
from agents.advanced_web_research import get_advanced_research

agent = get_advanced_research()
result = await agent.research_deep(
    "What are the latest features in React 19?"
)
# Renderer is used automatically for JS-heavy documentation sites
```

### Manual Renderer Call

Direct access to renderer with full logging:

```python
from core.web_tools import fetch_and_extract_with_renderer

extracted, fetch_log = await fetch_and_extract_with_renderer(
    "https://vuejs.org",
    timeout=15.0
)

print(f"Used renderer: {fetch_log.used_renderer}")
print(f"Renderer OK: {fetch_log.renderer_ok}")
print(f"Extracted: {fetch_log.extract_chars} chars")
print(f"Text: {extracted.text}")
```

## See Also

- Main README: `/root/quantumdev-open/README.md`
- Web Tools Documentation: `/root/quantumdev-open/core/web_tools.py`
- Renderer Service: `/root/quantumdev-open/services/web_renderer/README.md`
- Test Script: `/root/quantumdev-open/scripts/test_renderer_pipeline.py`
