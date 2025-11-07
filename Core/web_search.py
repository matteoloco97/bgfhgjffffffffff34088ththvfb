# core/web_search.py — resilient multi-provider + heuristic fallback (clean)
import os, re, html
from typing import List, Dict
from urllib.parse import urlparse, parse_qs, unquote, quote_plus
import requests

UA = os.getenv(
    "SEARCH_UA",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"
)

DEBUG = os.getenv("WEBSEARCH_DEBUG", "0") == "1"
PROVIDER_TIMEOUT_S = float(os.getenv("WEBSEARCH_PROVIDER_TIMEOUT_S", "4.5"))

# Feature flags (0/1)
EN_DDG_HTML = os.getenv("EN_DDG_HTML", "1") == "1"
EN_DDG_LITE = os.getenv("EN_DDG_LITE", "1") == "1"
EN_BING_HTML = os.getenv("EN_BING_HTML", "1") == "1"
EN_BROWSERLESS = os.getenv("BROWSERLESS_USE", "0") == "1"  # coerente con .env
HEURISTIC_SEEDS_ENABLED = os.getenv("HEURISTIC_SEEDS_ENABLED", "1") == "1"

# Endpoints
DDG_HTML_PRIMARY = os.getenv("DDG_HTML_URL", "https://html.duckduckgo.com/html/")
DDG_HTML_MIRRORS = [
    "https://duckduckgo.com/html/",
    "https://lite.duckduckgo.com/html/",
]
DDG_LITE_URL = "https://duckduckgo.com/lite/"

BLS_URL   = (os.getenv("BROWSERLESS_URL", "") or "").rstrip("/")
BLS_TOKEN = os.getenv("BROWSERLESS_TOKEN", "")

# ---------------------------------------------------------------------

def _log(msg: str):
    if DEBUG:
        print(f"[web_search] {msg}")

def _strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "")

def _http_get(url: str, timeout: float, headers: Dict[str, str]) -> str:
    r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r.text

