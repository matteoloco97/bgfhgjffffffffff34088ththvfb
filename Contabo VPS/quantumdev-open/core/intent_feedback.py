#!/usr/bin/env python3
# core/intent_feedback.py — Lightweight JSONL logger per decisioni di routing / intent
#
# Obiettivo:
# - Nessuna dipendenza esterna (niente Redis, niente DB)
# - Nessun impatto sul flusso principale (fail-silent)
# - Log append-only in JSONL per analisi offline
#
# Formato tipico delle righe:
# {
#   "ts": 1731938400.123,
#   "query": "...",
#   "intent_used": "WEB_SEARCH" | "DIRECT_LLM" | "CACHE_SEMANTIC" | ...,
#   "satisfaction": 1.0,
#   "response_time_s": 0.85,
#   "...": "altri campi opzionali"
# }

from __future__ import annotations
import os
import json
import time
import threading
from typing import Any, Dict, Optional

# Path di default per il log; sovrascrivibile via ENV
_DEFAULT_PATH = os.getenv(
    "INTENT_FEEDBACK_LOG",
    "/root/quantumdev-open/logs/intent_decisions.jsonl"
)

# Lock globale per evitare race-condition su file
_lock = threading.Lock()


class IntentFeedbackSystem:
    """Logger minimale su file JSONL, usato da quantum_api._fb_record()."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or _DEFAULT_PATH
        # Crea la cartella se non esiste
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
        except Exception:
            # Se fallisce la creazione directory, lasceremo fallire in record_feedback
            pass

    def record_feedback(self, **kwargs: Any) -> None:
        """
        Scrive una riga JSONL con i dati passati.
        Non deve MAI far fallire il main-flow: eventuali errori vengono silenziati.
        """
        try:
            entry: Dict[str, Any] = {
                "ts": time.time(),
            }
            entry.update(kwargs)

            line = json.dumps(entry, ensure_ascii=False)
            with _lock:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except Exception:
            # Fail-silent: nessun log, ma nemmeno crash dell'app
            return
