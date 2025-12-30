# core/web_tools.py
"""
Robust web page fetch + text extraction for QuantumDev.

Responsabilità:
- fare HTTP GET con header realistici (UA, Accept-Language)
- gestire redirect / HTTPS / timeout separati
- estrarre testo leggibile (articolo / contenuto principale)
- ripulire nav / menu / cookie banner il più possibile
- estrarre, se possibile, l'og:image per anteprime

Dipendenze opzionali consigliate:
    pip install trafilatura readability-lxml beautifulsoup4 aiohttp

Se le librerie non sono installate, usa fallback più semplici.

ASYNC PARALLELIZATION (Phase 1):
- Fully async fetch using aiohttp instead of requests
- Parallel URL fetching with asyncio.gather()
- Per-domain rate limiting
- Exponential backoff for 429/503 errors
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import asyncio
import time
from dataclasses import dataclass, field, asdict
from typing import Optional, Tuple, List, Dict, Any
from collections import defaultdict

import requests
from requests.exceptions import RequestException
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import urljoin, urlparse
from core.robust_content_extraction import extract_content_robust

# Async HTTP support
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    aiohttp = None
    AIOHTTP_AVAILABLE = False

logger = logging.getLogger(__name__)

# ===================== Config =====================

# User-Agent (can be overridden via SEARCH_UA or WEB_EXTRACT_UA)
DEFAULT_UA = os.getenv(
    "SEARCH_UA",
    os.getenv(
        "WEB_EXTRACT_UA",
        # UA abbastanza "normale"
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122 Safari/537.36",
    ),
)

# Accept-Language (can be overridden via WEB_ACCEPT_LANGUAGE or SEARCH_LANG)
DEFAULT_LANG = os.getenv(
    "WEB_ACCEPT_LANGUAGE",
    os.getenv(
        "SEARCH_LANG",
        os.getenv(
            "WEB_EXTRACT_LANG",
            "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
        ),
    ),
)

# Timeout totale di default (secondi)
DEFAULT_TIMEOUT_S = float(os.getenv("WEB_EXTRACT_TIMEOUT_S", "8.0"))

# Limite massimo di byte letti dal body (per evitare esplosioni)
MAX_HTML_BYTES = int(os.getenv("WEB_MAX_HTML_BYTES", os.getenv("WEB_EXTRACT_MAX_BYTES", str(2_000_000))))

# ===================== Issue 3: Renderer Config =====================

# Renderer service URL
RENDERER_URL = os.getenv("RENDERER_URL", "http://127.0.0.1:8890/render")

# Enable/disable renderer fallback (1=enabled, 0=disabled)
RENDERER_ENABLED = os.getenv("RENDERER_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")

# Renderer timeout in seconds
RENDERER_TIMEOUT_S = float(os.getenv("RENDERER_TIMEOUT_S", "15"))

# Max concurrent renderer requests
RENDERER_MAX_CONCURRENT = int(os.getenv("RENDERER_MAX_CONCURRENT", "2"))

# ===================== Issue 3: Extraction Config =====================

# Minimum characters for extraction to be considered successful
EXTRACT_MIN_CHARS = int(os.getenv("EXTRACT_MIN_CHARS", "800"))

# JS-heavy detection threshold (ratio of script-like content)
EXTRACT_JS_HEAVY_THRESHOLD = float(os.getenv("EXTRACT_JS_HEAVY_THRESHOLD", "0.30"))

# JS density multiplier for threshold calculation (script matches per KB)
JS_DENSITY_MULTIPLIER = 10

# Minimum text-to-HTML ratio for content to be considered valid
MIN_TEXT_RATIO = 0.01

# Minimum HTML size to apply text ratio check
MIN_HTML_SIZE_FOR_RATIO_CHECK = 5000

# Default connect timeout in seconds
DEFAULT_CONNECT_TIMEOUT_S = float(os.getenv("HTTP_CONNECT_TIMEOUT_S", "3.0"))

# ===================== Async Config (Phase 1) =====================

# Max concurrent HTTP requests
HTTP_MAX_CONCURRENT = int(os.getenv("HTTP_MAX_CONCURRENT", "6"))

# Rate limiting: max requests per second per domain
HTTP_RATE_LIMIT_PER_DOMAIN = float(os.getenv("HTTP_RATE_LIMIT_PER_DOMAIN", "2.0"))

# Exponential backoff config
MAX_RETRIES_ASYNC = int(os.getenv("HTTP_MAX_RETRIES", "3"))
BACKOFF_BASE = float(os.getenv("HTTP_BACKOFF_BASE", "0.5"))
BACKOFF_MAX = float(os.getenv("HTTP_BACKOFF_MAX", "10.0"))

# ===================== HTTP Session (module-level singleton) =====================

def _create_http_session() -> requests.Session:
    """Crea una sessione HTTP ottimizzata con connection pooling."""
    session = requests.Session()
    session.trust_env = False
    retry = Retry(total=1, backoff_factor=0.2, status_forcelist=[502, 503, 504])
    adapter = HTTPAdapter(pool_connections=5, pool_maxsize=10, max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

_HTTP_SESSION: Optional[requests.Session] = None

def _get_http_session() -> requests.Session:
    """Ritorna la sessione HTTP singleton."""
    global _HTTP_SESSION
    if _HTTP_SESSION is None:
        _HTTP_SESSION = _create_http_session()
    return _HTTP_SESSION


# ===================== Async HTTP Session (Phase 1) =====================

_AIOHTTP_SESSION: Optional['aiohttp.ClientSession'] = None
_AIOHTTP_SESSION_LOCK: Optional[asyncio.Lock] = None


class DomainRateLimiter:
    """Per-domain rate limiter to respect server limits."""
    
    def __init__(self, rate_per_second: float = HTTP_RATE_LIMIT_PER_DOMAIN):
        self.rate_per_second = rate_per_second
        self.min_interval = 1.0 / rate_per_second if rate_per_second > 0 else 0
        self.last_request: Dict[str, float] = defaultdict(float)
        self.lock = asyncio.Lock()
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc or ""
        except Exception:
            return ""
    
    async def acquire(self, url: str) -> None:
        """Wait if necessary to respect rate limit for this domain."""
        domain = self._extract_domain(url)
        if not domain:
            return
        
        async with self.lock:
            now = time.time()
            last = self.last_request.get(domain, 0)
            elapsed = now - last
            
            if elapsed < self.min_interval:
                wait_time = self.min_interval - elapsed
                logger.debug(f"Rate limiting {domain}: waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
            
            self.last_request[domain] = time.time()


_DOMAIN_RATE_LIMITER: Optional[DomainRateLimiter] = None


async def get_aiohttp_session() -> Optional['aiohttp.ClientSession']:
    """Get or create global aiohttp session with connection pooling."""
    global _AIOHTTP_SESSION, _AIOHTTP_SESSION_LOCK
    
    if not AIOHTTP_AVAILABLE:
        logger.warning("aiohttp not available, cannot create async HTTP session")
        return None
    
    # Initialize lock on first call
    if _AIOHTTP_SESSION_LOCK is None:
        _AIOHTTP_SESSION_LOCK = asyncio.Lock()
    
    async with _AIOHTTP_SESSION_LOCK:
        if _AIOHTTP_SESSION is None or _AIOHTTP_SESSION.closed:
            try:
                connector = aiohttp.TCPConnector(
                    limit=HTTP_MAX_CONCURRENT * 2,  # Total pool size
                    limit_per_host=HTTP_MAX_CONCURRENT,
                    ttl_dns_cache=300,
                    enable_cleanup_closed=True,
                    force_close=False,
                    keepalive_timeout=30
                )
                
                timeout = aiohttp.ClientTimeout(
                    total=DEFAULT_TIMEOUT_S,
                    connect=DEFAULT_CONNECT_TIMEOUT_S,
                    sock_read=DEFAULT_TIMEOUT_S - DEFAULT_CONNECT_TIMEOUT_S
                )
                
                _AIOHTTP_SESSION = aiohttp.ClientSession(
                    connector=connector,
                    timeout=timeout,
                    headers={
                        'User-Agent': DEFAULT_UA,
                        'Accept-Language': DEFAULT_LANG,
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    }
                )
                
                logger.info(
                    f"Aiohttp session initialized: max_concurrent={HTTP_MAX_CONCURRENT}, "
                    f"timeout={DEFAULT_TIMEOUT_S}s"
                )
            except Exception as e:
                logger.error(f"Failed to create aiohttp session: {e}")
                return None
    
    return _AIOHTTP_SESSION


async def close_aiohttp_session():
    """Cleanup aiohttp session on shutdown."""
    global _AIOHTTP_SESSION
    if _AIOHTTP_SESSION and not _AIOHTTP_SESSION.closed:
        await _AIOHTTP_SESSION.close()
        _AIOHTTP_SESSION = None
        logger.info("Aiohttp session closed")


def get_domain_rate_limiter() -> DomainRateLimiter:
    """Get or create domain rate limiter singleton."""
    global _DOMAIN_RATE_LIMITER
    if _DOMAIN_RATE_LIMITER is None:
        _DOMAIN_RATE_LIMITER = DomainRateLimiter()
    return _DOMAIN_RATE_LIMITER


# ===================== Helper dataclass =====================

@dataclass
class ExtractResult:
    text: str
    og_image: Optional[str] = None


# ===================== Issue 3: Enhanced Extraction Result =====================

@dataclass
class ExtractedContent:
    """Enhanced extraction result with metadata."""
    text: str
    title: str = ""
    meta_description: str = ""
    content_length: int = 0
    og_image: Optional[str] = None
    
    def __post_init__(self):
        self.content_length = len(self.text)


@dataclass
class FetchLog:
    """Structured log entry for URL fetch operations (Issue 3)."""
    url: str
    fetch_ok: bool = False
    status_code: int = 0
    final_url: str = ""
    bytes_fetched: int = 0
    extract_chars: int = 0
    used_renderer: bool = False
    renderer_ok: bool = False
    timings_ms: Dict[str, float] = field(default_factory=dict)
    error: Optional[str] = None
    
    def to_json(self) -> str:
        """Return structured JSON log line."""
        return json.dumps(asdict(self), ensure_ascii=False)
    
    def log(self) -> None:
        """Log the fetch result as structured JSON."""
        logger.info(f"[FETCH_LOG] {self.to_json()}")


# ===================== Issue 3: JS-Heavy Detection =====================

# Keywords that indicate JS-heavy pages
JS_HEAVY_KEYWORDS = [
    "enable javascript",
    "javascript is required",
    "please enable javascript",
    "app-root",
    "__NEXT_DATA__",
    "__NUXT__",
    "hydrate",
    "chunk",
    "webpack",
    "react-root",
    "ng-app",
    "vue-app",
    "data-reactroot",
    "data-v-",
    "noscript",
]


def _is_js_heavy(html: str, extracted_text: str) -> bool:
    """
    Detect if a page is JS-heavy and requires rendering.
    
    Heuristics:
    1. Extracted text is too short (< EXTRACT_MIN_CHARS)
    2. High ratio of script-like content (braces, function, var, etc.)
    3. Contains JS framework markers
    4. High link-to-text ratio (navigation-heavy with no content)
    
    Returns True if page likely needs JS rendering.
    """
    html_lower = html.lower()
    
    # Check 1: Extraction too short
    if len(extracted_text) < EXTRACT_MIN_CHARS:
        logger.debug(f"JS-heavy check: extracted_chars={len(extracted_text)} < {EXTRACT_MIN_CHARS}")
        return True
    
    # Check 2: JS framework keywords
    for keyword in JS_HEAVY_KEYWORDS:
        if keyword.lower() in html_lower:
            logger.debug(f"JS-heavy check: found keyword '{keyword}'")
            return True
    
    # Check 3: High script-like content ratio
    script_patterns = [
        r'\bfunction\s*\(',
        r'\bvar\s+\w+',
        r'\bconst\s+\w+',
        r'\blet\s+\w+',
        r'=>',
        r'\{\s*\}',
        r'module\.exports',
        r'import\s+\{',
        r'export\s+default',
    ]
    script_matches = 0
    for pattern in script_patterns:
        script_matches += len(re.findall(pattern, html))
    
    # Rough estimate of script density (matches per 1KB)
    html_len = max(len(html), 1)
    script_density = script_matches / (html_len / 1000)
    
    if script_density > EXTRACT_JS_HEAVY_THRESHOLD * JS_DENSITY_MULTIPLIER:
        logger.debug(f"JS-heavy check: script_density={script_density:.2f} > threshold")
        return True
    
    # Check 4: Very low text-to-html ratio
    text_ratio = len(extracted_text) / max(len(html), 1)
    if text_ratio < MIN_TEXT_RATIO and len(html) > MIN_HTML_SIZE_FOR_RATIO_CHECK:
        logger.debug(f"JS-heavy check: text_ratio={text_ratio:.4f} < {MIN_TEXT_RATIO}")
        return True
    
    return False


# ===================== Issue 3: Renderer Service Client =====================

_RENDERER_SEMAPHORE: Optional[asyncio.Semaphore] = None


def _get_renderer_semaphore() -> asyncio.Semaphore:
    """Get or create renderer concurrency semaphore."""
    global _RENDERER_SEMAPHORE
    if _RENDERER_SEMAPHORE is None:
        _RENDERER_SEMAPHORE = asyncio.Semaphore(RENDERER_MAX_CONCURRENT)
    return _RENDERER_SEMAPHORE


async def _call_renderer(url: str, timeout: float = RENDERER_TIMEOUT_S) -> Optional[Dict[str, Any]]:
    """
    Call the Playwright renderer microservice for JS rendering.
    
    Args:
        url: URL to render
        timeout: Timeout in seconds
        
    Returns:
        Dict with: ok, url, final_url, html, status_code, timings_ms, error
        or None if renderer is disabled or fails
    """
    if not RENDERER_ENABLED:
        logger.debug("Renderer is disabled (RENDERER_ENABLED=0)")
        return None
    
    semaphore = _get_renderer_semaphore()
    
    async with semaphore:
        try:
            session = await get_aiohttp_session()
            if not session:
                logger.warning("No aiohttp session available for renderer call")
                return None
            
            params = {"url": url}
            
            t0 = time.time()
            async with session.get(
                RENDERER_URL,
                params=params,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                elapsed_ms = (time.time() - t0) * 1000
                
                if resp.status != 200:
                    logger.warning(f"Renderer returned status {resp.status} for {url}")
                    return {
                        "ok": False,
                        "url": url,
                        "final_url": url,
                        "html": "",
                        "status_code": resp.status,
                        "timings_ms": {"total": elapsed_ms},
                        "error": f"HTTP {resp.status}",
                    }
                
                data = await resp.json()
                data["timings_ms"]["call"] = elapsed_ms
                return data
                
        except asyncio.TimeoutError:
            logger.warning(f"Renderer timeout for {url} after {timeout}s")
            return {
                "ok": False,
                "url": url,
                "error": "timeout",
            }
        except Exception as e:
            logger.warning(f"Renderer call failed for {url}: {e}")
            return {
                "ok": False,
                "url": url,
                "error": str(e),
            }


# ===================== Issue 3: Enhanced Extract with Title/Meta =====================

def _extract_title(html: str) -> str:
    """Extract page title from HTML."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        title_tag = soup.find('title')
        if title_tag:
            return title_tag.get_text(strip=True)
    except Exception:
        pass
    
    # Regex fallback
    match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    if match:
        return re.sub(r'\s+', ' ', match.group(1)).strip()
    return ""


