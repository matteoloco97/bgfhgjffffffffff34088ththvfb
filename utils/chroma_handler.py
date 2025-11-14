# utils/chroma_handler.py
# ChromaDB handler robusto:
# - embedding_function SEMPRE attaccata su get_collection
# - ensure_collections() compatibile
# - reembed_collection(): compat con client diversi (fallback senza include/offset)
# - search_topk(): ranking ibrido + fallback substring se manca l'embed
# - debug_dump(): stampa stato collezioni/contatori
# - PATCH: rimosso "ids" dagli include di get()/query() (non supportato)
# - PATCH: add_bet() mostra team nel documento se presente nei metadati
# - ADVANCED: filtri where + batch insert + cleanup dry-run + migrazione
# - PATCH (2025-11-07): _col() ora auto-crea la collection se non esiste (get-or-create con metadata corretti)
# - FIX (2025-11-07): PersistentClient SENZA tenant/database (evita NotFoundError) + fallback legacy

import os
import time
import math
import logging
from typing import Dict, List, Tuple, Any, Optional

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

# === PersistentClient (se disponibile) ===
try:
    # chromadb>=0.5.x
    from chromadb import PersistentClient  # type: ignore
    _HAS_PERSISTENT = True
except Exception:
    _HAS_PERSISTENT = False

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

# Metadata schema predefiniti per auto-create
META_SCHEMAS: Dict[str, Dict[str, Any]] = {
    FACTS: {"schema": "type=fact;fields=subject,value,source,ts"},
    PREFS: {"schema": "type=pref;fields=key,value,scope,ts"},
    BETS:  {"schema": "type=bet;fields=event,market,odds,stake,result,ts"},
}

log = logging.getLogger("chroma_handler")

# ---------------------------------------------------------------------
# Client & Embedding
# ---------------------------------------------------------------------

def _embedder():
    return embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)

def get_client():
    """
    Usa PersistentClient con solo 'path' (nessun tenant/database) per evitare
    NotFoundError; se fallisce, fallback al client legacy.
    """
    if _HAS_PERSISTENT:
        try:
            return PersistentClient(
                path=PERSIST_DIR,
                settings=Settings(anonymized_telemetry=False),
            )
        except Exception as e:
            log.warning(f"PersistentClient failed, falling back to legacy Client: {e}")
    # Fallback legacy
    return chromadb.Client(Settings(
        persist_directory=PERSIST_DIR,
        anonymized_telemetry=False,
    ))

def _get_or_create_with_embed(name: str, metadata: Optional[Dict[str, Any]] = None):
    client = get_client()
    meta = metadata or META_SCHEMAS.get(name, {})
    # Usa get_or_create_collection quando disponibile
    if hasattr(client, "get_or_create_collection"):
        return client.get_or_create_collection(
            name=name, metadata=meta, embedding_function=_embedder()
        )
    # Fallback 2-step
    try:
        return client.get_collection(name=name, embedding_function=_embedder())
    except Exception:
        try:
            return client.create_collection(
                name=name, metadata=meta, embedding_function=_embedder()
            )
        except Exception:
            # Rare race: se esiste già, riprova get
            return client.get_collection(name=name, embedding_function=_embedder())

def _col(name: str):
    """
    Recupera la collection con embedding_function.
    Se non esiste, la crea con i metadata standard (get-or-create, idempotente).
    """
    client = get_client()
    meta = META_SCHEMAS.get(name, {})
    # Idempotente: preferisci get_or_create_collection se presente
    if hasattr(client, "get_or_create_collection"):
        return client.get_or_create_collection(name=name, metadata=meta, embedding_function=_embedder())
    # Fallback 2-step
    try:
        return client.get_collection(name=name, embedding_function=_embedder())
    except Exception as e:
        log.warning(f"Collection [{name}] missing, creating it: {e}")
        try:
            return client.create_collection(name=name, metadata=meta, embedding_function=_embedder())
        except Exception:
            # se un'altra istanza l'ha creata nel frattempo
            return client.get_collection(name=name, embedding_function=_embedder())

# ---------------------------------------------------------------------
# Setup Collections
# ---------------------------------------------------------------------

def ensure_collections() -> bool:
    _get_or_create_with_embed(FACTS, META_SCHEMAS.get(FACTS))
    _get_or_create_with_embed(PREFS, META_SCHEMAS.get(PREFS))
    _get_or_create_with_embed(BETS,  META_SCHEMAS.get(BETS))
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
    return _rank(pool, k=k, w_sim=w_sim, w_time=w_time, w_src=w_src, half_life_days=half_life_d)

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

