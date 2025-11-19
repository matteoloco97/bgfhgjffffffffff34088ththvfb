#!/usr/bin/env python3
# core/web_tools.py — Fetch & Extract robusto
# Patch 2025-11:
# - timeout e size cap
# - charset detect (headers + apparent_encoding)
# - estrazione testo con preservazione blocchi
# - og:image esteso + risoluzione URL relativa
# - fallback Browserless opzionale (anche su pagine JS/Cloudflare)
# - sniff PDF via magic bytes oltre che da Content-Type
# - gestione contenuti non-HTML come testo grezzo
# - sessione HTTP riutilizzabile
# - ✅ MINI-CACHE DISCO: TTL breve + ETag/Last-Modified + conditional GET (304) + stale-on-error
# - ✅ Retry con backoff esponenziale leggero

from __future__ import annotations

import os, re, html, asyncio, json, time, hashlib
from typing import Tuple, Optional, Dict, Any
from urllib.parse import urlparse, urljoin
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

def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name, "1" if default else "0") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")

FETCH_TIMEOUT_S       = _env_float("WEB_FETCH_TIMEOUT_S", 20.0)
MAX_HTML_BYTES        = _env_int("WEB_MAX_HTML_BYTES", 1_800_000)   # ~1.8MB
MAX_EXTRACT_CHARS     = _env_int("WEB_TOOLS_MAX_CHARS", 20_000)     # taglio testo estratto
ACCEPT_LANGUAGE       = os.getenv("WEB_ACCEPT_LANGUAGE", "it-IT,it;q=0.9,en;q=0.6")
UA                    = os.getenv("SEARCH_UA", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36")

EN_BROWSERLESS        = (os.getenv("EN_BROWSERLESS") or os.getenv("BROWSERLESS_USE") or "0").strip().lower() in ("1", "true", "yes", "on")
BROWSERLESS_URL       = (os.getenv("BROWSERLESS_URL", "") or "").rstrip("/")
BROWSERLESS_TOKEN     = os.getenv("BROWSERLESS_TOKEN", "")

# Mini-cache (abilitata di default)
WEB_CACHE_ENABLED     = _env_bool("WEB_CACHE_ENABLED", True)
WEB_CACHE_DIR         = os.getenv("WEB_CACHE_DIR", "/tmp/quantum_web_cache")
WEB_CACHE_TTL_S       = _env_int("WEB_CACHE_TTL_S", 300)            # 5 min
WEB_CACHE_STALE_OK    = _env_bool("WEB_CACHE_STALE_OK", True)       # usa cache scaduta se rete fallisce
WEB_FETCH_RETRIES     = max(0, _env_int("WEB_FETCH_RETRIES", 1))    # tentativi extra oltre al primo
WEB_BACKOFF_BASE_S    = _env_float("WEB_BACKOFF_BASE_S", 0.35)

os.makedirs(WEB_CACHE_DIR, exist_ok=True)

# ========================= REGEX & HELPERS ===========================

# og:image (e varianti)
_META_OG_IMG = re.compile(
    r'''<meta[^>]+(?:property|name)=["'](?:og:image|twitter:image|twitter:image:src)["'][^>]+content=["']([^"']+)["']''',
    re.I
)
_LINK_IMAGE_SRC = re.compile(
    r'''<link[^>]+rel=["']image_src["'][^>]+href=["']([^"']+)["']''', re.I
)

# domini JS-heavy (suggeriscono fallback headless)
_JS_HEAVY_HINTS = (
    "medium.com", "bloomberg.com", "ft.com", "linkedin.com",
    "instagram.com", "x.com", "twitter.com"
)

# pattern tipici Cloudflare / pagine vuote
_CLOUDFLARE_HINTS = (
    "Attention Required! | Cloudflare",
    "Just a moment...",
    "cf-challenge",
    "cf-browser-verification"
)

_BLOCK_TAGS = re.compile(r"</?(?:p|div|section|article|ul|ol|li|br|h[1-6]|table|tr|td|th|header|footer|aside|nav)[^>]*>", re.I)
_SCRIPT_RE  = re.compile(r"(?is)<script[^>]*>.*?</script>")
_STYLE_RE   = re.compile(r"(?is)<style[^>]*>.*?</style>")
NOSCRIPT_RE = re.compile(r"(?is)<noscript[^>]*>.*?</noscript>")
TITLE_RE    = re.compile(r"(?is)<title[^>]*>(.*?)</title>")
TAG_RE      = re.compile(r"(?s)<[^>]+>")
WS_RE       = re.compile(r"[ \t\u00A0\u200B\u200C\u200D]+")
TOC_RE      = re.compile(r"(?is)^(indice(?:\s+dei)?\s+contenuti|table of contents)\s*:?.*$")

def _looks_html(content_type: str) -> bool:
    ct = (content_type or "").lower()
    return "text/html" in ct or "application/xhtml" in ct

def _is_pdf(content_type: str, url: str, first_bytes: bytes | None = None) -> bool:
    if "application/pdf" in (content_type or "").lower():
        return True
    if url.lower().endswith(".pdf"):
        return True
    try:
        if first_bytes and first_bytes.startswith(b"%PDF"):
            return True
    except Exception:
        pass
    return False

def _domain(u: str) -> str:
    try:
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
    # 1) requests prova già .encoding (da headers)
    enc = r.encoding
    if not enc:
        # 2) apparent_encoding (charset_normalizer/chardet)
        try:
            enc = r.apparent_encoding
        except Exception:
            enc = None
    enc = enc or "utf-8"
    try:
        return b.decode(enc, errors="replace")
    except Exception:
        try:
            return b.decode("utf-8", errors="replace")
        except Exception:
            return b.decode("latin-1", errors="replace")

def _extract_title(html_text: str) -> str:
    m = TITLE_RE.search(html_text or "")
    if not m:
        return ""
    t = html.unescape(m.group(1) or "").strip()
    # normalizza spazi multipli
    t = re.sub(r"\s+", " ", t)
    return t

def _remove_toc_lines(text: str) -> str:
    lines = text.splitlines()
    out = []
    for ln in lines:
        if TOC_RE.match(ln.strip()):
            # skip intero blocco TOC se le righe successive sono puntate
            continue
        out.append(ln)
    return "\n".join(out)

def _clean_html_keep_blocks(html_text: str) -> str:
    # rimuovi script/style/noscript
    t = _SCRIPT_RE.sub(" ", html_text)
    t = _STYLE_RE.sub(" ", t)
    t = NOSCRIPT_RE.sub(" ", t)

    # sostituisci blocchi con newline per preservare struttura
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

    # rimuovi eventuale TOC/Indice
    t = _remove_toc_lines(t)
    return t

def _extract_og_image(html_doc: str, base_url: str) -> Optional[str]:
    url = None
    m = _META_OG_IMG.search(html_doc)
    if m:
        url = m.group(1).strip()
    else:
        m2 = _LINK_IMAGE_SRC.search(html_doc)
        if m2:
            url = m2.group(1).strip()
    if not url:
        return None
    # risolvi URL relativo rispetto alla pagina
    try:
        return urljoin(base_url, url)
    except Exception:
        return url

# ========================= SESSIONE HTTP ==============================

def _http_headers() -> dict:
    return {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": ACCEPT_LANGUAGE,
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

_SESSION = requests.Session()
_SESSION.headers.update(_http_headers())

# ========================= MINI-CACHE (file) ==========================

def _cache_key(url: str) -> str:
    u = _normalize_url(url)
    h = hashlib.sha256(u.strip().encode("utf-8")).hexdigest()
    return os.path.join(WEB_CACHE_DIR, h)

def _cache_paths(url: str) -> tuple[str, str]:
    base = _cache_key(url)
    return base + ".txt", base + ".json"

def _cache_load(url: str) -> tuple[Optional[Dict[str, Any]], Optional[str], bool]:
    """
    Ritorna (meta, raw_text, fresh)
    - fresh=True se entro TTL
    - meta può contenere: saved_at, etag, last_modified, content_type, status, url
    """
    try:
        p_txt, p_meta = _cache_paths(url)
        if not (os.path.isfile(p_txt) and os.path.isfile(p_meta)):
            return None, None, False
        with open(p_meta, "r", encoding="utf-8") as f:
            meta = json.load(f)
        with open(p_txt, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()
        fresh = (time.time() - float(meta.get("saved_at", 0))) <= max(1, WEB_CACHE_TTL_S)
        return meta, raw, fresh
    except Exception:
        return None, None, False

def _cache_save(url: str, raw_text: str, resp: requests.Response, first_bytes: bytes):
    try:
        p_txt, p_meta = _cache_paths(url)
        meta = {
            "url": url,
            "saved_at": int(time.time()),
            "status": int(resp.status_code),
            "content_type": (resp.headers.get("Content-Type") or ""),
            "etag": resp.headers.get("ETag") or resp.headers.get("Etag"),
            "last_modified": resp.headers.get("Last-Modified") or resp.headers.get("last-modified"),
            "first_bytes_hex": first_bytes[:8].hex() if isinstance(first_bytes, (bytes, bytearray)) else "",
        }
        # write atomico
        tmptxt = p_txt + ".tmp"
        tmpmeta = p_meta + ".tmp"
        with open(tmptxt, "w", encoding="utf-8") as f:
            f.write(raw_text or "")
        with open(tmpmeta, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)
        os.replace(tmptxt, p_txt)
        os.replace(tmpmeta, p_meta)
    except Exception:
        pass

def _conditional_headers_from_meta(meta: Dict[str, Any]) -> Dict[str, str]:
    h: Dict[str, str] = {}
    et = (meta or {}).get("etag")
    lm = (meta or {}).get("last_modified")
    if et:
        h["If-None-Match"] = et
    if lm:
        h["If-Modified-Since"] = lm
    return h

# ========================= FETCHERS ==================================

def _stream_limited_get(url: str, meta_for_conditional: Optional[Dict[str, Any]] = None) -> Tuple[str, requests.Response, bytes, bool]:
    """
    GET con stream limitato in bytes per evitare mem bloat.
    Ritorna (text_or_raw, response, first_k_bytes, not_modified)
    """
    # retry + backoff
    attempts = 1 + max(0, WEB_FETCH_RETRIES)
    back = WEB_BACKOFF_BASE_S
    last_exc: Optional[Exception] = None

    hdrs = dict(_http_headers())
    if meta_for_conditional:
        hdrs.update(_conditional_headers_from_meta(meta_for_conditional))

    for i in range(attempts):
        try:
            r = _SESSION.get(url, timeout=FETCH_TIMEOUT_S, stream=True, allow_redirects=True, headers=hdrs)
            # 304 = Not Modified → usa cache
            if r.status_code == 304:
                return "", r, b"", True
            r.raise_for_status()

            buf = bytearray()
            first = b""
            read = 0
            for chunk in r.iter_content(chunk_size=32_768):
                if not chunk:
                    break
                if read == 0:
                    first = chunk[:8]  # per sniff PDF
                buf.extend(chunk)
                read += len(chunk)
                if read >= MAX_HTML_BYTES:
                    break

            text = _decode_bytes(bytes(buf), r)
            return text, r, first, False
        except Exception as e:
            last_exc = e
            if i < attempts - 1:
                try:
                    time.sleep(back)
                except Exception:
                    pass
                back *= 2.0
                continue
            # esauriti i tentativi → rilancia
            raise last_exc

def _browserless_content(url: str) -> Optional[str]:
    if not (EN_BROWSERLESS and BROWSERLESS_URL and BROWSERLESS_TOKEN):
        return None
    try:
        endpoint = f"{BROWSERLESS_URL}/content?token={BROWSERLESS_TOKEN}"
        payload = {"url": url, "waitFor": "body"}
        r = _SESSION.post(endpoint, json=payload, timeout=FETCH_TIMEOUT_S + 5)
        r.raise_for_status()
        return r.text
    except Exception:
        return None

def _needs_headless_fallback(html_text: str, url: str) -> bool:
    # troppo corto o Cloudflare/hints noti
    if len((html_text or "").strip()) < 400 and any(h in _domain(url) for h in _JS_HEAVY_HINTS):
        return True
    title = _extract_title(html_text or "")
    if any(h in (html_text or "") for h in _CLOUDFLARE_HINTS) or any(h in title for h in _CLOUDFLARE_HINTS):
        return True
    return False

# ========================= PUBLIC API =================================

async def fetch_and_extract(url: str) -> Tuple[str, Optional[str]]:
    """
    Scarica la pagina e restituisce (testo_pulito, og_image_url).
    - Limite bytes/char per sicurezza
    - Detect content-type / charset / magic bytes PDF
    - Mini-cache con TTL + ETag/Last-Modified (304) e stale-on-error
    - Fallback Browserless per siti JS-heavy/Cloudflare
    - Se PDF o contenuto binario, ritorna messaggio breve (niente parsing)
    """
    url = _normalize_url(url)

    # ===== 0) Cache lookup =====
    cached_meta, cached_raw, fresh = (None, None, False)
    if WEB_CACHE_ENABLED:
        cached_meta, cached_raw, fresh = _cache_load(url)
        if fresh and isinstance(cached_raw, str):
            # re-estrai da cache raw
            og_img = _extract_og_image(cached_raw, url)
            text_clean = _clean_html_keep_blocks(cached_raw)[:MAX_EXTRACT_CHARS]
            return (text_clean, og_img)

    # ===== 1) Fetch “raw” con limite (+ conditional se cache esiste) =====
    try:
        raw_html, resp, first_bytes, not_mod = await asyncio.to_thread(
            _stream_limited_get, url, cached_meta if cached_meta else None
        )
        # 304 → usa cache esistente (refresh timestamp)
        if not_mod and WEB_CACHE_ENABLED and isinstance(cached_raw, str):
            # touch saved_at
            try:
                p_txt, p_meta = _cache_paths(url)
                with open(p_meta, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                meta["saved_at"] = int(time.time())
                with open(p_meta + ".tmp", "w", encoding="utf-8") as f:
                    json.dump(meta, f, ensure_ascii=False)
                os.replace(p_meta + ".tmp", p_meta)
            except Exception:
                pass
            og_img = _extract_og_image(cached_raw, url)
            text_clean = _clean_html_keep_blocks(cached_raw)[:MAX_EXTRACT_CHARS]
            return (text_clean, og_img)
    except Exception as e:
        # 1.b) fallback headless
        bl_fallback = _browserless_content(url)
        if bl_fallback:
            text_full = bl_fallback
            og_img = _extract_og_image(text_full, url)
            text_clean = _clean_html_keep_blocks(text_full)[:MAX_EXTRACT_CHARS]
            # salva anche fallback in cache
            if WEB_CACHE_ENABLED:
                class _FakeResp:  # minimale per _cache_save
                    status_code = 200
                    headers = {"Content-Type": "text/html; charset=utf-8"}
                _cache_save(url, text_full, _FakeResp(), b"")
            return (text_clean, og_img)
        # Se abbiamo cache scaduta e consentito → usa stale
        if WEB_CACHE_ENABLED and WEB_CACHE_STALE_OK and isinstance(cached_raw, str):
            og_img = _extract_og_image(cached_raw, url)
            text_clean = _clean_html_keep_blocks(cached_raw)[:MAX_EXTRACT_CHARS]
            return (text_clean, og_img)
        return (f"[fetch failed: {e}]", None)

    ctype = (resp.headers.get("Content-Type") or "").lower()

    # 2) PDF/non-HTML → messaggio breve (+ cachea meta)
    if _is_pdf(ctype, url, first_bytes):
        if WEB_CACHE_ENABLED:
            _cache_save(url, raw_html or "", resp, first_bytes)
        return ("[PDF rilevato: apri la fonte per visualizzare il documento.]", None)

    # 3) Non-HTML ma testuale → estratto grezzo
    if not _looks_html(ctype):
        txt = (raw_html or "").strip()
        if WEB_CACHE_ENABLED:
            _cache_save(url, raw_html or "", resp, first_bytes)
        if not txt:
            return ("[contenuto non testuale o vuoto]", None)
        return (txt[:MAX_EXTRACT_CHARS], None)

    # 4) HTML: estrazione primaria
    og_img = _extract_og_image(raw_html, url)
    text_clean = _clean_html_keep_blocks(raw_html)

    # 5) Headless fallback se necessario
    if _needs_headless_fallback(raw_html, url):
        bl_html = _browserless_content(url)
        if bl_html:
            og_img = _extract_og_image(bl_html, url) or og_img
            text_clean = _clean_html_keep_blocks(bl_html)
            # salva il contenuto migliore in cache
            if WEB_CACHE_ENABLED:
                class _FakeResp:  # mantiene etag/last-mod precedenti? no, ma ok per mini-cache
                    status_code = 200
                    headers = {"Content-Type": "text/html; charset=utf-8"}
                _cache_save(url, bl_html, _FakeResp(), b"")
        else:
            # comunque cachea il raw
            if WEB_CACHE_ENABLED:
                _cache_save(url, raw_html or "", resp, first_bytes)
    else:
        # cachea il raw
        if WEB_CACHE_ENABLED:
            _cache_save(url, raw_html or "", resp, first_bytes)

    # 6) Taglio a misura
    text_clean = text_clean[:MAX_EXTRACT_CHARS]

    return (text_clean, og_img)
