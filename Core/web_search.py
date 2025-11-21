# core/web_search.py — resilient multi-provider + heuristic fallback (patched+snippets)
import os, re, html, time
from typing import List, Dict, Tuple, Optional
from urllib.parse import urlparse, parse_qs, unquote, quote_plus, urlunparse, urlencode
import requests

# ===================== Config =====================

UA = os.getenv(
    "SEARCH_UA",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"
)
SEARCH_LANG = os.getenv("SEARCH_LANG", "it-IT,it;q=0.9")

DEBUG = os.getenv("WEBSEARCH_DEBUG", "0") == "1"
PROVIDER_TIMEOUT_S = float(os.getenv("WEBSEARCH_PROVIDER_TIMEOUT_S", "4.5"))
MAX_RESULTS_HARD = int(os.getenv("WEBSEARCH_MAX_RESULTS_HARD", "20"))

# Feature flags (0/1)
EN_DDG_HTML    = os.getenv("EN_DDG_HTML", "1") == "1"
EN_DDG_LITE    = os.getenv("EN_DDG_LITE", "1") == "1"
EN_BING_HTML   = os.getenv("EN_BING_HTML", "1") == "1"
EN_BROWSERLESS = os.getenv("EN_BROWSERLESS", "0") == "1"   # ← coerente con .env
HEURISTIC_SEEDS_ENABLED = os.getenv("HEURISTIC_SEEDS_ENABLED", "1") == "1"

# Endpoints
DDG_HTML_PRIMARY = os.getenv("DDG_HTML_URL", "https://html.duckduckgo.com/html/").rstrip("/")
DDG_HTML_MIRRORS = [
    "https://duckduckgo.com/html",
    "https://lite.duckduckgo.com/html",
]
DDG_LITE_URL = "https://duckduckgo.com/lite/"

BLS_URL   = (os.getenv("BROWSERLESS_URL", "") or "").rstrip("/")
BLS_TOKEN = os.getenv("BROWSERLESS_TOKEN", "")

LANG_HDR = {"Accept-Language": SEARCH_LANG}

# ================== Helpers (log & clean) ==================

def _log(msg: str):
    if DEBUG:
        print(f"[web_search] {msg}")

def _strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "")

def _squash_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

_BAD_SCHEMES = ("javascript:", "data:", "mailto:", "tel:")
_TRACK_KEYS = {
    "utm_source","utm_medium","utm_campaign","utm_term","utm_content",
    "gclid","fbclid","igshid","si","ref","ref_src","spm"
}

def _clean_tracking(u: str) -> str:
    try:
        p = urlparse(u)
        if not p.scheme or p.scheme.lower().startswith(_BAD_SCHEMES):
            return u
        qs = parse_qs(p.query)
        kept = {k: v for k, v in qs.items() if k.lower() not in _TRACK_KEYS}
        new_q = urlencode([(k, vv) for k, vs in kept.items() for vv in vs])
        return urlunparse((p.scheme, p.netloc, p.path, p.params, new_q, ""))  # drop fragment
    except Exception:
        return u

def _clean_duck_url(u: str) -> str:
    try:
        if u.startswith("/l/?") or "duckduckgo.com/l/?" in u:
            base = u if u.startswith("http") else "https://duckduckgo.com" + u
            q = parse_qs(urlparse(base).query)
            if "uddg" in q and q["uddg"]:
                return _clean_tracking(unquote(q["uddg"][0]))
        return _clean_tracking(u)
    except Exception:
        return u

def _ok_url(u: str) -> bool:
    if not u:
        return False
    if any(u.lower().startswith(s) for s in _BAD_SCHEMES):
        return False
    host = (urlparse(u).hostname or "").lower()
    if not host:
        return False
    # filtra link interni DDG senza redirezione
    if "duckduckgo.com" in host and "uddg=" not in u:
        return False
    return True

def _normalize(row: Dict[str, str]) -> Dict[str, str]:
    url = (row.get("url") or "").strip()
    title = _squash_ws(html.unescape(_strip_tags(row.get("title") or "")))
    snippet = _squash_ws(html.unescape(_strip_tags(row.get("snippet") or "")))
    out = {"url": url, "title": title}
    if snippet:
        out["snippet"] = snippet
    return out

