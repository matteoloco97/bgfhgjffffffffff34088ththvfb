from fastapi import FastAPI, Request, Body
import requests
import os
import json
import hashlib
import redis
from dotenv import load_dotenv
from typing import Optional, List, Dict
from urllib.parse import urlparse

# --- core imports ---
from core.persona_store import get_persona, set_persona, reset_persona
from core.web_tools import fetch_and_extract
from core.chat_engine import reply_with_llm

# --- OPEN web search helpers ---
from core.source_policy import pick_domains
from core.web_querybuilder import build_query_variants

# === Init ===
load_dotenv()
app = FastAPI()

# === ENV ===
ENV_LLM_ENDPOINT    = os.getenv("LLM_ENDPOINT")
ENV_TUNNEL_ENDPOINT = os.getenv("TUNNEL_ENDPOINT")
LLM_MODEL           = os.getenv("LLM_MODEL", "Qwen/Qwen1.5-7B-Chat")
TEMPERATURE         = float(os.getenv("LLM_TEMPERATURE", 0.7))
MAX_TOKENS          = int(os.getenv("LLM_MAX_TOKENS", 1024))

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB   = int(os.getenv("REDIS_DB", 0))

# === Redis ===
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)

# --- Helpers ------------------------------------------------------------

def hash_prompt(prompt: str, system: str, temperature: float, max_tokens: int, model: str) -> str:
    h = hashlib.sha256()
    h.update(prompt.strip().lower().encode("utf-8"))
    h.update(system.strip().lower().encode("utf-8"))
    h.update(str(temperature).encode("utf-8"))
    h.update(str(max_tokens).encode("utf-8"))
    h.update(model.encode("utf-8"))
    return h.hexdigest()

def _normalize_base(url: str) -> str:
    return url.rstrip("/")

def _is_chat_url(url: str) -> bool:
    return "/v1/chat/completions" in url

def _build_chat_url(base_or_chat: str) -> str:
    u = _normalize_base(base_or_chat)
    if _is_chat_url(u):
        return u
    if u.endswith("/v1"):
        return f"{u}/chat/completions"
    return f"{u}/v1/chat/completions"

def _get_redis_str(key: str) -> Optional[str]:
    val = redis_client.get(key)
    if not val:
        return None
    try:
        return val.decode()
    except Exception:
        return str(val)

def get_endpoints() -> List[str]:
    redis_tunnel = _get_redis_str("gpu_tunnel_endpoint")
    redis_direct = _get_redis_str("gpu_active_endpoint")
    env_tunnel = ENV_TUNNEL_ENDPOINT
    env_direct = ENV_LLM_ENDPOINT

    tunnel = redis_tunnel or env_tunnel
    direct = redis_direct or env_direct

    out: List[str] = []
    if tunnel:
        out.append(_build_chat_url(tunnel))
    if direct:
        u = _build_chat_url(direct)
        if u not in out:
            out.append(u)
    return out

# --- Endpoints -----------------------------------------------------------

@app.get("/healthz")
def healthz():
    eps = get_endpoints()
    return {
        "ok": True,
        "model": LLM_MODEL,
        "endpoints_to_try": eps,
        "redis": {
            "gpu_tunnel_endpoint": _get_redis_str("gpu_tunnel_endpoint"),
            "gpu_active_endpoint": _get_redis_str("gpu_active_endpoint"),
        }
    }