def _extract_meta_description(html: str) -> str:
    """Extract meta description from HTML."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        meta = soup.find('meta', attrs={'name': 'description'})
        if meta and meta.get('content'):
            return meta['content'].strip()
    except Exception:
        pass
    
    # Regex fallback
    match = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)',
        html,
        re.IGNORECASE
    )
    if match:
        return match.group(1).strip()
    return ""


def extract_text(html: str, url: str = "") -> ExtractedContent:
    """
    Extract text from HTML with boilerplate removal (Issue 3 A2).
    
    Args:
        html: Raw HTML content
        url: Original URL (for context in extraction)
        
    Returns:
        ExtractedContent with text, title, meta_description, content_length
    """
    # Extract metadata first
    title = _extract_title(html)
    meta_description = _extract_meta_description(html)
    og_image = _extract_og_image(html, url) if url else None
    
    # Extract main content using robust extraction
    text = extract_content_robust(html, url)
    
    # Normalize whitespace
    text = _normalize_whitespace(text).strip()
    
    return ExtractedContent(
        text=text,
        title=title,
        meta_description=meta_description,
        content_length=len(text),
        og_image=og_image,
    )


# ===================== Issue 3: Fetch URL with Renderer Fallback =====================

async def fetch_url(
    url: str,
    timeout: float = DEFAULT_TIMEOUT_S,
    max_retries: int = MAX_RETRIES_ASYNC,
) -> Tuple[Optional[bytes], str, int, Dict[str, Any]]:
    """
    Fetch URL with crawler-grade robustness (Issue 3 A1).
    
    Features:
    - Retry with exponential backoff + jitter
    - Follow redirects (max 3)
    - Support gzip/br/deflate
    - Realistic headers (UA, Accept-Language, Accept-Encoding)
    - DNS cache / connection pooling via aiohttp
    
    Args:
        url: URL to fetch
        timeout: Total timeout in seconds
        max_retries: Maximum retry attempts
        
    Returns:
        Tuple of (content_bytes, final_url, status_code, headers_dict)
        Returns (None, url, 0, {}) on failure
    """
    session = await get_aiohttp_session()
    if not session:
        # Fallback to sync
        resp = _http_get(url, timeout)
        if resp:
            return (resp.content, resp.url, resp.status_code, dict(resp.headers))
        return (None, url, 0, {})
    
    rate_limiter = get_domain_rate_limiter()
    
    for attempt in range(max_retries):
        try:
            # Apply per-domain rate limiting
            await rate_limiter.acquire(url)
            
            # Add jitter to backoff
            if attempt > 0:
                jitter = random.uniform(0, 0.5)
                backoff = min(BACKOFF_BASE * (2 ** attempt) + jitter, BACKOFF_MAX)
                await asyncio.sleep(backoff)
            
            async with session.get(
                url,
                allow_redirects=True,
                max_redirects=3,
                timeout=aiohttp.ClientTimeout(total=timeout, connect=DEFAULT_CONNECT_TIMEOUT_S),
            ) as resp:
                # Check for rate limiting or server errors
                if resp.status in (429, 503):
                    if attempt < max_retries - 1:
                        backoff = min(BACKOFF_BASE * (2 ** attempt), BACKOFF_MAX)
                        logger.warning(
                            f"HTTP {resp.status} for {url}, backing off {backoff:.2f}s "
                            f"(attempt {attempt + 1}/{max_retries})"
                        )
                        continue
                    return (None, str(resp.url), resp.status, dict(resp.headers))
                
                # Check content-type
                ctype = resp.headers.get("Content-Type", "")
                if "text/html" not in ctype and "application/xhtml" not in ctype:
                    logger.info(f"Non-HTML content-type for {url}: {ctype}")
                    return (None, str(resp.url), resp.status, dict(resp.headers))
                
                # Read content (limit size)
                content = await resp.read()
                if len(content) > MAX_HTML_BYTES:
                    content = content[:MAX_HTML_BYTES]
                
                return (content, str(resp.url), resp.status, dict(resp.headers))
        
        except asyncio.TimeoutError:
            logger.warning(f"Timeout for {url} (attempt {attempt + 1}/{max_retries})")
        except Exception as e:
            logger.warning(f"Error fetching {url}: {e} (attempt {attempt + 1}/{max_retries})")
    
    return (None, url, 0, {})


async def fetch_and_extract_with_renderer(
    url: str,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> Tuple[ExtractedContent, FetchLog]:
    """
    Fetch and extract with automatic JS renderer fallback (Issue 3 A4).
    
    Pipeline:
    1. Fetch HTML (crawler-grade)
    2. Extract text
    3. If JS-heavy heuristics trigger → call renderer
    4. Re-extract from rendered HTML
    5. Return result with structured log
    
    Args:
        url: URL to fetch
        timeout: Timeout for initial fetch
        
    Returns:
        Tuple of (ExtractedContent, FetchLog)
    """
    fetch_log = FetchLog(url=url)
    t0 = time.time()
    
    # Step 1: Fetch HTML
    t_fetch_start = time.time()
    content_bytes, final_url, status_code, headers = await fetch_url(url, timeout)
    t_fetch_end = time.time()
    fetch_log.timings_ms["fetch"] = (t_fetch_end - t_fetch_start) * 1000
    
    fetch_log.final_url = final_url
    fetch_log.status_code = status_code
    
    if content_bytes is None:
        fetch_log.fetch_ok = False
        fetch_log.error = "fetch_failed"
        fetch_log.timings_ms["total"] = (time.time() - t0) * 1000
        fetch_log.log()
        return ExtractedContent(text="", title="", meta_description=""), fetch_log
    
    fetch_log.fetch_ok = True
    fetch_log.bytes_fetched = len(content_bytes)
    
    # Decode HTML
    encoding = None
    content_type = headers.get("Content-Type", "")
    if "charset=" in content_type:
        try:
            encoding = content_type.split("charset=")[-1].split(";")[0].strip()
        except Exception:
            pass
    
    try:
        html = content_bytes.decode(encoding or "utf-8", errors="replace")
    except Exception:
        html = content_bytes.decode("utf-8", errors="replace")
    
    # Step 2: Extract text
    t_extract_start = time.time()
    extracted = extract_text(html, final_url)
    t_extract_end = time.time()
    fetch_log.timings_ms["extract"] = (t_extract_end - t_extract_start) * 1000
    fetch_log.extract_chars = extracted.content_length
    
    # Step 3: Check if JS-heavy
    if _is_js_heavy(html, extracted.text):
        logger.info(f"JS-heavy detected for {url}, attempting renderer fallback")
        fetch_log.used_renderer = True
        
        # Step 4: Call renderer
        t_render_start = time.time()
        render_result = await _call_renderer(url, timeout=RENDERER_TIMEOUT_S)
        t_render_end = time.time()
        fetch_log.timings_ms["render"] = (t_render_end - t_render_start) * 1000
        
        if render_result and render_result.get("ok"):
            fetch_log.renderer_ok = True
            rendered_html = render_result.get("html", "")
            
            # Re-extract from rendered HTML
            t_reextract_start = time.time()
            extracted = extract_text(rendered_html, render_result.get("final_url", url))
            t_reextract_end = time.time()
            fetch_log.timings_ms["reextract"] = (t_reextract_end - t_reextract_start) * 1000
            fetch_log.extract_chars = extracted.content_length
            
            logger.info(f"Renderer success for {url}: {extracted.content_length} chars extracted")
        else:
            fetch_log.renderer_ok = False
            error_msg = render_result.get("error", "renderer_failed") if render_result else "renderer_unavailable"
            logger.warning(f"Renderer failed for {url}: {error_msg}")
            # Keep original extraction (may be partial)
    
    fetch_log.timings_ms["total"] = (time.time() - t0) * 1000
    fetch_log.log()
    
    return extracted, fetch_log


# ===================== HTTP layer =====================

def _build_headers() -> dict:
    return {
        "User-Agent": DEFAULT_UA,
        "Accept-Language": DEFAULT_LANG,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "close",
    }


def _http_get(url: str, timeout: float) -> Optional[requests.Response]:
    """
    HTTP GET con gestione redirect e timeout separati.
    OPTIMIZED: Connection pooling e migliore gestione errori.

    timeout: timeout "totale" desiderato. Lo splittiamo in connect/read.
    """
    headers = _build_headers()
    # provo a spezzare il timeout in connect + read
    connect_timeout = min(3.0, timeout * 0.35)  # OPTIMIZED: più tempo per lettura
    read_timeout = max(2.5, timeout * 0.65)

    try:
        # OPTIMIZATION: Usa sessione con connection pooling (module-level singleton)
        session = _get_http_session()
        
        resp = session.get(
            url,
            headers=headers,
            timeout=(connect_timeout, read_timeout),
            allow_redirects=True,
        )
        # Rifiuta content-type chiaramente non HTML
        ctype = resp.headers.get("Content-Type", "")
        if "text/html" not in ctype and "application/xhtml" not in ctype:
            logger.info("Non-HTML content-type per %s: %s", url, ctype)
            return None

        return resp
    except RequestException as e:
        logger.warning("HTTP error fetching %s: %s", url, e)
        return None


async def _http_get_async(
    url: str,
    timeout: float = DEFAULT_TIMEOUT_S,
    max_retries: int = MAX_RETRIES_ASYNC,
) -> Optional[Tuple[bytes, str, Dict[str, str]]]:
    """
    Async HTTP GET with exponential backoff and rate limiting.
    
    Returns:
        (content_bytes, final_url, headers) or None on failure
    
    Features:
    - Per-domain rate limiting
    - Exponential backoff for 429/503 errors
    - Proper encoding detection
    - Connection pooling via aiohttp session
    """
    session = await get_aiohttp_session()
    if not session:
        logger.warning("aiohttp session not available, falling back to sync")
        # Fallback to sync version
        resp = _http_get(url, timeout)
        if resp:
            return (resp.content, resp.url, dict(resp.headers))
        return None
    
    rate_limiter = get_domain_rate_limiter()
    
    for attempt in range(max_retries):
        try:
            # Apply per-domain rate limiting
            await rate_limiter.acquire(url)
            
            # Perform async GET
            async with session.get(url, allow_redirects=True, timeout=timeout) as resp:
                # Check for rate limiting or server errors
                if resp.status in (429, 503):
                    if attempt < max_retries - 1:
                        # Exponential backoff
                        backoff = min(BACKOFF_BASE * (2 ** attempt), BACKOFF_MAX)
                        logger.warning(
                            f"HTTP {resp.status} for {url}, backing off {backoff:.2f}s "
                            f"(attempt {attempt + 1}/{max_retries})"
                        )
                        await asyncio.sleep(backoff)
                        continue
                    else:
                        logger.error(f"Max retries reached for {url} (status {resp.status})")
                        return None
                
                # Check status
                resp.raise_for_status()
                
                # Check content-type
                ctype = resp.headers.get("Content-Type", "")
                if "text/html" not in ctype and "application/xhtml" not in ctype:
                    logger.info(f"Non-HTML content-type for {url}: {ctype}")
                    return None
                
                # Read content (limit size)
                content = await resp.read()
                if len(content) > MAX_HTML_BYTES:
                    content = content[:MAX_HTML_BYTES]
                
                return (content, str(resp.url), dict(resp.headers))
        
        except asyncio.TimeoutError:
            if attempt < max_retries - 1:
                backoff = min(BACKOFF_BASE * (2 ** attempt), BACKOFF_MAX)
                logger.warning(
                    f"Timeout for {url}, backing off {backoff:.2f}s "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                await asyncio.sleep(backoff)
            else:
                logger.error(f"Timeout fetching {url} after {max_retries} attempts")
                return None
        
        except Exception as e:
            if attempt < max_retries - 1:
                backoff = min(BACKOFF_BASE * (2 ** attempt), BACKOFF_MAX)
                logger.warning(
                    f"Error fetching {url}: {e}, backing off {backoff:.2f}s "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                await asyncio.sleep(backoff)
            else:
                logger.error(f"Failed to fetch {url} after {max_retries} attempts: {e}")
                return None
    
    return None


# ===================== Parsing helpers =====================

def _extract_with_trafilatura(html: str, url: str) -> Optional[str]:
    """
    Prova ad usare trafilatura, se disponibile.
    """
    try:
        import trafilatura  # type: ignore

        text = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=False,
            favor_recall=True,
        )
        if text:
            return text.strip()
        return None
    except Exception as e:  # noqa: BLE001
        logger.debug("Trafilatura non disponibile o fallita: %s", e)
        return None


def _extract_with_readability(html: str, url: str) -> Optional[str]:
    """
    Prova ad usare readability-lxml + BeautifulSoup come fallback più ricco.
    """
    try:
        from readability import Document  # type: ignore
        from bs4 import BeautifulSoup  # type: ignore

        doc = Document(html)
        summary_html = doc.summary(html_partial=True)
        soup = BeautifulSoup(summary_html, "html.parser")

        # Rimuovi script/style
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        text = soup.get_text(separator="\n")
        text = _normalize_whitespace(text)
        return text.strip() or None
    except Exception as e:  # noqa: BLE001
        logger.debug("Readability non disponibile o fallita: %s", e)
        return None


def _extract_og_image(html: str, base_url: str) -> Optional[str]:
    """
    Cerca l'og:image (o simili) nel markup.
    """
    try:
        from bs4 import BeautifulSoup  # type: ignore
    except Exception:
        # fallback minimale a regex
        match = re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
            html,
            re.IGNORECASE,
        )
        if match:
            url = match.group(1).strip()
            return urljoin(base_url, url)
        return None

    try:
        soup = BeautifulSoup(html, "html.parser")
        # og:image standard
        tag = soup.find("meta", attrs={"property": "og:image"})
        if not tag:
            # alternative comuni
            tag = soup.find("meta", attrs={"name": "twitter:image"})
        if tag and tag.get("content"):
            url = tag["content"].strip()
            return urljoin(base_url, url)
    except Exception as e:  # noqa: BLE001
        logger.debug("Errore parsing og:image: %s", e)

    return None


def _simple_html_text(html: str) -> str:
    """
    Fallback leggero: elimina script/style e prende il testo complessivo.
    """
    try:
        from bs4 import BeautifulSoup  # type: ignore

        soup = BeautifulSoup(html, "html.parser")

        # Elimina elementi chiaramente inutili
        for tag_name in [
            "script",
            "style",
            "noscript",
            "header",
            "footer",
            "nav",
            "aside",
            "form",
        ]:
            for t in soup.find_all(tag_name):
                t.decompose()

        text = soup.get_text(separator="\n")
        return _normalize_whitespace(text).strip()
    except Exception:
        # super fallback: regex
        html_no_script = re.sub(
            r"(?is)<(script|style|noscript).*?</\1>",
            " ",
            html,
        )
        text = re.sub(r"(?s)<[^>]+>", " ", html_no_script)
        return _normalize_whitespace(text).strip()


def _extract_title_and_description(html: str) -> str:
    """
    Ultimo fallback: title + meta description + primi paragrafi.
    """
    title = ""
    description = ""
    paragraphs: list[str] = []

    try:
        from bs4 import BeautifulSoup  # type: ignore

        soup = BeautifulSoup(html, "html.parser")

        # title
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        # meta description
        desc_tag = soup.find("meta", attrs={"name": "description"})
        if desc_tag and desc_tag.get("content"):
            description = desc_tag["content"].strip()

        # primi paragrafi
        for p in soup.find_all("p", limit=5):
            txt = p.get_text(separator=" ", strip=True)
            if txt:
                paragraphs.append(txt)
    except Exception:
        # fallback ancora più minimale con regex
        m_title = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.S)
        if m_title:
            title = re.sub(r"\s+", " ", m_title.group(1)).strip()

        m_desc = re.search(
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)',
            html,
            re.IGNORECASE | re.S,
        )
        if m_desc:
            description = re.sub(r"\s+", " ", m_desc.group(1)).strip()

    parts = []
    if title:
        parts.append(title)
    if description:
        parts.append(description)
    if paragraphs:
        parts.extend(paragraphs)

    return "\n\n".join(parts).strip()


def _normalize_whitespace(text: str) -> str:
    # normalizza spazi e linee multiple
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    # collassa troppe righe vuote
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _strip_tags(html_fragment: str) -> str:
    """
    Rimuove i tag HTML da un frammento, usato nei fallback regex.
    """
    without_scripts = re.sub(
        r"(?is)<(script|style|noscript).*?</\1>",
        " ",
        html_fragment,
    )
    text = re.sub(r"(?s)<[^>]+>", " ", without_scripts)
    return _normalize_whitespace(text).strip()


# ===================== PATCH 1: robust async fetch =====================

async def fetch_and_extract_robust(
    url: str,
    timeout: float = DEFAULT_TIMEOUT_S,
    max_retries: int = 2,
) -> Tuple[str, Optional[str]]:
    """
    Fetch con retry e multiple extraction strategies.
    SEMPRE ritorna qualcosa di utile, mai empty string.
    """
    last_error = None

    # helper async per riutilizzare l'HTTP sync senza bloccare l'event loop
    async def _http_get_async(u: str, t: float) -> Optional[requests.Response]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _http_get, u, t)

    for attempt in range(max_retries):
        try:
            resp = await _http_get_async(url, timeout)
            if not resp:
                continue

            html = resp.content[:MAX_HTML_BYTES].decode("utf-8", errors="replace")
            og_image = _extract_og_image(html, resp.url)

            # Multi-strategy robust extraction
            text = extract_content_robust(html, url)

            if text and len(text) > 100:
                return text, og_image

        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                await asyncio.sleep(0.5 * (attempt + 1))

    # LAST RESORT: Return URL + error info (NEVER empty)
    return f"[Contenuto non disponibile per {url}. Errore: {last_error}]", None


def _extract_aggressive(html: str) -> str:
    """
    Fallback più aggressivo che prende TUTTO il testo utile.
    """
    try:
        from bs4 import BeautifulSoup  # type: ignore
    except Exception:
        # fallback minimale se bs4 non c'è
        return _simple_html_text(html)

    soup = BeautifulSoup(html, "html.parser")

    # Remove noise
    for tag in soup(
        [
            "script",
            "style",
            "nav",
            "header",
            "footer",
            "aside",
            "iframe",
            "noscript",
        ]
    ):
        tag.decompose()

    # Get all paragraphs, divs with content, lists
    texts = []
    for tag in soup.find_all(["p", "div", "article", "section", "li"]):
        text = tag.get_text(strip=True)
        if len(text) > 30:  # Skip very short fragments
            texts.append(text)

    return "\n\n".join(texts[:50])  # Limit to first 50 blocks


def _extract_meta_and_paragraphs(html: str) -> str:
    """
    Ultra-fallback: meta description + tutti i <p>
    """
    parts = []

    # Title
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if m:
        parts.append(m.group(1).strip())

    # Meta description
    m = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)',
        html,
        re.I,
    )
    if m:
        parts.append(m.group(1).strip())

    # All paragraphs
    for m in re.finditer(r"<p[^>]*>(.*?)</p>", html, re.I | re.S):
        text = _strip_tags(m.group(1)).strip()
        if len(text) > 40:
            parts.append(text)

    return "\n\n".join(parts[:20])


# ===================== Public API =====================

def fetch_and_extract(url: str, timeout: float = DEFAULT_TIMEOUT_S) -> Tuple[str, Optional[str]]:
    """
    Funzione principale usata da quantum_api.

    Ritorna:
        (text, og_image_url)

    - text: contenuto “leggibile” per l’LLM
    - og_image_url: se trovata, altrimenti None
    """
    logger.info("fetch_and_extract url=%s timeout=%.2f", url, timeout)

    resp = _http_get(url, timeout=timeout)
    if not resp:
        return ("", None)

    # Limita body
    content = resp.content[:MAX_HTML_BYTES]

    # tenta decodifica con encoding dichiarato, poi fallback
    try:
        html = content.decode(resp.encoding or "utf-8", errors="replace")
    except Exception:
        html = content.decode("utf-8", errors="replace")

    # Prova OG image subito, così la abbiamo qualunque parser usiamo
    og_image = _extract_og_image(html, resp.url)

    # 1) Trafilatura (miglior qualità se disponibile)
    text = _extract_with_trafilatura(html, resp.url)
    if not text:
        # 2) Readability (se disponibile)
        text = _extract_with_readability(html, resp.url)
    if not text:
        # 3) Fallback: HTML -> testo “pulito”
        text = _simple_html_text(html)
    if not text:
        # 4) Ultima spiaggia: title + description + primi paragrafi
        text = _extract_title_and_description(html)

    # sicurezza finale
    text = _normalize_whitespace(text).strip()

    logger.info(
        "Estratti %d caratteri di testo da %s",
        len(text),
        url,
    )

    return text, og_image


async def fetch_and_extract_async(
    url: str,
    timeout: float = DEFAULT_TIMEOUT_S
) -> Tuple[str, Optional[str]]:
    """
    Fully async version of fetch_and_extract using aiohttp.
    
    Args:
        url: URL to fetch
        timeout: Total timeout in seconds
    
    Returns:
        (text, og_image_url) tuple
        - text: readable content for LLM
        - og_image_url: Open Graph image if found, else None
    
    Features (Phase 1 + Issue 3B):
    - Async HTTP with aiohttp
    - Per-domain rate limiting
    - Exponential backoff for errors
    - Proper encoding detection
    - **Automatic JS renderer fallback (Issue 3B)**
    """
    logger.info("[PERF] fetch_and_extract_async url=%s timeout=%.2f", url, timeout)
    
    # Issue 3B: Use renderer pipeline when enabled
    if RENDERER_ENABLED:
        extracted, fetch_log = await fetch_and_extract_with_renderer(url, timeout)
        # Return in the old format (text, og_image) for backward compatibility
        return extracted.text, extracted.og_image
    
    # Legacy path (when renderer is disabled)
    t0 = time.time()
    
    # Fetch with async HTTP
    result = await _http_get_async(url, timeout)
    if not result:
        logger.warning(f"Failed to fetch {url}")
        return ("", None)
    
    content, final_url, headers = result
    
    # Detect encoding from headers or content
    encoding = None
    content_type = headers.get("Content-Type", "")
    if "charset=" in content_type:
        try:
            encoding = content_type.split("charset=")[-1].split(";")[0].strip()
        except Exception:
            pass
    
    # Decode HTML
    try:
        html = content.decode(encoding or "utf-8", errors="replace")
    except Exception:
        html = content.decode("utf-8", errors="replace")
    
    # Extract og:image
    og_image = _extract_og_image(html, final_url)
    
    # Extract text using multiple strategies (CPU-bound, use thread pool)
    loop = asyncio.get_running_loop()
    
    # 1) Trafilatura (best quality if available)
    text = await loop.run_in_executor(None, _extract_with_trafilatura, html, final_url)
    if not text:
        # 2) Readability (if available)
        text = await loop.run_in_executor(None, _extract_with_readability, html, final_url)
    if not text:
        # 3) Fallback: HTML -> clean text
        text = await loop.run_in_executor(None, _simple_html_text, html)
    if not text:
        # 4) Last resort: title + description + first paragraphs
        text = await loop.run_in_executor(None, _extract_title_and_description, html)
    
    # Final normalization
    text = _normalize_whitespace(text).strip()
    
    elapsed = time.time() - t0
    logger.info(
        "[PERF] Extracted %d chars from %s in %.2fs",
        len(text),
        url,
        elapsed
    )
    
    return text, og_image


async def parallel_fetch_urls(
    urls: List[str],
    timeout: float = DEFAULT_TIMEOUT_S,
    max_concurrent: int = HTTP_MAX_CONCURRENT
) -> List[Dict[str, any]]:
    """
    Fetch multiple URLs in parallel with controlled concurrency.
    
    Args:
        urls: List of URLs to fetch
        timeout: Timeout per URL
        max_concurrent: Max concurrent requests
    
    Returns:
        List of dicts with keys: url, text, og_image, success, error
    
    Features:
    - Parallel fetching with asyncio.gather()
    - Graceful error handling (don't fail entire batch)
    - Per-URL timeout
    - Return partial results if some fetches fail
    """
    logger.info(f"[PERF] parallel_fetch_urls: {len(urls)} URLs, max_concurrent={max_concurrent}")
    t0 = time.time()
    
    # Use semaphore to limit concurrency
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def fetch_one(url: str) -> Dict[str, any]:
        """Fetch single URL with semaphore."""
        async with semaphore:
            try:
                text, og_image = await fetch_and_extract_async(url, timeout)
                return {
                    "url": url,
                    "text": text,
                    "og_image": og_image,
                    "success": bool(text),
                    "error": None
                }
            except Exception as e:
                logger.warning(f"Error fetching {url}: {e}")
                return {
                    "url": url,
                    "text": "",
                    "og_image": None,
                    "success": False,
                    "error": str(e)
                }
    
    # Gather all results (return_exceptions=False, errors handled in fetch_one)
    tasks = [fetch_one(url) for url in urls]
    results = await asyncio.gather(*tasks)
    
    elapsed = time.time() - t0
    success_count = sum(1 for r in results if r["success"])
    logger.info(
        f"[PERF] parallel_fetch_urls completed: {success_count}/{len(urls)} successful in {elapsed:.2f}s"
    )
    
    return results


__all__ = [
    "fetch_and_extract",
    "fetch_and_extract_async",
    "parallel_fetch_urls",
    "ExtractResult",
    "fetch_and_extract_robust",
    "close_aiohttp_session",
    # Issue 3: New exports
    "fetch_url",
    "extract_text",
    "fetch_and_extract_with_renderer",
    "ExtractedContent",
    "FetchLog",
    "EXTRACT_MIN_CHARS",
    "RENDERER_ENABLED",
]
