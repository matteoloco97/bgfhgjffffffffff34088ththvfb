#!/usr/bin/env python3
# backend/quantum_api.py — Smart routing (OpenAI-like), NO hardcoded weather
# - WEB_SEARCH non ricade più su DIRECT_LLM: usa fallback sicuro con fonti
# - Firma build esposta in /healthz per verifiche rapide
# - Prompt di sintesi “safe” in italiano (no numeri inventati)
# - Post-boost dei domini preferiti dopo il reranking ML

from fastapi import FastAPI, Request, Body
import requests, os, json, time, hashlib, redis, logging
from typing import Optional, List, Dict, Tuple
from dotenv import load_dotenv
from urllib.parse import urlparse

from core.persona_store import get_persona, set_persona, reset_persona
from core.web_tools import fetch_and_extract
from core.chat_engine import reply_with_llm

# Smart intent
from core.smart_intent_classifier import SmartIntentClassifier
try:
    from core.intent_feedback import IntentFeedbackSystem
except Exception:
    class IntentFeedbackSystem:
        def record_feedback(self, **kwargs): pass

# search helpers
from core.source_policy import pick_domains
from core.web_querybuilder import build_query_variants
from core.reranker import Reranker

BUILD_SIGNATURE = "smart-intent-2025-11-05-hardsafetynet"

load_dotenv()
app = FastAPI()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ============================= ENV ===================================

ENV_LLM_ENDPOINT    = os.getenv("LLM_ENDPOINT")
ENV_TUNNEL_ENDPOINT = os.getenv("TUNNEL_ENDPOINT")
LLM_MODEL           = os.getenv("LLM_MODEL","qwen2.5-32b-awq")
TEMPERATURE         = float(os.getenv("LLM_TEMPERATURE",0.7))
MAX_TOKENS          = int(os.getenv("LLM_MAX_TOKENS",1024))

REDIS_HOST = os.getenv("REDIS_HOST","localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT","6379"))
REDIS_DB   = int(os.getenv("REDIS_DB","0"))
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)

USE_RERANKER    = os.getenv("USE_RERANKER","1") == "1"
RERANKER_MODEL  = os.getenv("RERANKER_MODEL","BAAI/bge-reranker-base")
RERANKER_DEVICE = os.getenv("RERANKER_DEVICE","cpu")

_SMART_INTENT = SmartIntentClassifier()
_INTENT_FB    = IntentFeedbackSystem()
_reranker: Optional[Reranker] = None

# =========================== Helpers =================================

def get_reranker()->Optional[Reranker]:
    global _reranker
    if not USE_RERANKER: return None
    if _reranker is None:
        try:
            log.info(f"Init Reranker: {RERANKER_MODEL} on {RERANKER_DEVICE}")
            _reranker = Reranker(model=RERANKER_MODEL, device=RERANKER_DEVICE)
        except Exception as e:
            log.error(f"Reranker init failed: {e}")
            return None
    return _reranker

def _normalize_base(u:str)->str: return u.rstrip("/")
def _is_chat_url(u:str)->bool:   return "/v1/chat/completions" in u
def _build_chat_url(base_or_chat:str)->str:
    u = _normalize_base(base_or_chat)
    if _is_chat_url(u): return u
    if u.endswith("/v1"): return f"{u}/chat/completions"
    return f"{u}/v1/chat/completions"

def _get_redis_str(k:str)->Optional[str]:
    v = redis_client.get(k)
    return v.decode() if v else None

def get_endpoints()->List[str]:
    tunnel = _get_redis_str("gpu_tunnel_endpoint") or ENV_TUNNEL_ENDPOINT
    direct = _get_redis_str("gpu_active_endpoint") or ENV_LLM_ENDPOINT
    out=[]
    if tunnel: out.append(_build_chat_url(tunnel))
    if direct:
        u=_build_chat_url(direct)
        if u not in out: out.append(u)
    return out

def hash_prompt(prompt:str, system:str, temperature:float, max_tokens:int, model:str)->str:
    h=hashlib.sha256()
    for piece in (prompt.strip().lower(), system.strip().lower(), str(temperature), str(max_tokens), model):
        h.update(piece.encode("utf-8"))
    return h.hexdigest()

def _wrap(text:str, model:str)->Dict:
    now=int(time.time())
    return {
        "id":f"chatcmpl-router-{now}",
        "object":"chat.completion",
        "created":now,
        "model":model,
        "choices":[{"index":0,"message":{"role":"assistant","content":text},"finish_reason":"stop"}],
        "usage":{"prompt_tokens":0,"completion_tokens":0,"total_tokens":0}
    }

