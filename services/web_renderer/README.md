# Web Renderer Microservice

Playwright-based JavaScript rendering microservice for QuantumDev.

## Overview

This microservice renders JavaScript-heavy pages using Playwright/Chromium in headless mode. It's used as a fallback when static HTML extraction fails to get meaningful content from modern SPAs and JS-heavy websites.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Install Chromium browser
playwright install chromium

# Start the service
./start.sh
# or: uvicorn app:app --host 0.0.0.0 --port 8890
```

## API

### GET /render?url=...

Render a URL and return the HTML content.

**Parameters:**
- `url` (required): The URL to render

**Response:**
```json
{
  "ok": true,
  "url": "https://example.com",
  "final_url": "https://example.com/",
  "html": "<!DOCTYPE html>...",
  "status_code": 200,
  "timings_ms": {
    "load": 1234.5,
    "extra_wait": 500.0,
    "get_html": 50.2,
    "total": 1785.0
  }
}
```

**Error Response:**
```json
{
  "ok": false,
  "url": "https://example.com",
  "error": "page_load_timeout",
  "timings_ms": {"total": 15000.0}
}
```

### GET /health

Health check endpoint.

```json
{
  "status": "healthy",
  "browser_ready": true,
  "max_concurrent": 2
}
```

### GET /

Service info and configuration.

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `RENDERER_PORT` | 8890 | Port to listen on |
| `RENDERER_HOST` | 0.0.0.0 | Host to bind to |
| `RENDERER_TIMEOUT_MS` | 15000 | Page load timeout in milliseconds |
| `RENDERER_EXTRA_WAIT_MS` | 500 | Extra wait after networkidle (for slow SPAs) |
| `RENDERER_MAX_CONCURRENT` | 2 | Maximum concurrent render requests |
| `RENDERER_MAX_HTML_BYTES` | 2000000 | Maximum HTML size to return |
| `RENDERER_BLOCK_RESOURCES` | 1 | Block images/fonts/media (1=yes, 0=no) |
| `RENDERER_USER_AGENT` | Chrome/122 | Custom User-Agent |
| `RENDERER_ACCEPT_LANGUAGE` | it-IT,it... | Accept-Language header |
| `RENDERER_ALLOWLIST` | (empty) | Comma-separated allowed domains |

## Docker

```dockerfile
FROM python:3.11-slim

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

COPY . .

EXPOSE 8890
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8890"]
```

## Integration with QuantumDev

The main `core/web_tools.py` automatically uses this renderer as a fallback when:

1. Extracted text is too short (< `EXTRACT_MIN_CHARS`)
2. JS-heavy indicators are detected (React, Vue, Next.js, etc.)
3. Very low text-to-HTML ratio

Configure in your `.env`:

```env
RENDERER_URL=http://127.0.0.1:8890/render
RENDERER_ENABLED=1
RENDERER_TIMEOUT_S=15
RENDERER_MAX_CONCURRENT=2
```

## Security

- **Allowlist**: Use `RENDERER_ALLOWLIST` to restrict which domains can be rendered
- **Rate limiting**: Built-in semaphore limits concurrent renders
- **Resource blocking**: Images/fonts/media blocked by default for performance
- **Timeout**: Configurable timeout prevents hanging on slow pages

## Troubleshooting

### Browser fails to launch

Make sure Chromium is installed:
```bash
playwright install chromium
```

### High memory usage

Reduce `RENDERER_MAX_CONCURRENT` to 1.

### Slow rendering

Enable resource blocking (`RENDERER_BLOCK_RESOURCES=1`) and reduce timeout.