@app.post("/generate")
async def generate(request: Request, force: Optional[str] = None):
    data = await request.json()
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return {"error": "Prompt mancante."}

    if force not in (None, "tunnel", "direct"):
        return {"error": "Parametro 'force' non valido. Usa 'tunnel' o 'direct'."}

    system_from_body = (data.get("system") or "").strip()
    if system_from_body:
        system_prompt = system_from_body
    else:
        try:
            system_prompt = await get_persona("global", "default")
        except Exception:
            system_prompt = "Sei una GPT neutra e modulare."

    temperature = float(data.get("temperature", TEMPERATURE))
    max_tokens  = int(data.get("max_tokens", MAX_TOKENS))
    model_name  = (data.get("model") or LLM_MODEL).strip()

    cache_key = "cache:" + hash_prompt(prompt, system_prompt, temperature, max_tokens, model_name)
    cached = redis_client.get(cache_key)
    if cached:
        try:
            return {"cached": True, "response": json.loads(cached)}
        except Exception:
            return {"cached": True, "response": cached.decode()}

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    endpoints = get_endpoints()
    if force == "tunnel":
        endpoints = [e for e in endpoints if "trycloudflare.com" in e] + \
                    [e for e in endpoints if "trycloudflare.com" not in e]
    elif force == "direct":
        endpoints = [e for e in endpoints if "trycloudflare.com" not in e] + \
                    [e for e in endpoints if "trycloudflare.com" in e]

    last_err = None
    for url in endpoints:
        try:
            r = requests.post(url, json=payload, timeout=30)
            r.raise_for_status()
            result = r.json()
            redis_client.setex(cache_key, 86400, json.dumps(result))
            return {"cached": False, "endpoint_used": url, "response": result}
        except Exception as e:
            last_err = str(e)

    return {"error": "Nessun endpoint raggiungibile.", "last_error": last_err, "endpoints_tried": endpoints}

@app.post("/update_gpu")
async def update_gpu(request: Request):
    data = await request.json()
    llm_endpoint = (data.get("llm_endpoint") or "").strip()
    tunnel_endpoint = (data.get("tunnel_endpoint") or "").strip()
    model = (data.get("model") or LLM_MODEL).strip()

    if not llm_endpoint and not tunnel_endpoint:
        return {"error": "Dati mancanti: serve almeno llm_endpoint o tunnel_endpoint."}

    saved: Dict[str, str] = {}

    if llm_endpoint:
        ce = _build_chat_url(llm_endpoint)
        redis_client.set("gpu_active_endpoint", ce)
        saved["gpu_active_endpoint"] = ce

    if tunnel_endpoint:
        te = _build_chat_url(tunnel_endpoint)
        redis_client.set("gpu_tunnel_endpoint", te)
        saved["gpu_tunnel_endpoint"] = te

    if model:
        redis_client.set("gpu_active_model", model)
        saved["gpu_active_model"] = model

    print(f"GPU aggiornata: {json.dumps(saved)}")
    return {"status": "success", **saved}

# --- NUOVI ENDPOINT per bot/GUI --------------------------------------------

@app.post("/chat")
async def chat(payload: dict = Body(...)):
    src = payload.get("source", "tg")
    sid = str(payload.get("source_id"))
    text = (payload.get("text") or "").strip()
    if not sid or not text:
        return {"error": "source_id o text mancanti"}
    persona = await get_persona(src, sid)
    reply = await reply_with_llm(text, persona)
    return {"reply": reply}

@app.post("/persona/set")
async def persona_set(payload: dict = Body(...)):
    src = payload.get("source", "tg")
    sid = str(payload.get("source_id"))
    text = (payload.get("text") or "").strip()
    if not sid or not text:
        return {"error": "source_id o text mancanti"}
    await set_persona(src, sid, text)
    return {"ok": True}

@app.post("/persona/get")
async def persona_get(payload: dict = Body(...)):
    src = payload.get("source", "tg")
    sid = str(payload.get("source_id"))
    if not sid:
        return {"error": "source_id mancante"}
    p = await get_persona(src, sid)
    return {"persona": p}

@app.post("/persona/reset")
async def persona_reset(payload: dict = Body(...)):
    src = payload.get("source", "tg")
    sid = str(payload.get("source_id"))
    if not sid:
        return {"error": "source_id mancante"}
    await reset_persona(src, sid)
    return {"ok": True}