def _run_direct(payload:Dict, force:Optional[str])->Tuple[Optional[Dict],Optional[str],Optional[str]]:
    endpoints=get_endpoints()
    if force=="tunnel":
        endpoints=[e for e in endpoints if "trycloudflare.com" in e]+[e for e in endpoints if "trycloudflare.com" not in e]
    elif force=="direct":
        endpoints=[e for e in endpoints if "trycloudflare.com" not in e]+[e for e in endpoints if "trycloudflare.com" in e]
    last=None
    for url in endpoints:
        try:
            r=requests.post(url,json=payload,timeout=30); r.raise_for_status()
            return r.json(), url, None
        except Exception as e:
            last=str(e)
    return None, None, last

def _domain(u:str)->str:
    try:
        h=urlparse(u).hostname or ""
        parts=h.split("."); return ".".join(parts[-2:]) if len(parts)>=2 else h
    except Exception:
        return ""

def _boost(results:List[Dict], prefer:List[str])->List[Dict]:
    """Fallback semplice se il reranker ML non è disponibile."""
    pref=set(prefer or [])
    scored=[]
    for i,r in enumerate(results):
        base=1.0/(i+1.0); boost=2.0 if _domain(r.get("url","")) in pref else 1.0
        rr=dict(r); rr["_score"]=base*boost; scored.append(rr)
    scored.sort(key=lambda x:x["_score"], reverse=True)
    return scored

def _postboost_ranked(ranked: List[Dict], prefer: List[str]) -> List[Dict]:
    """Nudge finale: incrementa leggermente il punteggio dei domini preferiti e riordina."""
    pref = set(prefer or [])
    for r in ranked:
        dom = _domain(r.get("url",""))
        if dom in pref:
            r["rerank_score"] = (r.get("rerank_score") or 0.0) + 0.20
    return sorted(
        ranked,
        key=lambda x: ((x.get("rerank_score") or 0.0), (x.get("_score") or 0.0)),
        reverse=True
    )

def _safe_fallback_links(q: str) -> List[Dict]:
    """Fallback sicuro quando la SERP è vuota: link affidabili per dati live."""
    s = (q or "").lower()
    out: List[Dict] = []
    def add(u,t): out.append({"url":u,"title":t})
    # Meteo
    if "meteo" in s or "che tempo" in s or "weather" in s:
        add("https://www.meteoam.it/it/roma", "Meteo Aeronautica Militare – Roma")
        add("https://www.ilmeteo.it/meteo/Roma", "ILMETEO – Roma")
        add("https://www.3bmeteo.com/meteo/roma", "3B Meteo – Roma")
    # Prezzi/crypto/forex/borse
    if any(k in s for k in ["prezzo","quotazione","quanto vale","btc","bitcoin","eth","ethereum","eurusd","eur/usd","borsa","azioni","indice","cambio"]):
        add("https://coinmarketcap.com/currencies/bitcoin/","Bitcoin (BTC) – CoinMarketCap")
        add("https://www.coindesk.com/price/bitcoin/","Bitcoin Price – CoinDesk")
        add("https://www.binance.com/en/trade/BTC_USDT","BTC/USDT – Binance")
        add("https://www.investing.com/crypto/bitcoin/btc-usd","BTC/USD – Investing.com")
    # Generico
    if not out:
        add("https://www.ansa.it/","ANSA – Ultime notizie")
        add("https://it.wikipedia.org/wiki/Pagina_principale","Wikipedia (IT)")
    return out[:8]

# ===================== Web search pipeline ===========================

