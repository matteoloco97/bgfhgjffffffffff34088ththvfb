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
    pip install trafilatura readability-lxml beautifulsoup4

Se le librerie non sono installate, usa fallback più semplici.
"""

from __future__ import annotations

import logging
import os
import re
import asyncio
from dataclasses import dataclass
from typing import Optional, Tuple

import requests
from requests.exceptions import RequestException
from urllib.parse import urljoin
from core.robust_content_extraction import extract_content_robust

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
        # OPTIMIZATION: Usa sessione con connection pooling se disponibile
        session = getattr(_http_get, '_session', None)
        if session is None:
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            session = requests.Session()
            session.trust_env = False
            retry = Retry(total=1, backoff_factor=0.2, status_forcelist=[502, 503, 504])
            adapter = HTTPAdapter(pool_connections=5, pool_maxsize=10, max_retries=retry)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            _http_get._session = session  # type: ignore
        
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


__all__ = ["fetch_and_extract", "ExtractResult", "fetch_and_extract_robust"]
