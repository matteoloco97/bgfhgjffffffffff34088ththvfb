#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
services/web_renderer/app.py

Playwright-based web renderer microservice for QuantumDev.
Renders JavaScript-heavy pages and returns the resulting HTML.

Issue 3: JS Rendering Support
- Headless Chromium via Playwright
- Configurable timeouts and resource blocking
- Rate limiting via semaphore
- Structured JSON responses

Endpoint: GET /render?url=...

Response:
{
    "ok": bool,
    "url": str,
    "final_url": str,
    "html": str,
    "status_code": int,
    "timings_ms": {
        "load": float,
        "networkidle": float,
        "total": float
    },
    "error": str (if failed)
}

Run with: uvicorn app:app --host 0.0.0.0 --port 8890
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from typing import Optional, Set
from urllib.parse import urlparse

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# ===================== Configuration =====================

# Renderer timeout (for page load)
RENDERER_TIMEOUT_MS = int(os.getenv("RENDERER_TIMEOUT_MS", "15000"))

# Extra wait after networkidle (for slow SPAs)
RENDERER_EXTRA_WAIT_MS = int(os.getenv("RENDERER_EXTRA_WAIT_MS", "500"))

# Max concurrent renders
RENDERER_MAX_CONCURRENT = int(os.getenv("RENDERER_MAX_CONCURRENT", "2"))

# Max HTML size to return (2MB default)
RENDERER_MAX_HTML_BYTES = int(os.getenv("RENDERER_MAX_HTML_BYTES", str(2_000_000)))

# Block heavy resources (images, fonts, media)
RENDERER_BLOCK_RESOURCES = os.getenv("RENDERER_BLOCK_RESOURCES", "1").strip().lower() in ("1", "true", "yes")

# Resource types to block
BLOCKED_RESOURCE_TYPES = {"image", "font", "media", "stylesheet"}

# User-Agent (same as crawler for consistency)
RENDERER_USER_AGENT = os.getenv(
    "RENDERER_USER_AGENT",
    os.getenv(
        "SEARCH_UA",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122 Safari/537.36",
    ),
)

# Accept-Language
RENDERER_ACCEPT_LANGUAGE = os.getenv(
    "RENDERER_ACCEPT_LANGUAGE",
    os.getenv(
        "WEB_ACCEPT_LANGUAGE",
        "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    ),
)

# Optional URL allowlist (comma-separated domains, empty = allow all)
RENDERER_ALLOWLIST_RAW = os.getenv("RENDERER_ALLOWLIST", "")
RENDERER_ALLOWLIST: Set[str] = set(
    d.strip().lower() for d in RENDERER_ALLOWLIST_RAW.split(",") if d.strip()
)

# ===================== Playwright Setup =====================

_playwright = None
_browser = None
_browser_lock = asyncio.Lock()
_render_semaphore: Optional[asyncio.Semaphore] = None


def _get_semaphore() -> asyncio.Semaphore:
    """Get or create render semaphore."""
    global _render_semaphore
    if _render_semaphore is None:
        _render_semaphore = asyncio.Semaphore(RENDERER_MAX_CONCURRENT)
    return _render_semaphore


async def _get_browser():
    """Get or create browser instance."""
    global _playwright, _browser
    
    async with _browser_lock:
        if _browser is not None:
            return _browser
        
        try:
            from playwright.async_api import async_playwright
            
            _playwright = await async_playwright().start()
            _browser = await _playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--single-process",
                ]
            )
            logger.info(f"Playwright browser launched (max_concurrent={RENDERER_MAX_CONCURRENT})")
            return _browser
            
        except Exception as e:
            logger.error(f"Failed to launch browser: {e}")
            raise RuntimeError(f"Browser initialization failed: {e}")


async def _close_browser():
    """Close browser on shutdown."""
    global _playwright, _browser
    
    if _browser:
        try:
            await _browser.close()
        except Exception as e:
            logger.warning(f"Error closing browser: {e}")
        _browser = None
    
    if _playwright:
        try:
            await _playwright.stop()
        except Exception as e:
            logger.warning(f"Error stopping playwright: {e}")
        _playwright = None
    
    logger.info("Playwright browser closed")


# ===================== URL Validation =====================

def _extract_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower()
    except Exception:
        return ""


def _is_url_allowed(url: str) -> bool:
    """Check if URL is allowed based on allowlist."""
    if not RENDERER_ALLOWLIST:
        return True  # No allowlist = allow all
    
    domain = _extract_domain(url)
    if not domain:
        return False
    
    # Check exact match or subdomain match
    for allowed in RENDERER_ALLOWLIST:
        if domain == allowed or domain.endswith(f".{allowed}"):
            return True
    
    return False


def _is_valid_url(url: str) -> bool:
    """Validate URL format."""
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


# ===================== Response Models =====================

class RenderResponse(BaseModel):
    ok: bool
    url: str
    final_url: str = ""
    html: str = ""
    status_code: int = 0
    timings_ms: dict = {}
    error: Optional[str] = None


# ===================== FastAPI App =====================

app = FastAPI(
    title="QuantumDev Web Renderer",
    description="Playwright-based JS rendering microservice",
    version="1.0.0"
)