async def _web_search_pipeline(q:str, src:str, sid:str, k:int, nsum:int)->Dict:
    pol = pick_domains(q)
    variants = build_query_variants(q, pol)

    try:
        from core.web_search import search as web_search_core
    except Exception as e:
        return {"error":"Backend web_search non configurato (core/web_search.py).","_exception":str(e)}

    raw=[]
    for v in variants:
        try: raw.extend(web_search_core(v, num=6))
        except Exception: pass

    # dedup
    seen=set(); dedup=[]
    for r in raw:
        u=r.get("url")
        if not u or u in seen: continue
        dedup.append({"url":u,"title":r.get("title",""),"snippet":r.get("snippet", r.get("title",""))}); seen.add(u)

    if not dedup:
        return {"query":q,"policy_used":pol,"results":[],"summary":"",
                "note":"SERP vuota","reranker_used":False,
                "stats":{"raw_results":len(raw),"dedup_results":0,"returned":0}}

    reranker=get_reranker()
    if reranker:
        try:
            ranked=reranker.rerank(query=q, results=dedup, top_k=k); used=True
        except Exception:
            ranked=_boost(dedup, pol.get("prefer",[])); used=False
    else:
        ranked=_boost(dedup, pol.get("prefer",[])); used=False

    # Post-boost dei domini preferiti
    ranked = _postboost_ranked(ranked, pol.get("prefer", []))
    topk=ranked[:max(1,k)]

    # Estratti per sintesi
    extracts=[]
    for r in topk[:max(0,nsum)]:
        try:
            text,_=await fetch_and_extract(r["url"])
            if text: extracts.append({"url":r["url"],"title":r["title"],"text":text[:8000]})
        except Exception: pass

    # Prompt “safe” in ITA
    summary=""
    if extracts:
        persona=await get_persona(src, sid)
        ctx="\n\n".join([f"### {e['title']}\nURL: {e['url']}\n\n{e['text']}" for e in extracts])
        prompt=(
            "Leggi gli estratti qui sotto e rispondi alla query.\n"
            f"QUERY: {q}\n\n"
            "Regole importanti:\n"
            "- Rispondi in ITALIANO.\n"
            "- NON inventare numeri (temperature, prezzi, ecc.). Riporta valori solo se presenti nei testi estratti e con unità.\n"
            "- Se i valori sono discordanti o mancanti, NON stimare: scrivi «Apri le fonti per il dato in tempo reale».\n"
            "- Usa stile conciso e analitico.\n"
            "- Chiudi con un elenco «Fonti» (URL in chiaro).\n\n"
            f"{ctx}"
        )
        try:
            summary=await reply_with_llm(prompt, persona)
        except Exception:
            summary=""

    return {
        "query":q,
        "policy_used":pol,
        "results":[{"url":r["url"],"title":r["title"],"rerank_score":r.get("rerank_score"),"_score":r.get("_score")} for r in topk],
        "summary":summary,
        "reranker_used": used,
        "stats":{"raw_results":len(raw),"dedup_results":len(dedup),"returned":len(topk)}
    }

# ========================= API Endpoints =============================

@app.get("/healthz")
def healthz():
    rer_status="disabled"
    if USE_RERANKER:
        rer_status="ready" if get_reranker() else "failed"
    return {
        "ok": True,
        "model": LLM_MODEL,
        "endpoints_to_try": get_endpoints(),
        "reranker": {"enabled": USE_RERANKER, "status": rer_status, "model": RERANKER_MODEL if USE_RERANKER else None},
        "redis": {"gpu_tunnel_endpoint": _get_redis_str("gpu_tunnel_endpoint"), "gpu_active_endpoint": _get_redis_str("gpu_active_endpoint")},
        "smart_intent": True,
        "router_build": BUILD_SIGNATURE
    }

