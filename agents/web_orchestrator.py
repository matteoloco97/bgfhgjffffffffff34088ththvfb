# web_orchestrator.py
import os, re, json, asyncio, logging
from typing import List, Dict, Any, Optional
import aiohttp
from fastapi import FastAPI, Body
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("orch-auto")

# === ENV ===
CORE_SEARCH_URL   = os.getenv("QUANTUM_WEB_SEARCH_URL",  "http://127.0.0.1:8081/web/search")
CORE_SUMMARY_URL  = os.getenv("QUANTUM_WEB_SUMMARY_URL", "http://127.0.0.1:8081/web/summarize")
LLM_GENERATE_URL  = os.getenv("QUANTUM_API_URL",         "http://127.0.0.1:8081/generate")

ORCH_WEB_ENABLED  = os.getenv("ORCH_WEB_ENABLED", "1") == "1"
ORCH_WEB_PAGES    = int(os.getenv("ORCH_WEB_PAGES", "3"))   # quante fonti leggere/sintetizzare
SEARCH_K          = int(os.getenv("ORCH_SEARCH_K",  "8"))   # quanti risultati chiedere alla SERP

HTTP_TIMEOUT      = aiohttp.ClientTimeout(total=50)
app = FastAPI(title="Auto Orchestrator")

# === MODELLI ===
class ChatIn(BaseModel):
    source: str = "tg"
    source_id: str
    text: str

class ChatOut(BaseModel):
    reply: str
    sources: Optional[List[Dict[str, str]]] = None
    used_web: bool = False

# === Utils ===
URL_RE = re.compile(r'(https?://[^\s]+)', re.I)

def extract_urls(text: str) -> List[str]:
    return URL_RE.findall(text or "")[:ORCH_WEB_PAGES]

def looks_like_fresh_info(text: str) -> bool:
    """Heuristics per capire se servono dati aggiornati o web."""
    t = text.lower()
    need_now = any(x in t for x in [
        "oggi", "adesso", "ora", "ultime", "ultimi", "in tempo reale", "meteo", "previsioni",
        "notizie", "news", "prezzo", "quote", "classifica", "partita", "risultati", "uscite", "rilascio",
        "aggiornamenti", "breaking"
    ])
    is_troubleshoot = any(x in t for x in [
        "errore", "502", "stacktrace", "how to fix", "solution", "soluzione", "nginx", "kubernetes"
    ])
    return need_now or is_troubleshoot

def diversify_by_domain(items: List[Dict[str, str]], take: int) -> List[Dict[str, str]]:
    seen = set()
    picked = []
    for it in items:
        url = it.get("url","")
        dom = re.sub(r'^https?://(www\.)?', '', url).split('/')[0]
        if dom and dom not in seen:
            seen.add(dom)
            picked.append(it)
        if len(picked) >= take:
            break
    # se non bastano, riempi
    if len(picked) < take:
        for it in items:
            if it not in picked:
                picked.append(it)
            if len(picked) >= take:
                break
    return picked[:take]

async def http_json(session: aiohttp.ClientSession, method: str, url: str, payload: Any) -> Any:
    async with session.request(method, url, json=payload) as r:
        txt = await r.text()
        if r.status != 200:
            raise RuntimeError(f"{method} {url} -> {r.status}: {txt[:400]}")
        try:
            return json.loads(txt)
        except Exception:
            return txt

async def core_search(session: aiohttp.ClientSession, q: str) -> Dict[str, Any]:
    payload = {"source": "orch", "source_id": "auto", "q": q, "k": SEARCH_K, "summarize_top": 0}
    return await http_json(session, "POST", CORE_SEARCH_URL, payload)

async def core_summary(session: aiohttp.ClientSession, url: str) -> str:
    payload = {"source": "orch", "source_id": "auto", "url": url}
    data = await http_json(session, "POST", CORE_SUMMARY_URL, payload)
    return (data.get("summary") or "").strip()

async def llm_generate(session: aiohttp.ClientSession, prompt: str) -> str:
    data = await http_json(session, "POST", LLM_GENERATE_URL, {"prompt": prompt})
    try:
        return data["response"]["choices"][0]["message"]["content"].strip()
    except Exception:
        return (json.dumps(data, ensure_ascii=False)[:4000])

