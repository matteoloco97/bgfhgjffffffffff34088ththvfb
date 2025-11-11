#!/usr/bin/env python3
# core/web_tools.py — Fetch & Extract robusto
# Patch 2025-11: timeout, size cap, charset detect, block formatting,
#                og:image esteso, fallback Browserless opzionale.

from __future__ import annotations

import os, re, html, asyncio
from typing import Tuple, Optional
import requests

# ========================= ENV & COSTANTI ============================

def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)) or str(default)
    try:
        import re as _re
        m = _re.search(r"-?\d+", raw)
        return int(m.group(0)) if m else int(default)
    except Exception:
        return int(default)

def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default)) or str(default)
    try:
        import re as _re
        m = _re.search(r"-?\d+(?:\.\d+)?", raw)
        return float(m.group(0)) if m else float(default)
    except Exception:
        return float(default)

FETCH_TIMEOUT_S       = _env_float("WEB_FETCH_TIMEOUT_S", 20.0)
MAX_HTML_BYTES        = _env_int("WEB_MAX_HTML_BYTES", 1_800_000)   # ~1.8MB
MAX_EXTRACT_CHARS     = _env_int("WEB_TOOLS_MAX_CHARS", 20_000)     # taglio testo estratto
ACCEPT_LANGUAGE       = os.getenv("WEB_ACCEPT_LANGUAGE", "it-IT,it;q=0.9,en;q=0.6")
UA                    = os.getenv("SEARCH_UA", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36")

EN_BROWSERLESS        = (os.getenv("EN_BROWSERLESS") or os.getenv("BROWSERLESS_USE") or "0").strip() in ("1","true","yes","on")
BROWSERLESS_URL       = (os.getenv("BROWSERLESS_URL", "") or "").rstrip("/")
BROWSERLESS_TOKEN     = os.getenv("BROWSERLESS_TOKEN", "")

# ========================= REGEX & HELPERS ===========================

# og:image (e varianti) più coprente
_META_OG_IMG = re.compile(
    r'''<meta[^>]+(?:property|name)=["'](?:og:image|twitter:image|twitter:image:src)["'][^>]+content=["']([^"']+)["']''',
    re.I
)
_LINK_IMAGE_SRC = re.compile(
    r'''<link[^>]+rel=["']image_src["'][^>]+href=["']([^"']+)["']''', re.I
)

# Alcuni domini sono spesso JS-heavy → proviamo browserless se l'HTML è “vuoto”
_JS_HEAVY_HINTS = (
    "medium.com", "bloomberg.com", "ft.com", "linkedin.com",
    "instagram.com", "x.com", "twitter.com"
)

_BLOCK_TAGS = re.compile(r"</?(?:p|div|section|article|ul|ol|li|br|h[1-6]|table|tr|td|th|header|footer|aside|nav)[^>]*>", re.I)
_SCRIPT_RE  = re.compile(r"(?is)<script[^>]*>.*?</script>")
_STYLE_RE   = re.compile(r"(?is)<style[^>]*>.*?</style>")
TAG_RE      = re.compile(r"(?s)<[^>]+>")
WS_RE       = re.compile(r"[ \t\u00A0\u200B\u200C\u200D]+")

def _looks_html(content_type: str) -> bool:
    ct = (content_type or "").lower()
    return "text/html" in ct or "application/xhtml" in ct

def _is_pdf(content_type: str, url: str) -> bool:
    if "application/pdf" in (content_type or "").lower():
        return True
    return url.lower().endswith(".pdf")

def _domain(u: str) -> str:
    try:
        from urllib.parse import urlparse
        h = urlparse(u).hostname or ""
        return h.lower()
    except Exception:
        return ""

def _normalize_url(u: str) -> str:
    u = (u or "").strip()
    if not u:
        return u
    if not re.match(r"^https?://", u, re.I):
        return "https://" + u
    return u

def _decode_bytes(b: bytes, r: requests.Response) -> str:
    # 1) requests già tenta .encoding da header
    enc = r.encoding
    if not enc:
        # 2) usa apparent_encoding (chardet/charset_normalizer)
        try:
            enc = r.apparent_encoding
        except Exception:
            enc = None
    enc = enc or "utf-8"
    try:
        return b.decode(enc, errors="replace")
    except Exception:
        # fallback brutale
        try:
            return b.decode("utf-8", errors="replace")
        except Exception:
            return b.decode("latin-1", errors="replace")

def _clean_html_keep_blocks(html_text: str) -> str:
    # rimuovi script/style
    t = _SCRIPT_RE.sub(" ", html_text)
    t = _STYLE_RE.sub(" ", t)

    # sostituisci i blocchi con newline per preservare struttura
    t = _BLOCK_TAGS.sub("\n", t)

    # rimuovi il resto dei tag
    t = TAG_RE.sub(" ", t)

    # unescape & normalizza whitespace
    t = html.unescape(t)
    t = WS_RE.sub(" ", t)
    # riduci newlines multipli
    t = re.sub(r"\n{3,}", "\n\n", t).strip()

    # rimuovi caratteri invisibili comuni
    t = t.replace("\u200b", "")
    return t

def _extract_og_image(html_doc: str) -> Optional[str]:
    m = _META_OG_IMG.search(html_doc)
    if m:
        return m.group(1).strip()
    m2 = _LINK_IMAGE_SRC.search(html_doc)
    if m2:
        return m2.group(1).strip()
    return None

# ========================= FETCHERS ==================================

def _http_headers() -> dict:
    return {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": ACCEPT_LANGUAGE,
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

def _stream_limited_get(url: str) -> Tuple[str, requests.Response]:
    """
    GET con stream limitato in bytes per evitare mem bloat.
    Ritorna (html_text_or_raw_text, response)
    """
    r = requests.get(url, headers=_http_headers(), timeout=FETCH_TIMEOUT_S, stream=True, allow_redirects=True)
    r.raise_for_status()

    # Se non è HTML, prova comunque a leggere un pezzetto
    buf = bytearray()
    read = 0
    for chunk in r.iter_content(chunk_size=32_768):
        if not chunk:
            break
        buf.extend(chunk)
        read += len(chunk)
        if read >= MAX_HTML_BYTES:
            break

    text = _decode_bytes(bytes(buf), r)
    return text, r

def _browserless_content(url: str) -> Optional[str]:
    if not (EN_BROWSERLESS and BROWSERLESS_URL and BROWSERLESS_TOKEN):
        return None
    try:
        endpoint = f"{BROWSERLESS_URL}/content?token={BROWSERLESS_TOKEN}"
        payload = {"url": url, "waitFor": "body"}
        r = requests.post(endpoint, json=payload, timeout=FETCH_TIMEOUT_S + 5)
        r.raise_for_status()
        return r.text
    except Exception:
        return None

# ========================= PUBLIC API =================================

async def fetch_and_extract(url: str) -> Tuple[str, Optional[str]]:
    """
    Scarica la pagina e restituisce (testo_pulito, og_image_url).
    - Limite bytes/char per sicurezza
    - Detect content-type / charset
    - Fallback Browserless per siti JS-heavy se HTML “vuoto”
    - Se PDF o contenuto binario, ritorna messaggio breve (niente parsing)
    """
    url = _normalize_url(url)

    # 1) fetch “raw” con limite
    try:
        raw_html, resp = await asyncio.to_thread(_stream_limited_get, url)
    except Exception as e:
        # 1.b) hard fallback: prova direttamente Browserless se disponibile
        bl_fallback = _browserless_content(url)
        if bl_fallback:
            text_full = bl_fallback
            og_img = _extract_og_image(text_full)
            text_clean = _clean_html_keep_blocks(text_full)[:MAX_EXTRACT_CHARS]
            return (text_clean, og_img)
        return (f"[fetch failed: {e}]", None)

    ctype = (resp.headers.get("Content-Type") or "").lower()

    # 2) PDF/non-HTML → niente parsing avanzato
    if _is_pdf(ctype, url):
        return ("[PDF rilevato: apri la fonte per visualizzare il documento.]", None)

    # 3) Se non HTML ma testuale, restituisci un estratto
    if not _looks_html(ctype):
        # testo “grezzo”
        txt = raw_html.strip()
        if not txt:
            return ("[contenuto non testuale o vuoto]", None)
        return (txt[:MAX_EXTRACT_CHARS], None)

    # 4) HTML: estrai og:image e testo
    og_img = _extract_og_image(raw_html)
    text_clean = _clean_html_keep_blocks(raw_html)

    # 5) Se il testo sembra troppo corto (JS-heavy), prova Browserless come fallback
    if len(text_clean) < 400 and any(h in _domain(url) for h in _JS_HEAVY_HINTS):
        bl_html = _browserless_content(url)
        if bl_html:
            og_img = _extract_og_image(bl_html) or og_img
            text_clean = _clean_html_keep_blocks(bl_html)

    # 6) Taglio a misura
    text_clean = text_clean[:MAX_EXTRACT_CHARS]

    return (text_clean, og_img)