@app.post("/generate")
async def generate(request: Request, force: Optional[str] = None):
    data = await request.json()
    prompt = (data.get("prompt") or "").strip()
    if not prompt: return {"error":"Prompt mancante."}
    if force not in (None,"tunnel","direct"): return {"error":"Parametro 'force' non valido. Usa 'tunnel' o 'direct'."}

    try:
        system_prompt = (data.get("system") or await get_persona("global","default") or "Sei una GPT neutra e modulare.").strip()
    except Exception:
        system_prompt = "Sei una GPT neutra e modulare."
    temperature=float(data.get("temperature",TEMPERATURE))
    max_tokens=int(data.get("max_tokens",MAX_TOKENS))
    model_name=(data.get("model") or LLM_MODEL).strip()

    route = _SMART_INTENT.classify(prompt)
    used_intent = (route.get("intent") or "DIRECT_LLM").upper()

    cache_key = "cache:"+hash_prompt(prompt, system_prompt, temperature, max_tokens, model_name)+f":{used_intent}"
    cached = redis_client.get(cache_key)
    if cached:
        try: return json.loads(cached)
        except Exception: pass

    out = {"ok": True, "intent": used_intent, "confidence": route.get("confidence"), "reason": route.get("reason"), "router_build": BUILD_SIGNATURE}
    t0 = time.perf_counter()

    try:
        # ---------------------- WEB_READ ----------------------
        if used_intent=="WEB_READ":
            url = route.get("url")
            if url:
                text,_=await fetch_and_extract(url)
                persona = system_prompt
                msg = ("Riassumi in punti chiave e proponi next steps:\n"
                       f"URL: {url}\n\nTESTO:\n{(text or '')[:8000]}")
                summary = await reply_with_llm(msg, persona)
                out.update({"cached":False, "response":_wrap(summary, model_name), "source_url": url})
                _INTENT_FB.record_feedback(query=prompt, intent_used="WEB_READ", satisfaction=1.0, response_time_s=time.perf_counter()-t0)
                redis_client.setex(cache_key, 86400, json.dumps(out))
                return out
            else:
                # se manca url torniamo a DIRECT_LLM
                used_intent="DIRECT_LLM"
                out["intent"]=used_intent
                out["reason"]=(out.get("reason") or "")+"|url_missing_fallback"

        # --------------------- WEB_SEARCH ---------------------
        # (mai più fallback a DIRECT_LLM: usa safe fallback links)
        if used_intent=="WEB_SEARCH":
            ws = await _web_search_pipeline(q=prompt, src="global", sid="default",
                                            k=int(data.get("k",8)), nsum=int(data.get("summarize_top",3)))
            results = ws.get("results") or []
            summary = ws.get("summary","").strip()

            if not results:
                # Fallback sicuro: restituiamo fonti affidabili e un riepilogo neutro
                results = _safe_fallback_links(prompt)
                summary = summary or ("Per informazioni aggiornate è necessario consultare fonti live. "
                                      "Di seguito alcuni link affidabili. Apri i link per i dati correnti.")
                ws = {
                    "results": results,
                    "reranker_used": False,
                    "stats": {"raw_results": 0, "dedup_results": len(results), "returned": len(results)}
                }

            out.update({
                "cached": False,
                "response": _wrap(summary, model_name),
                "web": {
                    "results": results,
                    "reranker_used": ws.get("reranker_used", False),
                    "stats": ws.get("stats", {})
                }
            })
            _INTENT_FB.record_feedback(query=prompt, intent_used="WEB_SEARCH", satisfaction=1.0, response_time_s=time.perf_counter()-t0)
            redis_client.setex(cache_key, 86400, json.dumps(out))
            return out

        # --------------------- DIRECT_LLM ---------------------
        payload={"model":model_name,"messages":[
            {"role":"system","content":system_prompt},
            {"role":"user","content":prompt}],
            "temperature":temperature, "max_tokens":max_tokens}
        result, endpoint_used, last_err = _run_direct(payload, force)
        if not result:
            fail={"ok":False,"error":"Nessun endpoint raggiungibile.","last_error":last_err,"endpoints_tried":get_endpoints(),
                  "intent":used_intent,"confidence":route.get("confidence"),"reason":route.get("reason"),"router_build":BUILD_SIGNATURE}
            redis_client.setex(cache_key, 300, json.dumps(fail))
            return fail

        out.update({"cached":False,"endpoint_used":endpoint_used,"response":result})
        _INTENT_FB.record_feedback(query=prompt, intent_used="DIRECT_LLM", satisfaction=1.0, response_time_s=time.perf_counter()-t0)
        redis_client.setex(cache_key, 86400, json.dumps(out))
        return out

    except Exception as e:
        err={"ok":False,"error":f"{type(e).__name__}: {e}","intent":used_intent,"confidence":route.get("confidence"),
             "reason":route.get("reason"),"router_build":BUILD_SIGNATURE}
        redis_client.setex(cache_key, 600, json.dumps(err))
        return err

# ============== Persona & Web utils (come prima) =====================

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
        f"URL: {url}\n\nTESTO:\n{(text or '')[:120000]}"
    )
    summary = await reply_with_llm(prompt, persona)
    return {"summary": summary, "og_image": og_img}

@app.post("/web/search")
async def web_search(payload: dict = Body(...)):
    q    = (payload.get("q") or "").strip()
    src  = payload.get("source", "tg")
    sid  = str(payload.get("source_id"))
    k    = int(payload.get("k", 8))
    nsum = int(payload.get("summarize_top", 3))
    if not q or not sid:
        return {"error": "q o source_id mancanti"}
    ws = await _web_search_pipeline(q=q, src=src, sid=sid, k=k, nsum=nsum)
    if not ws.get("results"):
        # anche dall'endpoint pubblico, garantiamo un output utile
        ws["results"] = _safe_fallback_links(q)
        ws["summary"] = ws.get("summary") or "Ecco alcune fonti affidabili per consultare dati aggiornati."
        ws["reranker_used"] = ws.get("reranker_used", False)
        ws["stats"] = ws.get("stats", {"raw_results": 0, "dedup_results": len(ws['results']), "returned": len(ws['results'])})
    return ws