def build_synthesis_prompt(query: str, docs: List[Dict[str, str]]) -> str:
    """
    docs: [{idx:int,title:str,url:str,content:str}]
    """
    header = (
        "Sei un assistente che risponde SOLO usando le fonti fornite.\n"
        "Cita in linea come [1], [2]… quando usi una fonte. Mantieni la risposta concisa e pratica.\n"
        "Se l'informazione non è presente nelle fonti, dillo chiaramente.\n\n"
        f"Domanda: {query}\n\n"
        "Fonti:\n"
    )
    chunks = []
    for d in docs:
        i = d["idx"]
        title = d["title"] or "(senza titolo)"
        chunks.append(f"[{i}] {title} — {d['url']}\n---\n{d['content']}\n")
    footer = "\nAlla fine aggiungi una sezione 'Fonti:' con la lista numerata [i] titolo – url."
    return header + "\n".join(chunks) + footer

async def browse_and_answer(session: aiohttp.ClientSession, query: str) -> ChatOut:
    # 1) search
    s = await core_search(session, query)
    results = s.get("results") or []
    if not results:
        # niente fonti: almeno restituisco i link trovati dall'engine (se any)
        note = s.get("note") or "Nessun risultato."
        return ChatOut(
            reply=f"Non ho trovato contenuti da sintetizzare. {note}\nProva a riformulare la query.",
            sources=[],
            used_web=True
        )
    picks = diversify_by_domain(results, ORCH_WEB_PAGES)

    # 2) read
    docs = []
    out_sources = []
    for i, it in enumerate(picks, 1):
        url = it.get("url","")
        title = (it.get("title") or "").strip()
        try:
            content = await core_summary(session, url)
            if content:
                docs.append({"idx": i, "title": title, "url": url, "content": content})
                out_sources.append({"idx": i, "title": title, "url": url})
        except Exception as e:
            log.warning("read fail %s: %s", url, e)

    if not docs:
        # cadi almeno sui link
        listing = "\n".join([f"{i}. {it.get('title','(senza titolo)')}\n{it.get('url','')}" for i,it in enumerate(picks,1)])
        return ChatOut(
            reply=f"🔎 Top risultati:\n{listing}",
            sources=[{"idx": i, "title": it.get("title",""), "url": it.get("url","")} for i,it in enumerate(picks,1)],
            used_web=True
        )

    # 3) synth
    prompt = build_synthesis_prompt(query, docs)
    text = await llm_generate(session, prompt)
    return ChatOut(reply=text, sources=out_sources, used_web=True)

# === API ===
@app.post("/orchestrate", response_model=ChatOut)
async def orchestrate(payload: ChatIn = Body(...)):
    """
    Punto unico: decide se usare web o rispondere diretto.
    """
    text = (payload.text or "").strip()
    urls = extract_urls(text)

    async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
        # Se nel testo ci sono URL → riassumi direttamente le pagine
        if urls:
            docs = []
            srcs = []
            for i, u in enumerate(urls[:ORCH_WEB_PAGES], 1):
                try:
                    content = await core_summary(session, u)
                    if content:
                        docs.append({"idx": i, "title": "", "url": u, "content": content})
                        srcs.append({"idx": i, "title": "", "url": u})
                except Exception as e:
                    log.warning("direct read fail %s: %s", u, e)
            if docs:
                prompt = build_synthesis_prompt(text, docs)
                reply = await llm_generate(session, prompt)
                return ChatOut(reply=reply, sources=srcs, used_web=True)
            # se la lettura fallisce, prova la ricerca con la frase completa
            if ORCH_WEB_ENABLED:
                return await browse_and_answer(session, text)
            # altrimenti cade sul LLM secco
        # Se serve contenuto “fresco” o troubleshooting → web
        if ORCH_WEB_ENABLED and looks_like_fresh_info(text):
            return await browse_and_answer(session, text)

        # Altrimenti risposta secca del modello (senza fonti)
        prompt = f"Rispondi alla seguente richiesta in modo pratico e conciso:\n\n{text}"
        reply = await llm_generate(session, prompt)
        return ChatOut(reply=reply, sources=None, used_web=False)
