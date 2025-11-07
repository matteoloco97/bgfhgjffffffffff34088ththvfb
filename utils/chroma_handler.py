# utils/chroma_handler.py
# ChromaDB handler robusto:
# - embedding_function SEMPRE attaccata su get_collection
# - ensure_collections() compatibile
# - reembed_collection(): compat con client diversi (fallback senza include/offset)
# - search_topk(): ranking ibrido + fallback substring se manca l'embed
# - debug_dump(): stampa stato collezioni/contatori
# - PATCH: rimosso "ids" dagli include di get()/query() (non supportato)
# - PATCH: add_bet() mostra team nel documento se presente nei metadati

import os
import time
import math
from typing import Dict, List, Tuple, Any, Optional

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

# === ENV / costanti ===
PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "/memory/chroma")
FACTS = os.getenv("CHROMA_COLLECTION_FACTS", "facts")
PREFS = os.getenv("CHROMA_COLLECTION_PREFS", "prefs")
BETS  = os.getenv("CHROMA_COLLECTION_BETS", "betting_history")

EMBED_MODEL = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")

W_SIM   = float(os.getenv("MEM_WEIGHT_SIM", 0.7))   # similarità semantica
W_TIME  = float(os.getenv("MEM_WEIGHT_TIME", 0.2))  # recency
W_SRC   = float(os.getenv("MEM_WEIGHT_SRC", 0.1))   # prior fonte
HALF_LIFE_D = float(os.getenv("MEM_HALF_LIFE_D", 7))

SOURCE_PRIOR: Dict[str, float] = {
    "system": 1.00,
    "admin":  0.98,
    "user":   0.95,
    "web":    0.92,
    "model":  0.85,
    "bet":    0.90,
}

# ---------------------------------------------------------------------
# Client & Embedding
# ---------------------------------------------------------------------

def _embedder():
    return embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)

def get_client():
    # telemetry off per ambienti chiusi
    return chromadb.Client(Settings(persist_directory=PERSIST_DIR, anonymized_telemetry=False))

def _get_or_create_with_embed(name: str, metadata: Optional[Dict[str, Any]] = None):
    client = get_client()
    try:
        return client.get_collection(name=name, embedding_function=_embedder())
    except Exception:
        return client.create_collection(
            name=name, metadata=metadata or {}, embedding_function=_embedder()
        )

def _col(name: str):
    # IMPORTANT: sempre embedding_function su get_collection
    return get_client().get_collection(name=name, embedding_function=_embedder())

# ---------------------------------------------------------------------
# Setup Collections
# ---------------------------------------------------------------------

def ensure_collections() -> bool:
    _get_or_create_with_embed(FACTS, {"schema": "type=fact;fields=subject,value,source,ts"})
    _get_or_create_with_embed(PREFS, {"schema": "type=pref;fields=key,value,scope,ts"})
    _get_or_create_with_embed(BETS,  {"schema": "type=bet;fields=event,market,odds,stake,result,ts"})
    return True

# ---------------------------------------------------------------------
# Insert / Upsert
# ---------------------------------------------------------------------

def add_fact(subject: str, value: str, source: str = "system", metadata: Dict[str, Any] | None = None) -> str:
    col = _col(FACTS)
    _id = f"fact:{int(time.time() * 1000)}"
    md = {"subject": subject, "value": value, "source": source, "ts": int(time.time())}
    if metadata: md.update(metadata)
    col.add(ids=[_id], documents=[f"{subject} = {value}"], metadatas=[md])
    return _id

def add_pref(key: str, value: str, scope: str = "global", source: str = "user",
             metadata: Dict[str, Any] | None = None) -> str:
    col = _col(PREFS)
    _id = f"pref:{int(time.time() * 1000)}"
    md = {"key": key, "value": value, "scope": scope, "source": source, "ts": int(time.time())}
    if metadata: md.update(metadata)
    col.add(ids=[_id], documents=[f"{key}={value} (scope:{scope})"], metadatas=[md])
    return _id

def add_bet(event: str, market: str, odds: float, stake: float, result: str | None = None,
            source: str = "bet", metadata: Dict[str, Any] | None = None) -> str:
    col = _col(BETS)
    _id = f"bet:{int(time.time() * 1000)}"
    md = {"event": event, "market": market, "odds": odds, "stake": stake,
          "result": result or "open", "source": source, "ts": int(time.time())}
    if metadata: md.update(metadata)
    # PATCH: mostra team nel documento se presente
    team_part = f" | team={md.get('team')}" if md.get("team") else ""
    doc = f"{event} | {market} | odds={odds} | stake={stake} | result={md['result']}{team_part}"
    col.add(ids=[_id], documents=[doc], metadatas=[md])
    return _id

# ---------------------------------------------------------------------
# Retrieval helpers
# ---------------------------------------------------------------------

def _recency_score(ts: int, now: Optional[int] = None, half_life_days: float = HALF_LIFE_D) -> float:
    if not ts: return 0.0
    now = now or int(time.time())
    age_days = max(0.0, (now - ts) / 86400.0)
    return math.exp(-math.log(2) * (age_days / max(1e-9, half_life_days)))

def _src_prior(source: str) -> float:
    return SOURCE_PRIOR.get(source or "", 0.9)

def _to_similarity(dist: float) -> float:
    # Chroma cosine: 0=identico, 1=lontano → sim=1-dist
    return max(0.0, 1.0 - float(dist))