@app.post("/web/summarize")
async def web_summarize(payload: dict = Body(...)):
    url = (payload.get("url") or "").strip()
    src = payload.get("source", "tg")
    sid = str(payload.get("source_id"))
    if not url or not sid:
        return {"error": "url o source_id mancanti"}

    persona = await get_persona(src, sid)
    text, og_img = await fetch_and_extract(url)

    prompt = (
        "Riassumi la pagina in punti chiave, evidenzia dati, "
        "e proponi eventuali prossimi passi. Stile conciso.\n\n"
        f"URL: {url}\n\nTESTO:\n{text[:120000]}"
    )
    summary = await reply_with_llm(prompt, persona)
    return {"summary": summary, "og_image": og_img}

# ------------------ OPEN WEB SEARCH (nessuna censura, solo re-ranking) ------------------

def _domain(u: str) -> str:
    try:
        h = urlparse(u).hostname or ""
        parts = h.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else h
    except Exception:
        return ""

def _rerank_open(results: List[Dict[str, str]], prefer_domains: List[str]) -> List[Dict[str, str]]:
    pref = set(prefer_domains or [])
    scored: List[Dict[str, str]] = []
    for i, r in enumerate(results):
        base = 1.0 / (i + 1.0)
        boost = 2.0 if _domain(r.get("url", "")) in pref else 1.0
        r2 = dict(r)
        r2["_score"] = base * boost
        scored.append(r2)
    scored.sort(key=lambda x: x["_score"], reverse=True)
    return scored

@app.post("/web/search")
async def web_search(payload: dict = Body(...)):
    """
    payload: { q, source, source_id, k?: int, summarize_top?: int }

    OPEN mode:
      - nessuna blacklist, nessuna esclusione con -site:
      - preferenze di dominio solo come boost (re-ranking)
    """
    q    = (payload.get("q") or "").strip()
    src  = payload.get("source", "tg")
    sid  = str(payload.get("source_id"))
    k    = int(payload.get("k", 8))
    nsum = int(payload.get("summarize_top", 3))
    if not q or not sid:
        return {"error": "q o source_id mancanti"}

    pol = pick_domains(q)
    variants = build_query_variants(q, pol)

    try:
        from core.web_search import search as web_search_core
    except Exception:
        web_search_core = None

    if web_search_core is None:
        return {
            "error": "Backend web_search non configurato (core/web_search.py).",
            "hint": "Crea core/web_search.py con def search(query:str, num:int)->List[Dict[url,title]]."
        }

    raw: List[Dict[str, str]] = []
    for v in variants:
        try:
            raw.extend(web_search_core(v, num=6))
        except Exception:
            pass

    seen = set()
    dedup: List[Dict[str, str]] = []
    for r in raw:
        u = r.get("url")
        if not u or u in seen:
            continue
        dedup.append({"url": u, "title": r.get("title", "")})
        seen.add(u)

    if not dedup:
        return {"query": q, "policy_used": pol, "results": [], "summary": "", "note": "Nessun risultato dalla SERP."}

    ranked = _rerank_open(dedup, pol.get("prefer", []))
    topk = ranked[:max(1, k)]

    extracts = []
    for r in topk[:max(0, nsum)]:
        try:
            text, _img = await fetch_and_extract(r["url"])
            if text:
                extracts.append({"url": r["url"], "title": r["title"], "text": text[:8000]})
        except Exception:
            pass

    summary = ""
    if extracts:
        persona = await get_persona(src, sid)
        ctx = "\n\n".join([f"### {e['title']}\nURL: {e['url']}\n\n{e['text']}" for e in extracts])
        prompt = (
            "Leggi gli estratti qui sotto e rispondi alla query dell'utente:\n"
            f"QUERY: {q}\n\n"
            "Richiedi fonti con URL in fondo. Stile conciso e analitico.\n\n"
            f"{ctx}"
        )
        summary = await reply_with_llm(prompt, persona)

    return {
        "query": q,
        "policy_used": pol,
        "results": [{"url": r["url"], "title": r["title"]} for r in topk],
        "summary": summary
    }
PY
