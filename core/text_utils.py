mkdir -p /root/quantumdev-open/core

# --- core/text_utils.py ---
cat >/root/quantumdev-open/core/text_utils.py <<'PY'
import re
from html import unescape

def strip_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"(?is)<(script|style).*?>.*?</\\1>", " ", html)
    html = re.sub(r"(?i)<br\\s*/?>", "\n", html)
    html = re.sub(r"(?i)</p>", "\n", html)
    text = re.sub(r"(?s)<.*?>", " ", html)
    text = unescape(text)
    text = re.sub(r"[ \\t\\r\\f\\v]+", " ", text)
    text = re.sub(r"\\n\\s*\\n+", "\n\n", text)
    return text.strip()

def split_chunks(s: str, size: int):
    return [s[i:i+size] for i in range(0, len(s), size)] if s else []
PY

# --- core/persona_store.py ---
cat >/root/quantumdev-open/core/persona_store.py <<'PY'
import os, redis

_R = redis.Redis(
    host=os.getenv("REDIS_HOST","localhost"),
    port=int(os.getenv("REDIS_PORT",6379)),
    db=int(os.getenv("REDIS_DB",0)),
)

def _key(source: str, source_id: str) -> str:
    return f"persona:{source}:{source_id}"

async def get_persona(source: str, source_id: str) -> str:
    val = _R.get(_key(source, source_id))
    if val:
        return val.decode()
    return os.getenv("DEFAULT_PERSONA","Sei un assistente utile, conciso e amichevole.")

async def set_persona(source: str, source_id: str, text: str) -> None:
    _R.set(_key(source, source_id), text)

async def reset_persona(source: str, source_id: str) -> None:
    _R.delete(_key(source, source_id))
PY

# --- core/chat_engine.py ---
cat >/root/quantumdev-open/core/chat_engine.py <<'PY'
import os, requests

GENERATE_URL = os.getenv("QUANTUM_GENERATE_URL", "http://127.0.0.1:8081/generate")
SYSTEM_PREFIX = "Istruzioni di personalità:\n"

def build_prompt(user_text: str, persona: str) -> str:
    return f"{SYSTEM_PREFIX}{persona}\n\nUtente:\n{user_text}"

async def reply_with_llm(user_text: str, persona: str) -> str:
    prompt = build_prompt(user_text, persona)
    try:
        r = requests.post(GENERATE_URL, json={"prompt": prompt}, timeout=30)
        r.raise_for_status()
        data = r.json()
        try:
            return data["response"]["choices"][0]["message"]["content"].strip()
        except Exception:
            return str(data)[:4000]
    except Exception as e:
        return f"❌ Errore LLM: {e}"
PY

# --- core/web_tools.py ---
cat >/root/quantumdev-open/core/web_tools.py <<'PY'
import re, aiohttp
from .text_utils import strip_html

async def fetch_and_extract(url: str):
    og_img = None
    html = ""
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.get(url, headers={"User-Agent":"QuantumDevBot/1.0"}) as r:
            html = await r.text(errors="ignore")
    m = re.search(
        r'<meta[^>]+property=["\\\']og:image["\\\'][^>]+content=["\\\']([^"\\\']+)["\\\']',
        html, re.I
    )
    if m:
        og_img = m.group(1)
    text = strip_html(html)
    return text, og_img
PY