def _rank(items: List[Dict[str, Any]], k: int,
          w_sim: float = W_SIM, w_time: float = W_TIME, w_src: float = W_SRC,
          half_life_days: float = HALF_LIFE_D) -> List[Dict[str, Any]]:
    ranked = []
    for it in items:
        md = it.get("metadata", {}) or {}
        sim = float(it.get("similarity", 0.0))
        rec = _recency_score(int(md.get("ts") or 0), half_life_days=half_life_days)
        src = _src_prior(str(md.get("source") or ""))
        score = w_sim * sim + w_time * rec + w_src * src
        it["score"] = round(score, 6)
        it["sim"] = round(sim, 6)
        it["recency"] = round(rec, 6)
        it["src_prior"] = round(src, 3)
        ranked.append(it)
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:k]

# --- Fallback substring search (se non ci sono embedding/query fallisce)
def _substring_fallback(name: str, query: str, limit: int = 128) -> List[Dict[str, Any]]:
    col = _col(name)
    out: List[Dict[str, Any]] = []
    q = (query or "").lower()
    # tentiamo get() con include/offset/limit, SENZA "ids"
    try:
        data = col.get(include=["documents", "metadatas"], limit=limit, offset=0)
    except Exception:
        # versioni che non supportano include/offset/limit → full get
        data = col.get()
    ids  = data.get("ids") or []
    docs = data.get("documents") or []
    metas= data.get("metadatas") or []
    for i, _id in enumerate(ids):
        doc = (docs[i] or "")
        md  = (metas[i] or {})
        if q in str(doc).lower():
            out.append({
                "id": _id,
                "document": doc,
                "metadata": md,
                "distance": 1.0,          # peggiore (non abbiamo embedding)
                "similarity": 0.0,         # sim 0 → verrà tenuta in ranking via recency/src
                "collection": name
            })
    return out

def _query_collection(name: str, query: str, n: int) -> List[Dict[str, Any]]:
    col = _col(name)
    try:
        res = col.query(
            query_texts=[query],
            n_results=n,
            include=["documents", "metadatas", "distances"]  # ← niente "ids"
        )
        out: List[Dict[str, Any]] = []
        if not res or not res.get("ids"):
            return out
        for i in range(len(res["ids"][0])):
            dist = float(res["distances"][0][i])
            out.append({
                "id": res["ids"][0][i],
                "document": (res["documents"][0][i] if res.get("documents") else None),
                "metadata": (res["metadatas"][0][i] if res.get("metadatas") else None),
                "distance": dist,
                "similarity": _to_similarity(dist),
                "collection": name
            })
        return out
    except Exception:
        # Se query fallisce (mancano embedding, ecc.) → fallback substring match
        return _substring_fallback(name, query, limit=max(128, n*10))

def search_topk(query: str, k: int = 5, expand: Optional[int] = None,
                w_sim: float = W_SIM, w_time: float = W_TIME, w_src: float = W_SRC,
                half_life_days: float = HALF_LIFE_D,
                collections: Tuple[str, ...] = (FACTS, PREFS, BETS)) -> List[Dict[str, Any]]:
    expand = expand or (k * 3)
    pool: List[Dict[str, Any]] = []
    for c in collections:
        try:
            pool.extend(_query_collection(c, query, n=expand))
        except Exception:
            pass
    return _rank(pool, k=k, w_sim=w_sim, w_time=w_time, w_src=w_src, half_life_days=half_life_days)

# ---------------------------------------------------------------------
# Re-embed utilities
# ---------------------------------------------------------------------

def reembed_collection(name: str, batch: int = 512) -> int:
    """
    Rigenera gli embedding per TUTTI i record della collection (se presenti).
    Ritorna il numero processato. Compat con versioni senza include/offset.
    """
    col = _col(name)

    # 1) API recente: include/offset/limit (senza "ids" in include)
    try:
        total = 0
        offset = 0
        while True:
            data = col.get(include=["documents", "metadatas"], limit=batch, offset=offset)
            ids  = data.get("ids") or []
            if not ids:
                break
            docs = data.get("documents") or []
            metas= data.get("metadatas") or []
            col.update(ids=ids, documents=docs, metadatas=metas)
            offset += len(ids)
            total  += len(ids)
        return total
    except Exception:
        # 2) fallback: versioni che non supportano include/offset/limit
        try:
            data = col.get()
            ids  = data.get("ids") or []
            if not ids:
                return 0
            docs = data.get("documents") or []
            metas= data.get("metadatas") or []
            col.update(ids=ids, documents=docs, metadatas=metas)
            return len(ids)
        except Exception:
            return -1

def reembed_all(batch: int = 512) -> Dict[str, int]:
    out = {}
    for name in (FACTS, PREFS, BETS):
        try:
            out[name] = reembed_collection(name, batch=batch)
        except Exception:
            out[name] = -1
    return out

# ---------------------------------------------------------------------
# Debug helpers
# ---------------------------------------------------------------------

def debug_dump() -> Dict[str, Any]:
    """
    Ritorna info su client, path, collections e count stimato (peek).
    Utile per troubleshooting.
    """
    cli = get_client()
    cols = []
    try:
        listed = cli.list_collections()
    except Exception:
        listed = []
    for c in listed:
        try:
            col = _col(c.name)
            try:
                cnt = col.count()  # type: ignore[attr-defined]
            except Exception:
                data = col.get()
                cnt = len(data.get("ids") or [])
            cols.append({"name": c.name, "count": int(cnt)})
        except Exception:
            cols.append({"name": c.name, "count": -1})
    return {
        "persist_dir": PERSIST_DIR,
        "embed_model": EMBED_MODEL,
        "collections": cols
    }