@app.on_event("startup")
async def startup():
    """Initialize browser on startup."""
    try:
        await _get_browser()
        logger.info("Web renderer ready")
    except Exception as e:
        logger.error(f"Failed to initialize browser on startup: {e}")
        # Don't fail startup - browser will be initialized on first request


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    await _close_browser()


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    browser_ok = _browser is not None
    return {
        "status": "healthy" if browser_ok else "degraded",
        "browser_ready": browser_ok,
        "max_concurrent": RENDERER_MAX_CONCURRENT,
    }


@app.get("/render", response_model=RenderResponse)
async def render_page(url: str = Query(..., description="URL to render")):
    """
    Render a JavaScript-heavy page and return the resulting HTML.
    
    Uses Playwright/Chromium to:
    1. Navigate to the URL
    2. Wait for network idle
    3. Optionally wait extra time for SPAs
    4. Return the rendered HTML
    
    Args:
        url: The URL to render
        
    Returns:
        RenderResponse with ok, html, status_code, timings, etc.
    """
    t0 = time.time()
    timings = {}
    
    # Validate URL
    if not _is_valid_url(url):
        return RenderResponse(
            ok=False,
            url=url,
            error="invalid_url_format",
            timings_ms={"total": (time.time() - t0) * 1000}
        )
    
    # Check allowlist
    if not _is_url_allowed(url):
        logger.warning(f"URL not in allowlist: {url}")
        return RenderResponse(
            ok=False,
            url=url,
            error="url_not_allowed",
            timings_ms={"total": (time.time() - t0) * 1000}
        )
    
    # Acquire semaphore for rate limiting
    semaphore = _get_semaphore()
    
    async with semaphore:
        try:
            browser = await _get_browser()
            context = await browser.new_context(
                user_agent=RENDERER_USER_AGENT,
                locale=RENDERER_ACCEPT_LANGUAGE.split(",")[0].split(";")[0],
                viewport={"width": 1280, "height": 720},
            )
            
            page = await context.new_page()
            
            # Block heavy resources if enabled
            if RENDERER_BLOCK_RESOURCES:
                async def block_resources(route):
                    if route.request.resource_type in BLOCKED_RESOURCE_TYPES:
                        await route.abort()
                    else:
                        await route.continue_()
                
                await page.route("**/*", block_resources)
            
            try:
                # Navigate to page
                t_load_start = time.time()
                response = await page.goto(
                    url,
                    wait_until="networkidle",
                    timeout=RENDERER_TIMEOUT_MS
                )
                t_load_end = time.time()
                timings["load"] = (t_load_end - t_load_start) * 1000
                
                # Extra wait for slow SPAs
                if RENDERER_EXTRA_WAIT_MS > 0:
                    t_wait_start = time.time()
                    await asyncio.sleep(RENDERER_EXTRA_WAIT_MS / 1000)
                    t_wait_end = time.time()
                    timings["extra_wait"] = (t_wait_end - t_wait_start) * 1000
                
                # Get final URL (after redirects)
                final_url = page.url
                
                # Get status code
                status_code = response.status if response else 0
                
                # Get rendered HTML
                t_html_start = time.time()
                html = await page.content()
                t_html_end = time.time()
                timings["get_html"] = (t_html_end - t_html_start) * 1000
                
                # Truncate if too large
                if len(html) > RENDERER_MAX_HTML_BYTES:
                    html = html[:RENDERER_MAX_HTML_BYTES]
                    logger.info(f"HTML truncated for {url}: {len(html)} bytes")
                
                timings["total"] = (time.time() - t0) * 1000
                
                logger.info(
                    f"Rendered {url} -> {len(html)} bytes in {timings['total']:.0f}ms "
                    f"(status={status_code})"
                )
                
                return RenderResponse(
                    ok=True,
                    url=url,
                    final_url=final_url,
                    html=html,
                    status_code=status_code,
                    timings_ms=timings
                )
                
            finally:
                await page.close()
                await context.close()
                
        except Exception as e:
            timings["total"] = (time.time() - t0) * 1000
            error_str = str(e)
            
            # Simplify common errors
            if "Timeout" in error_str:
                error_str = "page_load_timeout"
            elif "net::" in error_str:
                error_str = "network_error"
            
            logger.warning(f"Render failed for {url}: {error_str}")
            
            return RenderResponse(
                ok=False,
                url=url,
                error=error_str,
                timings_ms=timings
            )


@app.get("/")
async def root():
    """Root endpoint with info."""
    return {
        "service": "QuantumDev Web Renderer",
        "version": "1.0.0",
        "endpoints": {
            "/render": "GET - Render a URL with Playwright",
            "/health": "GET - Health check",
        },
        "config": {
            "timeout_ms": RENDERER_TIMEOUT_MS,
            "extra_wait_ms": RENDERER_EXTRA_WAIT_MS,
            "max_concurrent": RENDERER_MAX_CONCURRENT,
            "block_resources": RENDERER_BLOCK_RESOURCES,
            "max_html_bytes": RENDERER_MAX_HTML_BYTES,
            "allowlist_enabled": bool(RENDERER_ALLOWLIST),
        }
    }


# ===================== Main Entry =====================

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("RENDERER_PORT", "8890"))
    host = os.getenv("RENDERER_HOST", "0.0.0.0")
    
    logger.info(f"Starting Web Renderer on {host}:{port}")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
    )