def _http_post(url: str, data: Dict[str, str], timeout: float, headers: Dict[str, str]) -> str:
    r = requests.post(url, headers=headers, data=data, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r.text

def _clean_duck_url(u: str) -> str:
    try:
        if u.startswith("/l/?") or "duckduckgo.com/l/?" in u:
            base = u if u.startswith("http") else "https://duckduckgo.com" + u
            q = parse_qs(urlparse(base).query)
            if "uddg" in q and q["uddg"]:
                return unquote(q["uddg"][0])
        return u
    except Exception:
        return u

def _parse_ddg_html(html_text: str) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    patterns = [
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        r'<a[^>]+class="result-link"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
    ]
    for pat in patterns:
        for m in re.finditer(pat, html_text, re.I | re.S):
            url = _clean_duck_url(m.group(1)).strip()
            title = html.unescape(_strip_tags(m.group(2))).strip()
            if not url:
                continue
            # scarta link interni DDG senza redirezione
            if "duckduckgo.com" in url and "uddg=" not in url:
                continue
            out.append({"url": url, "title": title})

    # dedup
    seen = set(); uniq: List[Dict[str, str]] = []
    for r in out:
        if r["url"] in seen:
            continue
        uniq.append(r); seen.add(r["url"])
    return uniq

# ---------------- DuckDuckGo providers ----------------

def _search_ddg_html_post(query: str, num: int) -> List[Dict[str, str]]:
    if not EN_DDG_HTML:
        return []
    try:
        _log("DDG HTML POST primary")
        html_text = _http_post(
            DDG_HTML_PRIMARY,
            data={"q": query},
            timeout=PROVIDER_TIMEOUT_S,
            headers={"User-Agent": UA, "Referer": DDG_HTML_PRIMARY, "Accept-Language": "it-IT,it;q=0.9"},
        )
        rows = _parse_ddg_html(html_text)
        _log(f"DDG POST hits: {len(rows)}")
        return rows[:num]
    except Exception as e:
        _log(f"POST fail {DDG_HTML_PRIMARY}: {e}")
        return []

def _search_ddg_html_get_all(query: str, num: int) -> List[Dict[str, str]]:
    if not EN_DDG_HTML:
        return []
    total: List[Dict[str, str]] = []
    mirrors = [DDG_HTML_PRIMARY] + DDG_HTML_MIRRORS
    for base in mirrors:
        try:
            _log("DDG HTML GET " + ("primary" if base == DDG_HTML_PRIMARY else f"mirror {base}"))
            url = f"{base}?q={quote_plus(query)}&kl=it-it&kp=-2"
            html_text = _http_get(url, timeout=PROVIDER_TIMEOUT_S, headers={"User-Agent": UA, "Accept-Language": "it-IT,it;q=0.9"})
            rows = _parse_ddg_html(html_text)
            total.extend(rows)
            if len(total) >= num:
                break
        except Exception as e:
            _log(f"GET fail {base}: {e}")
    _log(f"DDG GET total hits: {len(total)}")
    # dedup
    seen = set(); out: List[Dict[str, str]] = []
    for r in total:
        if r["url"] in seen:
            continue
        out.append(r); seen.add(r["url"])
    return out[:num]

def _search_ddg_lite(query: str, num: int) -> List[Dict[str, str]]:
    if not EN_DDG_LITE:
        return []
    try:
        _log("DDG LITE GET")
        url = f"{DDG_LITE_URL}?q={quote_plus(query)}&kl=it-it&kp=-2"
        html_text = _http_get(url, timeout=PROVIDER_TIMEOUT_S, headers={"User-Agent": UA, "Accept-Language": "it-IT,it;q=0.9"})
        rows = _parse_ddg_html(html_text)
        _log(f"DDG LITE hits: {len(rows)}")
        return rows[:num]
    except Exception as e:
        _log(f"DDG LITE GET fail: {e}")
        return []

# ---------------- Bing (HTML) ----------------

def _parse_bing_html(html_text: str) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for m in re.finditer(
        r'<li class="b_algo".*?<h2>.*?<a href="([^"]+)"[^>]*>(.*?)</a>',
        html_text, re.I | re.S
    ):
        url = m.group(1).strip()
        title = html.unescape(_strip_tags(m.group(2))).strip()
        if url and title:
            items.append({"url": url, "title": title})
    return items

def _search_bing_html(query: str, num: int) -> List[Dict[str, str]]:
    if not EN_BING_HTML:
        return []
    try:
        _log("BING HTML GET")
        url = f"https://www.bing.com/search?q={quote_plus(query)}&setlang=it-IT"
        text = _http_get(url, timeout=PROVIDER_TIMEOUT_S, headers={"User-Agent": UA, "Accept-Language": "it-IT,it;q=0.9"})
        rows = _parse_bing_html(text)
        _log(f"BING hits: {len(rows)}")
        return rows[:num]
    except Exception as e:
        _log(f"BING GET fail: {e}")
        return []

# ---------------- Browserless (optional) ----------------

def _search_ddg_lite_via_browserless(query: str, num: int) -> List[Dict[str, str]]:
    if not (EN_BROWSERLESS and BLS_URL and BLS_TOKEN):
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

# ---------------- Heuristic fallback ----------------

def _heuristic_results(query: str, num: int) -> List[Dict[str, str]]:
    q = (query or "").lower()
    seeds: List[Dict[str, str]] = []

    def add(url: str, title: str):
        seeds.append({"url": url, "title": title})

    # Meteo
    if "meteo" in q or "che tempo" in q or "weather" in q:
        add("https://www.meteoam.it/it/roma", "Meteo Aeronautica – Roma")
        add("https://www.ilmeteo.it/meteo/Roma", "ILMETEO – Roma")
        add("https://www.3bmeteo.com/meteo/roma", "3B Meteo – Roma")

    # Prezzi / Crypto / FX / Borsa
    if any(k in q for k in [
        "prezzo", "quotazione", "quanto vale", "btc", "bitcoin", "eth", "ethereum",
        "eurusd", "eur/usd", "borsa", "azioni", "indice", "cambio"
    ]):
        add("https://coinmarketcap.com/currencies/bitcoin/", "Bitcoin (BTC) – CoinMarketCap")
        add("https://www.coindesk.com/price/bitcoin/", "Bitcoin Price – CoinDesk")
        add("https://www.binance.com/en/trade/BTC_USDT", "BTC/USDT – Binance")
        add("https://www.investing.com/crypto/bitcoin/btc-usd", "BTC/USD – Investing.com")

    # Sport / Serie A
    if any(k in q for k in ["serie a", "risultati", "calcio", "partite"]):
        add("https://www.diretta.it/serie-a/", "Risultati Serie A – Diretta.it")
        add("https://www.legaseriea.it/serie-a", "Calendario e Risultati – Lega Serie A")
        add("https://www.flashscore.it/calcio/italia/serie-a/", "Live Serie A – FlashScore")

    # Generico fallback
    if not seeds:
        add("https://www.ansa.it/", "ANSA – Ultime notizie")
        add("https://it.wikipedia.org/wiki/Pagina_principale", "Wikipedia (IT) – Ricerca")

    # dedup & cut
    seen = set(); out: List[Dict[str, str]] = []
    for r in seeds:
        if r["url"] in seen:
            continue
        out.append(r); seen.add(r["url"])
        if len(out) >= max(1, num):
            break
    _log(f"Heuristic fallback used: {len(out)} links")
    return out

# ---------------- Public API ----------------

def search(query: str, num: int = 8) -> List[Dict[str, str]]:
    """
    Return: [{"url": "...", "title": "..."}] (max 'num').
    Order of attempts:
      1) DDG HTML POST
      2) DDG HTML GET (mirrors)
      3) DDG LITE
      4) BING HTML
      5) Browserless (optional)
      6) Heuristic fallback (if still empty)
    """
    q = (query or "").strip()
    if not q:
        return []

    results: List[Dict[str, str]] = []

    # 1) DDG HTML POST
    try:
        more = _search_ddg_html_post(q, num - len(results))
        results.extend(more)
    except Exception:
        pass
    if len(results) >= num:
        return results[:num]

    # 2) DDG HTML GET (mirrors)
    try:
        more = _search_ddg_html_get_all(q, num - len(results))
        # merge dedup
        seen = {r["url"] for r in results}
        for r in more:
            if r["url"] in seen:
                continue
            results.append(r); seen.add(r["url"])
            if len(results) >= num:
                break
    except Exception:
        pass
    if len(results) >= num:
        return results[:num]

    # 3) DDG LITE
    try:
        more = _search_ddg_lite(q, num - len(results))
        seen = {r["url"] for r in results}
        for r in more:
            if r["url"] in seen:
                continue
            results.append(r); seen.add(r["url"])
            if len(results) >= num:
                break
    except Exception:
        pass
    if len(results) >= num:
        return results[:num]

    # 4) Bing HTML
    try:
        more = _search_bing_html(q, num - len(results))
        seen = {r["url"] for r in results}
        for r in more:
            if r["url"] in seen:
                continue
            results.append(r); seen.add(r["url"])
            if len(results) >= num:
                break
    except Exception:
        pass
    if len(results) >= num:
        return results[:num]

    # 5) Browserless (optional)
    try:
        more = _search_ddg_lite_via_browserless(q, num - len(results))
        seen = {r["url"] for r in results}
        for r in more:
            if r["url"] in seen:
                continue
            results.append(r); seen.add(r["url"])
            if len(results) >= num:
                break
    except Exception:
        pass

    # 6) Fallback euristico — se ancora vuoto
    if HEURISTIC_SEEDS_ENABLED and not results:
        results = _heuristic_results(q, num)

    _log(f"TOTAL hits: {len(results)}")
    return results[:num]
