
#!/usr/bin/env python3
# utils/search_analytics.py — metriche qualità ricerca (file-based, robusto)
from __future__ import annotations
import os, time, json, math, datetime
from typing import Dict, List, Any, Tuple
from collections import Counter

_LOG = os.getenv("SEARCH_ANALYTICS_LOG", "/root/quantumdev-open/logs/search_analytics.jsonl")
_ROTATE_MB = float(os.getenv("SEARCH_ANALYTICS_ROTATE_MB", "50"))  # rotazione > 50 MB
_TOPK_DOMAINS = int(os.getenv("SEARCH_ANALYTICS_TOPK_DOMAINS", "5"))

def _ensure_dir(p: str):
    d = os.path.dirname(p)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)

def _rotate_if_needed(path: str):
    if _ROTATE_MB <= 0:
        return
    try:
        if os.path.isfile(path) and (os.path.getsize(path) > _ROTATE_MB * 1024 * 1024):
            ts = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
            new = f"{path}.{ts}.rotated"
            os.replace(path, new)
    except Exception:
        # non bloccare la pipeline se la rotazione fallisce
        pass

def _pctl(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    # p in [0,100]
    idx = max(0, min(len(values)-1, int(math.ceil((p/100.0)*len(values))-1)))
    return float(values[idx])

def _domain(u: str) -> str:
    try:
        from urllib.parse import urlparse
        h = urlparse(u).hostname or ""
        parts = h.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else h
    except Exception:
        return ""

class SearchAnalytics:
    """
    File JSONL con una riga per search. API stabile:

      - track_search(query, results, user_interaction)
      - report(days=7) -> dict
      - tail(n=50) -> List[dict]
      - clear() -> None

    Dove `user_interaction` può contenere:
      latency_ms, reranker_used, clicked_urls, cached,
      validation_confidence, raw_results, dedup_results, returned, fetch_timeouts, fetch_errors.
    """
    def __init__(self, path: str = _LOG):
        self.path = path
        _ensure_dir(self.path)

    def _dump(self, rec: Dict[str, Any]):
        _rotate_if_needed(self.path)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def track_search(self, query: str, results: List[Dict[str, Any]], user_interaction: Dict[str, Any]):
        # Normalizza input UI (compat con vecchie chiamate)
        ui = user_interaction or {}
        latency_ms = int(ui.get("latency_ms") or 0)
        reranker_used = bool(ui.get("reranker_used"))
        clicked_urls = list(ui.get("clicked_urls") or [])
        cached = bool(ui.get("cached", False))
        validation_conf = ui.get("validation_confidence")

        results = results or []
        results_count = len(results)
        result_urls = [r.get("url") for r in results if r.get("url")]
        result_domains = [_domain(u) for u in result_urls]
        top_domain = result_domains[0] if result_domains else None

        rec = {
            "ts": int(time.time()),
            "query": (query or "").strip(),
            "results_count": results_count,
            "latency_ms": latency_ms,
            "reranker_used": reranker_used,
            "clicked_urls": clicked_urls,
            "cached": cached,
            # extra osservabilità (se assenti restano null/omessi)
            "validation_confidence": validation_conf,
            "raw_results": ui.get("raw_results"),
            "dedup_results": ui.get("dedup_results"),
            "returned": ui.get("returned"),
            "fetch_timeouts": ui.get("fetch_timeouts"),
            "fetch_errors": ui.get("fetch_errors"),
            "result_urls": result_urls[:20],     # salva un sottoinsieme
            "result_domains": result_domains[:20],
            "top_domain": top_domain,
        }
        self._dump(rec)

    # ---------- IO ----------
    def _load(self, last_n: int | None = None) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        if not os.path.isfile(self.path):
            return rows
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
        return rows[-last_n:] if last_n else rows

    # ---------- Report ----------
    def report(self, days: int = 7) -> Dict[str, Any]:
        now = int(time.time())
        rows = [r for r in self._load() if int(r.get("ts", 0)) >= now - days * 86400]

        lats = [int(r.get("latency_ms") or 0) for r in rows]
        rerate = sum(1 for r in rows if r.get("reranker_used")) / max(1, len(rows))
        cache_hit = sum(1 for r in rows if r.get("cached")) / max(1, len(rows))
        miss_rate = sum(1 for r in rows if int(r.get("results_count") or 0) == 0) / max(1, len(rows))

        # CTR:
        # - ctr_any_click: % ricerche con >=1 click
        # - ctr_sources: #sorgenti uniche cliccate / #ricerche (storico precedente)
        any_click = sum(1 for r in rows if (r.get("clicked_urls") or []))
        ctr_any_click = any_click / max(1, len(rows))
        clicks_all = [u for r in rows for u in (r.get("clicked_urls") or [])]
        ctr_sources = (len(set(clicks_all)) / max(1, len(rows))) if rows else 0.0

        # Domains
        doms = [d for r in rows for d in (r.get("result_domains") or [])]
        top = Counter(doms).most_common(_TOPK_DOMAINS)
        top_share = [(d, c / max(1, len(doms))) for d, c in top]

        # Validation conf (se presente)
        confs = [float(r.get("validation_confidence")) for r in rows if r.get("validation_confidence") is not None]
        validation = {
            "avg": (sum(confs)/len(confs)) if confs else None,
            "share_ge_0_7": (sum(1 for x in confs if x >= 0.7)/len(confs)) if confs else None,
            "samples": len(confs)
        }

        # Distribuzione lunghezza query
        def _bucket(q: str) -> str:
            n = len((q or "").split())
            if n <= 2: return "short(<=2)"
            if n <= 5: return "mid(3-5)"
            return "long(>5)"
        qdist = Counter(_bucket(r.get("query","")) for r in rows)

        return {
            "samples": len(rows),
            "latency": {
                "avg_ms": (sum(lats)/len(lats)) if lats else 0.0,
                "p50_ms": _pctl(lats, 50) if lats else 0.0,
                "p90_ms": _pctl(lats, 90) if lats else 0.0,
                "p95_ms": _pctl(lats, 95) if lats else 0.0,
                "p99_ms": _pctl(lats, 99) if lats else 0.0,
            },
            "ctr_any_click": ctr_any_click,
            "ctr_sources": ctr_sources,
            "cache_hit_rate": cache_hit,
            "miss_rate": miss_rate,
            "reranker_usage_rate": rerate,
            "validation": validation,
            "top_domains": [{"domain": d, "share": s} for d, s in top_share],
            "query_len_distribution": dict(qdist),
        }

    # ---------- Debug helpers ----------
    def tail(self, n: int = 50) -> List[Dict[str, Any]]:
        return self._load(last_n=max(1, n))

    def clear(self) -> None:
        try:
            if os.path.isfile(self.path):
                os.remove(self.path)
        except Exception:
            pass