# ============================================================================
# ADVANCED FEATURES (2025-11-07)
# - Filtri where con fallback
# - Batch insert con validazione e report
# - Cleanup con dry-run + safe-guards
# - Migrazione collection con progress e metriche
# Tutte le funzioni sono additive e non rompono la compatibilità.
# ============================================================================

def _query_collection_where(name: str, query: str, n: int, where: dict | None = None) -> List[Dict[str, Any]]:
    """
    Query semantica con filtri `where`. Se fallisce, restituisce [].
    """
    col = _col(name)
    try:
        res = col.query(
            query_texts=[query],
            n_results=int(n),
            where=where or {},
            include=["documents", "metadatas", "distances"]
        )
        out: List[Dict[str, Any]] = []
        if not res or not res.get("ids"):
            return out
        for i in range(len(res["ids"][0])):
            dist = float((res.get("distances") or [[1.0]])[0][i])
            out.append({
                "id": (res.get("ids") or [[None]])[0][i],
                "document": (res.get("documents") or [[None]])[0][i],
                "metadata": (res.get("metadatas") or [[None]])[0][i],
                "distance": dist,
                "similarity": _to_similarity(dist),
                "collection": name
            })
        return out
    except Exception as e:
        log.warning(f"_query_collection_where failed on {name}: {e}")
        return []

def _query_collection_plain(name: str, query: str, n: int) -> List[Dict[str, Any]]:
    """Query semantica senza filtri (fallback generico)."""
    return _query_collection(name, query, n)

def search_topk_with_filters(query: str, k: int = 5, where: dict | None = None,
                             expand: Optional[int] = None,
                             w_sim: float = W_SIM, w_time: float = W_TIME, w_src: float = W_SRC,
                             half_life_days: float = HALF_LIFE_D,
                             collections: Tuple[str, ...] = (FACTS, PREFS, BETS)) -> List[Dict[str, Any]]:
    """
    Search con filtri metadata (where clauses) + fallback se i filtri falliscono.
    Esempi:
        # Ultimi 7 giorni: where={"ts": {"$gte": int(time.time()) - 7*86400}}
        # Team specifico: where={"team": "Milan"}
        # Combinato: where={"$and":[{"team":"Milan"},{"result":"win"},{"ts":{"$gte":week_ago}}]}
    """
    expand = expand or (k * 3)
    pool: List[Dict[str, Any]] = []
    for c in collections:
        try:
            got = _query_collection_where(c, query, n=expand, where=where)
            if not got:
                got = _query_collection_plain(c, query, n=expand)  # fallback
            pool.extend(got)
        except Exception as e:
            log.warning(f"Filter query failed on {c}: {e}")
            try:
                pool.extend(_query_collection_plain(c, query, n=expand))
            except Exception:
                pass
    return _rank(pool, k=k, w_sim=w_sim, w_time=w_time, w_src=w_src, half_life_days=half_life_days)

