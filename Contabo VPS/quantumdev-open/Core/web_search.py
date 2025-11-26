# core/web_search.py — resilient multi-provider + heuristic fallback (patched+snippets)
import os, re, html, time
from typing import List, Dict, Tuple, Optional
from urllib.parse import urlparse, parse_qs, unquote, quote_plus, urlunparse, urlencode
import requests

# Additional deps for domain ranking
try:
    import yaml  # type: ignore
except Exception:
    yaml = None  # if pyyaml is unavailable the policy will not be applied
from functools import lru_cache

# ===================== Config =====================

UA = os.getenv(
    "SEARCH_UA",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"
)
SEARCH_LANG = os.getenv("SEARCH_LANG", "it-IT,it;q=0.9")

DEBUG = os.getenv("WEBSEARCH_DEBUG", "0") == "1"
PROVIDER_TIMEOUT_S = float(os.getenv("WEBSEARCH_PROVIDER_TIMEOUT_S", "4.5"))
MAX_RESULTS_HARD = int(os.getenv("WEBSEARCH_MAX_RESULTS_HARD", "20"))

# Which backend to use for web search. Supported values:
#  - 'ddg'    : use DuckDuckGo/Bing HTML providers (default, legacy)
#  - 'serpapi': use SerpAPI (requires SERPAPI_KEY env var)
#  - 'google' : use Google Custom Search (requires GOOGLE_API_KEY + GOOGLE_CX)
#  - 'multi'  : query all supported providers (ddg, bing, serpapi/google) and merge
SEARCH_BACKEND = os.getenv("SEARCH_BACKEND", "ddg").strip().lower()

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

# --- SerpAPI / Google Custom Search (placeholder) ---

def _search_serpapi(query: str, num: int) -> List[Dict[str, str]]:
    """
    Fetch results from SerpAPI. This is a placeholder implementation that
    requires the SERPAPI_KEY environment variable to be set. If the key is
    unavailable or an error occurs, an empty list is returned. The returned
    items follow the same format as other providers.
    """
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key or num <= 0:
        return []
    try:
        params = {
            "api_key": api_key,
            "engine": "google",
            "q": query,
            "num": num,
            "hl": os.getenv("SEARCH_HL", "it"),
            "gl": os.getenv("SEARCH_GL", "it"),
        }
        r = requests.get("https://serpapi.com/search", params=params, timeout=PROVIDER_TIMEOUT_S)
        r.raise_for_status()
        data = r.json()
        items: List[Dict[str, str]] = []
        for ans in data.get("organic_results", [])[:num]:
            url = ans.get("link") or ans.get("url")
            title = ans.get("title") or ""
            snippet = ans.get("snippet") or ans.get("snippet_highlighted_words") or ""
            row = {"url": url or "", "title": title}
            if snippet:
                if isinstance(snippet, list):
                    snippet = " ".join(snippet)
                row["snippet"] = snippet
            items.append(row)
        return items
    except Exception as e:
        _log(f"SerpAPI error: {e}")
        return []


