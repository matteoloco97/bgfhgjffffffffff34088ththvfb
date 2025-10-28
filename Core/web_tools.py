# core/web_tools.py
import re, html, asyncio
import requests

# Estrae una OG image molto semplice
_META_OG_IMG = re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', re.I)

def _strip_tags(text: str) -> str:
    # fallback minimale senza BeautifulSoup
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    # normalizza spazi
    text = re.sub(r"\s+", " ", text).strip()
    return text

async def fetch_and_extract(url: str):
    def _fetch():
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        return r.text

    try:
        html_doc = await asyncio.to_thread(_fetch)
    except Exception as e:
        return (f"[fetch failed: {e}]", None)

    og_img = None
    m = _META_OG_IMG.search(html_doc)
    if m:
        og_img = m.group(1).strip()

    text = _strip_tags(html_doc)
    return (text, og_img)
