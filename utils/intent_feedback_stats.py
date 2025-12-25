#!/usr/bin/env python3
# utils/intent_feedback_stats.py — Analisi veloce dei log intent_decisions.jsonl

import os
import json
from collections import Counter, defaultdict
from typing import Dict, Any

LOG_PATH = os.getenv(
    "INTENT_FEEDBACK_LOG",
    "/root/quantumdev-open/logs/intent_decisions.jsonl"
)

def load_events(path: str):
    if not os.path.isfile(path):
        print(f"[INFO] Nessun file di log trovato: {path}")
        return []
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                continue
    return events

def main():
    print(f"[INFO] Leggo log da: {LOG_PATH}")
    events = load_events(LOG_PATH)
    if not events:
        print("[INFO] Nessun evento.")
        return

    total = len(events)
    intents = Counter()
    sat_sum: Dict[str, float] = defaultdict(float)
    sat_count: Dict[str, int] = defaultdict(int)

    for ev in events:
        intent = str(ev.get("intent_used") or "UNKNOWN")
        intents[intent] += 1
        if "satisfaction" in ev:
            try:
                s = float(ev["satisfaction"])
                sat_sum[intent] += s
                sat_count[intent] += 1
            except Exception:
                pass

    print(f"\nTotale eventi: {total}\n")
    print("Per intent:")
    for intent, cnt in intents.most_common():
        avg = None
        if sat_count[intent] > 0:
            avg = sat_sum[intent] / sat_count[intent]
        if avg is not None:
            print(f"  - {intent:15s} : {cnt:5d}  (satisfaction media = {avg:.2f})")
        else:
            print(f"  - {intent:15s} : {cnt:5d}")

    print("\nEsempi ultimi 5 eventi:")
    for ev in events[-5:]:
        q = (ev.get("query") or "")[:80].replace("\n", " ")
        print(f"  - intent={ev.get('intent_used')} | sat={ev.get('satisfaction')} | q='{q}'")

if __name__ == "__main__":
    main()
