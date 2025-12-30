#!/bin/bash
# Start the Web Renderer microservice
# 
# Usage:
#   ./start.sh           # Start on default port 8890
#   ./start.sh 8891      # Start on custom port
#
# Environment variables:
#   RENDERER_PORT          - Port to listen on (default: 8890)
#   RENDERER_HOST          - Host to bind to (default: 0.0.0.0)
#   RENDERER_TIMEOUT_MS    - Page load timeout (default: 15000)
#   RENDERER_MAX_CONCURRENT - Max concurrent renders (default: 2)
#   RENDERER_BLOCK_RESOURCES - Block images/fonts (default: 1)
#   RENDERER_ALLOWLIST     - Comma-separated allowed domains (empty = all)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Default port
PORT="${1:-${RENDERER_PORT:-8890}}"
HOST="${RENDERER_HOST:-0.0.0.0}"

# Check if playwright browsers are installed
if ! python3 -c "from playwright.sync_api import sync_playwright" 2>/dev/null; then
    echo "Installing playwright..."
    pip install playwright
fi

# Check if chromium is installed
if ! python3 -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch()
    browser.close()
" 2>/dev/null; then
    echo "Installing chromium browser..."
    playwright install chromium
fi

echo "Starting Web Renderer on ${HOST}:${PORT}..."
echo "Config:"
echo "  - Timeout: ${RENDERER_TIMEOUT_MS:-15000}ms"
echo "  - Max concurrent: ${RENDERER_MAX_CONCURRENT:-2}"
echo "  - Block resources: ${RENDERER_BLOCK_RESOURCES:-1}"

exec uvicorn app:app --host "$HOST" --port "$PORT" --log-level info