def _append_unique(base: List[Dict[str, str]], more: List[Dict[str, str]], limit: int) -> None:
    """Aggiunge a 'base' elementi di 'more' evitando duplicati URL, fino a 'limit'."""
    if not more or len(base) >= limit:
        return
    seen = {r["url"] for r in base}
    for r in more:
        u = r.get("url")
        if not u or u in seen:
            continue
        base.append(r)
        seen.add(u)
        if len(base) >= limit:
            break

# ===================== HTTP =====================

_session = requests.Session()
_session.headers.update({"User-Agent": UA, **LANG_HDR})

def _http_get(url: str, timeout: float) -> str:
    r = _session.get(url, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r.text

def _http_post(url: str, data: Dict[str, str], timeout: float) -> str:
    r = _session.post(url, data=data, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r.text

# ===================== Parsers =====================

def _ddg_pair_results_and_snippets(html_text: str) -> List[Dict[str, str]]:
    """
    Parser robusto per DuckDuckGo (html/lite):
    - trova <a class="result__a">...</a> o varianti
    - associa il primo snippet successivo (result__snippet / result-link)
    """
    out: List[Dict[str, str]] = []

    link_patts = [
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        r'<a[^>]+class="result-link"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
    ]
    snip_pat = re.compile(
        r'(?:<div[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</div>|'
        r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>)',
        re.I | re.S
    )

    for p in link_patts:
        for m in re.finditer(p, html_text, re.I | re.S):
            raw_url = m.group(1)
            title = m.group(2)
            url = _clean_duck_url(raw_url).strip()
            if not (_ok_url(url) and title):
                continue
            # cerca snippet vicino (finestra limitata per evitare match troppo lontani)
            window = html_text[m.end(): m.end() + 1200]
            sm = snip_pat.search(window)
            snippet = ""
            if sm:
                snippet = sm.group(1) or sm.group(2) or ""
            out.append({
                "url": url,
                "title": html.unescape(_strip_tags(title)).strip(),
                "snippet": html.unescape(_strip_tags(snippet)).strip()
            })

    # dedup su URL, conserva il primo (di solito il più completo)
    seen = set()
    uniq: List[Dict[str, str]] = []
    for r in out:
        if r["url"] in seen:
            continue
        uniq.append(r)
        seen.add(r["url"])
    return uniq

def _parse_ddg_html(html_text: str) -> List[Dict[str, str]]:
    return _ddg_pair_results_and_snippets(html_text)

def _parse_bing_html(html_text: str) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    # blocchi classici
    for m in re.finditer(
        r'<li class="b_algo".*?<h2>.*?<a href="([^"]+)"[^>]*>(.*?)</a>(?:.*?<div class="b_caption">.*?<p>(.*?)</p>)?',
        html_text, re.I | re.S
    ):
        url = _clean_tracking((m.group(1) or "").strip())
        title = html.unescape(_strip_tags(m.group(2) or "")).strip()
        snippet = html.unescape(_strip_tags(m.group(3) or "")).strip()
        if _ok_url(url) and title:
            row = {"url": url, "title": title}
            if snippet:
                row["snippet"] = snippet
            items.append(row)

    # fallback (markup varianti)
    if not items:
        for m in re.finditer(r'<h2[^>]*>\s*<a\s+href="([^"]+)"[^>]*>(.*?)</a>', html_text, re.I | re.S):
            url = _clean_tracking(m.group(1).strip())
            title = html.unescape(_strip_tags(m.group(2))).strip()
            if _ok_url(url) and title:
                items.append({"url": url, "title": title})
    return items

# ===================== Providers =====================

def _search_ddg_html_post(query: str, num: int) -> List[Dict[str, str]]:
    if not EN_DDG_HTML or num <= 0:
        return []
    try:
        _log("DDG HTML POST primary")
        html_text = _http_post(
            DDG_HTML_PRIMARY + "/",
            data={"q": query, "kl": "it-it", "kp": "-2"},
            timeout=PROVIDER_TIMEOUT_S,
        )
        rows = _parse_ddg_html(html_text)
        _log(f"DDG POST hits: {len(rows)}")
        return rows[:num]
    except Exception as e:
        _log(f"POST fail {DDG_HTML_PRIMARY}: {e}")
        return []

def _search_ddg_html_get_all(query: str, num: int) -> List[Dict[str, str]]:
    if not EN_DDG_HTML or num <= 0:
        return []
    total: List[Dict[str, str]] = []
    mirrors = [DDG_HTML_PRIMARY] + DDG_HTML_MIRRORS
    for base in mirrors:
        try:
            _log("DDG HTML GET " + base)
            url = f"{base}?q={quote_plus(query)}&kl=it-it&kp=-2"
            html_text = _http_get(url, timeout=PROVIDER_TIMEOUT_S)
            rows = _parse_ddg_html(html_text)
            _append_unique(total, rows, num)
            if len(total) >= num:
                break
        except Exception as e:
            _log(f"GET fail {base}: {e}")
    _log(f"DDG GET total hits: {len(total)}")
    return total[:num]

def _search_ddg_lite(query: str, num: int) -> List[Dict[str, str]]:
    if not EN_DDG_LITE or num <= 0:
        return []
    try:
        _log("DDG LITE GET")
        url = f"{DDG_LITE_URL}?q={quote_plus(query)}&kl=it-it&kp=-2"
        html_text = _http_get(url, timeout=PROVIDER_TIMEOUT_S)
        rows = _parse_ddg_html(html_text)
        _log(f"DDG LITE hits: {len(rows)}")
        return rows[:num]
    except Exception as e:
        _log(f"DDG LITE GET fail: {e}")
        return []

def _search_bing_html(query: str, num: int) -> List[Dict[str, str]]:
    if not EN_BING_HTML or num <= 0:
        return []
    try:
        _log("BING HTML GET")
        url = f"https://www.bing.com/search?q={quote_plus(query)}&setlang=it-IT"
        text = _http_get(url, timeout=PROVIDER_TIMEOUT_S)
        rows = _parse_bing_html(text)
        _log(f"BING hits: {len(rows)}")
        return rows[:num]
    except Exception as e:
        _log(f"BING GET fail: {e}")
        return []

def _search_ddg_lite_via_browserless(query: str, num: int) -> List[Dict[str, str]]:
    if not (EN_BROWSERLESS and BLS_URL and BLS_TOKEN) or num <= 0:
        return []
    try:
        url = f"{DDG_LITE_URL}?q={quote_plus(query)}&kl=it-it&kp=-2"
        _log(f"BLS /content {url}")
        bls_endpoint = f"{BLS_URL}/content?token={BLS_TOKEN}"
        payload = {"url": url, "waitFor": "body"}
        r = requests.post(bls_endpoint, json=payload, timeout=PROVIDER_TIMEOUT_S + 2.0)
        r.raise_for_status()
        rows = _parse_ddg_html(r.text)
        _log(f"BLS parsed: {len(rows)} hits")
        return rows[:num]
    except Exception as e:
        _log(f"BLS error: {e}")
        return []

# ================= Heuristic fallback (no generic) =================

def _heuristic_results(query: str, num: int) -> List[Dict[str, str]]:
    """
    Fallback SOLO per categorie specifiche. Nessun fallback generico.
    Se vuoto → ritorna [] (il chiamante segnalerà 'no_results').
    """
    q = (query or "").lower()
    seeds: List[Dict[str, str]] = []

    def add(url: str, title: str, snippet: Optional[str] = None):
        row = {"url": url, "title": title}
        if snippet:
            row["snippet"] = snippet
        seeds.append(row)

    # Meteo (fonti nazionali, non legate a una città fissa)
    if ("meteo" in q) or ("che tempo" in q) or ("weather" in q) or ("previsioni" in q):
        add("https://www.meteoam.it/", "Meteo Aeronautica Militare")
        add("https://www.ilmeteo.it/", "ILMETEO")
        add("https://www.3bmeteo.com/", "3B Meteo")

    # Prezzi / Crypto / FX / Borsa
    if any(k in q for k in [
        "prezzo", "quotazione", "quanto vale", "btc", "bitcoin", "eth", "ethereum",
        "eurusd", "eur/usd", "borsa", "azioni", "indice", "cambio", "forex", "fx"
    ]):
        add("https://coinmarketcap.com/currencies/bitcoin/", "Bitcoin (BTC) – CoinMarketCap")
        add("https://www.coindesk.com/price/bitcoin/", "Bitcoin Price – CoinDesk")
        add("https://www.investing.com/crypto/bitcoin/btc-usd", "BTC/USD – Investing.com")

    # Sport / Serie A (live risultati)
    if any(k in q for k in ["serie a", "risultati", "calcio", "partite", "live score", "diretta"]):
        add("https://www.flashscore.it/calcio/italia/serie-a/", "Live Serie A – FlashScore")
        add("https://www.diretta.it/serie-a/", "Risultati Serie A – Diretta.it")
        add("https://www.legaseriea.it/serie-a", "Calendario e Risultati – Lega Serie A")

    # dedup & cut
    seen = set()
    out: List[Dict[str, str]] = []
    for r in seeds:
        if r["url"] in seen:
            continue
        out.append(r)
        seen.add(r["url"])
        if len(out) >= max(1, num):
            break
    _log(f"Heuristic fallback used: {len(out)} links")
    return out

# ================= Tiny in-memory cache =================

_CACHE: Dict[Tuple[str, int], Tuple[float, List[Dict[str, str]]]] = {}
_CACHE_TTL = 30.0  # secondi

def _cache_get(q: str, n: int) -> Optional[List[Dict[str, str]]]:
    key = (q.strip().lower(), int(n))
    hit = _CACHE.get(key)
    if not hit:
        return None
    ts, data = hit
    if time.time() - ts > _CACHE_TTL:
        _CACHE.pop(key, None)
        return None
    return data

def _cache_set(q: str, n: int, data: List[Dict[str, str]]):
    key = (q.strip().lower(), int(n))
    _CACHE[key] = (time.time(), data[:])

# ================= Public API =================

def search(query: str, num: int = 8) -> List[Dict[str, str]]:
    """
    Return: [{"url": "...", "title": "...", "snippet": "...?"}] (max 'num').
    Order:
      1) DDG HTML POST
      2) DDG HTML GET (mirrors)
      3) DDG LITE
      4) BING HTML
      5) Browserless (optional)
      6) Heuristic fallback di categoria (se ancora vuoto; può restituire [])
    """
    q = (query or "").strip()
    if not q or num <= 0:
        return []

    # clamp a hard cap (evita sprechi e overfetch)
    num = max(1, min(int(num), MAX_RESULTS_HARD))

    # cache veloce
    ch = _cache_get(q, num)
    if ch is not None:
        return ch[:num]

    results: List[Dict[str, str]] = []

    # 1) DDG HTML POST
    try:
        results.extend(_search_ddg_html_post(q, num - len(results)))
    except Exception:
        pass
    if len(results) >= num:
        norm = [_normalize(r) for r in results if _ok_url(r.get("url", ""))][:num]
        _cache_set(q, num, norm)
        return norm

    # 2) DDG HTML GET (mirrors)
    try:
        more = _search_ddg_html_get_all(q, num - len(results))
        _append_unique(results, more, num)
    except Exception:
        pass
    if len(results) >= num:
        norm = [_normalize(r) for r in results if _ok_url(r.get("url", ""))][:num]
        _cache_set(q, num, norm)
        return norm

    # 3) DDG LITE
    try:
        more = _search_ddg_lite(q, num - len(results))
        _append_unique(results, more, num)
    except Exception:
        pass
    if len(results) >= num:
        norm = [_normalize(r) for r in results if _ok_url(r.get("url", ""))][:num]
        _cache_set(q, num, norm)
        return norm

    # 4) Bing HTML
    try:
        more = _search_bing_html(q, num - len(results))
        _append_unique(results, more, num)
    except Exception:
        pass
    if len(results) >= num:
        norm = [_normalize(r) for r in results if _ok_url(r.get("url", ""))][:num]
        _cache_set(q, num, norm)
        return norm

    # 5) Browserless (optional)
    try:
        more = _search_ddg_lite_via_browserless(q, num - len(results))
        _append_unique(results, more, num)
    except Exception:
        pass

    # 6) Fallback euristico — se ancora vuoto
    if HEURISTIC_SEEDS_ENABLED and not results:
        results = _heuristic_results(q, num)

    # normalizza titoli, URL (e snippet se presente)
    norm = [_normalize(r) for r in results if _ok_url(r.get("url", ""))][:num]
    _log(f"TOTAL hits: {len(norm)}")
    _cache_set(q, num, norm)
    return norm
