# core/web_search.py
import os, re, html
from typing import List, Dict
from urllib.parse import urlparse, parse_qs, unquote, quote_plus
import requests

UA = os.getenv(
    "SEARCH_UA",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"
)

# Endpoint HTML “puro” (quello giusto è *html.duckduckgo.com*)
DDG_HTML = os.getenv("DDG_HTML_URL", "https://html.duckduckgo.com/html/")
DEBUG = os.getenv("WEBSEARCH_DEBUG", "0") == "1"

# Browserless
BLS_URL   = os.getenv("BROWSERLESS_URL", "").rstrip("/")
BLS_TOKEN = os.getenv("BROWSERLESS_TOKEN", "")

def _log(msg: str):
    if DEBUG:
        print(f"[web_search] {msg}")

def _strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s)

def _clean_duck_url(u: str) -> str:
    # DDG spesso reindirizza a /l/?uddg=<URL-encoded> -> estrai l’URL reale
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
    """
    Estrae <a class="result__a" href="...">Titolo</a> (HTML)
    e <a class="result-link" ...> per la versione lite.
    """
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
            # scarta link interni DDG (tranne redirect con uddg=)
            if "duckduckgo.com" in url and "uddg=" not in url:
                continue
            out.append({"url": url, "title": title})

    # dedup per URL
    seen = set()
    uniq: List[Dict[str, str]] = []
    for r in out:
        u = r["url"]
        if u in seen:
            continue
        uniq.append(r); seen.add(u)
    return uniq

def _ddg_html_direct(query: str, num: int) -> List[Dict[str, str]]:
    """
    Primo tentativo: POST su https://html.duckduckgo.com/html/
    (è l’endpoint storico “no-js” usato anche su Tor).
    """
    try:
        _log("DDG html.duckduckgo.com POST")
        headers = {
            "User-Agent": UA,
            "Referer": DDG_HTML,
        }
        r = requests.post(DDG_HTML, data={"q": query}, headers=headers, timeout=15)
        r.raise_for_status()
        items = _parse_ddg_html(r.text)
        _log(f"HTTP parsed: {len(items)} hits")
        return items[:num]
    except Exception as e:
        _log(f"DDG html error: {e}")
        return []

def _ddg_lite_direct(query: str, num: int) -> List[Dict[str, str]]:
    """
    Secondo tentativo senza browserless: GET su /lite (a volte basta).
    """
    try:
        url = f"https://duckduckgo.com/lite/?q={quote_plus(query)}"
        _log("DDG GET /lite")
        headers = {"User-Agent": UA}
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        items = _parse_ddg_html(r.text)
        _log(f"HTTP lite parsed: {len(items)} hits")
        return items[:num]
    except Exception as e:
        _log(f"DDG lite error: {e}")
        return []

def _ddg_lite_via_browserless(query: str, num: int) -> List[Dict[str, str]]:
    """
    Terzo tentativo: Browserless /content su /lite.
    """
    if not (BLS_URL and BLS_TOKEN):
        return []
    try:
        url = f"https://duckduckgo.com/lite/?q={quote_plus(query)}"
        _log(f"BLS /content {url}")
        bls_endpoint = f"{BLS_URL}/content?token={BLS_TOKEN}"
        payload = {"url": url, "waitFor": "body"}
        r = requests.post(bls_endpoint, json=payload, timeout=25)
        r.raise_for_status()
        html_text = r.text
        items = _parse_ddg_html(html_text)
        _log(f"BLS parsed: {len(items)} hits")
        return items[:num]
    except Exception as e:
        _log(f"BLS error: {e}")
        return []

def search(query: str, num: int = 8) -> List[Dict[str, str]]:
    """
    Ritorna: [{"url": "...", "title": "..."}] (max 'num').
    Nessuna censura: dedup + preferenze gestite dal layer superiore.
    """
    q = (query or "").strip()
    if not q:
        return []

    results: List[Dict[str, str]] = []

    # 1) HTML “puro” (spesso basta)
    results.extend(_ddg_html_direct(q, num))
    if len(results) >= num:
        return results[:num]

    # 2) Lite diretto
    more = _ddg_lite_direct(q, num * 2)
    # merge dedup
    seen = {r["url"] for r in results}
    for it in more:
        if it["url"] not in seen:
            results.append(it); seen.add(it["url"])
        if len(results) >= num:
            return results[:num]

    # 3) Lite via Browserless (headless Chromium)
    more = _ddg_lite_via_browserless(q, num * 2)
    for it in more:
        if it["url"] not in seen:
            results.append(it); seen.add(it["url"])
        if len(results) >= num:
            break

    return results[:num]
