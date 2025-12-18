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

import logging
import os
import re
import asyncio
import time
from dataclasses import dataclass
from typing import Optional, Tuple, List, Dict
from collections import defaultdict

import requests
from requests.exceptions import RequestException
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import urljoin
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

DEFAULT_UA = os.getenv(
    "WEB_EXTRACT_UA",
    # UA abbastanza “normale”
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122 Safari/537.36",
)

DEFAULT_LANG = os.getenv(
    "WEB_EXTRACT_LANG",
    "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
)

# Timeout totale di default (secondi)
DEFAULT_TIMEOUT_S = float(os.getenv("WEB_EXTRACT_TIMEOUT_S", "8.0"))

# Limite massimo di byte letti dal body (per evitare esplosioni)
MAX_HTML_BYTES = int(os.getenv("WEB_EXTRACT_MAX_BYTES", str(1_500_000)))

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
                    connect=3.0,
                    sock_read=DEFAULT_TIMEOUT_S - 3.0
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
    
    Features (Phase 1):
    - Async HTTP with aiohttp
    - Per-domain rate limiting
    - Exponential backoff for errors
    - Proper encoding detection
    """
    logger.info("[PERF] fetch_and_extract_async url=%s timeout=%.2f", url, timeout)
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
]