def add_bets_batch(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Batch insert per bet con validazione e report.
    Returns: {"inserted":[ids], "skipped":[{"item":..., "reason":"..."}], "count":N}
    """
    if not items:
        return {"inserted": [], "skipped": [], "count": 0}

    col = _col(BETS)
    ids, docs, metas = [], [], []
    skipped = []
    now = int(time.time())

    for it in items:
        # Validazione base
        if not it.get("event") or not it.get("market"):
            skipped.append({"item": it, "reason": "missing_required_fields"})
            continue
        # Odds/stake devono esistere ed essere >0
        if "odds" not in it or "stake" not in it:
            skipped.append({"item": it, "reason": "missing_odds_or_stake"})
            continue
        try:
            odds = float(it.get("odds"))
            stake = float(it.get("stake"))
        except (ValueError, TypeError):
            skipped.append({"item": it, "reason": "invalid_numeric_values"})
            continue
        if odds <= 0 or stake <= 0:
            skipped.append({"item": it, "reason": "invalid_range"})
            continue

        _id = f"bet:{now}:{__import__('random').randint(1000,9999)}"
        event  = it["event"]
        market = it.get("market", "?")
        result = it.get("result", "open")
        source = it.get("source", "bet")

        md = {"event":event,"market":market,"odds":odds,"stake":stake,
              "result":result,"source":source,"ts":now}
        extra = it.get("metadata") or {}
        if extra: md.update(extra)

        team_part = f" | team={md.get('team')}" if md.get("team") else ""
        doc = f"{event} | {market} | odds={odds} | stake={stake} | result={result}{team_part}"

        ids.append(_id); docs.append(doc); metas.append(md)

    if ids:
        col.add(ids=ids, documents=docs, metadatas=metas)

    return {"inserted": ids, "skipped": skipped, "count": len(ids)}

def cleanup_old(collection: str, older_than_days: int, dry_run: bool = False) -> Dict[str, Any]:
    """
    Elimina documenti con metadata 'ts' più vecchi di N giorni.
    Usa where-clause quando disponibile, altrimenti fallback via get().
    """
    if older_than_days < 1:
        raise ValueError("older_than_days deve essere >= 1")

    col = _col(collection)
    threshold = int(time.time()) - older_than_days * 86400

    # Metodo efficiente: where-clause
    try:
        if not dry_run:
            col.delete(where={"ts": {"$lt": threshold}})
            return {"deleted": -1, "method": "where_clause", "dry_run": False}
    except Exception:
        pass

    # Fallback: scansione completa
    try:
        data = col.get(include=["metadatas"])
        ids   = data.get("ids") or []
        metas = data.get("metadatas") or []
        to_del = []
        now = int(time.time())

        for i, _id in enumerate(ids):
            md = metas[i] if i < len(metas) else {}
            ts = int((md or {}).get("ts") or 0)
            if ts and ts < threshold:
                to_del.append({"id": _id, "ts": ts, "age_days": (now - ts)//86400})

        if dry_run:
            return {"deleted": 0, "candidates": to_del, "dry_run": True, "count": len(to_del)}

        if to_del:
            col.delete(ids=[c["id"] for c in to_del])

        return {"deleted": len(to_del), "candidates": to_del[:10], "dry_run": False}
    except Exception as e:
        return {"error": str(e), "deleted": 0, "dry_run": dry_run}

def cleanup_old_facts(days: int = 90, dry_run: bool = False) -> Dict[str, Any]:
    return cleanup_old(FACTS, days, dry_run=dry_run)

def cleanup_old_bets(days: int = 365, dry_run: bool = False) -> Dict[str, Any]:
    return cleanup_old(BETS, days, dry_run=dry_run)

def migrate_collection(old_name: str, new_name: str, new_model: str,
                       batch_size: int = 500, delete_old: bool = False) -> Dict[str, Any]:
    """
    Copia old_name -> new_name rigenerando embedding con 'new_model'.
    Supporta batch per collezioni grandi e metriche di progresso.
    """
    import time as time_module

    start = time_module.time()
    client = get_client()

    new_embed = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=new_model)
    try:
        new_col = client.create_collection(name=new_name, embedding_function=new_embed)
        log.info(f"[migrate] created {new_name}")
    except Exception as e:
        if "already exists" in str(e).lower():
            new_col = client.get_collection(name=new_name, embedding_function=new_embed)
            log.warning(f"[migrate] {new_name} already exists, using it")
        else:
            raise

    old_col = _col(old_name)

    total_migrated, batch_count, offset = 0, 0, 0
    try:
        while True:
            data = old_col.get(include=["documents","metadatas"], limit=batch_size, offset=offset)
            ids   = data.get("ids") or []
            if not ids:
                break
            docs  = data.get("documents") or []
            metas = data.get("metadatas") or []
            new_col.add(ids=ids, documents=docs, metadatas=metas)
            total_migrated += len(ids)
            batch_count    += 1
            offset         += batch_size
            log.info(f"[migrate] batch {batch_count}: +{len(ids)} (total={total_migrated})")
    except Exception:
        # Fallback: full get (collezione piccola / client vecchio)
        log.warning("[migrate] offset/limit unsupported, using full get()")
        data = old_col.get()
        ids   = data.get("ids") or []
        docs  = data.get("documents") or []
        metas = data.get("metadatas") or []
        if ids:
            new_col.add(ids=ids, documents=docs, metadatas=metas)
            total_migrated = len(ids)
            batch_count = 1

    elapsed = time_module.time() - start
    old_deleted = False
    if delete_old and total_migrated > 0:
        try:
            client.delete_collection(old_name)
            old_deleted = True
            log.info(f"[migrate] deleted old collection {old_name}")
        except Exception as e:
            log.error(f"[migrate] delete old failed: {e}")

    return {
        "migrated": total_migrated,
        "time_seconds": round(elapsed, 2),
        "batches": batch_count,
        "old_deleted": old_deleted,
        "rate_per_second": round(total_migrated/elapsed, 2) if elapsed > 0 else 0.0
    }