def _search_google_cse(query: str, num: int) -> List[Dict[str, str]]:
    """
    Fetch results from Google Custom Search. Requires GOOGLE_API_KEY and GOOGLE_CX
    environment variables. Returns empty list on error. This function is a
    placeholder and may be improved with paging & error handling.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    cx = os.getenv("GOOGLE_CX")
    if not api_key or not cx or num <= 0:
        return []
    try:
        params = {
            "key": api_key,
            "cx": cx,
            "q": query,
            "num": max(1, min(num, 10)),
            "hl": os.getenv("SEARCH_HL", "it"),
            "gl": os.getenv("SEARCH_GL", "it"),
        }
        r = requests.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=PROVIDER_TIMEOUT_S)
        r.raise_for_status()
        data = r.json()
        items: List[Dict[str, str]] = []
        for res in data.get("items", [])[:num]:
            url = res.get("link") or res.get("url")
            title = res.get("title") or ""
            snippet = res.get("snippet") or ""
            row = {"url": url or "", "title": title}
            if snippet:
                row["snippet"] = snippet
            items.append(row)
        return items
    except Exception as e:
        _log(f"Google CSE error: {e}")
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

# ===================== Domain policy (boost/allow) =====================

@lru_cache()  # cache the policy file once per process
def _load_domain_policy() -> Dict[str, Dict[str, List[str]]]:
    """
    Load domain policy configuration.

    The policy YAML must have a top-level `categories` key, each containing:

      triggers: list[str]  → substrings that trigger this category
      prefer  : list[str]  → domains to boost
      allow   : list[str]  → domains to allow (neutral)
      avoid   : list[str]  → domains to drop entirely (optional)

    The default category is used when no trigger matches. If the policy file
    cannot be loaded or PyYAML is unavailable, an empty dict is returned.
    """
    path = os.getenv("SOURCE_DOMAIN_POLICY_FILE", "config/source_policy.yaml")
    if not yaml:
        _log("pyyaml non installato: salta policy dominî")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
            cats = cfg.get("categories") or {}
            norm_cats: Dict[str, Dict[str, List[str]]] = {}
            for name, node in cats.items():
                triggers = [str(t).lower() for t in (node.get("triggers") or [])]
                prefer = [str(d).lower() for d in (node.get("prefer") or [])]
                allow = [str(d).lower() for d in (node.get("allow") or [])]
                avoid = [str(d).lower() for d in (node.get("avoid") or [])]
                norm_cats[name] = {
                    "triggers": triggers,
                    "prefer": prefer,
                    "allow": allow,
                    "avoid": avoid,
                }
            return norm_cats
    except Exception as e:
        _log(f"Impossibile caricare la domain policy da {path}: {e}")
        return {}


def _get_domain_policy(query: str) -> Dict[str, List[str]]:
    """
    Given a user query, determine which domain policy category applies and
    return a dictionary containing lists for `prefer`, `allow` and `avoid`.

    If no trigger matches, the `default` category is used. Missing entries
    default to empty lists. The returned lists are copies and safe to mutate.
    """
    cfg = _load_domain_policy()
    if not cfg:
        return {"prefer": [], "allow": [], "avoid": []}
    s = (query or "").lower()
    for name, node in cfg.items():
        if name == "default":
            continue
        for trig in node.get("triggers", []):
            if trig and trig in s:
                return {
                    "prefer": node.get("prefer", [])[:],
                    "allow": node.get("allow", [])[:],
                    "avoid": node.get("avoid", [])[:],
                }
    default_node = cfg.get("default") or {}
    return {
        "prefer": default_node.get("prefer", [])[:],
        "allow": default_node.get("allow", [])[:],
        "avoid": default_node.get("avoid", [])[:],
    }


def _rank_by_domain_policy(results: List[Dict[str, str]], query: str) -> List[Dict[str, str]]:
    """
    Reorder and filter search results according to the domain policy for
    the given query. Results whose host matches a domain in the `avoid`
    list are removed entirely. Remaining results are scored:

      +2 → host matches a domain in `prefer`
      +1 → host matches a domain in `allow`
      0  → all others

    The returned list is sorted by score descending while preserving
    original order within the same score bucket.
    """
    policy = _get_domain_policy(query)
    prefer_domains = policy.get("prefer", []) or []
    allow_domains = policy.get("allow", []) or []
    avoid_domains = policy.get("avoid", []) or []
    if not (prefer_domains or allow_domains or avoid_domains):
        return results

    def host_matches(host: str, domain_list: List[str]) -> bool:
        for d in domain_list:
            if d and (host == d or host.endswith("." + d) or host.endswith(d)):
                return True
        return False

    scored: List[Tuple[int, int, Dict[str, str]]] = []
    for idx, r in enumerate(results):
        try:
            host = (urlparse(r.get("url", "")).hostname or "").lower()
        except Exception:
            host = ""
        # skip avoid domains
        if host and host_matches(host, avoid_domains):
            continue
        score = 0
        if host and host_matches(host, prefer_domains):
            score = 2
        elif host and host_matches(host, allow_domains):
            score = 1
        scored.append((score, idx, r))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [r for _, _, r in scored]

# === Multi-backend aggregator ===
def _aggregate_multi(query: str, num: int) -> List[Dict[str, str]]:
    """
    Query all supported providers (DDG HTML POST/GET/LITE, Bing, SerpAPI or Google)
    and merge results. Duplicate URLs are removed preserving the first appearance.
    Results are normalised and ranked by domain policy. Heuristic fallback is used
    only if no provider returns any result.
    """
    out: List[Dict[str, str]] = []
    remaining = num
    # collect from ddg/bing regardless of any early exit
    # DuckDuckGo
    try:
        out.extend(_search_ddg_html_post(query, remaining))
    except Exception:
        pass
    if len(out) < num:
        try:
            more = _search_ddg_html_get_all(query, num - len(out))
            _append_unique(out, more, num)
        except Exception:
            pass
    if len(out) < num:
        try:
            more = _search_ddg_lite(query, num - len(out))
            _append_unique(out, more, num)
        except Exception:
            pass
    # Bing
    if len(out) < num:
        try:
            more = _search_bing_html(query, num - len(out))
            _append_unique(out, more, num)
        except Exception:
            pass
    # SerpAPI/Google CSE (if configured)
    # attempt SerpAPI first
    if len(out) < num:
        try:
            api_res = _search_serpapi(query, num - len(out))
            _append_unique(out, api_res, num)
        except Exception:
            pass
    if len(out) < num:
        try:
            api_res = _search_google_cse(query, num - len(out))
            _append_unique(out, api_res, num)
        except Exception:
            pass
    # Browserless fallback (lite) is deliberately omitted in multi mode to
    # avoid heavy headless calls except as last resort
    # Heuristics if still empty
    if HEURISTIC_SEEDS_ENABLED and not out:
        out = _heuristic_results(query, num)
    # normalise and rank
    norm = [_normalize(r) for r in out if _ok_url(r.get("url", ""))]
    ranked = _rank_by_domain_policy(norm, query)
    return ranked[:num]

# ================= Public API =================

def search(query: str, num: int = 8) -> List[Dict[str, str]]:
    """
    Perform a web search and return up to `num` results in a normalised
    format: each dict contains at least `url` and `title`, with optional
    `snippet`. Results are filtered and ranked according to domain policy.

    Behaviour depends on the `SEARCH_BACKEND` environment variable:

      'serpapi' → query SerpAPI only.
      'google'  → query Google Custom Search only.
      'multi'   → query all available providers (DDG/Bing/SerpAPI/Google) and merge.
      default   → legacy sequential search (DDG → Bing → browserless fallback).

    Results are cached for a short TTL to avoid repeated network calls.
    """
    q = (query or "").strip()
    if not q or num <= 0:
        return []

    # clamp to hard cap
    num = max(1, min(int(num), MAX_RESULTS_HARD))

    # check cache
    cached = _cache_get(q, num)
    if cached is not None:
        return cached[:num]

    backend = SEARCH_BACKEND
    # explicit single-backend mode
    if backend in ("serpapi", "google"):
        if backend == "serpapi":
            try:
                results = _search_serpapi(q, num)
            except Exception:
                results = []
        else:
            try:
                results = _search_google_cse(q, num)
            except Exception:
                results = []
        # fallback heuristics if nothing
        if HEURISTIC_SEEDS_ENABLED and not results:
            results = _heuristic_results(q, num)
        norm = [_normalize(r) for r in results if _ok_url(r.get("url", ""))]
        ranked = _rank_by_domain_policy(norm, q)
        final = ranked[:num]
        _cache_set(q, num, final)
        return final

    # multi-backend aggregator mode
    if backend == "multi":
        final = _aggregate_multi(q, num)
        _cache_set(q, num, final)
        return final

    # legacy sequential search (ddg/bing/browserless)
    results: List[Dict[str, str]] = []
    # 1) DDG POST
    try:
        results.extend(_search_ddg_html_post(q, num - len(results)))
    except Exception:
        pass
    if len(results) >= num:
        norm = [_normalize(r) for r in results if _ok_url(r.get("url", ""))]
        final = _rank_by_domain_policy(norm, q)[:num]
        _cache_set(q, num, final)
        return final
    # 2) DDG GET (mirrors)
    try:
        more = _search_ddg_html_get_all(q, num - len(results))
        _append_unique(results, more, num)
    except Exception:
        pass
    if len(results) >= num:
        norm = [_normalize(r) for r in results if _ok_url(r.get("url", ""))]
        final = _rank_by_domain_policy(norm, q)[:num]
        _cache_set(q, num, final)
        return final
    # 3) DDG LITE
    try:
        more = _search_ddg_lite(q, num - len(results))
        _append_unique(results, more, num)
    except Exception:
        pass
    if len(results) >= num:
        norm = [_normalize(r) for r in results if _ok_url(r.get("url", ""))]
        final = _rank_by_domain_policy(norm, q)[:num]
        _cache_set(q, num, final)
        return final
    # 4) Bing HTML
    try:
        more = _search_bing_html(q, num - len(results))
        _append_unique(results, more, num)
    except Exception:
        pass
    if len(results) >= num:
        norm = [_normalize(r) for r in results if _ok_url(r.get("url", ""))]
        final = _rank_by_domain_policy(norm, q)[:num]
        _cache_set(q, num, final)
        return final
    # 5) optional browserless fallback
    try:
        more = _search_ddg_lite_via_browserless(q, num - len(results))
        _append_unique(results, more, num)
    except Exception:
        pass
    # fallback heuristics
    if HEURISTIC_SEEDS_ENABLED and not results:
        results = _heuristic_results(q, num)
    norm_all = [_normalize(r) for r in results if _ok_url(r.get("url", ""))]
    final = _rank_by_domain_policy(norm_all, q)[:num]
    _cache_set(q, num, final)
    return final
