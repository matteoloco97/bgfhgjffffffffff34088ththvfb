#!/root/quantumdev-open/utils python3
"""
utils/chroma_cleanup.py — Cleanup ChromaDB via API o local fallback.

Uso tipico (systemd template):
  python -m utils.chroma_cleanup betting_history:365 --prefer api

Uso CLI:
  python -m utils.chroma_cleanup facts:90 --dry-run true
  python -m utils.chroma_cleanup prefs --days 365 --prefer local
"""

import os, sys, json, argparse
from pathlib import Path

# --- Bootstrap PYTHONPATH alla root progetto ---
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests  # type: ignore

# Fallback locale se l'API non risponde
from utils.chroma_handler import cleanup_old

def _to_bool(x) -> bool:
    if isinstance(x, bool): return x
    return str(x).strip().lower() in ("1","true","yes","y")

def call_api(api_url: str, collection: str, days: int, dry_run: bool) -> dict:
    payload = {"collection": collection, "days": int(days), "dry_run": bool(dry_run)}
    r = requests.post(api_url, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()

def run_local(collection: str, days: int, dry_run: bool) -> dict:
    return cleanup_old(collection, int(days), dry_run=bool(dry_run))

def main() -> int:
    p = argparse.ArgumentParser(description="ChromaDB cleanup runner (API + local fallback)")
    p.add_argument("instance", help="Formato: collection[:days]  es. betting_history:365")
    p.add_argument("--api-url", default=os.getenv("API_URL","http://127.0.0.1:8081/memory/cleanup"))
    p.add_argument("--days", type=int, default=None, help="Override giorni (se non passato usa instance o DEFAULT_DAYS)")
    p.add_argument("--default-days", type=int, default=int(os.getenv("DEFAULT_DAYS","90")))
    p.add_argument("--dry-run", default=os.getenv("DRY_RUN","false"), help="true/false (default env DRY_RUN)")
    p.add_argument("--prefer", choices=["api","local"], default=os.getenv("CLEANUP_PREFER","api"),
                   help="Tenta prima API o direttamente locale")
    p.add_argument("--json", action="store_true", help="Forza output JSON (default già JSON)")
    args = p.parse_args()

    # Parse instance "collection[:days]"
    inst = args.instance
    if ":" in inst:
        col, rest = inst.split(":", 1)
        inst_days = int(rest.split(":")[0]) if rest.strip() else args.default_days
    else:
        col = inst
        inst_days = args.default_days

    days = args.days if args.days is not None else inst_days
    dry = _to_bool(args.dry_run)

    out, err = None, None

    if args.prefer == "api":
        try:
            out = call_api(args.api_url, col, days, dry)
        except Exception as e:
            err = f"api_error: {e}"

    if out is None:
        try:
            out = run_local(col, days, dry)
        except Exception as e:
            err = f"{(err + ' | ') if err else ''}local_error: {e}"

    result = {
        "ok": out is not None,
        "collection": col,
        "days": days,
        "dry_run": dry,
        "prefer": args.prefer,
        "api_url": args.api_url,
        "result": out,
    }
    if err:
        result["error"] = err

    print(json.dumps(result, ensure_ascii=False))
    return 0 if out is not None else 1

if __name__ == "__main__":
    raise SystemExit(main())
